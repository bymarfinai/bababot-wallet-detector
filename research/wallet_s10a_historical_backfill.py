from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from research.wallet_s1_data_foundation import (
    build_helius_gtfa_payload,
    validate_solana_address,
)
from research.wallet_s2_transaction_normalizer import normalize_transaction
from research.wallet_s3_position_reconstruction import reconstruct_positions
from research.wallet_s4_historical_performance import compute_wallet_performance
from research.wallet_s5_classification import classify_wallet
from research.wallet_s7_qualified_registry import (
    build_registry_record,
    build_registry_snapshot,
)
from research.wallet_s9_smart_money_signal import (
    build_smart_money_signal_snapshot,
)
from research.wallet_supabase_adapter import SupabaseRestClient
from research.wallet_s10a0_wallet_universe_discovery import (
    wallet_addresses_from_universe,
)
from research.wallet_s10a1_candidate_refinement import (
    wallet_addresses_from_refinement,
)

STAGE10A_VERSION = "wallet-s10a-v1"
STAGE8_VERSION = "wallet-s8-v1"
HELIUS_ENDPOINT = "https://mainnet.helius-rpc.com/"
DEFAULT_PAGE_LIMIT = 100
DEFAULT_MAX_PAGES_PER_WALLET = 1000
DEFAULT_RPC_PAGE_LIMIT = 1000
DEFAULT_RPC_MAX_SIGNATURES = 1000
DEFAULT_RPC_ATTEMPTS = 5
DEFAULT_MAX_SUPPORTED_TRANSACTION_VERSION = 1
DEFAULT_SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
ROLLING_SIGNAL_SECONDS = 60 * 60

FetchPage = Callable[
    [str, str, int, str | None],
    dict[str, Any],
]


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


def _signature(tx: dict[str, Any]) -> str:
    transaction = tx.get("transaction") or {}
    signatures = transaction.get("signatures") or []
    return str(signatures[0]) if signatures else ""


def _fetch_helius_page(
    api_key: str,
    wallet: str,
    limit: int,
    pagination_token: str | None,
    *,
    attempts: int = 4,
) -> dict[str, Any]:
    payload = build_helius_gtfa_payload(
        wallet,
        limit=limit,
        pagination_token=pagination_token,
        sort_order="desc",
    )
    endpoint = f"{HELIUS_ENDPOINT}?api-key={api_key}"
    body = json.dumps(payload).encode("utf-8")

    last_error: Exception | None = None
    for attempt in range(attempts):
        request = Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=45) as response:
                parsed = json.loads(
                    response.read().decode("utf-8")
                )
            if parsed.get("error"):
                raise RuntimeError(
                    f"Helius RPC error: {parsed['error']}"
                )
            return parsed
        except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            time.sleep(min(2 ** attempt, 8))

    raise RuntimeError(
        f"Helius request failed after {attempts} attempts: {last_error}"
    )


def _safe_rpc_origin(url: str) -> str:
    parts = urlsplit(str(url))
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("RPC URL must be an absolute HTTP(S) URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", "", ""))


def _rpc_request(
    rpc_url: str,
    method: str,
    params: list[Any],
    *,
    attempts: int = DEFAULT_RPC_ATTEMPTS,
) -> Any:
    if int(attempts) < 1:
        raise ValueError("attempts must be >= 1")
    _safe_rpc_origin(rpc_url)
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }).encode("utf-8")

    last_error: Exception | None = None
    for attempt in range(int(attempts)):
        request = Request(
            rpc_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=45) as response:
                parsed = json.loads(response.read().decode("utf-8"))
            if parsed.get("error") is not None:
                raise RuntimeError(
                    f"RPC {method} error: {parsed['error']}"
                )
            return parsed.get("result")
        except (
            HTTPError,
            URLError,
            TimeoutError,
            RuntimeError,
            json.JSONDecodeError,
        ) as exc:
            last_error = exc
            if attempt == int(attempts) - 1:
                break
            time.sleep(min(2 ** attempt, 8))

    raise RuntimeError(
        f"RPC {method} failed after {attempts} attempts: {last_error}"
    )


def fetch_wallet_history_rpc(
    rpc_url: str,
    wallet: str,
    *,
    max_signatures: int = DEFAULT_RPC_MAX_SIGNATURES,
    page_limit: int = DEFAULT_RPC_PAGE_LIMIT,
    min_block_time_unix: int | None = None,
    allow_bounded_history: bool = False,
    rpc_call: Callable[[str, list[Any]], Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch wallet history through standard Solana JSON-RPC.

    Complete history is required by default. A bounded history is allowed only
    when explicitly requested and is labeled incomplete for smoke/probe use.
    """
    wallet = validate_solana_address(wallet)
    _safe_rpc_origin(rpc_url)
    if not 1 <= int(page_limit) <= 1000:
        raise ValueError("page_limit must be between 1 and 1000")
    if int(max_signatures) < 1:
        raise ValueError("max_signatures must be >= 1")
    if min_block_time_unix is not None:
        min_block_time_unix = int(min_block_time_unix)

    caller = rpc_call or (
        lambda method, params: _rpc_request(rpc_url, method, params)
    )

    signatures: list[dict[str, Any]] = []
    before: str | None = None
    reached_history_end = False
    reached_time_floor = False

    while len(signatures) < int(max_signatures):
        remaining = int(max_signatures) - len(signatures)
        limit = min(int(page_limit), remaining)
        config: dict[str, Any] = {
            "limit": limit,
            "commitment": "finalized",
        }
        if before:
            config["before"] = before
        page = caller(
            "getSignaturesForAddress",
            [wallet, config],
        )
        if page is None:
            raise RuntimeError(
                f"getSignaturesForAddress returned null for {wallet}"
            )
        rows = list(page)
        if not rows:
            reached_history_end = True
            break

        stop = False
        for row in rows:
            if row.get("err") is not None:
                continue
            block_time = row.get("blockTime")
            if (
                min_block_time_unix is not None
                and block_time is not None
                and int(block_time) < min_block_time_unix
            ):
                reached_time_floor = True
                stop = True
                break
            signatures.append(dict(row))
            if len(signatures) >= int(max_signatures):
                stop = True
                break

        if reached_time_floor:
            break
        if len(rows) < limit:
            reached_history_end = True
            break
        if stop and len(signatures) >= int(max_signatures):
            break

        before = str(rows[-1].get("signature") or "")
        if not before:
            raise RuntimeError(
                "signature pagination row missing signature"
            )

    bounded = not reached_history_end and not reached_time_floor
    if bounded and not allow_bounded_history:
        raise RuntimeError(
            f"incomplete RPC wallet history for {wallet}: "
            f"max_signatures={max_signatures} reached"
        )

    by_signature: dict[str, dict[str, Any]] = {}
    missing_transaction_count = 0
    for row in signatures:
        signature = str(row.get("signature") or "")
        if not signature:
            continue
        tx = caller(
            "getTransaction",
            [
                signature,
                {
                    "commitment": "finalized",
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": (
                        DEFAULT_MAX_SUPPORTED_TRANSACTION_VERSION
                    ),
                },
            ],
        )
        if tx is None:
            missing_transaction_count += 1
            continue
        tx = dict(tx)
        if tx.get("slot") is None and row.get("slot") is not None:
            tx["slot"] = int(row["slot"])
        if (
            tx.get("blockTime") is None
            and row.get("blockTime") is not None
        ):
            tx["blockTime"] = int(row["blockTime"])
        existing = by_signature.get(signature)
        if existing is not None:
            if _canonical_json(existing) != _canonical_json(tx):
                raise ValueError(
                    f"conflicting RPC payload for signature {signature}"
                )
            continue
        by_signature[signature] = tx

    rows = sorted(
        by_signature.values(),
        key=lambda tx: (
            int(tx.get("blockTime"))
            if tx.get("blockTime") is not None
            else 2**63 - 1,
            int(tx.get("slot") or 0),
            _signature(tx),
        ),
    )
    times = [
        int(tx["blockTime"])
        for tx in rows
        if tx.get("blockTime") is not None
    ]
    return rows, {
        "wallet": wallet,
        "provider": "solana-json-rpc",
        "source_origin": _safe_rpc_origin(rpc_url),
        "signature_count": len(signatures),
        "transaction_count": len(rows),
        "missing_transaction_count": missing_transaction_count,
        "history_complete": bool(reached_history_end),
        "bounded_history": bool(bounded),
        "time_floor_reached": bool(reached_time_floor),
        "min_block_time_unix": min_block_time_unix,
        "first_block_time": min(times) if times else None,
        "last_block_time": max(times) if times else None,
    }


def fetch_complete_wallet_history(
    api_key: str,
    wallet: str,
    *,
    page_limit: int = DEFAULT_PAGE_LIMIT,
    max_pages: int = DEFAULT_MAX_PAGES_PER_WALLET,
    fetch_page: FetchPage | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch complete filtered wallet history or fail closed at a page cap."""
    wallet = validate_solana_address(wallet)
    if not api_key:
        raise ValueError("Helius API key is required")
    if not 1 <= int(page_limit) <= 100:
        raise ValueError("page_limit must be between 1 and 100")
    if int(max_pages) < 1:
        raise ValueError("max_pages must be >= 1")

    fetcher = fetch_page or (
        lambda key, w, limit, token: _fetch_helius_page(
            key,
            w,
            limit,
            token,
        )
    )
    pagination_token: str | None = None
    pages = 0
    by_signature: dict[str, dict[str, Any]] = {}
    missing_signature_count = 0
    complete = False

    while pages < int(max_pages):
        payload = fetcher(
            api_key,
            wallet,
            int(page_limit),
            pagination_token,
        )
        result = payload.get("result") or {}
        data = list(result.get("data") or [])
        pages += 1

        for tx in data:
            signature = _signature(tx)
            if not signature:
                missing_signature_count += 1
                continue
            existing = by_signature.get(signature)
            if existing is not None:
                if _canonical_json(existing) != _canonical_json(tx):
                    raise ValueError(
                        f"conflicting Helius payload for signature {signature}"
                    )
                continue
            by_signature[signature] = dict(tx)

        pagination_token = (
            str(result.get("paginationToken"))
            if result.get("paginationToken")
            else None
        )
        if not pagination_token:
            complete = True
            break

    if not complete:
        raise RuntimeError(
            f"incomplete wallet history for {wallet}: "
            f"max_pages={max_pages} reached before pagination exhausted"
        )

    rows = sorted(
        by_signature.values(),
        key=lambda tx: (
            int(tx.get("blockTime"))
            if tx.get("blockTime") is not None
            else 2**63 - 1,
            int(tx.get("slot") or 0),
            _signature(tx),
        ),
    )
    times = [
        int(tx["blockTime"])
        for tx in rows
        if tx.get("blockTime") is not None
    ]
    report = {
        "wallet": wallet,
        "pages_fetched": pages,
        "transaction_count": len(rows),
        "missing_signature_count": missing_signature_count,
        "history_complete": True,
        "first_block_time": min(times) if times else None,
        "last_block_time": max(times) if times else None,
    }
    return rows, report


def normalize_wallet_histories(
    raw_by_wallet: dict[str, Iterable[dict[str, Any]]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    normalized: dict[str, list[dict[str, Any]]] = {}
    errors: list[dict[str, Any]] = []

    for raw_wallet, transactions in sorted(raw_by_wallet.items()):
        wallet = validate_solana_address(raw_wallet)
        seen: set[str] = set()
        rows: list[dict[str, Any]] = []
        for tx in transactions:
            signature = _signature(tx)
            if not signature:
                errors.append({
                    "wallet": wallet,
                    "signature": None,
                    "error": "MISSING_SIGNATURE",
                })
                continue
            if signature in seen:
                continue
            seen.add(signature)
            try:
                row = normalize_transaction(tx, wallet)
            except Exception as exc:
                errors.append({
                    "wallet": wallet,
                    "signature": signature,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                continue
            if row.get("block_time") is None:
                errors.append({
                    "wallet": wallet,
                    "signature": signature,
                    "error": "MISSING_BLOCK_TIME",
                })
                continue
            rows.append(row)

        normalized[wallet] = sorted(
            rows,
            key=lambda row: (
                int(row["block_time"]),
                int(row.get("slot") or 0),
                str(row.get("signature") or ""),
            ),
        )

    return normalized, {
        "wallet_count": len(normalized),
        "normalized_event_count": sum(
            len(rows) for rows in normalized.values()
        ),
        "normalization_error_count": len(errors),
        "normalization_errors": errors,
    }


def _classification_record(
    wallet: str,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    reconstruction = reconstruct_positions(events, wallet=wallet)
    performance = compute_wallet_performance(reconstruction)
    classification = classify_wallet(performance)
    return build_registry_record(
        wallet=wallet,
        performance=performance,
        classification=classification,
        meme_profile=None,
        explosion_profile=None,
    )


def _snapshot_id(
    universe_fingerprint: str,
    sequence: int,
    *,
    effective_after: int | None,
) -> str:
    suffix = (
        "initial"
        if effective_after is None
        else str(int(effective_after))
    )
    return (
        f"historical-causal-{universe_fingerprint[:12]}-"
        f"{sequence:06d}-{suffix}"
    )


def _decorate_stage8_event(
    normalized: dict[str, Any],
    *,
    record: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    wallet = str(normalized["wallet"])
    signature = str(normalized["signature"])
    return {
        **normalized,
        "stage8_version": STAGE8_VERSION,
        "live_event_id": f"{wallet}:{signature}",
        "idempotency_key": f"{wallet}:{signature}",
        "registry_snapshot_id": snapshot["snapshot_id"],
        "registry_snapshot_fingerprint": (
            snapshot["snapshot_fingerprint"]
        ),
        "registry_record_fingerprint": record["record_fingerprint"],
        "primary_segment": record.get("primary_segment"),
        "qualifying_segments": list(
            record.get("qualifying_segments") or []
        ),
        # Stage-6 evidence is deliberately absent in historical causal
        # replay until an as-of-safe specialty reconstruction exists.
        "meme_hunter_evidence": None,
        "special_labels": {
            **dict(record.get("special_labels") or {}),
            "meme_hunter": "NOT_AVAILABLE_CAUSALLY_STAGE10A",
        },
        "received_at": None,
    }


def build_causal_historical_replay(
    normalized_by_wallet: dict[str, Iterable[dict[str, Any]]],
    *,
    signal_from_unix: int | None = None,
    signal_to_unix: int | None = None,
    universe_effective_after_unix: int | None = None,
) -> dict[str, Any]:
    """Rebuild historical qualification using only information available then.

    A transaction that changes a wallet's qualification is evaluated using the
    status that existed *before* that timestamp. Qualification changes become
    effective only for later timestamps.
    """
    wallets = sorted(
        validate_solana_address(wallet)
        for wallet in normalized_by_wallet
    )
    if not wallets:
        raise ValueError("at least one wallet is required")

    normalized: dict[str, list[dict[str, Any]]] = {
        wallet: sorted(
            [dict(row) for row in normalized_by_wallet[wallet]],
            key=lambda row: (
                int(row["block_time"]),
                int(row.get("slot") or 0),
                str(row.get("signature") or ""),
            ),
        )
        for wallet in wallets
    }

    if universe_effective_after_unix is not None:
        universe_effective_after_unix = int(
            universe_effective_after_unix
        )

    universe_core = {
        "version": STAGE10A_VERSION,
        "wallets": wallets,
        "universe_effective_after_unix": universe_effective_after_unix,
        "population_policy": (
            "wallet identities are eligible for smart-money use only after "
            "their discovery universe is observable; historical "
            "qualification is reconstructed causally"
        ),
    }
    universe_fingerprint = _fingerprint(universe_core)

    current_records = {
        wallet: _classification_record(wallet, [])
        for wallet in wallets
    }
    prefixes: dict[str, list[dict[str, Any]]] = {
        wallet: [] for wallet in wallets
    }

    sequence = 0
    current_snapshot = build_registry_snapshot(
        [current_records[wallet] for wallet in wallets],
        snapshot_id=_snapshot_id(
            universe_fingerprint,
            sequence,
            effective_after=None,
        ),
    )
    registry_snapshots = [current_snapshot]
    transitions: list[dict[str, Any]] = []

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for wallet in wallets:
        for row in normalized[wallet]:
            grouped[int(row["block_time"])].append(row)

    persisted_events: list[dict[str, Any]] = []
    rolling_events: list[dict[str, Any]] = []
    signal_snapshots: list[dict[str, Any]] = []
    eligible_directional_event_count = 0

    if signal_from_unix is not None:
        signal_from_unix = int(signal_from_unix)
    if signal_to_unix is not None:
        signal_to_unix = int(signal_to_unix)
    if universe_effective_after_unix is not None:
        if signal_from_unix is None:
            signal_from_unix = universe_effective_after_unix + 1
        elif signal_from_unix <= universe_effective_after_unix:
            raise ValueError(
                "signal_from_unix must be strictly after "
                "universe_effective_after_unix"
            )
    if (
        signal_from_unix is not None
        and signal_to_unix is not None
        and signal_to_unix < signal_from_unix
    ):
        raise ValueError("signal_to_unix must be >= signal_from_unix")

    persistence_floor = (
        signal_from_unix - ROLLING_SIGNAL_SECONDS
        if signal_from_unix is not None
        else None
    )
    if universe_effective_after_unix is not None:
        persistence_floor = (
            universe_effective_after_unix
            if persistence_floor is None
            else max(
                persistence_floor,
                universe_effective_after_unix,
            )
        )

    for block_time in sorted(grouped):
        rows = sorted(
            grouped[block_time],
            key=lambda row: (
                int(row.get("slot") or 0),
                str(row.get("wallet") or ""),
                str(row.get("signature") or ""),
            ),
        )

        # 1) Consume this timestamp with qualification known strictly before it.
        directional_at_time = False
        for row in rows:
            wallet = str(row["wallet"])
            record = current_records[wallet]
            universe_is_live = (
                universe_effective_after_unix is None
                or block_time > universe_effective_after_unix
            )
            if (
                universe_is_live
                and bool(record.get("live_monitor_eligible"))
                and record.get("registry_status") == "ACTIVE"
            ):
                live_event = _decorate_stage8_event(
                    row,
                    record=record,
                    snapshot=current_snapshot,
                )
                if (
                    persistence_floor is None
                    or block_time > persistence_floor
                ) and (
                    signal_to_unix is None
                    or block_time <= signal_to_unix
                ):
                    persisted_events.append(live_event)

                if (
                    live_event.get("event_type") == "SWAP"
                    and live_event.get("side") in {"BUY", "SELL"}
                    and live_event.get("base_asset")
                ):
                    rolling_events.append(live_event)
                    directional_at_time = True
                    eligible_directional_event_count += 1

        rolling_events = [
            row
            for row in rolling_events
            if int(row["block_time"])
            > block_time - ROLLING_SIGNAL_SECONDS
        ]

        in_signal_range = (
            (signal_from_unix is None or block_time >= signal_from_unix)
            and (signal_to_unix is None or block_time <= signal_to_unix)
        )
        if directional_at_time and in_signal_range:
            signal_snapshot = build_smart_money_signal_snapshot(
                rolling_events,
                as_of=block_time,
            )
            if signal_snapshot["signal_count"]:
                signal_snapshots.append(signal_snapshot)

        # 2) Only after the timestamp is consumed do its trades affect status.
        affected_wallets: set[str] = set()
        for row in rows:
            wallet = str(row["wallet"])
            prefixes[wallet].append(row)
            if (
                row.get("event_type") == "SWAP"
                and row.get("side") == "SELL"
            ):
                affected_wallets.add(wallet)

        changed = False
        for wallet in sorted(affected_wallets):
            previous = current_records[wallet]
            updated = _classification_record(
                wallet,
                prefixes[wallet],
            )
            if (
                updated["record_fingerprint"]
                != previous["record_fingerprint"]
            ):
                current_records[wallet] = updated
                changed = True
                if (
                    previous.get("registry_status")
                    != updated.get("registry_status")
                    or previous.get("primary_segment")
                    != updated.get("primary_segment")
                    or previous.get("qualifying_segments")
                    != updated.get("qualifying_segments")
                ):
                    transitions.append({
                        "wallet": wallet,
                        "effective_strictly_after_unix": block_time,
                        "from_status": previous.get("registry_status"),
                        "to_status": updated.get("registry_status"),
                        "from_primary_segment": previous.get(
                            "primary_segment"
                        ),
                        "to_primary_segment": updated.get(
                            "primary_segment"
                        ),
                        "to_qualifying_segments": list(
                            updated.get("qualifying_segments") or []
                        ),
                    })

        if changed:
            sequence += 1
            current_snapshot = build_registry_snapshot(
                [current_records[wallet] for wallet in wallets],
                snapshot_id=_snapshot_id(
                    universe_fingerprint,
                    sequence,
                    effective_after=block_time,
                ),
            )
            registry_snapshots.append(current_snapshot)

    return {
        "version": STAGE10A_VERSION,
        "universe": {
            **universe_core,
            "universe_fingerprint": universe_fingerprint,
        },
        "methodology": {
            "qualification": "CAUSAL_STAGE3_TO_STAGE7_RECONSTRUCTION",
            "qualification_effective_policy": (
                "STATUS_CHANGES_EFFECTIVE_STRICTLY_AFTER_TRIGGER_TIMESTAMP"
            ),
            "universe_activation_policy": (
                "SMART_MONEY_EVENTS_STRICTLY_AFTER_DISCOVERY_UNIVERSE"
            ),
            "universe_effective_after_unix": (
                universe_effective_after_unix
            ),
            "stage6_historical_policy": (
                "DISABLED_UNTIL_AS_OF_SAFE_SPECIALTY_RECONSTRUCTION"
            ),
            "rule_d_historical_readiness": False,
            "survivorship_note": (
                "wallet-universe selection provenance must be evaluated "
                "separately; current-registry-only universes are research-only"
            ),
        },
        "signal_from_unix": signal_from_unix,
        "signal_to_unix": signal_to_unix,
        "registry_snapshots": registry_snapshots,
        "qualification_transitions": transitions,
        "wallet_events": persisted_events,
        "signal_snapshots": signal_snapshots,
        "summary": {
            "wallet_count": len(wallets),
            "normalized_event_count": sum(
                len(rows) for rows in normalized.values()
            ),
            "causal_registry_snapshot_count": len(
                registry_snapshots
            ),
            "qualification_transition_count": len(transitions),
            "persisted_wallet_event_count": len(persisted_events),
            "eligible_directional_event_count": (
                eligible_directional_event_count
            ),
            "stage9_snapshot_count": len(signal_snapshots),
            "stage9_signal_count": sum(
                int(row.get("signal_count") or 0)
                for row in signal_snapshots
            ),
        },
    }


def collect_real_histories(
    api_key: str,
    wallets: Iterable[str],
    *,
    page_limit: int = DEFAULT_PAGE_LIMIT,
    max_pages_per_wallet: int = DEFAULT_MAX_PAGES_PER_WALLET,
    fetch_page: FetchPage | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    raw_by_wallet: dict[str, list[dict[str, Any]]] = {}
    wallet_reports: list[dict[str, Any]] = []

    for wallet in sorted({
        validate_solana_address(value) for value in wallets
    }):
        rows, report = fetch_complete_wallet_history(
            api_key,
            wallet,
            page_limit=page_limit,
            max_pages=max_pages_per_wallet,
            fetch_page=fetch_page,
        )
        raw_by_wallet[wallet] = rows
        wallet_reports.append(report)

    return raw_by_wallet, {
        "wallet_count": len(raw_by_wallet),
        "wallet_reports": wallet_reports,
        "history_complete_for_all_wallets": all(
            bool(row["history_complete"]) for row in wallet_reports
        ),
        "raw_transaction_rows_across_wallets": sum(
            len(rows) for rows in raw_by_wallet.values()
        ),
    }


def collect_real_histories_rpc(
    rpc_url: str,
    wallets: Iterable[str],
    *,
    max_signatures_per_wallet: int = DEFAULT_RPC_MAX_SIGNATURES,
    page_limit: int = DEFAULT_RPC_PAGE_LIMIT,
    min_block_time_unix: int | None = None,
    allow_bounded_history: bool = False,
    rpc_call: Callable[[str, list[Any]], Any] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    raw_by_wallet: dict[str, list[dict[str, Any]]] = {}
    wallet_reports: list[dict[str, Any]] = []

    for wallet in sorted({
        validate_solana_address(value) for value in wallets
    }):
        rows, report = fetch_wallet_history_rpc(
            rpc_url,
            wallet,
            max_signatures=max_signatures_per_wallet,
            page_limit=page_limit,
            min_block_time_unix=min_block_time_unix,
            allow_bounded_history=allow_bounded_history,
            rpc_call=rpc_call,
        )
        raw_by_wallet[wallet] = rows
        wallet_reports.append(report)

    return raw_by_wallet, {
        "provider": "solana-json-rpc",
        "source_origin": _safe_rpc_origin(rpc_url),
        "wallet_count": len(raw_by_wallet),
        "wallet_reports": wallet_reports,
        "history_complete_for_all_wallets": all(
            bool(row["history_complete"]) for row in wallet_reports
        ),
        "bounded_history_present": any(
            bool(row["bounded_history"]) for row in wallet_reports
        ),
        "raw_transaction_rows_across_wallets": sum(
            len(rows) for rows in raw_by_wallet.values()
        ),
    }


def _refinement_discovery_cutoff(
    refinement_file: str | None,
) -> int | None:
    if not refinement_file:
        return None
    parsed = json.loads(
        Path(refinement_file).read_text(encoding="utf-8")
    )
    refinement = (
        parsed.get("refinement")
        if isinstance(parsed, dict) and "refinement" in parsed
        else parsed
    )
    if not isinstance(refinement, dict):
        raise ValueError(
            "refinement file must contain a Stage-10A-1A object"
        )
    times = [
        int(event["block_time"])
        for record in refinement.get("records") or []
        for event in record.get("events") or []
        if event.get("block_time") is not None
    ]
    return max(times) if times else None


def persist_stage10a_backfill(
    client: SupabaseRestClient,
    *,
    raw_by_wallet: dict[str, Iterable[dict[str, Any]]],
    normalized_by_wallet: dict[str, Iterable[dict[str, Any]]],
    replay: dict[str, Any],
    raw_source: str = "helius_gtfa",
) -> dict[str, Any]:
    raw_rows = client.persist_historical_raw(
        raw_by_wallet,
        source=raw_source,
    )
    normalized_rows = client.persist_normalized_history(
        normalized_by_wallet
    )
    registry_result = client.persist_registry_snapshots(
        replay.get("registry_snapshots") or []
    )
    wallet_event_rows = client.persist_wallet_events(
        replay.get("wallet_events") or []
    )
    signal_result = client.persist_signal_snapshots(
        replay.get("signal_snapshots") or []
    )
    return {
        "historical_raw_rows": raw_rows,
        "normalized_history_rows": normalized_rows,
        **registry_result,
        "wallet_event_rows": wallet_event_rows,
        **signal_result,
    }


def persist_stage10a_replay(
    client: SupabaseRestClient,
    replay: dict[str, Any],
) -> dict[str, Any]:
    """Compatibility helper for callers that already persisted raw evidence."""
    registry_result = client.persist_registry_snapshots(
        replay.get("registry_snapshots") or []
    )
    wallet_event_rows = client.persist_wallet_events(
        replay.get("wallet_events") or []
    )
    signal_result = client.persist_signal_snapshots(
        replay.get("signal_snapshots") or []
    )
    return {
        **registry_result,
        "wallet_event_rows": wallet_event_rows,
        **signal_result,
    }


def _load_wallets(
    explicit: Iterable[str],
    wallets_file: str | None,
    universe_file: str | None = None,
    refinement_file: str | None = None,
) -> list[str]:
    values = list(explicit)

    if refinement_file:
        parsed = json.loads(
            Path(refinement_file).read_text(encoding="utf-8")
        )
        refinement = (
            parsed.get("refinement")
            if isinstance(parsed, dict) and "refinement" in parsed
            else parsed
        )
        if not isinstance(refinement, dict):
            raise ValueError(
                "refinement file must contain a Stage-10A-1A object"
            )
        values.extend(
            wallet_addresses_from_refinement(
                refinement,
                trader_only=True,
            )
        )

    if universe_file:
        parsed = json.loads(
            Path(universe_file).read_text(encoding="utf-8")
        )
        universe = (
            parsed.get("universe")
            if isinstance(parsed, dict) and "universe" in parsed
            else parsed
        )
        if not isinstance(universe, dict):
            raise ValueError("universe file must contain a Stage-10A-0 object")
        values.extend(wallet_addresses_from_universe(universe))

    if wallets_file:
        path = Path(wallets_file)
        raw = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                raise ValueError("wallets JSON must be an array")
            values.extend(str(value) for value in parsed)
        else:
            values.extend(
                line.strip()
                for line in raw.splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )

    wallets = sorted({validate_solana_address(v) for v in values})
    if not wallets:
        raise ValueError("at least one wallet is required")
    return wallets


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
            "Stage 10A causal historical wallet backfill into Supabase"
        )
    )
    parser.add_argument(
        "--wallet",
        action="append",
        default=[],
        help="Wallet address; repeatable",
    )
    parser.add_argument(
        "--wallets-file",
        default=None,
        help="JSON array or newline-delimited wallet addresses",
    )
    parser.add_argument(
        "--universe-file",
        default=None,
        help=(
            "Stage-10A-0 discovery artifact. Manual/raw universe input is "
            "primarily for bootstrap/debugging."
        ),
    )
    parser.add_argument(
        "--refinement-file",
        default=None,
        help=(
            "Stage-10A-1A refinement artifact. Preferred production input; "
            "only TRADER_CANDIDATE wallets are backfilled."
        ),
    )
    parser.add_argument(
        "--history-source",
        choices=["rpc", "helius"],
        default="rpc",
        help="Historical transaction provider.",
    )
    parser.add_argument(
        "--rpc-url",
        default=(
            os.environ.get("SOLANA_RPC_URL")
            or DEFAULT_SOLANA_RPC_URL
        ),
    )
    parser.add_argument(
        "--rpc-max-signatures-per-wallet",
        type=int,
        default=DEFAULT_RPC_MAX_SIGNATURES,
    )
    parser.add_argument(
        "--rpc-page-limit",
        type=int,
        default=DEFAULT_RPC_PAGE_LIMIT,
    )
    parser.add_argument(
        "--history-min-block-time-unix",
        type=int,
        default=None,
        help=(
            "Optional lower time floor for RPC history. Reaching this floor "
            "is explicit bounded coverage, not full lifetime history."
        ),
    )
    parser.add_argument(
        "--allow-bounded-history",
        action="store_true",
        help=(
            "Allow explicitly incomplete RPC history for smoke/probe use. "
            "Do not use bounded history as full qualification evidence."
        ),
    )
    parser.add_argument(
        "--signal-from-unix",
        type=int,
        default=None,
        help=(
            "Earliest timestamp for emitted Stage-9 snapshots. When a "
            "refinement file is supplied, defaults to strictly after the "
            "discovery cutoff."
        ),
    )
    parser.add_argument(
        "--signal-to-unix",
        type=int,
        default=None,
        help="Latest timestamp for emitted Stage-9 snapshots",
    )
    parser.add_argument(
        "--page-limit",
        type=int,
        default=DEFAULT_PAGE_LIMIT,
    )
    parser.add_argument(
        "--max-pages-per-wallet",
        type=int,
        default=DEFAULT_MAX_PAGES_PER_WALLET,
    )
    parser.add_argument(
        "--max-wallets",
        type=int,
        default=None,
        help="Optional deterministic wallet cap for smoke/probe cohorts.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build causal replay but do not write Supabase",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Write a local audit report JSON",
    )
    args = parser.parse_args()

    wallets = _load_wallets(
        args.wallet,
        args.wallets_file,
        args.universe_file,
        args.refinement_file,
    )
    if args.max_wallets is not None:
        if int(args.max_wallets) < 1:
            raise SystemExit("--max-wallets must be >= 1")
        wallets = wallets[: int(args.max_wallets)]

    discovery_cutoff = _refinement_discovery_cutoff(
        args.refinement_file
    )
    signal_from = args.signal_from_unix
    if signal_from is None and discovery_cutoff is not None:
        signal_from = discovery_cutoff + 1

    raw_source = "helius_gtfa"
    if args.history_source == "helius":
        api_key = os.environ.get("HELIUS_API_KEY")
        if not api_key:
            raise SystemExit(
                "HELIUS_API_KEY is required for --history-source helius"
            )
        raw_by_wallet, fetch_report = collect_real_histories(
            api_key,
            wallets,
            page_limit=args.page_limit,
            max_pages_per_wallet=args.max_pages_per_wallet,
        )
    else:
        raw_source = "solana_json_rpc"
        raw_by_wallet, fetch_report = collect_real_histories_rpc(
            args.rpc_url,
            wallets,
            max_signatures_per_wallet=(
                args.rpc_max_signatures_per_wallet
            ),
            page_limit=args.rpc_page_limit,
            min_block_time_unix=args.history_min_block_time_unix,
            allow_bounded_history=args.allow_bounded_history,
        )

    normalized, normalize_report = normalize_wallet_histories(
        raw_by_wallet
    )

    replay = build_causal_historical_replay(
        normalized,
        signal_from_unix=signal_from,
        signal_to_unix=args.signal_to_unix,
        universe_effective_after_unix=discovery_cutoff,
    )

    bounded_history = bool(
        fetch_report.get("bounded_history_present")
    )
    if bounded_history:
        # A bounded history is valid for transport/normalization smoke work,
        # but it must not be represented as qualification-grade full history.
        replay["methodology"]["qualification_grade_history"] = False
        replay["methodology"]["bounded_history_warning"] = (
            "history is explicitly incomplete; do not interpret current "
            "classification as full-lifetime wallet qualification"
        )
    else:
        replay["methodology"]["qualification_grade_history"] = bool(
            fetch_report.get("history_complete_for_all_wallets")
        )

    persistence = None
    if not args.dry_run:
        if bounded_history:
            raise SystemExit(
                "bounded history cannot be persisted as production "
                "qualification evidence; rerun without --allow-bounded-history"
            )
        client = SupabaseRestClient.from_env()
        persistence = persist_stage10a_backfill(
            client,
            raw_by_wallet=raw_by_wallet,
            normalized_by_wallet=normalized,
            replay=replay,
            raw_source=raw_source,
        )

    report = {
        "version": STAGE10A_VERSION,
        "source_kind": "REAL",
        "history_source": args.history_source,
        "raw_source": raw_source,
        "wallet_selection": {
            "wallet_count": len(wallets),
            "refinement_file": bool(args.refinement_file),
            "max_wallets": args.max_wallets,
            "discovery_cutoff_unix": discovery_cutoff,
        },
        "fetch": fetch_report,
        "normalization": normalize_report,
        "causal_replay": replay,
        "supabase_persistence": persistence,
        "dry_run": bool(args.dry_run),
        "edge_claim": None,
        "production_rule_selected": False,
    }
    report["report_fingerprint"] = _fingerprint(report)
    _write_json(args.out, report)
    print(json.dumps({
        "history_source": args.history_source,
        "wallet_count": len(wallets),
        "raw_transaction_rows": fetch_report[
            "raw_transaction_rows_across_wallets"
        ],
        "normalized_event_count": normalize_report[
            "normalized_event_count"
        ],
        "history_complete_for_all_wallets": fetch_report[
            "history_complete_for_all_wallets"
        ],
        "bounded_history_present": bool(
            fetch_report.get("bounded_history_present")
        ),
        "registry_snapshot_count": len(
            replay.get("registry_snapshots") or []
        ),
        "transition_count": len(replay.get("transitions") or []),
        "wallet_event_count": len(
            replay.get("wallet_events") or []
        ),
        "signal_snapshot_count": len(
            replay.get("signal_snapshots") or []
        ),
        "qualification_grade_history": replay["methodology"].get(
            "qualification_grade_history"
        ),
        "persisted": not args.dry_run,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
