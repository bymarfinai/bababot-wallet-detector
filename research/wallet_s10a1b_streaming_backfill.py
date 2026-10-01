from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
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
from research.wallet_s3_streaming_reconstruction import (
    empty_stream_state,
    consume_stream_page,
)
from research.wallet_s4_historical_performance import compute_wallet_performance
from research.wallet_s5_classification import classify_wallet
from research.wallet_supabase_adapter import SupabaseRestClient

STREAMING_VERSION = "wallet-s10a1b-stream-v2"
SCAN_STATE_TABLE = "wallet_history_scan_state"
TRADE_SUMMARY_TABLE = "wallet_historical_trade_summaries"
PROFILE_TABLE = "wallet_historical_profiles"


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


def _load_scan_state(
    client: SupabaseRestClient,
    universe_fp: str,
    wallet: str,
) -> dict[str, Any] | None:
    rows = client.select_rows(
        SCAN_STATE_TABLE,
        query={
            "select": "*",
            "universe_fingerprint": f"eq.{universe_fp}",
            "wallet": f"eq.{wallet}",
            "limit": "1",
        },
    )
    return dict(rows[0]) if rows else None


def _save_scan_state(
    client: SupabaseRestClient,
    row: dict[str, Any],
) -> None:
    payload = dict(row)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    client.upsert_rows(
        SCAN_STATE_TABLE,
        [payload],
        on_conflict="universe_fingerprint,wallet",
    )


def _trade_summary_row(
    universe_fp: str,
    episode: dict[str, Any],
) -> dict[str, Any]:
    return {
        "universe_fingerprint": universe_fp,
        "wallet": str(episode["wallet"]),
        "episode_id": str(episode["episode_id"]),
        "base_asset": str(episode["base_asset"]),
        "quote_asset": str(episode["quote_asset"]),
        "quote_is_usd": bool(episode.get("quote_is_usd")),
        "opened_at": episode.get("opened_at"),
        "closed_at": int(episode["closed_at"]),
        "opened_slot": episode.get("opened_slot"),
        "close_slot": episode.get("close_slot"),
        "holding_seconds": episode.get("holding_seconds"),
        "realized_cost_quote": str(episode["realized_cost_quote"]),
        "realized_proceeds_quote": str(
            episode["realized_proceeds_quote"]
        ),
        "realized_pnl_quote": str(episode["realized_pnl_quote"]),
        "realized_roi_pct": str(episode["realized_roi_pct"]),
        "network_fee_lamports": int(
            episode.get("network_fee_lamports") or 0
        ),
        "buy_count": int(episode.get("buy_count") or 0),
        "sell_count": int(episode.get("sell_count") or 0),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _episode_from_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "episode_id": str(row["episode_id"]),
        "wallet": str(row["wallet"]),
        "base_asset": str(row["base_asset"]),
        "quote_asset": str(row["quote_asset"]),
        "quote_is_usd": bool(row.get("quote_is_usd")),
        "status": "CLOSED",
        "opened_at": row.get("opened_at"),
        "closed_at": row.get("closed_at"),
        "opened_slot": row.get("opened_slot"),
        "close_slot": row.get("close_slot"),
        "holding_seconds": row.get("holding_seconds"),
        "realized_cost_quote": str(row["realized_cost_quote"]),
        "realized_proceeds_quote": str(
            row["realized_proceeds_quote"]
        ),
        "realized_pnl_quote": str(row["realized_pnl_quote"]),
        "realized_roi_pct": str(row["realized_roi_pct"]),
        "network_fee_lamports": int(
            row.get("network_fee_lamports") or 0
        ),
        "buy_count": int(row.get("buy_count") or 0),
        "sell_count": int(row.get("sell_count") or 0),
        "eligible_for_performance_metrics": True,
    }


def _finalize_profile(
    *,
    client: SupabaseRestClient,
    universe_fp: str,
    wallet: str,
    as_of: int,
    state_row: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = client.select_all_rows(
        TRADE_SUMMARY_TABLE,
        query={
            "select": (
                "episode_id,wallet,base_asset,quote_asset,quote_is_usd,"
                "opened_at,closed_at,opened_slot,close_slot,holding_seconds,"
                "realized_cost_quote,realized_proceeds_quote,"
                "realized_pnl_quote,realized_roi_pct,"
                "network_fee_lamports,buy_count,sell_count"
            ),
            "universe_fingerprint": f"eq.{universe_fp}",
            "wallet": f"eq.{wallet}",
            "order": "closed_at.asc,close_slot.asc,episode_id.asc",
        },
    )
    episodes = [_episode_from_summary(row) for row in rows]
    performance = compute_wallet_performance(
        {
            "wallet": wallet,
            "scorable_closed_episodes": episodes,
        }
    )
    classification = classify_wallet(performance)

    client.upsert_rows(
        PROFILE_TABLE,
        [{
            "universe_fingerprint": universe_fp,
            "wallet": wallet,
            "history_as_of_unix": int(as_of),
            "stage4_version": performance.get("version"),
            "stage5_version": classification.get("version"),
            "closed_trade_count": int(
                performance.get("closed_trade_count") or 0
            ),
            "performance_payload": performance,
            "classification_payload": classification,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }],
        on_conflict="universe_fingerprint,wallet",
    )

    state_row = dict(state_row)
    state_row["history_complete"] = True
    state_row["profile_finalized_at"] = (
        datetime.now(timezone.utc).isoformat()
    )
    state_row["closed_trade_summary_count"] = len(rows)
    _save_scan_state(client, state_row)
    return performance, classification


def backfill_wallet(
    *,
    client: SupabaseRestClient,
    endpoint: str,
    source_label: str,
    universe_fp: str,
    wallet: str,
    as_of: int,
    page_limit: int,
    max_pages: int,
    request_delay_seconds: float,
) -> dict[str, Any]:
    origin = _safe_indexed_origin(endpoint)
    stored = _load_scan_state(client, universe_fp, wallet)

    if stored:
        if str(stored.get("version") or "") != STREAMING_VERSION:
            raise RuntimeError(
                f"incompatible V2 scan state for {wallet}: "
                f"{stored.get('version')!r}"
            )
        if int(stored["history_as_of_unix"]) != int(as_of):
            raise RuntimeError(f"V2 history cutoff mismatch for {wallet}")
        existing_origin = str(stored.get("source_origin") or "")
        token = stored.get("next_pagination_token")
        if token and existing_origin and existing_origin != origin:
            raise RuntimeError(
                f"provider cursor cannot move across origins for {wallet}"
            )
        if bool(stored.get("history_complete")):
            return {
                "wallet": wallet,
                "history_complete": True,
                "skipped_complete": True,
                "pages_fetched_this_run": 0,
                "transactions_scanned_this_run": 0,
                "normalized_events_this_run": 0,
                "compact_trade_rows_this_run": 0,
            }
        if bool(stored.get("scan_exhausted")):
            _finalize_profile(
                client=client,
                universe_fp=universe_fp,
                wallet=wallet,
                as_of=int(as_of),
                state_row=stored,
            )
            return {
                "wallet": wallet,
                "history_complete": True,
                "skipped_complete": False,
                "pages_fetched_this_run": 0,
                "transactions_scanned_this_run": 0,
                "normalized_events_this_run": 0,
                "compact_trade_rows_this_run": 0,
                "finalized_from_checkpoint": True,
            }

        state_row = dict(stored)
        stage3_state = dict(stored.get("stage3_state") or {})
        pagination_token = (
            str(stored["next_pagination_token"])
            if stored.get("next_pagination_token")
            else None
        )
    else:
        stage3_state = empty_stream_state(wallet)
        pagination_token = None
        state_row = {
            "universe_fingerprint": universe_fp,
            "wallet": wallet,
            "version": STREAMING_VERSION,
            "provider": "indexed_gtfa",
            "source_label": source_label,
            "source_origin": origin,
            "history_as_of_unix": int(as_of),
            "scan_exhausted": False,
            "history_complete": False,
            "next_pagination_token": None,
            "last_signature": None,
            "pages_fetched_total": 0,
            "transactions_scanned_total": 0,
            "normalized_events_total": 0,
            "normalization_errors_total": 0,
            "closed_trade_summary_count": 0,
            "stage3_state": stage3_state,
            "profile_finalized_at": None,
        }
        _save_scan_state(client, state_row)

    pages_run = 0
    tx_run = 0
    normalized_run = 0
    compact_run = 0

    while pages_run < int(max_pages):
        payload = _fetch_indexed_gtfa_page(
            endpoint,
            wallet,
            int(page_limit),
            pagination_token,
            request_delay_seconds=request_delay_seconds,
            history_as_of_unix=int(as_of),
            sort_order="asc",
        )
        result = payload.get("result") or {}
        raw_rows = [dict(x) for x in (result.get("data") or [])]
        next_token = (
            str(result["paginationToken"])
            if result.get("paginationToken")
            else None
        )

        normalized_by_wallet, norm_report = normalize_wallet_histories(
            {wallet: raw_rows}
        )
        normalized_rows = list(normalized_by_wallet.get(wallet) or [])
        streamed = consume_stream_page(
            stage3_state,
            normalized_rows,
            wallet=wallet,
        )
        stage3_state = dict(streamed["state"])
        compact_rows = [
            _trade_summary_row(universe_fp, episode)
            for episode in streamed["closed_episodes"]
        ]

        # Persist compact outputs before advancing the cursor. If checkpointing
        # fails afterwards, replaying the same page is safe because episode rows
        # are idempotent by universe + wallet + episode_id.
        if compact_rows:
            client.upsert_rows(
                TRADE_SUMMARY_TABLE,
                compact_rows,
                on_conflict="universe_fingerprint,wallet,episode_id",
            )

        pages_run += 1
        tx_run += len(raw_rows)
        normalized_run += len(normalized_rows)
        compact_run += len(compact_rows)

        state_row["source_label"] = source_label
        state_row["source_origin"] = origin
        state_row["next_pagination_token"] = next_token
        state_row["last_signature"] = (
            _signature(raw_rows[-1]) if raw_rows else state_row.get(
                "last_signature"
            )
        )
        state_row["pages_fetched_total"] = int(
            state_row.get("pages_fetched_total") or 0
        ) + 1
        state_row["transactions_scanned_total"] = int(
            state_row.get("transactions_scanned_total") or 0
        ) + len(raw_rows)
        state_row["normalized_events_total"] = int(
            state_row.get("normalized_events_total") or 0
        ) + len(normalized_rows)
        state_row["normalization_errors_total"] = int(
            state_row.get("normalization_errors_total") or 0
        ) + int(norm_report.get("normalization_error_count") or 0)
        state_row["closed_trade_summary_count"] = int(
            stage3_state.get("scorable_closed_episode_count") or 0
        )
        state_row["stage3_state"] = stage3_state
        state_row["scan_exhausted"] = next_token is None
        state_row["history_complete"] = False
        _save_scan_state(client, state_row)

        # raw_rows and normalized_rows fall out of scope every page: neither is
        # written to historical_wallet_transactions/normalized_wallet_history.
        pagination_token = next_token
        if next_token is None:
            _finalize_profile(
                client=client,
                universe_fp=universe_fp,
                wallet=wallet,
                as_of=int(as_of),
                state_row=state_row,
            )
            return {
                "wallet": wallet,
                "history_complete": True,
                "skipped_complete": False,
                "pages_fetched_this_run": pages_run,
                "transactions_scanned_this_run": tx_run,
                "normalized_events_this_run": normalized_run,
                "compact_trade_rows_this_run": compact_run,
            }

    raise RuntimeError(
        f"incomplete V2 indexed history for {wallet}; "
        f"max_pages={max_pages}; compact checkpoint persisted"
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
    wallets = wallet_addresses_from_refinement(refinement, trader_only=True)

    reports = [
        backfill_wallet(
            client=client,
            endpoint=endpoint,
            source_label=source_label,
            universe_fp=universe_fp,
            wallet=wallet,
            as_of=int(as_of),
            page_limit=int(page_limit),
            max_pages=int(max_pages_per_wallet),
            request_delay_seconds=float(request_delay_seconds),
        )
        for wallet in wallets
    ]

    complete = all(bool(row["history_complete"]) for row in reports)
    pages_run = sum(int(row["pages_fetched_this_run"]) for row in reports)
    tx_run = sum(
        int(row["transactions_scanned_this_run"]) for row in reports
    )
    normalized_run = sum(
        int(row["normalized_events_this_run"]) for row in reports
    )
    compact_run = sum(
        int(row["compact_trade_rows_this_run"]) for row in reports
    )
    skipped = sum(int(bool(row["skipped_complete"])) for row in reports)

    return {
        "version": STREAMING_VERSION,
        "backfill": {
            "fetch": {
                "provider": "indexed_gtfa",
                "source_label": source_label,
                "source_origin": _safe_indexed_origin(endpoint),
                "history_as_of_unix": int(as_of),
                "wallet_count": len(wallets),
                "history_complete_for_all_wallets": complete,
                "qualification_grade": complete,
                "raw_transaction_rows_across_wallets": 0,
                "transactions_scanned_this_run": tx_run,
                "sort_order": "asc",
            },
            "normalization": {
                "normalized_event_count": normalized_run,
                "persisted_normalized_event_count": 0,
                "transient_only": True,
            },
            "persistence": {
                "persisted": True,
                "checkpointed_per_page": True,
                "streaming_compact_v2": True,
                "raw_rows_persisted_this_run": 0,
                "normalized_rows_persisted_this_run": 0,
                "compact_trade_rows_persisted_this_run": compact_run,
                "complete_wallet_count": sum(
                    int(bool(row["history_complete"])) for row in reports
                ),
                "skipped_complete_wallet_count": skipped,
            },
            "resume": {
                "pages_fetched_this_run": pages_run,
                "wallet_reports": reports,
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refinement-file", required=True)
    parser.add_argument(
        "--indexed-rpc-url",
        default=os.environ.get("ALCHEMY_SOLANA_RPC_URL") or "",
    )
    parser.add_argument(
        "--indexed-source-label",
        default="alchemy-solana-gtfa",
    )
    parser.add_argument("--history-as-of-unix", type=int, required=True)
    parser.add_argument("--page-limit", type=int, default=100)
    parser.add_argument("--max-pages-per-wallet", type=int, default=5000)
    parser.add_argument(
        "--indexed-min-request-interval-ms",
        type=float,
        default=1000.0,
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

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
