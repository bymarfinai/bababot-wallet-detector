from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any, Iterable

from research.wallet_s1_data_foundation import _account_keys
from research.wallet_s2_transaction_normalizer import normalize_transaction
from research.wallet_s7_qualified_registry import verify_registry_snapshot

STAGE8_VERSION = "wallet-s8-v1"
ROLLING_WINDOWS_SECONDS = {
    "5m": 5 * 60,
    "15m": 15 * 60,
    "1h": 60 * 60,
}
HELIUS_MAX_ACCOUNTS_PER_WEBHOOK = 100_000
ZERO = Decimal("0")


def _d(value: Any) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(str(value))


def _s(value: Decimal) -> str:
    if value == ZERO:
        return "0"
    return format(value.normalize(), "f")


def _signature(tx: dict[str, Any]) -> str:
    transaction = tx.get("transaction") or {}
    signatures = transaction.get("signatures") or []
    return str(signatures[0]) if signatures else ""


def _token_balance_owners(tx: dict[str, Any]) -> set[str]:
    meta = tx.get("meta") or {}
    owners: set[str] = set()
    for key in ("preTokenBalances", "postTokenBalances"):
        for row in meta.get(key) or []:
            owner = str(row.get("owner") or "")
            if owner:
                owners.add(owner)
    return owners


def transaction_touches_wallet(
    tx: dict[str, Any],
    wallet: str,
) -> bool:
    """Detect wallet participation from account keys or token-balance ownership."""
    return (
        wallet in set(_account_keys(tx))
        or wallet in _token_balance_owners(tx)
    )


def build_live_subscription_plan(
    snapshot: dict[str, Any],
    *,
    provider: str = "helius",
    transport: str = "raw_webhook",
    max_addresses_per_subscription: int = HELIUS_MAX_ACCOUNTS_PER_WEBHOOK,
) -> dict[str, Any]:
    """Turn an integrity-verified Stage-7 snapshot into provider subscription batches."""
    verify_registry_snapshot(snapshot)
    if max_addresses_per_subscription < 1:
        raise ValueError("max_addresses_per_subscription must be >= 1")

    active_wallets = list(snapshot.get("active_wallets") or [])
    batches = [
        active_wallets[i:i + max_addresses_per_subscription]
        for i in range(0, len(active_wallets), max_addresses_per_subscription)
    ]

    return {
        "version": STAGE8_VERSION,
        "registry_snapshot_id": snapshot["snapshot_id"],
        "registry_snapshot_fingerprint": snapshot["snapshot_fingerprint"],
        "provider": provider,
        "transport": transport,
        "address_count": len(active_wallets),
        "batch_count": len(batches),
        "batches": [
            {
                "batch_index": index,
                "account_addresses": addresses,
                "address_count": len(addresses),
            }
            for index, addresses in enumerate(batches)
        ],
        "delivery_contract": {
            "capture": "ALL_TRANSACTIONS_TOUCHING_ACTIVE_WALLETS",
            "auth_header_required": True,
            "delivery_semantics": "AT_LEAST_ONCE_SAFE",
            "idempotency_key": "wallet+signature",
            "normalization_contract": "STAGE2_RPC_TRANSACTION_SHAPE",
        },
    }


def live_event_to_persistence_row(event: dict[str, Any]) -> dict[str, Any]:
    """Create a storage-neutral row with a DB-safe idempotency key."""
    wallet = str(event.get("wallet") or "")
    signature = str(event.get("signature") or "")
    if not wallet or not signature:
        raise ValueError("live event requires wallet and signature")

    return {
        "idempotency_key": f"{wallet}:{signature}",
        "wallet": wallet,
        "signature": signature,
        "slot": event.get("slot"),
        "block_time": event.get("block_time"),
        "event_type": event.get("event_type"),
        "side": event.get("side"),
        "base_asset": event.get("base_asset"),
        "quote_asset": event.get("quote_asset"),
        "base_amount": event.get("base_amount"),
        "quote_amount": event.get("quote_amount"),
        "usd_notional": event.get("usd_notional"),
        "primary_segment": event.get("primary_segment"),
        "qualifying_segments": list(event.get("qualifying_segments") or []),
        "meme_hunter_evidence": event.get("meme_hunter_evidence"),
        "special_labels": dict(event.get("special_labels") or {}),
        "registry_snapshot_id": event.get("registry_snapshot_id"),
        "registry_record_fingerprint": event.get("registry_record_fingerprint"),
        "payload": dict(event),
    }


def _segment_membership_counts(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    buy_sets: dict[str, set[str]] = defaultdict(set)
    sell_sets: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        side = str(row.get("side") or "")
        wallet = str(row.get("wallet") or "")
        for segment in row.get("qualifying_segments") or []:
            segment = str(segment)
            if side == "BUY":
                buy_sets[segment].add(wallet)
            elif side == "SELL":
                sell_sets[segment].add(wallet)

    segments = sorted(set(buy_sets) | set(sell_sets))
    return {
        segment: {
            "buy_wallet_count": len(buy_sets.get(segment, set())),
            "sell_wallet_count": len(sell_sets.get(segment, set())),
        }
        for segment in segments
    }


def _aggregate_symbol_rows(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    buy_rows = [row for row in rows if row.get("side") == "BUY"]
    sell_rows = [row for row in rows if row.get("side") == "SELL"]

    buy_wallets = {str(row["wallet"]) for row in buy_rows}
    sell_wallets = {str(row["wallet"]) for row in sell_rows}
    all_wallets = buy_wallets | sell_wallets

    buy_base = sum((_d(row.get("base_amount")) for row in buy_rows), ZERO)
    sell_base = sum((_d(row.get("base_amount")) for row in sell_rows), ZERO)
    net_base = buy_base - sell_base

    usd_buy_rows = [row for row in buy_rows if row.get("usd_notional") is not None]
    usd_sell_rows = [row for row in sell_rows if row.get("usd_notional") is not None]
    usd_buy = sum((_d(row.get("usd_notional")) for row in usd_buy_rows), ZERO)
    usd_sell = sum((_d(row.get("usd_notional")) for row in usd_sell_rows), ZERO)

    if net_base > ZERO:
        flow_state = "ACCUMULATION"
    elif net_base < ZERO:
        flow_state = "DISTRIBUTION"
    else:
        flow_state = "BALANCED"

    return {
        "base_asset": str(rows[0]["base_asset"]),
        "event_count": len(rows),
        "buy_event_count": len(buy_rows),
        "sell_event_count": len(sell_rows),
        "unique_wallet_count": len(all_wallets),
        "buy_wallet_count": len(buy_wallets),
        "sell_wallet_count": len(sell_wallets),
        "wallet_net_count": len(buy_wallets) - len(sell_wallets),
        "buy_base_amount": _s(buy_base),
        "sell_base_amount": _s(sell_base),
        "net_base_amount": _s(net_base),
        "flow_state": flow_state,
        "usd_priced_event_count": len(usd_buy_rows) + len(usd_sell_rows),
        "unpriced_event_count": (
            len(rows) - len(usd_buy_rows) - len(usd_sell_rows)
        ),
        "usd_buy_notional": _s(usd_buy),
        "usd_sell_notional": _s(usd_sell),
        "usd_net_notional": _s(usd_buy - usd_sell),
        "quote_assets": sorted({
            str(row.get("quote_asset") or "")
            for row in rows
            if row.get("quote_asset")
        }),
        "segment_membership_wallet_counts": _segment_membership_counts(rows),
        "last_activity_time": max(int(row["block_time"]) for row in rows),
        "last_slot": max(
            int(row["slot"])
            for row in rows
            if row.get("slot") is not None
        ) if any(row.get("slot") is not None for row in rows) else None,
    }


def aggregate_live_events(
    events: Iterable[dict[str, Any]],
    *,
    as_of: int,
    windows_seconds: dict[str, int] = ROLLING_WINDOWS_SECONDS,
) -> dict[str, Any]:
    """Build trailing 5m/15m/1h smart-money summaries from normalized live trades."""
    trade_rows = [
        dict(row)
        for row in events
        if row.get("event_type") == "SWAP"
        and row.get("side") in {"BUY", "SELL"}
        and row.get("base_asset")
        and row.get("block_time") is not None
    ]

    result: dict[str, Any] = {
        "version": STAGE8_VERSION,
        "as_of": int(as_of),
        "windows": {},
    }

    for window_name, seconds in windows_seconds.items():
        seconds = int(seconds)
        if seconds <= 0:
            raise ValueError("window seconds must be positive")
        lower = int(as_of) - seconds
        window_rows = [
            row
            for row in trade_rows
            if lower < int(row["block_time"]) <= int(as_of)
        ]

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in window_rows:
            grouped[str(row["base_asset"])].append(row)

        symbols = [
            _aggregate_symbol_rows(grouped[base_asset])
            for base_asset in sorted(grouped)
        ]

        result["windows"][window_name] = {
            "window_seconds": seconds,
            "from_exclusive": lower,
            "to_inclusive": int(as_of),
            "trade_event_count": len(window_rows),
            "symbol_count": len(symbols),
            "symbols": symbols,
        }

    return result


class LiveWalletMonitor:
    """Provider-neutral live core.

    The transport adapter feeds standard Solana getTransaction-shaped payloads.
    Production persistence should enforce a UNIQUE(wallet, signature) constraint.
    """

    def __init__(self, registry_snapshot: dict[str, Any]):
        self._events: list[dict[str, Any]] = []
        self._seen_keys: set[tuple[str, str]] = set()
        self._ingest_attempts = 0
        self._duplicate_count = 0
        self._normalization_error_count = 0
        self.refresh_registry(registry_snapshot)

    def refresh_registry(self, registry_snapshot: dict[str, Any]) -> None:
        verify_registry_snapshot(registry_snapshot)
        self._snapshot = dict(registry_snapshot)
        self._records_by_wallet = {
            str(row["wallet"]): dict(row)
            for row in registry_snapshot.get("records") or []
            if bool(row.get("live_monitor_eligible"))
            and row.get("registry_status") == "ACTIVE"
        }
        active_wallets = set(registry_snapshot.get("active_wallets") or [])
        if active_wallets != set(self._records_by_wallet):
            raise ValueError("registry active-wallet contract mismatch")

    @property
    def active_wallets(self) -> list[str]:
        return sorted(self._records_by_wallet)

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def ingest_rpc_transaction(
        self,
        tx: dict[str, Any],
        *,
        received_at: int | None = None,
    ) -> dict[str, Any]:
        self._ingest_attempts += 1
        signature = _signature(tx)
        if not signature:
            return {
                "status": "INVALID",
                "reason": "MISSING_SIGNATURE",
                "accepted_events": [],
                "duplicates": [],
                "errors": [],
            }

        touched = [
            wallet
            for wallet in self.active_wallets
            if transaction_touches_wallet(tx, wallet)
        ]
        if not touched:
            return {
                "status": "IGNORED",
                "reason": "NO_ACTIVE_WALLET_TOUCHED",
                "signature": signature,
                "accepted_events": [],
                "duplicates": [],
                "errors": [],
            }

        accepted: list[dict[str, Any]] = []
        duplicates: list[str] = []
        errors: list[dict[str, str]] = []

        for wallet in touched:
            key = (wallet, signature)
            if key in self._seen_keys:
                duplicates.append(wallet)
                self._duplicate_count += 1
                continue

            try:
                normalized = normalize_transaction(tx, wallet)
            except Exception as exc:
                errors.append({
                    "wallet": wallet,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                self._normalization_error_count += 1
                continue

            record = self._records_by_wallet[wallet]
            live_event = {
                **normalized,
                "stage8_version": STAGE8_VERSION,
                "live_event_id": f"{wallet}:{signature}",
                "idempotency_key": f"{wallet}:{signature}",
                "registry_snapshot_id": self._snapshot["snapshot_id"],
                "registry_snapshot_fingerprint": (
                    self._snapshot["snapshot_fingerprint"]
                ),
                "registry_record_fingerprint": record["record_fingerprint"],
                "primary_segment": record.get("primary_segment"),
                "qualifying_segments": list(
                    record.get("qualifying_segments") or []
                ),
                "meme_hunter_evidence": record.get(
                    "meme_hunter_evidence"
                ),
                "special_labels": dict(record.get("special_labels") or {}),
                "received_at": received_at,
            }
            self._seen_keys.add(key)
            self._events.append(live_event)
            accepted.append(live_event)

        status = "ACCEPTED"
        if not accepted and duplicates and not errors:
            status = "DUPLICATE"
        elif not accepted and errors:
            status = "ERROR"
        elif errors:
            status = "PARTIAL"

        return {
            "status": status,
            "signature": signature,
            "touched_active_wallets": touched,
            "accepted_events": accepted,
            "duplicates": duplicates,
            "errors": errors,
        }

    def ingest_rpc_batch(
        self,
        transactions: Iterable[dict[str, Any]],
        *,
        received_at: int | None = None,
    ) -> dict[str, Any]:
        results = [
            self.ingest_rpc_transaction(tx, received_at=received_at)
            for tx in transactions
        ]
        return {
            "version": STAGE8_VERSION,
            "delivery_count": len(results),
            "accepted_event_count": sum(
                len(row.get("accepted_events") or [])
                for row in results
            ),
            "duplicate_wallet_event_count": sum(
                len(row.get("duplicates") or [])
                for row in results
            ),
            "normalization_error_count": sum(
                len(row.get("errors") or [])
                for row in results
            ),
            "results": results,
        }

    def aggregate(self, *, as_of: int) -> dict[str, Any]:
        return aggregate_live_events(self._events, as_of=as_of)

    def prune_events_before(self, block_time: int) -> int:
        before = len(self._events)
        self._events = [
            row
            for row in self._events
            if row.get("block_time") is None
            or int(row["block_time"]) >= int(block_time)
        ]
        return before - len(self._events)

    def status(self) -> dict[str, Any]:
        trade_events = [
            row
            for row in self._events
            if row.get("event_type") == "SWAP"
            and row.get("side") in {"BUY", "SELL"}
        ]
        block_times = [
            int(row["block_time"])
            for row in self._events
            if row.get("block_time") is not None
        ]
        return {
            "version": STAGE8_VERSION,
            "registry_snapshot_id": self._snapshot["snapshot_id"],
            "registry_snapshot_fingerprint": (
                self._snapshot["snapshot_fingerprint"]
            ),
            "active_wallet_count": len(self._records_by_wallet),
            "active_wallets": self.active_wallets,
            "ingest_attempts": self._ingest_attempts,
            "seen_wallet_signature_count": len(self._seen_keys),
            "stored_event_count": len(self._events),
            "stored_trade_event_count": len(trade_events),
            "duplicate_wallet_event_count": self._duplicate_count,
            "normalization_error_count": self._normalization_error_count,
            "latest_block_time": max(block_times) if block_times else None,
        }
