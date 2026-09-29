from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

from research.wallet_s2_transaction_normalizer import normalize_transaction
from research.wallet_s10a0_wallet_universe_discovery import (
    DEFAULT_MAX_SUPPORTED_TRANSACTION_VERSION,
    DEFAULT_SOLANA_RPC_URL,
    SolanaJsonRpcBlockSource,
    _safe_rpc_origin,
    verify_candidate_universe,
)
from research.wallet_supabase_adapter import SupabaseRestClient

STAGE10A1A_VERSION = "wallet-s10a1a-v1"
CHAIN = "solana"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _signature(tx_entry: dict[str, Any]) -> str:
    transaction = tx_entry.get("transaction") or {}
    signatures = transaction.get("signatures") or []
    return str(signatures[0]) if signatures else ""


def _enriched_transaction(
    tx_entry: dict[str, Any],
    *,
    slot: int,
    block_time: int,
) -> dict[str, Any]:
    enriched = dict(tx_entry)
    enriched["slot"] = int(slot)
    enriched["blockTime"] = int(block_time)
    return enriched


def _transactions_by_signature(
    blocks: Iterable[dict[str, Any]],
    *,
    required_slots: set[int],
) -> dict[str, dict[str, Any]]:
    by_signature: dict[str, dict[str, Any]] = {}
    seen_slots: set[int] = set()

    for wrapper in blocks:
        if wrapper.get("slot") is None:
            raise ValueError("block wrapper requires slot")
        slot = int(wrapper["slot"])
        if slot not in required_slots:
            raise ValueError(
                f"refinement block slot {slot} is outside discovery slots"
            )
        if slot in seen_slots:
            raise ValueError(f"duplicate refinement block slot {slot}")
        seen_slots.add(slot)

        block = wrapper.get("block")
        if not isinstance(block, dict):
            raise ValueError(f"missing block payload for slot {slot}")
        block_time = block.get("blockTime")
        if block_time is None:
            raise ValueError(
                f"refinement block {slot} requires blockTime"
            )

        for tx_entry in block.get("transactions") or []:
            signature = _signature(tx_entry)
            if not signature:
                continue
            enriched = _enriched_transaction(
                tx_entry,
                slot=slot,
                block_time=int(block_time),
            )
            existing = by_signature.get(signature)
            if existing is not None:
                if _canonical_json(existing) != _canonical_json(enriched):
                    raise ValueError(
                        f"conflicting duplicate transaction {signature}"
                    )
                continue
            by_signature[signature] = enriched

    missing_slots = sorted(required_slots - seen_slots)
    if missing_slots:
        raise RuntimeError(
            "refinement did not refetch every discovery slot: "
            + ",".join(str(slot) for slot in missing_slots)
        )
    return by_signature


def _event_decision(normalized: dict[str, Any]) -> tuple[bool, bool, str]:
    event_type = str(normalized.get("event_type") or "")
    side = str(normalized.get("side") or "")

    if event_type != "SWAP":
        return False, False, f"REJECT_EVENT_TYPE_{event_type or 'UNKNOWN'}"
    if side not in {"BUY", "SELL"}:
        return False, False, f"REJECT_SWAP_SIDE_{side or 'UNKNOWN'}"
    if side == "BUY":
        return True, True, "DIRECTIONAL_SWAP_BUY"
    return True, False, "DIRECTIONAL_SWAP_SELL"


def build_candidate_refinement(
    universe: dict[str, Any],
    blocks: Iterable[dict[str, Any]],
    *,
    source_label: str,
    source_origin: str,
) -> dict[str, Any]:
    """Refine activity candidates using only Stage-2 transaction semantics.

    This stage answers whether an observed activity candidate has a directional
    BUY/SELL swap. It does not use performance, future returns, or Stage 3-5
    qualification.
    """
    verify_candidate_universe(universe)
    if not str(source_label or "").strip():
        raise ValueError("source_label is required")

    scan = universe.get("scan") or {}
    scanned_slots = {
        int(slot) for slot in (scan.get("scanned_slots") or [])
    }
    if not scanned_slots:
        raise ValueError("candidate universe has no scanned slots")

    tx_by_signature = _transactions_by_signature(
        blocks,
        required_slots=scanned_slots,
    )

    records: list[dict[str, Any]] = []
    missing_evidence: list[str] = []

    for source_record in sorted(
        universe.get("records") or [],
        key=lambda row: str(row.get("wallet") or ""),
    ):
        wallet = str(source_record.get("wallet") or "")
        events: list[dict[str, Any]] = []

        for evidence in sorted(
            source_record.get("evidence") or [],
            key=lambda row: (
                int(row.get("block_time") or 0),
                int(row.get("slot") or 0),
                str(row.get("signature") or ""),
            ),
        ):
            signature = str(evidence.get("signature") or "")
            tx = tx_by_signature.get(signature)
            if tx is None:
                missing_evidence.append(f"{wallet}:{signature}")
                continue

            normalized = normalize_transaction(tx, wallet)
            trader_event, meme_buy_event, reason = _event_decision(
                normalized
            )
            event_core = {
                "version": STAGE10A1A_VERSION,
                "chain": CHAIN,
                "wallet": wallet,
                "signature": signature,
                "slot": int(evidence["slot"]),
                "block_time": int(evidence["block_time"]),
                "discovery_reason": evidence.get("discovery_reason"),
                "stage2_version": normalized.get("version"),
                "event_type": normalized.get("event_type"),
                "side": normalized.get("side"),
                "base_asset": normalized.get("base_asset"),
                "quote_asset": normalized.get("quote_asset"),
                "confidence": normalized.get("confidence"),
                "trader_candidate_event": trader_event,
                "meme_buy_candidate_event": meme_buy_event,
                "refinement_reason": reason,
                "normalized_event": normalized,
            }
            events.append({
                **event_core,
                "event_fingerprint": _fingerprint(event_core),
            })

        trader_events = [
            row for row in events if row["trader_candidate_event"]
        ]
        buy_events = [
            row for row in trader_events if row.get("side") == "BUY"
        ]
        sell_events = [
            row for row in trader_events if row.get("side") == "SELL"
        ]
        base_assets = sorted({
            str(row["base_asset"])
            for row in trader_events
            if row.get("base_asset")
        })

        trader_candidate = bool(trader_events)
        meme_buy_candidate = bool(buy_events)
        record_core = {
            "version": STAGE10A1A_VERSION,
            "chain": CHAIN,
            "wallet": wallet,
            "source_universe_fingerprint": universe[
                "universe_fingerprint"
            ],
            "activity_evidence_count": len(events),
            "trader_event_count": len(trader_events),
            "buy_event_count": len(buy_events),
            "sell_event_count": len(sell_events),
            "meme_buy_event_count": len(buy_events),
            "trader_candidate": trader_candidate,
            "meme_buy_candidate": meme_buy_candidate,
            "candidate_status": (
                "TRADER_CANDIDATE"
                if trader_candidate
                else "NON_TRADER_ACTIVITY"
            ),
            "historical_backfill_eligible": trader_candidate,
            "observed_base_assets": base_assets,
            "events": events,
        }
        records.append({
            **record_core,
            "record_fingerprint": _fingerprint(record_core),
        })

    if missing_evidence:
        preview = ", ".join(missing_evidence[:5])
        raise RuntimeError(
            "refinement is incomplete; discovery evidence signatures "
            f"were not found in refetched finalized blocks: {preview}"
        )

    trader_records = [
        row for row in records if row["trader_candidate"]
    ]
    meme_records = [
        row for row in records if row["meme_buy_candidate"]
    ]
    refinement_core = {
        "version": STAGE10A1A_VERSION,
        "chain": CHAIN,
        "source_universe_fingerprint": universe[
            "universe_fingerprint"
        ],
        "source": {
            "kind": "SOLANA_JSON_RPC",
            "label": str(source_label).strip(),
            "origin": _safe_rpc_origin(source_origin),
        },
        "activity_candidate_wallet_count": len(records),
        "trader_candidate_wallet_count": len(trader_records),
        "non_trader_activity_wallet_count": (
            len(records) - len(trader_records)
        ),
        "meme_buy_candidate_wallet_count": len(meme_records),
        "trader_event_count": sum(
            int(row["trader_event_count"]) for row in records
        ),
        "buy_event_count": sum(
            int(row["buy_event_count"]) for row in records
        ),
        "sell_event_count": sum(
            int(row["sell_event_count"]) for row in records
        ),
        "records": records,
        "contract": {
            "uses_stage2_normalizer": True,
            "performance_filter": None,
            "future_return_filter": None,
            "trader_rule": "SWAP_AND_SIDE_BUY_OR_SELL",
            "meme_candidate_rule": "TRADER_BUY_EVENT",
            "normal_track_handoff": (
                "WALLET_STAGE10A1_CAUSAL_HISTORICAL_BACKFILL"
            ),
            "meme_track_handoff": (
                "WALLET_STAGE6_CAUSAL_EXPLOSION_ANALYSIS"
            ),
        },
    }
    return {
        **refinement_core,
        "refinement_fingerprint": _fingerprint(refinement_core),
    }


def verify_candidate_refinement(
    refinement: dict[str, Any],
) -> bool:
    if str(refinement.get("version") or "") != STAGE10A1A_VERSION:
        raise ValueError("unsupported candidate-refinement version")
    source_universe = str(
        refinement.get("source_universe_fingerprint") or ""
    )
    if not source_universe:
        raise ValueError("refinement requires source universe fingerprint")

    records = list(refinement.get("records") or [])
    seen_wallets: set[str] = set()
    trader_count = 0
    meme_count = 0

    for record in records:
        wallet = str(record.get("wallet") or "")
        if not wallet:
            raise ValueError("refinement record requires wallet")
        if wallet in seen_wallets:
            raise ValueError(f"duplicate refinement wallet: {wallet}")
        seen_wallets.add(wallet)

        actual = str(record.get("record_fingerprint") or "")
        core = {
            key: value
            for key, value in record.items()
            if key != "record_fingerprint"
        }
        if not actual or actual != _fingerprint(core):
            raise ValueError(
                f"refinement record fingerprint mismatch: {wallet}"
            )

        for event in record.get("events") or []:
            event_actual = str(event.get("event_fingerprint") or "")
            event_core = {
                key: value
                for key, value in event.items()
                if key != "event_fingerprint"
            }
            if not event_actual or event_actual != _fingerprint(
                event_core
            ):
                raise ValueError(
                    f"refinement event fingerprint mismatch: "
                    f"{wallet}:{event.get('signature')}"
                )

        trader_candidate = bool(record.get("trader_candidate"))
        meme_candidate = bool(record.get("meme_buy_candidate"))
        if meme_candidate and not trader_candidate:
            raise ValueError(
                "meme buy candidate must also be a trader candidate"
            )
        trader_count += int(trader_candidate)
        meme_count += int(meme_candidate)

    if int(
        refinement.get("activity_candidate_wallet_count") or 0
    ) != len(records):
        raise ValueError("activity candidate wallet count mismatch")
    if int(
        refinement.get("trader_candidate_wallet_count") or 0
    ) != trader_count:
        raise ValueError("trader candidate wallet count mismatch")
    if int(
        refinement.get("meme_buy_candidate_wallet_count") or 0
    ) != meme_count:
        raise ValueError("meme buy candidate wallet count mismatch")

    core = {
        key: value
        for key, value in refinement.items()
        if key != "refinement_fingerprint"
    }
    actual = str(refinement.get("refinement_fingerprint") or "")
    if not actual or actual != _fingerprint(core):
        raise ValueError("candidate-refinement fingerprint mismatch")
    return True


def wallet_addresses_from_refinement(
    refinement: dict[str, Any],
    *,
    trader_only: bool = True,
) -> list[str]:
    verify_candidate_refinement(refinement)
    rows = refinement.get("records") or []
    return sorted(
        str(row["wallet"])
        for row in rows
        if not trader_only or bool(row.get("trader_candidate"))
    )


def scan_candidate_refinement(
    universe: dict[str, Any],
    source: SolanaJsonRpcBlockSource,
) -> dict[str, Any]:
    verify_candidate_universe(universe)
    slots = sorted({
        int(slot)
        for slot in (universe.get("scan") or {}).get(
            "scanned_slots", []
        )
    })
    if not slots:
        raise ValueError("candidate universe has no scanned slots")

    blocks = [
        {"slot": slot, "block": source.get_block(slot)}
        for slot in slots
    ]
    refinement = build_candidate_refinement(
        universe,
        blocks,
        source_label=source.source_label,
        source_origin=source.public_origin,
    )
    verify_candidate_refinement(refinement)
    return refinement


def _load_universe(path: str | Path) -> dict[str, Any]:
    parsed = json.loads(Path(path).read_text(encoding="utf-8"))
    universe = (
        parsed.get("universe")
        if isinstance(parsed, dict) and "universe" in parsed
        else parsed
    )
    if not isinstance(universe, dict):
        raise ValueError("universe file must contain a Stage-10A-0 object")
    verify_candidate_universe(universe)
    return universe


def _write_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Stage 10A-1A Stage-2 trader/meme candidate refinement"
        )
    )
    parser.add_argument("--universe-file", required=True)
    parser.add_argument(
        "--rpc-url",
        default=(
            os.environ.get("SOLANA_RPC_URL")
            or DEFAULT_SOLANA_RPC_URL
        ),
    )
    parser.add_argument(
        "--source-label",
        default=os.environ.get(
            "SOLANA_RPC_SOURCE_LABEL",
            "solana-json-rpc",
        ),
    )
    parser.add_argument(
        "--max-supported-transaction-version",
        type=int,
        default=DEFAULT_MAX_SUPPORTED_TRANSACTION_VERSION,
    )
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--persist-supabase",
        action="store_true",
    )
    parser.add_argument(
        "--require-trader-candidates",
        action="store_true",
    )
    args = parser.parse_args()

    universe = _load_universe(args.universe_file)
    source = SolanaJsonRpcBlockSource(
        args.rpc_url,
        source_label=args.source_label,
        max_supported_transaction_version=(
            args.max_supported_transaction_version
        ),
    )
    refinement = scan_candidate_refinement(universe, source)

    if (
        args.require_trader_candidates
        and not refinement["trader_candidate_wallet_count"]
    ):
        raise SystemExit("no trader candidates found")

    persistence = None
    if args.persist_supabase:
        client = SupabaseRestClient.from_env()
        client.persist_candidate_universe(universe)
        persistence = client.persist_candidate_refinement(
            universe,
            refinement,
        )

    output = {
        "refinement": refinement,
        "persistence": persistence,
    }
    _write_json(args.out, output)
    print(json.dumps({
        "version": refinement["version"],
        "source_universe_fingerprint": (
            refinement["source_universe_fingerprint"]
        ),
        "refinement_fingerprint": (
            refinement["refinement_fingerprint"]
        ),
        "activity_candidate_wallet_count": (
            refinement["activity_candidate_wallet_count"]
        ),
        "trader_candidate_wallet_count": (
            refinement["trader_candidate_wallet_count"]
        ),
        "meme_buy_candidate_wallet_count": (
            refinement["meme_buy_candidate_wallet_count"]
        ),
        "trader_event_count": refinement["trader_event_count"],
        "buy_event_count": refinement["buy_event_count"],
        "sell_event_count": refinement["sell_event_count"],
        "persisted": bool(args.persist_supabase),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
