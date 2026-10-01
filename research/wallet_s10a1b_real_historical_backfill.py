from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from research.wallet_s1_data_foundation import (
    build_helius_gtfa_payload,
    validate_solana_address,
)
from research.wallet_s10a0_wallet_universe_discovery import (
    DEFAULT_MAX_SUPPORTED_TRANSACTION_VERSION,
    DEFAULT_SOLANA_RPC_URL,
    _safe_rpc_origin,
)
from research.wallet_s10a1_candidate_refinement import (
    verify_candidate_refinement,
    wallet_addresses_from_refinement,
)
from research.wallet_s10a_historical_backfill import (
    build_causal_historical_replay,
    collect_real_histories,
    normalize_wallet_histories,
    persist_stage10a_backfill,
)
from research.wallet_supabase_adapter import SupabaseRestClient

STAGE10A1B_VERSION = "wallet-s10a1b-v1"
DEFAULT_SIGNATURE_PAGE_LIMIT = 1000
DEFAULT_MAX_SIGNATURE_PAGES_PER_WALLET = 1000
DEFAULT_TRANSACTION_BATCH_SIZE = 20
DEFAULT_RPC_ATTEMPTS = 5

RpcTransport = Callable[
    [str, str, dict[str, str], bytes],
    tuple[int, bytes],
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


def _default_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes,
) -> tuple[int, bytes]:
    request = Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )
    with urlopen(request, timeout=60) as response:
        return int(response.status), response.read()


def _safe_indexed_origin(url: str) -> str:
    """Return a credential-free provider origin for provenance/reporting."""
    parts = urlsplit(str(url or "").strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError(
            "indexed RPC URL must be an absolute HTTP(S) URL"
        )
    return urlunsplit((parts.scheme, parts.netloc, "/", "", ""))


def _fetch_indexed_gtfa_page(
    endpoint: str,
    wallet: str,
    limit: int,
    pagination_token: str | None,
    *,
    attempts: int = 8,
    transport: RpcTransport | None = None,
    request_delay_seconds: float = 0.0,
    history_as_of_unix: int | None = None,
    resume_before_signature: str | None = None,
    sort_order: str = "desc",
) -> dict[str, Any]:
    """Fetch one provider-neutral getTransactionsForAddress page.

    Helius, Alchemy, QuickNode, or any compatible indexed Solana RPC may
    supply the endpoint. Credentials may live in the URL; they are never
    copied into reports or evidence.
    """
    _safe_indexed_origin(endpoint)
    if int(attempts) < 1:
        raise ValueError("attempts must be >= 1")
    if float(request_delay_seconds) < 0:
        raise ValueError("request_delay_seconds must be >= 0")

    payload = build_helius_gtfa_payload(
        wallet,
        limit=int(limit),
        pagination_token=pagination_token,
        sort_order=str(sort_order),
    )
    # Versioned Solana transactions require the client to opt in.
    # Alchemy returns -32015 when this field is omitted.
    payload["params"][1]["maxSupportedTransactionVersion"] = (
        DEFAULT_MAX_SUPPORTED_TRANSACTION_VERSION
    )
    filters = payload["params"][1]["filters"]
    if history_as_of_unix is not None:
        filters["blockTime"] = {"lte": int(history_as_of_unix)}
    if resume_before_signature:
        filters["signature"] = {
            "lt": str(resume_before_signature),
        }
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    sender = transport or _default_transport
    last_error: Exception | None = None

    for attempt in range(int(attempts)):
        try:
            if float(request_delay_seconds) > 0:
                time.sleep(float(request_delay_seconds))
            status, raw = sender(
                "POST",
                endpoint,
                headers,
                body,
            )
            if not 200 <= int(status) < 300:
                raise RuntimeError(
                    f"indexed RPC HTTP status {status}: "
                    f"{raw.decode('utf-8', errors='replace')}"
                )
            parsed = json.loads(raw.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise TypeError(
                    "indexed RPC response must be an object"
                )
            if parsed.get("error") is not None:
                raise RuntimeError(
                    f"indexed RPC error: {parsed['error']}"
                )
            result = parsed.get("result")
            if result is None:
                raise RuntimeError(
                    "indexed getTransactionsForAddress returned null"
                )
            if not isinstance(result, dict):
                raise TypeError(
                    "indexed getTransactionsForAddress result "
                    "must be an object"
                )
            return parsed
        except (
            HTTPError,
            URLError,
            TimeoutError,
            RuntimeError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            last_error = exc
            if attempt == int(attempts) - 1:
                break
            time.sleep(min(2 ** attempt, 64))

    raise RuntimeError(
        "indexed getTransactionsForAddress failed after "
        f"{attempts} attempts: {last_error}"
    )


class SolanaWalletHistoryRpc:
    """Provider-neutral finalized Solana wallet-history reader."""

    def __init__(
        self,
        rpc_url: str,
        *,
        source_label: str = "solana-json-rpc",
        transport: RpcTransport | None = None,
        attempts: int = DEFAULT_RPC_ATTEMPTS,
        max_supported_transaction_version: int = (
            DEFAULT_MAX_SUPPORTED_TRANSACTION_VERSION
        ),
        min_request_interval_seconds: float = 0.0,
    ):
        rpc_url = str(rpc_url or "").strip()
        _safe_rpc_origin(rpc_url)
        if not source_label.strip():
            raise ValueError("source_label is required")
        if int(attempts) < 1:
            raise ValueError("attempts must be >= 1")
        if int(max_supported_transaction_version) < 0:
            raise ValueError(
                "max_supported_transaction_version must be >= 0"
            )
        if float(min_request_interval_seconds) < 0:
            raise ValueError(
                "min_request_interval_seconds must be >= 0"
            )

        self.rpc_url = rpc_url
        self.source_label = source_label.strip()
        self.transport = transport or _default_transport
        self.attempts = int(attempts)
        self.max_supported_transaction_version = int(
            max_supported_transaction_version
        )
        self.min_request_interval_seconds = float(
            min_request_interval_seconds
        )
        self._last_request_started_at: float | None = None
        self._request_id = 0

    def _pace_request(self) -> None:
        interval = self.min_request_interval_seconds
        if interval <= 0:
            return
        now = time.monotonic()
        if self._last_request_started_at is not None:
            remaining = interval - (
                now - self._last_request_started_at
            )
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_started_at = time.monotonic()

    @property
    def public_origin(self) -> str:
        return _safe_rpc_origin(self.rpc_url)

    def _post(
        self,
        payload: Any,
        *,
        attempts: int | None = None,
    ) -> Any:
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        last_error: Exception | None = None
        attempt_count = self.attempts if attempts is None else int(attempts)
        if attempt_count < 1:
            raise ValueError("attempts must be >= 1")

        for attempt in range(attempt_count):
            try:
                self._pace_request()
                status, raw = self.transport(
                    "POST",
                    self.rpc_url,
                    headers,
                    body,
                )
                if not 200 <= int(status) < 300:
                    raise RuntimeError(
                        f"RPC HTTP status {status}: "
                        f"{raw.decode('utf-8', errors='replace')}"
                    )
                return json.loads(raw.decode("utf-8"))
            except (
                HTTPError,
                URLError,
                TimeoutError,
                RuntimeError,
                json.JSONDecodeError,
            ) as exc:
                last_error = exc
                if attempt == attempt_count - 1:
                    break
                time.sleep(min(2 ** attempt, 8))

        raise RuntimeError(
            f"RPC request failed after {attempt_count} attempts: "
            f"{last_error}"
        )

    def rpc(self, method: str, params: list[Any]) -> Any:
        last_error: Any = None
        for attempt in range(self.attempts):
            self._request_id += 1
            payload = {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": method,
                "params": params,
            }
            try:
                # Keep transport attempts at one here. This method owns the
                # retry/backoff policy, avoiding nested exponential retries
                # when public RPC returns HTTP or JSON-RPC 429.
                response = self._post(payload, attempts=1)
            except RuntimeError as exc:
                last_error = str(exc)
                if attempt < self.attempts - 1:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                raise RuntimeError(
                    f"RPC {method} failed after "
                    f"{self.attempts} attempts: {last_error}"
                ) from exc

            if not isinstance(response, dict):
                raise TypeError(
                    f"RPC {method} response must be an object"
                )
            error = response.get("error")
            if error is None:
                return response.get("result")
            last_error = dict(error) if isinstance(error, dict) else {
                "message": str(error)
            }
            code = last_error.get("code")
            if code == 429 and attempt < self.attempts - 1:
                time.sleep(min(2 ** attempt, 8))
                continue
            raise RuntimeError(
                f"RPC {method} error: {last_error}"
            )
        raise RuntimeError(
            f"RPC {method} rate-limited after {self.attempts} attempts: "
            f"{last_error}"
        )

    def rpc_batch(
        self,
        calls: list[tuple[str, list[Any]]],
    ) -> list[Any]:
        if not calls:
            return []

        payload: list[dict[str, Any]] = []
        ids: list[int] = []
        for method, params in calls:
            self._request_id += 1
            request_id = self._request_id
            ids.append(request_id)
            payload.append({
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            })

        # Batch requests are an optimization only. Public Solana RPC
        # endpoints may reject bursts with HTTP 429 even while scalar calls
        # remain available. Fail the batch attempt immediately so the caller
        # can fall back to the scalar retry/backoff path without paying the
        # full batch retry delay first.
        response = self._post(payload, attempts=1)
        if not isinstance(response, list):
            raise TypeError("RPC batch response must be an array")

        by_id: dict[int, dict[str, Any]] = {}
        for item in response:
            if not isinstance(item, dict) or item.get("id") is None:
                raise TypeError("invalid RPC batch response item")
            by_id[int(item["id"])] = item

        results: list[Any] = []
        for request_id in ids:
            item = by_id.get(request_id)
            if item is None:
                raise RuntimeError(
                    f"RPC batch missing response id {request_id}"
                )
            if item.get("error") is not None:
                raise RuntimeError(
                    f"RPC batch error: {item['error']}"
                )
            results.append(item.get("result"))
        return results

    def first_available_block(self) -> int:
        result = self.rpc("getFirstAvailableBlock", [])
        if result is None:
            raise RuntimeError("getFirstAvailableBlock returned null")
        return int(result)

    def signatures_page(
        self,
        wallet: str,
        *,
        limit: int,
        before: str | None,
    ) -> list[dict[str, Any]]:
        config: dict[str, Any] = {
            "commitment": "finalized",
            "limit": int(limit),
        }
        if before:
            config["before"] = before
        result = self.rpc(
            "getSignaturesForAddress",
            [validate_solana_address(wallet), config],
        )
        if result is None:
            raise RuntimeError(
                "getSignaturesForAddress returned null"
            )
        if not isinstance(result, list):
            raise TypeError(
                "getSignaturesForAddress result must be an array"
            )
        return [dict(row) for row in result]

    def transactions(
        self,
        signatures: Iterable[str],
        *,
        batch_size: int = DEFAULT_TRANSACTION_BATCH_SIZE,
    ) -> dict[str, dict[str, Any]]:
        ordered = list(dict.fromkeys(
            str(signature)
            for signature in signatures
            if str(signature)
        ))
        if int(batch_size) < 1:
            raise ValueError("batch_size must be >= 1")

        output: dict[str, dict[str, Any]] = {}
        config = {
            "commitment": "finalized",
            "encoding": "jsonParsed",
            "maxSupportedTransactionVersion": (
                self.max_supported_transaction_version
            ),
        }

        def store(signature: str, result: Any) -> None:
            if result is None:
                raise RuntimeError(
                    "getTransaction returned null for "
                    f"{signature}; provider history is incomplete"
                )
            if not isinstance(result, dict):
                raise TypeError(
                    f"invalid getTransaction result for {signature}"
                )
            transaction = result.get("transaction") or {}
            signatures_result = transaction.get("signatures") or []
            if (
                not signatures_result
                or str(signatures_result[0]) != signature
            ):
                raise ValueError(
                    f"transaction signature mismatch for {signature}"
                )
            output[signature] = dict(result)

        for start in range(0, len(ordered), int(batch_size)):
            batch = ordered[start:start + int(batch_size)]

            if len(batch) == 1:
                signature = batch[0]
                result = self.rpc(
                    "getTransaction",
                    [signature, config],
                )
                store(signature, result)
                continue

            try:
                results = self.rpc_batch([
                    ("getTransaction", [signature, config])
                    for signature in batch
                ])
                for signature, result in zip(batch, results):
                    store(signature, result)
            except RuntimeError as exc:
                message = str(exc)
                if "429" not in message and "Too many requests" not in message:
                    raise
                # Public Solana RPC commonly rejects bursty getTransaction
                # batches even when ordinary single requests are accepted.
                # Fall back to the rate-limit-aware scalar RPC path.
                for signature in batch:
                    result = self.rpc(
                        "getTransaction",
                        [signature, config],
                    )
                    store(signature, result)

        return output


def build_refinement_subset(
    refinement: dict[str, Any],
    wallets: Iterable[str],
) -> dict[str, Any]:
    """Create a deterministic trader-only refinement shard/subset."""
    verify_candidate_refinement(refinement)
    wanted = {
        validate_solana_address(wallet)
        for wallet in wallets
    }
    if not wanted:
        raise ValueError("refinement subset requires at least one wallet")

    source_records = {
        str(row["wallet"]): row
        for row in refinement.get("records") or []
        if bool(row.get("trader_candidate"))
    }
    missing = sorted(wanted - set(source_records))
    if missing:
        raise ValueError(
            "refinement subset contains non-trader or unknown wallet: "
            + ",".join(missing)
        )

    records = [
        dict(source_records[wallet])
        for wallet in sorted(wanted)
    ]
    subset_core = {
        "version": refinement["version"],
        "chain": refinement.get("chain") or "solana",
        "source_universe_fingerprint": refinement[
            "source_universe_fingerprint"
        ],
        "parent_refinement_fingerprint": refinement[
            "refinement_fingerprint"
        ],
        "source": dict(refinement.get("source") or {}),
        "activity_candidate_wallet_count": len(records),
        "trader_candidate_wallet_count": len(records),
        "non_trader_activity_wallet_count": 0,
        "meme_buy_candidate_wallet_count": sum(
            int(bool(row.get("meme_buy_candidate")))
            for row in records
        ),
        "trader_event_count": sum(
            int(row.get("trader_event_count") or 0)
            for row in records
        ),
        "buy_event_count": sum(
            int(row.get("buy_event_count") or 0)
            for row in records
        ),
        "sell_event_count": sum(
            int(row.get("sell_event_count") or 0)
            for row in records
        ),
        "records": records,
        "contract": {
            **dict(refinement.get("contract") or {}),
            "population_scope": "TRADER_CANDIDATE_SUBSET",
        },
    }
    return {
        **subset_core,
        "refinement_fingerprint": _fingerprint(subset_core),
    }


def build_refinement_shard(
    refinement: dict[str, Any],
    *,
    shard_index: int,
    shard_count: int,
) -> dict[str, Any]:
    verify_candidate_refinement(refinement)
    shard_index = int(shard_index)
    shard_count = int(shard_count)
    if shard_count < 1:
        raise ValueError("shard_count must be >= 1")
    if shard_index < 0 or shard_index >= shard_count:
        raise ValueError(
            "shard_index must satisfy 0 <= shard_index < shard_count"
        )

    wallets = wallet_addresses_from_refinement(
        refinement,
        trader_only=True,
    )
    selected = [
        wallet
        for index, wallet in enumerate(wallets)
        if index % shard_count == shard_index
    ]
    if not selected:
        raise ValueError(
            f"refinement shard {shard_index}/{shard_count} is empty"
        )
    return build_refinement_subset(refinement, selected)


def refinement_effective_after_unix(
    refinement: dict[str, Any],
) -> int:
    verify_candidate_refinement(refinement)
    times = [
        int(event["block_time"])
        for record in refinement.get("records") or []
        for event in record.get("events") or []
        if event.get("block_time") is not None
    ]
    if not times:
        raise ValueError(
            "refinement has no event timestamps for causal activation"
        )
    return max(times)


def _fetch_wallet_signature_index(
    source: SolanaWalletHistoryRpc,
    wallet: str,
    *,
    as_of_unix: int,
    page_limit: int,
    max_pages: int,
    fail_on_incomplete: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    wallet = validate_solana_address(wallet)
    if not 1 <= int(page_limit) <= 1000:
        raise ValueError("page_limit must be between 1 and 1000")
    if int(max_pages) < 1:
        raise ValueError("max_pages must be >= 1")

    before: str | None = None
    pages = 0
    exhausted = False
    included: dict[str, dict[str, Any]] = {}
    missing_block_time = 0

    while pages < int(max_pages):
        rows = source.signatures_page(
            wallet,
            limit=int(page_limit),
            before=before,
        )
        pages += 1
        if not rows:
            exhausted = True
            break

        last_signature = str(rows[-1].get("signature") or "")
        if not last_signature:
            raise ValueError(
                "signature pagination row missing signature"
            )
        if before is not None and last_signature == before:
            raise RuntimeError(
                f"signature pagination cursor did not advance for {wallet}"
            )

        for row in rows:
            signature = str(row.get("signature") or "")
            if not signature:
                raise ValueError(
                    "getSignaturesForAddress row missing signature"
                )
            block_time = row.get("blockTime")
            if block_time is None:
                missing_block_time += 1
                continue
            if int(block_time) <= int(as_of_unix):
                existing = included.get(signature)
                if existing is not None:
                    if _canonical_json(existing) != _canonical_json(row):
                        raise ValueError(
                            f"conflicting signature row {signature}"
                        )
                    continue
                included[signature] = dict(row)

        before = last_signature
        if len(rows) < int(page_limit):
            exhausted = True
            break

    if not exhausted and fail_on_incomplete:
        raise RuntimeError(
            f"incomplete signature history for {wallet}: "
            f"max_pages={max_pages} reached before pagination exhausted"
        )

    ordered = sorted(
        included.values(),
        key=lambda row: (
            int(row.get("blockTime") or 0),
            int(row.get("slot") or 0),
            str(row.get("signature") or ""),
        ),
    )
    times = [
        int(row["blockTime"])
        for row in ordered
        if row.get("blockTime") is not None
    ]
    return ordered, {
        "wallet": wallet,
        "signature_pages_fetched": pages,
        "signature_count_as_of": len(ordered),
        "missing_block_time_signature_count": missing_block_time,
        "signature_pagination_exhausted": bool(exhausted),
        "first_signature_block_time": min(times) if times else None,
        "last_signature_block_time": max(times) if times else None,
    }


def plan_solana_rpc_history_capacity(
    source: SolanaWalletHistoryRpc,
    wallets: Iterable[str],
    *,
    as_of_unix: int,
    signature_page_limit: int = DEFAULT_SIGNATURE_PAGE_LIMIT,
    probe_max_pages_per_wallet: int = 5,
) -> dict[str, Any]:
    """Partition wallets by whether signature history exhausts within a cap.

    This is an execution-capacity classification only. HIGH_VOLUME wallets
    remain in the candidate universe and are never treated as unqualified.
    """
    wallet_list = sorted({
        validate_solana_address(wallet)
        for wallet in wallets
    })
    if not wallet_list:
        raise ValueError("at least one wallet is required")

    first_available_slot = source.first_available_block()
    archive_from_genesis = first_available_slot == 0
    reports: list[dict[str, Any]] = []
    standard_wallets: list[str] = []
    high_volume_wallets: list[str] = []

    for wallet in wallet_list:
        rows, report = _fetch_wallet_signature_index(
            source,
            wallet,
            as_of_unix=int(as_of_unix),
            page_limit=int(signature_page_limit),
            max_pages=int(probe_max_pages_per_wallet),
            fail_on_incomplete=False,
        )
        report["probed_signature_count"] = len(rows)
        if bool(report["signature_pagination_exhausted"]):
            report["capacity_lane"] = "STANDARD"
            standard_wallets.append(wallet)
        else:
            report["capacity_lane"] = "HIGH_VOLUME"
            high_volume_wallets.append(wallet)
        reports.append(report)

    core = {
        "version": STAGE10A1B_VERSION,
        "provider": "solana_json_rpc",
        "source_label": source.source_label,
        "source_origin": source.public_origin,
        "history_as_of_unix": int(as_of_unix),
        "provider_first_available_slot": first_available_slot,
        "provider_archive_from_genesis": archive_from_genesis,
        "probe_signature_page_limit": int(signature_page_limit),
        "probe_max_pages_per_wallet": int(
            probe_max_pages_per_wallet
        ),
        "wallet_count": len(wallet_list),
        "standard_wallet_count": len(standard_wallets),
        "high_volume_wallet_count": len(high_volume_wallets),
        "standard_wallets": standard_wallets,
        "high_volume_wallets": high_volume_wallets,
        "wallet_reports": reports,
        "policy": {
            "quality_filter": None,
            "high_volume_is_unqualified": False,
            "high_volume_action": (
                "REQUIRES_HIGH_CAPACITY_OR_INDEXED_HISTORY_PROVIDER"
            ),
        },
    }
    return {
        **core,
        "plan_fingerprint": _fingerprint(core),
    }


def collect_solana_rpc_histories(
    source: SolanaWalletHistoryRpc,
    wallets: Iterable[str],
    *,
    as_of_unix: int,
    signature_page_limit: int = DEFAULT_SIGNATURE_PAGE_LIMIT,
    max_signature_pages_per_wallet: int = (
        DEFAULT_MAX_SIGNATURE_PAGES_PER_WALLET
    ),
    transaction_batch_size: int = DEFAULT_TRANSACTION_BATCH_SIZE,
    require_archive_from_genesis: bool = True,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    as_of_unix = int(as_of_unix)
    wallet_list = sorted({
        validate_solana_address(wallet)
        for wallet in wallets
    })
    if not wallet_list:
        raise ValueError("at least one wallet is required")

    first_available_slot = source.first_available_block()
    archive_from_genesis = first_available_slot == 0
    if require_archive_from_genesis and not archive_from_genesis:
        raise RuntimeError(
            "qualification-grade historical backfill requires a "
            "provider whose getFirstAvailableBlock is 0; "
            f"provider first available slot is {first_available_slot}"
        )

    signature_rows_by_wallet: dict[str, list[dict[str, Any]]] = {}
    wallet_reports: list[dict[str, Any]] = []
    all_signatures: list[str] = []

    for wallet in wallet_list:
        rows, report = _fetch_wallet_signature_index(
            source,
            wallet,
            as_of_unix=as_of_unix,
            page_limit=signature_page_limit,
            max_pages=max_signature_pages_per_wallet,
        )
        signature_rows_by_wallet[wallet] = rows
        wallet_reports.append(report)
        all_signatures.extend(
            str(row["signature"]) for row in rows
        )

    unique_signatures = list(dict.fromkeys(all_signatures))
    tx_by_signature = source.transactions(
        unique_signatures,
        batch_size=transaction_batch_size,
    )

    raw_by_wallet: dict[str, list[dict[str, Any]]] = {}
    for wallet in wallet_list:
        txs: list[dict[str, Any]] = []
        for signature_row in signature_rows_by_wallet[wallet]:
            signature = str(signature_row["signature"])
            tx = tx_by_signature.get(signature)
            if tx is None:
                raise RuntimeError(
                    f"missing fetched transaction {signature}"
                )
            block_time = tx.get("blockTime")
            if block_time is None:
                raise RuntimeError(
                    f"transaction {signature} has no blockTime"
                )
            if int(block_time) > as_of_unix:
                raise RuntimeError(
                    f"transaction {signature} exceeds as-of cutoff"
                )
            txs.append(dict(tx))

        raw_by_wallet[wallet] = sorted(
            txs,
            key=lambda tx: (
                int(tx.get("blockTime") or 0),
                int(tx.get("slot") or 0),
                str(
                    (tx.get("transaction") or {})
                    .get("signatures", [""])[0]
                ),
            ),
        )

    for report in wallet_reports:
        wallet = str(report["wallet"])
        report["transaction_count_as_of"] = len(
            raw_by_wallet[wallet]
        )
        report["history_complete"] = (
            bool(report["signature_pagination_exhausted"])
            and (
                archive_from_genesis
                or not require_archive_from_genesis
            )
        )

    report = {
        "provider": "solana_json_rpc",
        "source_label": source.source_label,
        "source_origin": source.public_origin,
        "history_as_of_unix": as_of_unix,
        "provider_first_available_slot": first_available_slot,
        "provider_archive_from_genesis": archive_from_genesis,
        "qualification_grade": (
            archive_from_genesis
            and all(
                bool(row["signature_pagination_exhausted"])
                for row in wallet_reports
            )
        ),
        "wallet_count": len(wallet_list),
        "wallet_reports": wallet_reports,
        "unique_signature_count": len(unique_signatures),
        "raw_transaction_rows_across_wallets": sum(
            len(rows) for rows in raw_by_wallet.values()
        ),
    }
    return raw_by_wallet, report


def collect_helius_histories_as_of(
    api_key: str,
    wallets: Iterable[str],
    *,
    as_of_unix: int,
    page_limit: int = 100,
    max_pages_per_wallet: int = 1000,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    raw, report = collect_real_histories(
        api_key,
        wallets,
        page_limit=page_limit,
        max_pages_per_wallet=max_pages_per_wallet,
    )
    filtered: dict[str, list[dict[str, Any]]] = {}
    excluded_future = 0

    for wallet, rows in sorted(raw.items()):
        kept: list[dict[str, Any]] = []
        for tx in rows:
            block_time = tx.get("blockTime")
            if block_time is None:
                continue
            if int(block_time) <= int(as_of_unix):
                kept.append(dict(tx))
            else:
                excluded_future += 1
        filtered[wallet] = kept

    return filtered, {
        **report,
        "provider": "helius_gtfa",
        "history_as_of_unix": int(as_of_unix),
        "excluded_post_as_of_transaction_count": excluded_future,
        "qualification_grade": bool(
            report.get("history_complete_for_all_wallets")
        ),
    }


def collect_indexed_histories_as_of(
    endpoint: str,
    source_label: str,
    wallets: Iterable[str],
    *,
    as_of_unix: int,
    page_limit: int = 100,
    max_pages_per_wallet: int = 1000,
    min_request_interval_seconds: float = 0.0,
    fetch_page: Callable[
        [str, str, int, str | None],
        dict[str, Any],
    ] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Collect complete gTFA history from a compatible indexed provider."""
    endpoint = str(endpoint or "").strip()
    source_label = str(source_label or "").strip()
    if not endpoint:
        raise ValueError("indexed RPC endpoint is required")
    if not source_label:
        raise ValueError("indexed RPC source label is required")
    public_origin = _safe_indexed_origin(endpoint)

    if fetch_page is None:
        def provider_fetch_page(
            _credential: str,
            wallet: str,
            limit: int,
            pagination_token: str | None,
        ) -> dict[str, Any]:
            return _fetch_indexed_gtfa_page(
                endpoint,
                wallet,
                limit,
                pagination_token,
                request_delay_seconds=min_request_interval_seconds,
            )
    else:
        provider_fetch_page = fetch_page

    raw, report = collect_real_histories(
        "indexed-rpc",
        wallets,
        page_limit=page_limit,
        max_pages_per_wallet=max_pages_per_wallet,
        fetch_page=provider_fetch_page,
    )

    filtered: dict[str, list[dict[str, Any]]] = {}
    excluded_future = 0
    for wallet, rows in sorted(raw.items()):
        kept: list[dict[str, Any]] = []
        for tx in rows:
            block_time = tx.get("blockTime")
            if block_time is None:
                continue
            if int(block_time) <= int(as_of_unix):
                kept.append(dict(tx))
            else:
                excluded_future += 1
        filtered[wallet] = kept

    return filtered, {
        **report,
        "provider": "indexed_gtfa",
        "source_label": source_label,
        "source_origin": public_origin,
        "history_as_of_unix": int(as_of_unix),
        "excluded_post_as_of_transaction_count": excluded_future,
        "qualification_grade": bool(
            report.get("history_complete_for_all_wallets")
        ),
    }


def _load_refinement(path: str | Path) -> dict[str, Any]:
    parsed = json.loads(Path(path).read_text(encoding="utf-8"))
    refinement = (
        parsed.get("refinement")
        if isinstance(parsed, dict) and "refinement" in parsed
        else parsed
    )
    if not isinstance(refinement, dict):
        raise ValueError(
            "refinement file must contain a Stage-10A-1A object"
        )
    verify_candidate_refinement(refinement)
    return refinement


def _validate_backfill_wallet_coverage(
    refinement: dict[str, Any],
    raw_by_wallet: dict[str, Iterable[dict[str, Any]]],
) -> None:
    expected_wallets = set(
        wallet_addresses_from_refinement(
            refinement,
            trader_only=True,
        )
    )
    actual_wallets = {
        validate_solana_address(wallet)
        for wallet in raw_by_wallet
    }
    if actual_wallets != expected_wallets:
        missing = sorted(expected_wallets - actual_wallets)
        extra = sorted(actual_wallets - expected_wallets)
        raise ValueError(
            "historical backfill wallet coverage does not match "
            f"refinement; missing={missing} extra={extra}"
        )


def build_stage10a1b_evidence_report(
    refinement: dict[str, Any],
    *,
    raw_by_wallet: dict[str, list[dict[str, Any]]],
    fetch_report: dict[str, Any],
    history_as_of_unix: int,
) -> tuple[
    dict[str, Any],
    dict[str, list[dict[str, Any]]],
]:
    verify_candidate_refinement(refinement)
    _validate_backfill_wallet_coverage(
        refinement,
        raw_by_wallet,
    )
    effective_after = refinement_effective_after_unix(refinement)
    history_as_of_unix = int(history_as_of_unix)
    if history_as_of_unix <= effective_after:
        raise ValueError(
            "history_as_of_unix must be strictly after the "
            "discovery/refinement activation time"
        )

    normalized, normalization_report = normalize_wallet_histories(
        raw_by_wallet
    )
    report_core = {
        "version": STAGE10A1B_VERSION,
        "mode": "HISTORICAL_EVIDENCE_BACKFILL",
        "source_kind": "REAL",
        "source_refinement_fingerprint": refinement[
            "refinement_fingerprint"
        ],
        "parent_refinement_fingerprint": refinement.get(
            "parent_refinement_fingerprint"
        ),
        "universe_effective_after_unix": effective_after,
        "history_as_of_unix": history_as_of_unix,
        "fetch": fetch_report,
        "normalization": normalization_report,
        "stage3_to_stage5_executed": False,
        "edge_claim": None,
    }
    report = {
        **report_core,
        "report_fingerprint": _fingerprint(report_core),
    }
    return report, normalized


def persist_stage10a1b_evidence(
    client: SupabaseRestClient,
    *,
    raw_by_wallet: dict[str, Iterable[dict[str, Any]]],
    normalized_by_wallet: dict[str, Iterable[dict[str, Any]]],
    raw_source: str,
) -> dict[str, int]:
    raw_rows = client.persist_historical_raw(
        raw_by_wallet,
        source=raw_source,
    )
    normalized_rows = client.persist_normalized_history(
        normalized_by_wallet
    )
    return {
        "historical_raw_rows": raw_rows,
        "normalized_history_rows": normalized_rows,
    }


def write_stage10a1b_evidence_bundle(
    directory: str | Path,
    *,
    report: dict[str, Any],
    raw_by_wallet: dict[str, Iterable[dict[str, Any]]],
    normalized_by_wallet: dict[str, Iterable[dict[str, Any]]],
    raw_source: str,
) -> dict[str, Any]:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "version": STAGE10A1B_VERSION,
        "source_kind": "REAL",
        "raw_source": raw_source,
        "report_fingerprint": report["report_fingerprint"],
        "source_refinement_fingerprint": report[
            "source_refinement_fingerprint"
        ],
        "parent_refinement_fingerprint": report.get(
            "parent_refinement_fingerprint"
        ),
        "history_as_of_unix": report["history_as_of_unix"],
        "universe_effective_after_unix": report[
            "universe_effective_after_unix"
        ],
        "wallet_count": int(
            report["fetch"].get("wallet_count") or 0
        ),
        "raw_transaction_rows": int(
            report["fetch"].get(
                "raw_transaction_rows_across_wallets"
            ) or 0
        ),
        "normalized_event_count": int(
            report["normalization"].get(
                "normalized_event_count"
            ) or 0
        ),
        "qualification_grade": bool(
            report["fetch"].get("qualification_grade")
        ),
        "files": {
            "raw": "raw.jsonl",
            "normalized": "normalized.jsonl",
            "report": "report.json",
        },
    }

    with (root / "raw.jsonl").open("w", encoding="utf-8") as handle:
        for wallet, rows in sorted(raw_by_wallet.items()):
            for tx in rows:
                handle.write(json.dumps(
                    {
                        "wallet": wallet,
                        "source": raw_source,
                        "transaction": tx,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=str,
                ) + "\n")

    with (root / "normalized.jsonl").open(
        "w",
        encoding="utf-8",
    ) as handle:
        for wallet, rows in sorted(normalized_by_wallet.items()):
            for event in rows:
                handle.write(json.dumps(
                    {
                        "wallet": wallet,
                        "event": event,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=str,
                ) + "\n")

    (root / "report.json").write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        ) + "\n",
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    return manifest


def build_stage10a1b_report(
    refinement: dict[str, Any],
    *,
    raw_by_wallet: dict[str, list[dict[str, Any]]],
    fetch_report: dict[str, Any],
    history_as_of_unix: int,
    signal_from_unix: int | None = None,
    signal_to_unix: int | None = None,
) -> tuple[
    dict[str, Any],
    dict[str, list[dict[str, Any]]],
    dict[str, Any],
]:
    effective_after = refinement_effective_after_unix(refinement)
    history_as_of_unix = int(history_as_of_unix)

    expected_wallets = set(
        wallet_addresses_from_refinement(
            refinement,
            trader_only=True,
        )
    )
    actual_wallets = {
        validate_solana_address(wallet)
        for wallet in raw_by_wallet
    }
    if actual_wallets != expected_wallets:
        missing = sorted(expected_wallets - actual_wallets)
        extra = sorted(actual_wallets - expected_wallets)
        raise ValueError(
            "historical backfill wallet coverage does not match "
            f"refinement; missing={missing} extra={extra}"
        )

    if history_as_of_unix <= effective_after:
        raise ValueError(
            "history_as_of_unix must be strictly after the "
            "discovery/refinement activation time"
        )
    if signal_from_unix is None:
        signal_from_unix = effective_after + 1
    if signal_to_unix is None:
        signal_to_unix = history_as_of_unix

    normalized, normalization_report = normalize_wallet_histories(
        raw_by_wallet
    )
    replay = build_causal_historical_replay(
        normalized,
        signal_from_unix=int(signal_from_unix),
        signal_to_unix=int(signal_to_unix),
        universe_effective_after_unix=effective_after,
    )

    report_core = {
        "version": STAGE10A1B_VERSION,
        "source_kind": "REAL",
        "source_refinement_fingerprint": refinement[
            "refinement_fingerprint"
        ],
        "universe_effective_after_unix": effective_after,
        "history_as_of_unix": history_as_of_unix,
        "fetch": fetch_report,
        "normalization": normalization_report,
        "causal_replay": replay,
        "edge_claim": None,
        "production_rule_selected": False,
    }
    report = {
        **report_core,
        "report_fingerprint": _fingerprint(report_core),
    }
    return report, normalized, replay


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
            "Stage 10A-1B real causal historical backfill for "
            "Stage-10A-1A trader candidates"
        )
    )
    parser.add_argument("--refinement-file", required=True)
    parser.add_argument(
        "--shard-count",
        type=int,
        default=1,
        help="Deterministically split sorted trader wallets into N shards.",
    )
    parser.add_argument(
        "--shard-index",
        type=int,
        default=0,
        help="Zero-based shard index when --shard-count > 1.",
    )
    parser.add_argument(
        "--provider",
        choices=["solana-rpc", "helius", "indexed-rpc"],
        default="solana-rpc",
    )
    parser.add_argument(
        "--history-as-of-unix",
        type=int,
        required=True,
        help="Latest historical timestamp allowed into this backfill.",
    )
    parser.add_argument("--signal-from-unix", type=int, default=None)
    parser.add_argument("--signal-to-unix", type=int, default=None)
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
        "--indexed-rpc-url",
        default=(
            os.environ.get("INDEXED_SOLANA_RPC_URL")
            or os.environ.get("ALCHEMY_SOLANA_RPC_URL")
            or ""
        ),
        help=(
            "Full credential-bearing URL for a compatible indexed "
            "getTransactionsForAddress provider. Never written to output."
        ),
    )
    parser.add_argument(
        "--indexed-source-label",
        default=os.environ.get(
            "INDEXED_SOLANA_RPC_SOURCE_LABEL",
            "indexed-solana-gtfa",
        ),
    )
    parser.add_argument(
        "--indexed-max-pages-per-wallet",
        type=int,
        default=int(
            os.environ.get(
                "INDEXED_SOLANA_MAX_PAGES_PER_WALLET",
                "5000",
            )
        ),
        help=(
            "Fail-closed page cap for indexed full-history pagination. "
            "Alchemy full transaction mode returns at most 100 rows/page."
        ),
    )
    parser.add_argument(
        "--indexed-min-request-interval-ms",
        type=float,
        default=float(
            os.environ.get(
                "INDEXED_SOLANA_MIN_REQUEST_INTERVAL_MS",
                "0",
            )
        ),
        help=(
            "Minimum delay before each indexed history request. "
            "Use this to remain below provider CU/s limits."
        ),
    )
    parser.add_argument(
        "--signature-page-limit",
        type=int,
        default=DEFAULT_SIGNATURE_PAGE_LIMIT,
    )
    parser.add_argument(
        "--max-signature-pages-per-wallet",
        type=int,
        default=DEFAULT_MAX_SIGNATURE_PAGES_PER_WALLET,
    )
    parser.add_argument(
        "--transaction-batch-size",
        type=int,
        default=DEFAULT_TRANSACTION_BATCH_SIZE,
    )
    parser.add_argument(
        "--rpc-min-request-interval-ms",
        type=float,
        default=0.0,
        help=(
            "Minimum spacing between native RPC HTTP requests. "
            "Useful for rate-limited public endpoints; 300ms is "
            "approximately 3.3 requests/second."
        ),
    )
    parser.add_argument(
        "--allow-provider-retention-gap",
        action="store_true",
        help=(
            "Allow native RPC whose first available block is >0. "
            "Output is not qualification-grade when used."
        ),
    )
    parser.add_argument(
        "--evidence-only",
        action="store_true",
        help=(
            "Stop after raw + Stage-2 normalized historical evidence. "
            "This is the production Stage-10A-1B population mode; "
            "Stage 3-5 reconstruction belongs to Stage 10A-1C."
        ),
    )
    parser.add_argument(
        "--evidence-dir",
        default=None,
        help="Optional directory for manifest/raw/normalized/report files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build report but do not write Supabase.",
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    refinement = _load_refinement(args.refinement_file)
    if args.shard_count != 1 or args.shard_index != 0:
        refinement = build_refinement_shard(
            refinement,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
        )
    wallets = wallet_addresses_from_refinement(
        refinement,
        trader_only=True,
    )
    if not wallets:
        raise SystemExit("no TRADER_CANDIDATE wallets to backfill")

    raw_source: str
    if args.provider == "solana-rpc":
        source = SolanaWalletHistoryRpc(
            args.rpc_url,
            source_label=args.source_label,
            min_request_interval_seconds=(
                float(args.rpc_min_request_interval_ms) / 1000.0
            ),
        )
        raw_by_wallet, fetch_report = collect_solana_rpc_histories(
            source,
            wallets,
            as_of_unix=args.history_as_of_unix,
            signature_page_limit=args.signature_page_limit,
            max_signature_pages_per_wallet=(
                args.max_signature_pages_per_wallet
            ),
            transaction_batch_size=args.transaction_batch_size,
            require_archive_from_genesis=(
                not args.allow_provider_retention_gap
            ),
        )
        raw_source = "solana_json_rpc"
    elif args.provider == "helius":
        api_key = os.environ.get("HELIUS_API_KEY")
        if not api_key:
            raise SystemExit(
                "HELIUS_API_KEY is required when --provider helius"
            )
        raw_by_wallet, fetch_report = collect_helius_histories_as_of(
            api_key,
            wallets,
            as_of_unix=args.history_as_of_unix,
        )
        raw_source = "helius_gtfa"
    else:
        indexed_rpc_url = str(args.indexed_rpc_url or "").strip()
        if not indexed_rpc_url:
            raise SystemExit(
                "INDEXED_SOLANA_RPC_URL or ALCHEMY_SOLANA_RPC_URL "
                "is required when --provider indexed-rpc"
            )
        raw_by_wallet, fetch_report = collect_indexed_histories_as_of(
            indexed_rpc_url,
            args.indexed_source_label,
            wallets,
            as_of_unix=args.history_as_of_unix,
            max_pages_per_wallet=args.indexed_max_pages_per_wallet,
            min_request_interval_seconds=(
                float(args.indexed_min_request_interval_ms) / 1000.0
            ),
        )
        raw_source = "indexed_gtfa"

    replay = None
    if args.evidence_only:
        report, normalized = build_stage10a1b_evidence_report(
            refinement,
            raw_by_wallet=raw_by_wallet,
            fetch_report=fetch_report,
            history_as_of_unix=args.history_as_of_unix,
        )
    else:
        report, normalized, replay = build_stage10a1b_report(
            refinement,
            raw_by_wallet=raw_by_wallet,
            fetch_report=fetch_report,
            history_as_of_unix=args.history_as_of_unix,
            signal_from_unix=args.signal_from_unix,
            signal_to_unix=args.signal_to_unix,
        )

    bundle_manifest = None
    if args.evidence_dir:
        bundle_manifest = write_stage10a1b_evidence_bundle(
            args.evidence_dir,
            report=report,
            raw_by_wallet=raw_by_wallet,
            normalized_by_wallet=normalized,
            raw_source=raw_source,
        )

    persistence = None
    if not args.dry_run:
        if not bool(fetch_report.get("qualification_grade")):
            raise RuntimeError(
                "refusing Supabase production persistence from a "
                "non-qualification-grade history source"
            )
        client = SupabaseRestClient.from_env()
        if args.evidence_only:
            persistence = persist_stage10a1b_evidence(
                client,
                raw_by_wallet=raw_by_wallet,
                normalized_by_wallet=normalized,
                raw_source=raw_source,
            )
        else:
            if replay is None:
                raise RuntimeError("causal replay is unexpectedly absent")
            persistence = persist_stage10a_backfill(
                client,
                raw_by_wallet=raw_by_wallet,
                normalized_by_wallet=normalized,
                replay=replay,
                raw_source=raw_source,
            )

    output = {
        "backfill": report,
        "evidence_bundle_manifest": bundle_manifest,
        "supabase_persistence": persistence,
        "dry_run": bool(args.dry_run),
    }
    _write_json(args.out, output)
    print(json.dumps({
        "version": report["version"],
        "provider": fetch_report.get("provider"),
        "qualification_grade": fetch_report.get(
            "qualification_grade"
        ),
        "wallet_count": fetch_report.get("wallet_count"),
        "raw_transaction_rows": fetch_report.get(
            "raw_transaction_rows_across_wallets"
        ),
        "mode": report.get("mode", "CAUSAL_REPLAY_INTEGRATION"),
        "normalized_event_count": report[
            "normalization"
        ]["normalized_event_count"],
        "universe_effective_after_unix": report[
            "universe_effective_after_unix"
        ],
        "history_as_of_unix": report["history_as_of_unix"],
        "report_fingerprint": report["report_fingerprint"],
        "shard_index": int(args.shard_index),
        "shard_count": int(args.shard_count),
        "persisted": not args.dry_run,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
