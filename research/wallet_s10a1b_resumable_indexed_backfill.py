from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from research.wallet_s10a1_candidate_refinement import (
    verify_candidate_refinement,
    wallet_addresses_from_refinement,
)
from research.wallet_s10a1b_real_historical_backfill import (
    _fetch_indexed_gtfa_page,
    _safe_indexed_origin,
)
from research.wallet_s10a_historical_backfill import normalize_wallet_histories
from research.wallet_supabase_adapter import SupabaseRestClient

CHECKPOINT_KEY = "stage10a1b_checkpoint"
CHECKPOINT_VERSION = "wallet-s10a1b-checkpoint-v1"


def _load_refinement(path: str | Path) -> dict[str, Any]:
    parsed = json.loads(Path(path).read_text(encoding="utf-8"))
    refinement = parsed.get("refinement") if isinstance(parsed, dict) else parsed
    if not isinstance(refinement, dict):
        raise ValueError("refinement file must contain an object")
    verify_candidate_refinement(refinement)
    return refinement


def _signature(tx: dict[str, Any]) -> str:
    sigs = ((tx.get("transaction") or {}).get("signatures") or [])
    return str(sigs[0]) if sigs else ""


def _checkpoint(
    client: SupabaseRestClient,
    universe_fp: str,
    wallet: str,
) -> dict[str, Any] | None:
    rows = client.select_rows(
        "wallet_universe_candidates",
        query={
            "select": "refinement_payload",
            "universe_fingerprint": f"eq.{universe_fp}",
            "wallet": f"eq.{wallet}",
            "limit": "1",
        },
    )
    if not rows:
        raise RuntimeError(f"missing persisted candidate row: {wallet}")
    payload = rows[0].get("refinement_payload") or {}
    value = payload.get(CHECKPOINT_KEY)
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("version") != CHECKPOINT_VERSION:
        raise RuntimeError(f"invalid checkpoint for {wallet}")
    return dict(value)


def _save_checkpoint(
    client: SupabaseRestClient,
    universe_fp: str,
    record: dict[str, Any],
    checkpoint: dict[str, Any],
) -> None:
    payload = dict(record)
    payload[CHECKPOINT_KEY] = dict(checkpoint)
    client.patch_rows(
        "wallet_universe_candidates",
        query={
            "universe_fingerprint": f"eq.{universe_fp}",
            "wallet": f"eq.{record['wallet']}",
        },
        payload={"refinement_payload": payload},
    )


def backfill_wallet(
    *,
    client: SupabaseRestClient,
    endpoint: str,
    source_label: str,
    universe_fp: str,
    record: dict[str, Any],
    as_of: int,
    page_limit: int,
    max_pages: int,
    request_delay_seconds: float,
) -> dict[str, Any]:
    wallet = str(record["wallet"])
    cp = _checkpoint(client, universe_fp, wallet)
    if cp:
        if int(cp["history_as_of_unix"]) != int(as_of):
            raise RuntimeError(f"checkpoint cutoff mismatch for {wallet}")
        if bool(cp.get("history_complete")):
            return {
                "wallet": wallet,
                "history_complete": True,
                "skipped_complete": True,
                "pages_fetched_this_run": 0,
                "raw_rows_persisted_this_run": 0,
                "normalized_rows_persisted_this_run": 0,
            }

    anchor = cp.get("resume_before_signature") if cp else None
    pages_total = int(cp.get("pages_fetched_total") or 0) if cp else 0
    raw_total = int(cp.get("raw_rows_persisted") or 0) if cp else 0
    norm_total = int(cp.get("normalized_rows_persisted") or 0) if cp else 0
    token: str | None = None
    pages_run = raw_run = norm_run = 0

    while pages_run < int(max_pages):
        payload = _fetch_indexed_gtfa_page(
            endpoint,
            wallet,
            int(page_limit),
            token,
            request_delay_seconds=request_delay_seconds,
            history_as_of_unix=int(as_of),
            resume_before_signature=str(anchor) if anchor else None,
        )
        result = payload.get("result") or {}
        rows = [dict(x) for x in (result.get("data") or [])]
        token = (
            str(result.get("paginationToken"))
            if result.get("paginationToken")
            else None
        )
        pages_run += 1
        pages_total += 1

        if rows:
            normalized, _ = normalize_wallet_histories({wallet: rows})
            raw_count = client.persist_historical_raw(
                {wallet: rows},
                source="indexed_gtfa",
            )
            norm_count = client.persist_normalized_history(normalized)
            raw_run += int(raw_count)
            norm_run += int(norm_count)
            raw_total += int(raw_count)
            norm_total += int(norm_count)
            anchor = _signature(rows[-1])
            if not anchor:
                raise RuntimeError(f"missing resume signature for {wallet}")

        complete = token is None
        checkpoint = {
            "version": CHECKPOINT_VERSION,
            "provider": "indexed_gtfa",
            "source_label": source_label,
            "source_origin": _safe_indexed_origin(endpoint),
            "history_as_of_unix": int(as_of),
            "history_complete": bool(complete),
            "qualification_grade": bool(complete),
            "resume_before_signature": anchor,
            "pages_fetched_total": pages_total,
            "raw_rows_persisted": raw_total,
            "normalized_rows_persisted": norm_total,
        }
        _save_checkpoint(client, universe_fp, record, checkpoint)
        if complete:
            return {
                "wallet": wallet,
                "history_complete": True,
                "skipped_complete": False,
                "pages_fetched_this_run": pages_run,
                "raw_rows_persisted_this_run": raw_run,
                "normalized_rows_persisted_this_run": norm_run,
            }

    raise RuntimeError(
        f"incomplete indexed history for {wallet}; "
        f"max_pages={max_pages}; checkpoint persisted"
    )


def run(
    *,
    refinement: dict[str, Any],
    client: SupabaseRestClient,
    endpoint: str,
    source_label: str,
    as_of: int,
    page_limit: int = 100,
    max_pages_per_wallet: int = 5000,
    request_delay_seconds: float = 1.0,
) -> dict[str, Any]:
    verify_candidate_refinement(refinement)
    universe_fp = str(refinement["source_universe_fingerprint"])
    records = {
        str(r["wallet"]): dict(r)
        for r in refinement.get("records") or []
        if bool(r.get("trader_candidate"))
    }
    wallets = wallet_addresses_from_refinement(refinement, trader_only=True)
    reports = [
        backfill_wallet(
            client=client,
            endpoint=endpoint,
            source_label=source_label,
            universe_fp=universe_fp,
            record=records[wallet],
            as_of=int(as_of),
            page_limit=int(page_limit),
            max_pages=int(max_pages_per_wallet),
            request_delay_seconds=float(request_delay_seconds),
        )
        for wallet in wallets
    ]
    complete = all(bool(r["history_complete"]) for r in reports)
    raw_run = sum(int(r["raw_rows_persisted_this_run"]) for r in reports)
    norm_run = sum(
        int(r["normalized_rows_persisted_this_run"]) for r in reports
    )
    skipped = sum(int(bool(r["skipped_complete"])) for r in reports)
    return {
        "version": "wallet-s10a1b-resumable-v1",
        "backfill": {
            "fetch": {
                "provider": "indexed_gtfa",
                "source_label": source_label,
                "source_origin": _safe_indexed_origin(endpoint),
                "history_as_of_unix": int(as_of),
                "wallet_count": len(wallets),
                "history_complete_for_all_wallets": complete,
                "qualification_grade": complete,
                "raw_transaction_rows_across_wallets": raw_run,
            },
            "normalization": {"normalized_event_count": norm_run},
            "persistence": {
                "persisted": True,
                "checkpointed_per_page": True,
                "complete_wallet_count": sum(
                    int(bool(r["history_complete"])) for r in reports
                ),
                "skipped_complete_wallet_count": skipped,
                "raw_rows_persisted_this_run": raw_run,
                "normalized_rows_persisted_this_run": norm_run,
            },
            "resume": {"wallet_reports": reports},
        },
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--refinement-file", required=True)
    p.add_argument(
        "--indexed-rpc-url",
        default=os.environ.get("ALCHEMY_SOLANA_RPC_URL") or "",
    )
    p.add_argument(
        "--indexed-source-label",
        default="alchemy-solana-gtfa",
    )
    p.add_argument("--history-as-of-unix", type=int, required=True)
    p.add_argument("--page-limit", type=int, default=100)
    p.add_argument("--max-pages-per-wallet", type=int, default=5000)
    p.add_argument(
        "--indexed-min-request-interval-ms",
        type=float,
        default=1000.0,
    )
    p.add_argument("--out", required=True)
    args = p.parse_args()

    if not str(args.indexed_rpc_url).strip():
        raise SystemExit("indexed RPC URL is required")
    report = run(
        refinement=_load_refinement(args.refinement_file),
        client=SupabaseRestClient.from_env(),
        endpoint=str(args.indexed_rpc_url),
        source_label=str(args.indexed_source_label),
        as_of=int(args.history_as_of_unix),
        page_limit=int(args.page_limit),
        max_pages_per_wallet=int(args.max_pages_per_wallet),
        request_delay_seconds=(
            float(args.indexed_min_request_interval_ms) / 1000.0
        ),
    )
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["backfill"]["persistence"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
