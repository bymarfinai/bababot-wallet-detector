from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from typing import Any, Iterable

from research.wallet_s8_live_monitor import (
    ROLLING_WINDOWS_SECONDS,
    aggregate_live_events,
)

STAGE9_VERSION = "wallet-s9-v1"
CHAIN = "solana"
WINDOW_ORDER = ("5m", "15m", "1h")
DIRECTIONAL_STATES = {"ACCUMULATION", "DISTRIBUTION"}
ZERO = Decimal("0")


def _d(value: Any) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(str(value))


def _s(value: Decimal) -> str:
    if value == ZERO:
        return "0"
    return format(value.normalize(), "f")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _direction(value: Decimal) -> str:
    if value > ZERO:
        return "ACCUMULATION"
    if value < ZERO:
        return "DISTRIBUTION"
    return "NEUTRAL"


def _external_state(stage8_state: str) -> str:
    if stage8_state == "BALANCED":
        return "NEUTRAL"
    if stage8_state in DIRECTIONAL_STATES:
        return stage8_state
    raise ValueError(f"unsupported Stage-8 flow state: {stage8_state!r}")


def _valid_trade_events(
    events: Iterable[dict[str, Any]],
    *,
    as_of: int,
) -> list[dict[str, Any]]:
    lower = int(as_of) - ROLLING_WINDOWS_SECONDS["1h"]
    rows = [
        dict(row)
        for row in events
        if row.get("event_type") == "SWAP"
        and row.get("side") in {"BUY", "SELL"}
        and row.get("base_asset")
        and row.get("wallet")
        and row.get("block_time") is not None
        and lower < int(row["block_time"]) <= int(as_of)
    ]
    return sorted(
        rows,
        key=lambda row: (
            int(row["block_time"]),
            int(row.get("slot") or 0),
            str(row.get("wallet") or ""),
            str(row.get("signature") or ""),
        ),
    )


def _summarize_exact_band(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    buy_rows = [row for row in rows if row.get("side") == "BUY"]
    sell_rows = [row for row in rows if row.get("side") == "SELL"]
    buy_wallets = {str(row["wallet"]) for row in buy_rows}
    sell_wallets = {str(row["wallet"]) for row in sell_rows}

    buy_base = sum((_d(row.get("base_amount")) for row in buy_rows), ZERO)
    sell_base = sum((_d(row.get("base_amount")) for row in sell_rows), ZERO)
    net_base = buy_base - sell_base

    return {
        "event_count": len(rows),
        "buy_event_count": len(buy_rows),
        "sell_event_count": len(sell_rows),
        "buy_wallet_count": len(buy_wallets),
        "sell_wallet_count": len(sell_wallets),
        "unique_wallet_count": len(buy_wallets | sell_wallets),
        "net_base_amount": _s(net_base),
        "state": _direction(net_base),
    }


def _time_bands(
    rows: list[dict[str, Any]],
    *,
    as_of: int,
) -> dict[str, dict[str, Any]]:
    boundaries = {
        "0_5m": (int(as_of) - 300, int(as_of)),
        "5_15m": (int(as_of) - 900, int(as_of) - 300),
        "15_60m": (int(as_of) - 3600, int(as_of) - 900),
    }
    result: dict[str, dict[str, Any]] = {}
    for name, (lower, upper) in boundaries.items():
        band_rows = [
            row
            for row in rows
            if lower < int(row["block_time"]) <= upper
        ]
        result[name] = {
            "from_exclusive": lower,
            "to_inclusive": upper,
            **_summarize_exact_band(band_rows),
        }
    return result


def _freshness(
    last_activity_time: int,
    *,
    as_of: int,
) -> dict[str, Any]:
    age = max(0, int(as_of) - int(last_activity_time))
    if age < 300:
        bucket = "WITHIN_5M"
    elif age < 900:
        bucket = "WITHIN_15M"
    elif age < 3600:
        bucket = "WITHIN_1H"
    else:
        bucket = "STALE"
    return {
        "last_activity_time": int(last_activity_time),
        "age_seconds": age,
        "bucket": bucket,
    }


def _usd_flow(symbol_row: dict[str, Any]) -> dict[str, Any]:
    priced = int(symbol_row.get("usd_priced_event_count") or 0)
    unpriced = int(symbol_row.get("unpriced_event_count") or 0)
    net = _d(symbol_row.get("usd_net_notional"))

    if priced == 0:
        coverage = "UNAVAILABLE"
        direction = "UNAVAILABLE"
    else:
        coverage = "COMPLETE" if unpriced == 0 else "PARTIAL"
        direction = (
            "POSITIVE"
            if net > ZERO
            else "NEGATIVE"
            if net < ZERO
            else "FLAT"
        )

    return {
        "coverage": coverage,
        "priced_event_count": priced,
        "unpriced_event_count": unpriced,
        "validated_usd_buy_notional": str(
            symbol_row.get("usd_buy_notional") or "0"
        ),
        "validated_usd_sell_notional": str(
            symbol_row.get("usd_sell_notional") or "0"
        ),
        "validated_usd_net_notional": str(
            symbol_row.get("usd_net_notional") or "0"
        ),
        "direction": direction,
    }


def _contributor_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_wallet: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_wallet[str(row["wallet"])].append(row)

    output: list[dict[str, Any]] = []
    for wallet in sorted(by_wallet):
        wallet_rows = by_wallet[wallet]
        label_statuses = sorted({
            str((row.get("special_labels") or {}).get("meme_hunter") or "")
            for row in wallet_rows
            if (row.get("special_labels") or {}).get("meme_hunter")
        })
        evidence_rows = [
            row.get("meme_hunter_evidence")
            for row in wallet_rows
            if row.get("meme_hunter_evidence")
        ]
        evidence = evidence_rows[-1] if evidence_rows else None
        registry_snapshots = sorted({
            str(row.get("registry_snapshot_id") or "")
            for row in wallet_rows
            if row.get("registry_snapshot_id")
        })

        output.append({
            "wallet": wallet,
            "sides": sorted({str(row["side"]) for row in wallet_rows}),
            "event_count": len(wallet_rows),
            "latest_activity_time": max(
                int(row["block_time"]) for row in wallet_rows
            ),
            "primary_segments_observed": sorted({
                str(row.get("primary_segment"))
                for row in wallet_rows
                if row.get("primary_segment")
            }),
            "qualifying_segments": sorted({
                str(segment)
                for row in wallet_rows
                for segment in row.get("qualifying_segments") or []
            }),
            "meme_label_statuses": label_statuses,
            "meme_evidence_available": bool(
                evidence
                and (
                    evidence.get("evidence_profile_available")
                    or int(evidence.get("matched_explosion_events") or 0) > 0
                )
            ),
            "matched_explosion_events": int(
                (evidence or {}).get("matched_explosion_events") or 0
            ),
            "matched_explosion_distinct_tokens": int(
                (evidence or {}).get("matched_distinct_tokens") or 0
            ),
            "registry_snapshot_ids": registry_snapshots,
        })
    return output


def _meme_evidence_summary(
    contributors: list[dict[str, Any]],
) -> dict[str, Any]:
    evidence_wallets = [
        row for row in contributors if row["meme_evidence_available"]
    ]
    status_counts: dict[str, int] = {}
    for row in contributors:
        for status in row["meme_label_statuses"]:
            status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "evidence_wallet_count": len(evidence_wallets),
        "label_status_counts": dict(sorted(status_counts.items())),
        "historical_matched_explosion_events_sum": sum(
            int(row["matched_explosion_events"])
            for row in evidence_wallets
        ),
        "historical_matched_explosion_distinct_tokens_sum": sum(
            int(row["matched_explosion_distinct_tokens"])
            for row in evidence_wallets
        ),
        "calibration_status": "EVIDENCE_ONLY_STAGE6_V1",
    }


def _window_view(symbol_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": _external_state(str(symbol_row["flow_state"])),
        "event_count": int(symbol_row.get("event_count") or 0),
        "buy_event_count": int(symbol_row.get("buy_event_count") or 0),
        "sell_event_count": int(symbol_row.get("sell_event_count") or 0),
        "unique_wallet_count": int(symbol_row.get("unique_wallet_count") or 0),
        "buy_wallet_count": int(symbol_row.get("buy_wallet_count") or 0),
        "sell_wallet_count": int(symbol_row.get("sell_wallet_count") or 0),
        "wallet_net_count": int(symbol_row.get("wallet_net_count") or 0),
        "net_base_amount": str(symbol_row.get("net_base_amount") or "0"),
        "segment_membership_wallet_counts": dict(
            symbol_row.get("segment_membership_wallet_counts") or {}
        ),
        "last_activity_time": int(symbol_row["last_activity_time"]),
        "usd_flow": _usd_flow(symbol_row),
    }


def _persistence(
    *,
    current_state: str,
    windows: dict[str, dict[str, Any]],
    bands: dict[str, dict[str, Any]],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    active_windows = [
        name for name in WINDOW_ORDER if name in windows
    ]
    window_states = {
        name: windows[name]["state"] for name in active_windows
    }
    matching_windows = [
        name
        for name in active_windows
        if current_state in DIRECTIONAL_STATES
        and windows[name]["state"] == current_state
    ]

    matching_bands = [
        name
        for name in ("0_5m", "5_15m", "15_60m")
        if current_state in DIRECTIONAL_STATES
        and bands[name]["event_count"] > 0
        and bands[name]["state"] == current_state
    ]

    times = [int(row["block_time"]) for row in rows]
    activity_span = max(times) - min(times) if times else 0

    return {
        "active_windows": active_windows,
        "window_states": window_states,
        "directional_agreement_windows": matching_windows,
        "all_active_windows_agree": (
            bool(active_windows)
            and len(set(window_states.values())) == 1
        ),
        "exact_time_bands": bands,
        "directional_time_bands_matching_current": matching_bands,
        "spans_15m_directionally": (
            current_state in DIRECTIONAL_STATES
            and all(name in matching_bands for name in ("0_5m", "5_15m"))
        ),
        "spans_1h_directionally": (
            current_state in DIRECTIONAL_STATES
            and all(
                name in matching_bands
                for name in ("0_5m", "5_15m", "15_60m")
            )
        ),
        "activity_span_seconds_observed": activity_span,
        "note": (
            "rolling-window agreement is reported separately from exact "
            "non-overlapping time-band persistence"
        ),
    }


def build_smart_money_signal_snapshot(
    events: Iterable[dict[str, Any]],
    *,
    as_of: int,
) -> dict[str, Any]:
    """Convert factual Stage-8 activity into an independent Stage-9 signal contract."""
    rows = _valid_trade_events(events, as_of=int(as_of))
    aggregation = aggregate_live_events(rows, as_of=int(as_of))

    by_window_symbol: dict[str, dict[str, dict[str, Any]]] = {}
    token_set: set[str] = set()
    for window_name in WINDOW_ORDER:
        symbols = {
            str(row["base_asset"]): row
            for row in aggregation["windows"][window_name]["symbols"]
        }
        by_window_symbol[window_name] = symbols
        token_set.update(symbols)

    signals: list[dict[str, Any]] = []
    for token in sorted(token_set):
        token_rows = [
            row for row in rows if str(row["base_asset"]) == token
        ]
        window_rows = {
            window_name: _window_view(
                by_window_symbol[window_name][token]
            )
            for window_name in WINDOW_ORDER
            if token in by_window_symbol[window_name]
        }
        basis_window = next(
            window_name
            for window_name in WINDOW_ORDER
            if window_name in window_rows
        )
        basis = window_rows[basis_window]
        current_state = basis["state"]
        bands = _time_bands(token_rows, as_of=int(as_of))
        contributors = _contributor_rows(token_rows)

        registry_snapshot_ids = sorted({
            str(row.get("registry_snapshot_id") or "")
            for row in token_rows
            if row.get("registry_snapshot_id")
        })
        registry_snapshot_fingerprints = sorted({
            str(row.get("registry_snapshot_fingerprint") or "")
            for row in token_rows
            if row.get("registry_snapshot_fingerprint")
        })

        signal_core = {
            "version": STAGE9_VERSION,
            "chain": CHAIN,
            "base_asset": token,
            "as_of": int(as_of),
            "state": current_state,
            "state_basis_window": basis_window,
            "freshness": _freshness(
                int(basis["last_activity_time"]),
                as_of=int(as_of),
            ),
            "qualified_wallet_activity": {
                "unique_wallet_count": int(basis["unique_wallet_count"]),
                "buy_wallet_count": int(basis["buy_wallet_count"]),
                "sell_wallet_count": int(basis["sell_wallet_count"]),
                "wallet_net_count": int(basis["wallet_net_count"]),
                "segment_membership_wallet_counts": dict(
                    basis["segment_membership_wallet_counts"]
                ),
            },
            "base_flow": {
                "net_base_amount": str(basis["net_base_amount"]),
                "direction": current_state,
            },
            "validated_usd_flow": dict(basis["usd_flow"]),
            "window_metrics": window_rows,
            "persistence": _persistence(
                current_state=current_state,
                windows=window_rows,
                bands=bands,
                rows=token_rows,
            ),
            "meme_hunter_evidence": _meme_evidence_summary(contributors),
            "contributors": contributors,
            "registry_provenance": {
                "snapshot_ids": registry_snapshot_ids,
                "snapshot_fingerprints": registry_snapshot_fingerprints,
                "mixed_snapshot_ids": len(registry_snapshot_ids) > 1,
                "mixed_snapshot_fingerprints": (
                    len(registry_snapshot_fingerprints) > 1
                ),
                "policy": "EVENT_TIME_QUALIFICATION_PROVENANCE",
            },
            "scoring": {
                "strength_score": None,
                "policy": "NO_ARBITRARY_SCORE_BEFORE_STAGE10_11_VALIDATION",
            },
        }
        signals.append({
            **signal_core,
            "signal_fingerprint": _fingerprint(signal_core),
        })

    snapshot_core = {
        "version": STAGE9_VERSION,
        "chain": CHAIN,
        "as_of": int(as_of),
        "signal_count": len(signals),
        "signals": signals,
        "contract": {
            "type": "SMART_MONEY_SIGNAL_SNAPSHOT",
            "descriptive_only": True,
            "entry_rule": None,
            "strength_score": None,
            "consumer_boundary": "INDEPENDENT_JSON",
            "next_validation_stage": "WALLET_ONLY_PAPER_TRADING",
        },
    }
    return {
        **snapshot_core,
        "snapshot_fingerprint": _fingerprint(snapshot_core),
    }


def serialize_signal_snapshot(
    snapshot: dict[str, Any],
    *,
    pretty: bool = False,
) -> str:
    """Serialize the external handoff without changing its semantic content."""
    return json.dumps(
        snapshot,
        sort_keys=True,
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    )
