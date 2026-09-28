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

from research.wallet_s1_data_foundation import validate_solana_address
from research.wallet_supabase_adapter import SupabaseRestClient

STAGE10A0_VERSION = "wallet-s10a0-v1"
CHAIN = "solana"
DEFAULT_SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
DEFAULT_LOOKBACK_SLOTS = 32
DEFAULT_RPC_ATTEMPTS = 5
DEFAULT_MAX_SUPPORTED_TRANSACTION_VERSION = 1

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


def _safe_rpc_origin(url: str) -> str:
    parts = urlsplit(str(url))
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("RPC URL must be an absolute HTTP(S) URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", "", ""))


def _default_rpc_transport(
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


class SolanaJsonRpcBlockSource:
    """Provider-neutral Solana JSON-RPC block scanner.

    Any standards-compatible Solana RPC endpoint can be used. Helius may be
    supplied as the endpoint, but discovery semantics do not depend on Helius.
    """

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
    ):
        rpc_url = str(rpc_url or "").strip()
        _safe_rpc_origin(rpc_url)
        if not source_label.strip():
            raise ValueError("source_label is required")
        if attempts < 1:
            raise ValueError("attempts must be >= 1")
        if int(max_supported_transaction_version) < 0:
            raise ValueError(
                "max_supported_transaction_version must be >= 0"
            )
        self.rpc_url = rpc_url
        self.source_label = source_label.strip()
        self.transport = transport or _default_rpc_transport
        self.attempts = int(attempts)
        self.max_supported_transaction_version = int(
            max_supported_transaction_version
        )
        self._request_id = 0

    @property
    def public_origin(self) -> str:
        return _safe_rpc_origin(self.rpc_url)

    def _rpc(self, method: str, params: list[Any]) -> Any:
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        last_error: Exception | None = None

        for attempt in range(self.attempts):
            try:
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
                response = json.loads(raw.decode("utf-8"))
                if response.get("error") is not None:
                    raise RuntimeError(
                        f"RPC {method} error: {response['error']}"
                    )
                return response.get("result")
            except (
                HTTPError,
                URLError,
                TimeoutError,
                RuntimeError,
                json.JSONDecodeError,
            ) as exc:
                last_error = exc
                if attempt == self.attempts - 1:
                    break
                time.sleep(min(2 ** attempt, 8))

        raise RuntimeError(
            f"RPC {method} failed after {self.attempts} attempts: "
            f"{last_error}"
        )

    def get_slot(self) -> int:
        result = self._rpc("getSlot", [{"commitment": "finalized"}])
        if result is None:
            raise RuntimeError("getSlot returned null")
        return int(result)

    def get_blocks(self, start_slot: int, end_slot: int) -> list[int]:
        start_slot = int(start_slot)
        end_slot = int(end_slot)
        if start_slot < 0 or end_slot < start_slot:
            raise ValueError("invalid slot range")
        result = self._rpc(
            "getBlocks",
            [
                start_slot,
                end_slot,
                {"commitment": "finalized"},
            ],
        )
        if result is None:
            raise RuntimeError("getBlocks returned null")
        slots = sorted({int(slot) for slot in result})
        if any(slot < start_slot or slot > end_slot for slot in slots):
            raise ValueError("RPC returned slot outside requested range")
        return slots

    def get_block(self, slot: int) -> dict[str, Any]:
        result = self._rpc(
            "getBlock",
            [
                int(slot),
                {
                    "commitment": "finalized",
                    "encoding": "jsonParsed",
                    "transactionDetails": "full",
                    "rewards": False,
                    "maxSupportedTransactionVersion": (
                        self.max_supported_transaction_version
                    ),
                },
            ],
        )
        if result is None:
            raise RuntimeError(f"getBlock returned null for slot {slot}")
        if not isinstance(result, dict):
            raise TypeError(f"invalid block payload for slot {slot}")
        return result


def _signature(tx_entry: dict[str, Any]) -> str:
    transaction = tx_entry.get("transaction") or {}
    signatures = transaction.get("signatures") or []
    return str(signatures[0]) if signatures else ""


def _signer_addresses(tx_entry: dict[str, Any]) -> set[str]:
    transaction = tx_entry.get("transaction") or {}
    message = transaction.get("message") or {}
    keys = list(message.get("accountKeys") or [])
    signers: set[str] = set()

    if any(isinstance(item, dict) for item in keys):
        for item in keys:
            if not isinstance(item, dict):
                continue
            if not bool(item.get("signer")):
                continue
            pubkey = str(item.get("pubkey") or "")
            if pubkey:
                try:
                    signers.add(validate_solana_address(pubkey))
                except ValueError:
                    continue
        return signers

    header = message.get("header") or {}
    required = int(header.get("numRequiredSignatures") or 0)
    for item in keys[:required]:
        pubkey = str(item or "")
        if pubkey:
            try:
                signers.add(validate_solana_address(pubkey))
            except ValueError:
                continue
    return signers


def _token_balance_map(
    rows: Iterable[dict[str, Any]],
) -> dict[tuple[int, str], tuple[int, str | None]]:
    output: dict[tuple[int, str], tuple[int, str | None]] = {}
    for row in rows:
        if row.get("accountIndex") is None:
            continue
        mint = str(row.get("mint") or "")
        if not mint:
            continue
        ui = row.get("uiTokenAmount") or {}
        amount = int(str(ui.get("amount") or "0"))
        owner_raw = str(row.get("owner") or "").strip()
        owner: str | None = None
        if owner_raw:
            try:
                owner = validate_solana_address(owner_raw)
            except ValueError:
                owner = None
        output[(int(row["accountIndex"]), mint)] = (amount, owner)
    return output


def extract_transaction_candidate_evidence(
    tx_entry: dict[str, Any],
    *,
    slot: int,
    block_time: int,
    source_label: str,
) -> list[dict[str, Any]]:
    """Return signer wallets that demonstrably own a changed token balance."""
    meta = tx_entry.get("meta") or {}
    if meta.get("err") is not None:
        return []

    signature = _signature(tx_entry)
    if not signature:
        return []

    signers = _signer_addresses(tx_entry)
    if not signers:
        return []

    before = _token_balance_map(meta.get("preTokenBalances") or [])
    after = _token_balance_map(meta.get("postTokenBalances") or [])
    owner_mints: dict[str, set[str]] = defaultdict(set)

    for key in sorted(set(before) | set(after)):
        pre_amount, pre_owner = before.get(key, (0, None))
        post_amount, post_owner = after.get(key, (0, None))
        if pre_amount == post_amount:
            continue
        mint = key[1]
        for owner in {pre_owner, post_owner}:
            if owner is not None and owner in signers:
                owner_mints[owner].add(mint)

    return [
        {
            "wallet": wallet,
            "signature": signature,
            "slot": int(slot),
            "block_time": int(block_time),
            "changed_mints": sorted(owner_mints[wallet]),
            "discovery_reason": "SIGNER_WITH_TOKEN_BALANCE_CHANGE",
            "discovery_source": source_label,
        }
        for wallet in sorted(owner_mints)
    ]


def build_candidate_universe(
    blocks: Iterable[dict[str, Any]],
    *,
    source_label: str,
    source_origin: str,
    requested_start_slot: int,
    requested_end_slot: int,
    cutoff_unix: int | None = None,
) -> dict[str, Any]:
    """Build one deterministic, causal candidate-wallet universe."""
    requested_start_slot = int(requested_start_slot)
    requested_end_slot = int(requested_end_slot)
    if requested_start_slot < 0 or requested_end_slot < requested_start_slot:
        raise ValueError("invalid requested slot range")
    if not source_label.strip():
        raise ValueError("source_label is required")
    safe_origin = _safe_rpc_origin(source_origin)

    ordered_blocks: dict[int, dict[str, Any]] = {}
    for raw in blocks:
        row = dict(raw)
        if row.get("slot") is None:
            raise ValueError("block wrapper requires slot")
        slot = int(row["slot"])
        if slot < requested_start_slot or slot > requested_end_slot:
            raise ValueError("block outside requested range")
        if slot in ordered_blocks:
            if _canonical_json(ordered_blocks[slot]) != _canonical_json(row):
                raise ValueError(f"conflicting duplicate block slot {slot}")
            continue
        ordered_blocks[slot] = row

    evidence_by_wallet: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    scanned_slots: list[int] = []
    transaction_count = 0
    eligible_transaction_count = 0

    for slot in sorted(ordered_blocks):
        wrapper = ordered_blocks[slot]
        block = wrapper.get("block")
        if not isinstance(block, dict):
            raise ValueError(f"missing block payload for slot {slot}")
        block_time_raw = block.get("blockTime")
        if block_time_raw is None:
            continue
        block_time = int(block_time_raw)
        if cutoff_unix is not None and block_time > int(cutoff_unix):
            continue

        scanned_slots.append(slot)
        transactions = list(block.get("transactions") or [])
        transaction_count += len(transactions)

        for tx_entry in transactions:
            evidence = extract_transaction_candidate_evidence(
                tx_entry,
                slot=slot,
                block_time=block_time,
                source_label=source_label,
            )
            if evidence:
                eligible_transaction_count += 1
            for row in evidence:
                wallet = row["wallet"]
                signature = row["signature"]
                existing = evidence_by_wallet[wallet].get(signature)
                if existing is not None:
                    if _canonical_json(existing) != _canonical_json(row):
                        raise ValueError(
                            f"conflicting duplicate evidence {wallet}:{signature}"
                        )
                    continue
                evidence_by_wallet[wallet][signature] = row

    records: list[dict[str, Any]] = []
    for wallet in sorted(evidence_by_wallet):
        evidence = sorted(
            evidence_by_wallet[wallet].values(),
            key=lambda row: (
                int(row["block_time"]),
                int(row["slot"]),
                str(row["signature"]),
            ),
        )
        first = evidence[0]
        last = evidence[-1]
        mints = sorted({
            mint
            for row in evidence
            for mint in row.get("changed_mints") or []
        })
        core = {
            "version": STAGE10A0_VERSION,
            "chain": CHAIN,
            "wallet": wallet,
            "discovered_at": int(first["block_time"]),
            "first_observed_at": int(first["block_time"]),
            "last_observed_at": int(last["block_time"]),
            "first_observed_slot": int(first["slot"]),
            "last_observed_slot": int(last["slot"]),
            "activity_count": len(evidence),
            "distinct_changed_mint_count": len(mints),
            "changed_mints": mints,
            "discovery_source": source_label,
            "discovery_reason": "SIGNER_WITH_TOKEN_BALANCE_CHANGE",
            "evidence_signature_count": len(evidence),
            "evidence_signatures": [
                str(row["signature"]) for row in evidence
            ],
            "evidence": evidence,
        }
        records.append({
            **core,
            "record_fingerprint": _fingerprint(core),
        })

    snapshot_core = {
        "version": STAGE10A0_VERSION,
        "chain": CHAIN,
        "source": {
            "kind": "SOLANA_JSON_RPC",
            "label": source_label,
            "origin": safe_origin,
        },
        "scan": {
            "requested_start_slot": requested_start_slot,
            "requested_end_slot": requested_end_slot,
            "cutoff_unix": (
                None if cutoff_unix is None else int(cutoff_unix)
            ),
            "scanned_block_count": len(scanned_slots),
            "scanned_slots": scanned_slots,
            "transaction_count": transaction_count,
            "eligible_transaction_count": eligible_transaction_count,
        },
        "candidate_wallet_count": len(records),
        "records": records,
        "contract": {
            "discovery_only": True,
            "quality_classification": None,
            "performance_score": None,
            "handoff": "WALLET_STAGE10A1_CAUSAL_HISTORICAL_BACKFILL",
            "candidate_rule": "SIGNER_WITH_TOKEN_BALANCE_CHANGE",
        },
    }
    return {
        **snapshot_core,
        "universe_fingerprint": _fingerprint(snapshot_core),
    }


def verify_candidate_universe(universe: dict[str, Any]) -> bool:
    if str(universe.get("version") or "") != STAGE10A0_VERSION:
        raise ValueError("unsupported candidate-universe version")

    scan = universe.get("scan") or {}
    source = universe.get("source") or {}
    records = list(universe.get("records") or [])

    seen_wallets: set[str] = set()
    for record in records:
        wallet = validate_solana_address(str(record.get("wallet") or ""))
        if wallet in seen_wallets:
            raise ValueError(f"duplicate wallet in candidate universe: {wallet}")
        seen_wallets.add(wallet)
        actual = str(record.get("record_fingerprint") or "")
        core = {
            key: value
            for key, value in record.items()
            if key != "record_fingerprint"
        }
        if not actual or actual != _fingerprint(core):
            raise ValueError(f"candidate record fingerprint mismatch: {wallet}")

    snapshot_core = {
        key: value
        for key, value in universe.items()
        if key != "universe_fingerprint"
    }
    actual_universe = str(universe.get("universe_fingerprint") or "")
    if not actual_universe or actual_universe != _fingerprint(snapshot_core):
        raise ValueError("candidate-universe fingerprint mismatch")

    if int(universe.get("candidate_wallet_count") or 0) != len(records):
        raise ValueError("candidate wallet count mismatch")
    if str(source.get("kind") or "") != "SOLANA_JSON_RPC":
        raise ValueError("unsupported discovery source kind")
    _safe_rpc_origin(str(source.get("origin") or ""))
    if scan.get("requested_start_slot") is None or scan.get(
        "requested_end_slot"
    ) is None:
        raise ValueError("candidate universe missing scan bounds")
    return True


def scan_candidate_universe(
    source: SolanaJsonRpcBlockSource,
    *,
    start_slot: int | None = None,
    end_slot: int | None = None,
    lookback_slots: int = DEFAULT_LOOKBACK_SLOTS,
    cutoff_unix: int | None = None,
) -> dict[str, Any]:
    if end_slot is None:
        end_slot = source.get_slot()
    end_slot = int(end_slot)

    if start_slot is None:
        if int(lookback_slots) < 1:
            raise ValueError("lookback_slots must be >= 1")
        start_slot = max(0, end_slot - int(lookback_slots) + 1)
    start_slot = int(start_slot)
    if start_slot > end_slot:
        raise ValueError("start_slot must be <= end_slot")

    slots = source.get_blocks(start_slot, end_slot)
    if not slots:
        raise RuntimeError("no finalized blocks returned for requested range")

    blocks = [
        {"slot": slot, "block": source.get_block(slot)}
        for slot in slots
    ]
    universe = build_candidate_universe(
        blocks,
        source_label=source.source_label,
        source_origin=source.public_origin,
        requested_start_slot=start_slot,
        requested_end_slot=end_slot,
        cutoff_unix=cutoff_unix,
    )
    verify_candidate_universe(universe)
    return universe


def wallet_addresses_from_universe(
    universe: dict[str, Any],
) -> list[str]:
    verify_candidate_universe(universe)
    return sorted(
        validate_solana_address(str(row["wallet"]))
        for row in universe.get("records") or []
    )


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
        description="Stage 10A-0 automatic Solana wallet-universe discovery"
    )
    parser.add_argument(
        "--rpc-url",
        default=(
            os.environ.get("SOLANA_RPC_URL")
            or DEFAULT_SOLANA_RPC_URL
        ),
        help=(
            "Solana JSON-RPC endpoint. Defaults to public mainnet RPC; "
            "Helius or another compatible endpoint may be supplied."
        ),
    )
    parser.add_argument(
        "--source-label",
        default=os.environ.get("SOLANA_RPC_SOURCE_LABEL", "solana-json-rpc"),
    )
    parser.add_argument("--start-slot", type=int, default=None)
    parser.add_argument("--end-slot", type=int, default=None)
    parser.add_argument(
        "--lookback-slots",
        type=int,
        default=DEFAULT_LOOKBACK_SLOTS,
    )
    parser.add_argument(
        "--max-supported-transaction-version",
        type=int,
        default=DEFAULT_MAX_SUPPORTED_TRANSACTION_VERSION,
    )
    parser.add_argument("--cutoff-unix", type=int, default=None)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--persist-supabase",
        action="store_true",
        help="Persist universe + evidence using server-side Supabase env.",
    )
    parser.add_argument(
        "--require-candidates",
        action="store_true",
        help="Fail if the scanned real range yields zero candidate wallets.",
    )
    args = parser.parse_args()

    source = SolanaJsonRpcBlockSource(
        args.rpc_url,
        source_label=args.source_label,
        max_supported_transaction_version=(
            args.max_supported_transaction_version
        ),
    )
    universe = scan_candidate_universe(
        source,
        start_slot=args.start_slot,
        end_slot=args.end_slot,
        lookback_slots=args.lookback_slots,
        cutoff_unix=args.cutoff_unix,
    )

    if args.require_candidates and not universe["candidate_wallet_count"]:
        raise SystemExit("no candidate wallets discovered")

    persistence = None
    if args.persist_supabase:
        persistence = SupabaseRestClient.from_env().persist_candidate_universe(
            universe
        )

    output = {
        "universe": universe,
        "persistence": persistence,
    }
    _write_json(args.out, output)
    print(json.dumps({
        "version": universe["version"],
        "universe_fingerprint": universe["universe_fingerprint"],
        "scanned_block_count": universe["scan"]["scanned_block_count"],
        "transaction_count": universe["scan"]["transaction_count"],
        "candidate_wallet_count": universe["candidate_wallet_count"],
        "persisted": bool(args.persist_supabase),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
