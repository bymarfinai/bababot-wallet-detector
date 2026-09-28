from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping

from research.wallet_s10_paper_trading import (
    PaperTradingConfig,
    RULE_IDS,
    run_wallet_only_paper_trading,
)

STAGE10_REPLAY_VERSION = "wallet-s10-replay-v1"
REAL_SOURCE_KIND = "REAL"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            text = raw.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid JSONL at {path}:{line_number}: {exc}"
                ) from exc
            if not isinstance(value, dict):
                raise ValueError(
                    f"JSONL row must be an object at {path}:{line_number}"
                )
            rows.append(value)
    return rows


def _require_nonempty_text(
    mapping: Mapping[str, Any],
    key: str,
) -> str:
    value = str(mapping.get(key) or "").strip()
    if not value:
        raise ValueError(f"manifest requires non-empty {key}")
    return value


def validate_replay_manifest(
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    version = _require_nonempty_text(manifest, "version")
    if version != STAGE10_REPLAY_VERSION:
        raise ValueError(
            f"unsupported replay manifest version: {version!r}"
        )

    source_kind = _require_nonempty_text(manifest, "source_kind").upper()
    if source_kind != REAL_SOURCE_KIND:
        raise ValueError(
            "Stage-10 empirical replay accepts source_kind=REAL only"
        )

    dataset_id = _require_nonempty_text(manifest, "dataset_id")
    signal_source = _require_nonempty_text(manifest, "signal_source")
    price_source = _require_nonempty_text(manifest, "price_source")
    venue = _require_nonempty_text(manifest, "venue")

    fee = Decimal(str(manifest.get("fee_bps_per_side")))
    slippage = Decimal(str(manifest.get("slippage_bps_per_side")))
    if fee < 0 or slippage < 0:
        raise ValueError("manifest fee/slippage must be >= 0")

    max_holding_seconds = int(
        manifest.get("max_holding_seconds") or 24 * 60 * 60
    )
    max_entry_delay = manifest.get("max_entry_delay_seconds")
    if max_entry_delay is not None:
        max_entry_delay = int(max_entry_delay)

    normalized = {
        "version": version,
        "source_kind": source_kind,
        "dataset_id": dataset_id,
        "signal_source": signal_source,
        "price_source": price_source,
        "venue": venue,
        "fee_bps_per_side": str(fee),
        "slippage_bps_per_side": str(slippage),
        "max_holding_seconds": max_holding_seconds,
        "max_entry_delay_seconds": max_entry_delay,
        "notes": str(manifest.get("notes") or ""),
    }
    return {
        **normalized,
        "manifest_fingerprint": _fingerprint(normalized),
    }


def _validate_signal_snapshots(
    snapshots: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = [dict(row) for row in snapshots]
    if not rows:
        raise ValueError("real replay requires at least one Stage-9 snapshot")

    seen_as_of: set[int] = set()
    for row in rows:
        if str(row.get("version") or "") != "wallet-s9-v1":
            raise ValueError("replay contains unsupported Stage-9 snapshot")
        as_of = int(row["as_of"])
        if as_of in seen_as_of:
            raise ValueError(
                f"duplicate Stage-9 snapshot timestamp: {as_of}"
            )
        seen_as_of.add(as_of)

        for signal in row.get("signals") or []:
            if str(signal.get("version") or "") != "wallet-s9-v1":
                raise ValueError(
                    "replay snapshot contains incompatible Stage-9 signal"
                )
            if int(signal.get("as_of", as_of)) != as_of:
                raise ValueError(
                    "Stage-9 signal timestamp must equal snapshot timestamp"
                )

    return sorted(rows, key=lambda row: int(row["as_of"]))


def _validate_price_rows(
    rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    for raw in rows:
        row = dict(raw)
        token = str(row.get("base_asset") or "").strip()
        if not token:
            raise ValueError("price row requires base_asset")
        ts = int(row["timestamp"])
        key = (token, ts)
        if key in seen:
            raise ValueError(
                f"duplicate price row for {token} at {ts}"
            )
        seen.add(key)

        source = str(row.get("source") or "").strip()
        if not source:
            raise ValueError(
                f"price row requires source for {token} at {ts}"
            )

        for field in ("open", "high", "low", "close"):
            value = Decimal(str(row[field]))
            if value <= 0:
                raise ValueError(
                    f"price row {field} must be > 0 for {token} at {ts}"
                )

        output.append({
            "base_asset": token,
            "timestamp": ts,
            "open": str(row["open"]),
            "high": str(row["high"]),
            "low": str(row["low"]),
            "close": str(row["close"]),
            "source": source,
            "venue": str(row.get("venue") or ""),
        })

    if not output:
        raise ValueError("real replay requires at least one OHLC price row")

    return sorted(
        output,
        key=lambda row: (row["base_asset"], row["timestamp"]),
    )


def _bars_by_token(
    rows: Iterable[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        result.setdefault(str(row["base_asset"]), []).append({
            "timestamp": int(row["timestamp"]),
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
        })
    return result


def build_replay_preflight(
    signal_snapshots: Iterable[dict[str, Any]],
    price_rows: Iterable[dict[str, Any]],
    *,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    manifest_row = validate_replay_manifest(manifest)
    snapshots = _validate_signal_snapshots(signal_snapshots)
    prices = _validate_price_rows(price_rows)

    signals = [
        dict(signal)
        for snapshot in snapshots
        for signal in snapshot.get("signals") or []
    ]
    directional = [
        row
        for row in signals
        if row.get("state") in {"ACCUMULATION", "DISTRIBUTION"}
    ]
    tokens = sorted({
        str(row.get("base_asset") or "")
        for row in directional
        if row.get("base_asset")
    })
    bars_by_token = _bars_by_token(prices)

    token_coverage: dict[str, Any] = {}
    missing_price_tokens: list[str] = []
    no_post_signal_bar_tokens: list[str] = []

    for token in tokens:
        token_signals = [
            row for row in directional
            if str(row["base_asset"]) == token
        ]
        token_bars = bars_by_token.get(token) or []
        signal_times = [int(row["as_of"]) for row in token_signals]
        bar_times = [int(row["timestamp"]) for row in token_bars]

        has_price_rows = bool(token_bars)
        has_post_signal_bar = (
            has_price_rows
            and any(
                bar_time > signal_time
                for signal_time in signal_times
                for bar_time in bar_times
            )
        )
        if not has_price_rows:
            missing_price_tokens.append(token)
        elif not has_post_signal_bar:
            no_post_signal_bar_tokens.append(token)

        token_coverage[token] = {
            "signal_count": len(token_signals),
            "price_bar_count": len(token_bars),
            "first_signal_time": min(signal_times),
            "last_signal_time": max(signal_times),
            "first_price_time": min(bar_times) if bar_times else None,
            "last_price_time": max(bar_times) if bar_times else None,
            "has_any_price_rows": has_price_rows,
            "has_post_signal_bar": has_post_signal_bar,
        }

    preflight_core = {
        "version": STAGE10_REPLAY_VERSION,
        "dataset_id": manifest_row["dataset_id"],
        "manifest_fingerprint": manifest_row["manifest_fingerprint"],
        "source_kind": manifest_row["source_kind"],
        "snapshot_count": len(snapshots),
        "signal_count": len(signals),
        "directional_signal_count": len(directional),
        "directional_token_count": len(tokens),
        "price_row_count": len(prices),
        "price_token_count": len(bars_by_token),
        "missing_price_tokens": missing_price_tokens,
        "no_post_signal_bar_tokens": no_post_signal_bar_tokens,
        "token_coverage": token_coverage,
        "ready_for_replay": (
            bool(directional)
            and not missing_price_tokens
            and not no_post_signal_bar_tokens
        ),
        "readiness_policy": (
            "all directional signal tokens require at least one "
            "strictly-post-signal OHLC bar"
        ),
    }
    return {
        **preflight_core,
        "preflight_fingerprint": _fingerprint(preflight_core),
    }


def run_empirical_replay(
    signal_snapshots: Iterable[dict[str, Any]],
    price_rows: Iterable[dict[str, Any]],
    *,
    manifest: Mapping[str, Any],
    rule_ids: Iterable[str] = RULE_IDS,
) -> dict[str, Any]:
    manifest_row = validate_replay_manifest(manifest)
    snapshots = _validate_signal_snapshots(signal_snapshots)
    prices = _validate_price_rows(price_rows)
    preflight = build_replay_preflight(
        snapshots,
        prices,
        manifest=manifest_row,
    )
    if not preflight["ready_for_replay"]:
        raise ValueError(
            "replay preflight failed: missing causal price coverage"
        )

    config = PaperTradingConfig(
        fee_bps_per_side=Decimal(
            manifest_row["fee_bps_per_side"]
        ),
        slippage_bps_per_side=Decimal(
            manifest_row["slippage_bps_per_side"]
        ),
        max_holding_seconds=int(
            manifest_row["max_holding_seconds"]
        ),
        max_entry_delay_seconds=manifest_row[
            "max_entry_delay_seconds"
        ],
    )
    result = run_wallet_only_paper_trading(
        snapshots,
        _bars_by_token(prices),
        config=config,
        rule_ids=rule_ids,
    )

    empirical_core = {
        "version": STAGE10_REPLAY_VERSION,
        "dataset": manifest_row,
        "preflight": preflight,
        "paper_trading_result": result,
        "claims": {
            "data_source_kind": "REAL",
            "unit_test_fixture": False,
            "production_rule_selected": False,
            "edge_validated": False,
            "next_step": "STAGE11_CHRONOLOGICAL_VALIDATION",
        },
    }
    return {
        **empirical_core,
        "empirical_result_fingerprint": _fingerprint(empirical_core),
    }


def load_replay_bundle(
    bundle_dir: str | Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    root = Path(bundle_dir)
    manifest = _read_json(root / "manifest.json")
    snapshots = _read_jsonl(root / "signals.jsonl")
    prices = _read_jsonl(root / "prices.jsonl")
    return manifest, snapshots, prices


def write_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(
            value,
            handle,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Stage-10 empirical wallet-only replay"
    )
    parser.add_argument(
        "--bundle",
        required=True,
        help="Directory containing manifest.json, signals.jsonl, prices.jsonl",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output JSON path",
    )
    parser.add_argument(
        "--rules",
        default="A,B,C,D,E",
        help="Comma-separated rule IDs",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate real dataset coverage without running trades",
    )
    args = parser.parse_args()

    manifest, snapshots, prices = load_replay_bundle(args.bundle)
    if args.preflight_only:
        output = build_replay_preflight(
            snapshots,
            prices,
            manifest=manifest,
        )
    else:
        rules = [
            value.strip()
            for value in args.rules.split(",")
            if value.strip()
        ]
        output = run_empirical_replay(
            snapshots,
            prices,
            manifest=manifest,
            rule_ids=rules,
        )

    write_json(args.out, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
