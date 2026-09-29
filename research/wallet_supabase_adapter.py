from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any, Callable, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from research.wallet_s7_qualified_registry import verify_registry_snapshot

DEFAULT_BATCH_SIZE = 250
Transport = Callable[
    [str, str, dict[str, str], bytes | None],
    tuple[int, bytes],
]


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")


def _default_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None,
) -> tuple[int, bytes]:
    request = Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )
    with urlopen(request, timeout=60) as response:
        return int(response.status), response.read()


def _chunks(rows: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    if size < 1:
        raise ValueError("batch size must be >= 1")
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def _registry_snapshot_row(snapshot: dict[str, Any]) -> dict[str, Any]:
    verify_registry_snapshot(snapshot)
    return {
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_fingerprint": snapshot["snapshot_fingerprint"],
        "stage7_version": snapshot["version"],
        "active_wallet_count": int(snapshot.get("active_wallet_count") or 0),
        "total_record_count": int(snapshot.get("record_count") or 0),
        "source_payload": snapshot,
    }


def _registry_record_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    verify_registry_snapshot(snapshot)
    rows: list[dict[str, Any]] = []
    for record in snapshot.get("records") or []:
        rows.append({
            "snapshot_id": snapshot["snapshot_id"],
            "wallet": record["wallet"],
            "chain": record.get("chain") or "solana",
            "record_fingerprint": record["record_fingerprint"],
            "registry_status": record["registry_status"],
            "live_monitor_eligible": bool(record["live_monitor_eligible"]),
            "primary_segment": record.get("primary_segment"),
            "qualifying_segments": list(record.get("qualifying_segments") or []),
            "classification": dict(record.get("classification") or {}),
            "performance_summary": record.get("performance_summary"),
            "meme_hunter_evidence": record.get("meme_hunter_evidence"),
            "special_labels": dict(record.get("special_labels") or {}),
            "source_versions": dict(record.get("source_versions") or {}),
            "source_payload": record,
        })
    return rows


def candidate_universe_rows(
    universe: dict[str, Any],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    if str(universe.get("version") or "") != "wallet-s10a0-v1":
        raise ValueError("unsupported Stage-10A-0 universe version")
    fingerprint = str(universe.get("universe_fingerprint") or "")
    if not fingerprint:
        raise ValueError("candidate universe requires fingerprint")

    source = universe.get("source") or {}
    scan = universe.get("scan") or {}
    snapshot_row = {
        "universe_fingerprint": fingerprint,
        "version": universe["version"],
        "chain": universe.get("chain") or "solana",
        "source_kind": source.get("kind"),
        "source_label": source.get("label"),
        "source_origin": source.get("origin"),
        "requested_start_slot": int(scan["requested_start_slot"]),
        "requested_end_slot": int(scan["requested_end_slot"]),
        "cutoff_unix": (
            None
            if scan.get("cutoff_unix") is None
            else int(scan["cutoff_unix"])
        ),
        "scanned_block_count": int(
            scan.get("scanned_block_count") or 0
        ),
        "transaction_count": int(scan.get("transaction_count") or 0),
        "eligible_transaction_count": int(
            scan.get("eligible_transaction_count") or 0
        ),
        "candidate_wallet_count": int(
            universe.get("candidate_wallet_count") or 0
        ),
        "source_payload": universe,
    }

    candidate_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    for record in universe.get("records") or []:
        wallet = str(record.get("wallet") or "")
        if not wallet:
            raise ValueError("candidate record requires wallet")
        candidate_rows.append({
            "universe_fingerprint": fingerprint,
            "wallet": wallet,
            "record_fingerprint": record["record_fingerprint"],
            "chain": record.get("chain") or "solana",
            "discovered_at_unix": int(record["discovered_at"]),
            "first_observed_at_unix": int(record["first_observed_at"]),
            "last_observed_at_unix": int(record["last_observed_at"]),
            "first_observed_slot": int(record["first_observed_slot"]),
            "last_observed_slot": int(record["last_observed_slot"]),
            "activity_count": int(record.get("activity_count") or 0),
            "distinct_changed_mint_count": int(
                record.get("distinct_changed_mint_count") or 0
            ),
            "evidence_signature_count": int(
                record.get("evidence_signature_count") or 0
            ),
            "discovery_source": record.get("discovery_source"),
            "discovery_reason": record.get("discovery_reason"),
            "changed_mints": list(record.get("changed_mints") or []),
            "evidence_signatures": list(
                record.get("evidence_signatures") or []
            ),
            "source_payload": record,
        })
        for evidence in record.get("evidence") or []:
            evidence_rows.append({
                "universe_fingerprint": fingerprint,
                "wallet": wallet,
                "signature": evidence["signature"],
                "slot": int(evidence["slot"]),
                "block_time_unix": int(evidence["block_time"]),
                "discovery_source": evidence.get("discovery_source"),
                "discovery_reason": evidence.get("discovery_reason"),
                "changed_mints": list(
                    evidence.get("changed_mints") or []
                ),
                "evidence_payload": evidence,
            })

    return snapshot_row, candidate_rows, evidence_rows


def candidate_refinement_rows(
    universe: dict[str, Any],
    refinement: dict[str, Any],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    snapshot, candidates, evidence = candidate_universe_rows(universe)

    universe_fp = str(universe.get("universe_fingerprint") or "")
    if str(refinement.get("source_universe_fingerprint") or "") != universe_fp:
        raise ValueError("refinement source universe does not match universe")
    if str(refinement.get("version") or "") != "wallet-s10a1a-v1":
        raise ValueError("unsupported Stage-10A-1A refinement version")

    snapshot.update({
        "refinement_version": refinement["version"],
        "refinement_fingerprint": refinement["refinement_fingerprint"],
        "trader_candidate_wallet_count": int(
            refinement.get("trader_candidate_wallet_count") or 0
        ),
        "non_trader_activity_wallet_count": int(
            refinement.get("non_trader_activity_wallet_count") or 0
        ),
        "meme_buy_candidate_wallet_count": int(
            refinement.get("meme_buy_candidate_wallet_count") or 0
        ),
        "refinement_payload": refinement,
    })

    refinement_by_wallet = {
        str(row["wallet"]): row
        for row in refinement.get("records") or []
    }
    for row in candidates:
        refined = refinement_by_wallet.get(str(row["wallet"]))
        if refined is None:
            raise ValueError(
                f"missing refinement record for wallet {row['wallet']}"
            )
        row.update({
            "refinement_version": refined["version"],
            "refinement_record_fingerprint": refined[
                "record_fingerprint"
            ],
            "candidate_status": refined["candidate_status"],
            "trader_candidate": bool(refined["trader_candidate"]),
            "meme_buy_candidate": bool(
                refined["meme_buy_candidate"]
            ),
            "historical_backfill_eligible": bool(
                refined["historical_backfill_eligible"]
            ),
            "trader_event_count": int(
                refined.get("trader_event_count") or 0
            ),
            "buy_event_count": int(
                refined.get("buy_event_count") or 0
            ),
            "sell_event_count": int(
                refined.get("sell_event_count") or 0
            ),
            "meme_buy_event_count": int(
                refined.get("meme_buy_event_count") or 0
            ),
            "observed_base_assets": list(
                refined.get("observed_base_assets") or []
            ),
            "refinement_payload": refined,
        })

    refinement_events = {
        (str(record["wallet"]), str(event["signature"])): event
        for record in refinement.get("records") or []
        for event in record.get("events") or []
    }
    for row in evidence:
        key = (str(row["wallet"]), str(row["signature"]))
        refined = refinement_events.get(key)
        if refined is None:
            raise ValueError(
                "missing refinement event for "
                f"{row['wallet']}:{row['signature']}"
            )
        row.update({
            "refinement_version": refined["version"],
            "refinement_event_fingerprint": refined[
                "event_fingerprint"
            ],
            "stage2_version": refined.get("stage2_version"),
            "event_type": refined.get("event_type"),
            "side": refined.get("side"),
            "base_asset": refined.get("base_asset"),
            "quote_asset": refined.get("quote_asset"),
            "confidence": refined.get("confidence"),
            "trader_candidate_event": bool(
                refined["trader_candidate_event"]
            ),
            "meme_buy_candidate_event": bool(
                refined["meme_buy_candidate_event"]
            ),
            "refinement_reason": refined.get("refinement_reason"),
            "stage2_normalized_payload": refined.get(
                "normalized_event"
            ),
        })

    return snapshot, candidates, evidence


def raw_wallet_transaction_row(
    wallet: str,
    tx: dict[str, Any],
) -> dict[str, Any]:
    wallet = str(wallet or "")
    transaction = tx.get("transaction") or {}
    signatures = transaction.get("signatures") or []
    signature = str(signatures[0]) if signatures else ""
    if not wallet or not signature:
        raise ValueError(
            "historical raw transaction requires wallet and signature"
        )
    return {
        "wallet": wallet,
        "signature": signature,
        "chain": "solana",
        "source": "helius_gtfa",
        "slot": tx.get("slot"),
        "block_time_unix": tx.get("blockTime"),
        "raw_payload": tx,
    }


def normalized_history_row(
    event: dict[str, Any],
) -> dict[str, Any]:
    wallet = str(event.get("wallet") or "")
    signature = str(event.get("signature") or "")
    block_time = event.get("block_time")
    if not wallet or not signature or block_time is None:
        raise ValueError(
            "normalized history event requires wallet, signature, block_time"
        )
    return {
        "wallet": wallet,
        "signature": signature,
        "stage2_version": event.get("version") or "wallet-s2-v1",
        "chain": event.get("chain") or "solana",
        "slot": event.get("slot"),
        "block_time_unix": int(block_time),
        "event_type": event.get("event_type"),
        "side": event.get("side"),
        "base_asset": event.get("base_asset"),
        "quote_asset": event.get("quote_asset"),
        "base_amount": event.get("base_amount"),
        "quote_amount": event.get("quote_amount"),
        "usd_notional": event.get("usd_notional"),
        "execution_price": event.get("execution_price_quote"),
        "network_fee_lamports": event.get("network_fee_lamports"),
        "normalized_payload": event,
    }


def wallet_event_row(event: dict[str, Any]) -> dict[str, Any]:
    wallet = str(event.get("wallet") or "")
    signature = str(event.get("signature") or "")
    if not wallet or not signature:
        raise ValueError("wallet event requires wallet and signature")
    block_time = event.get("block_time")
    if block_time is None:
        raise ValueError("wallet event requires block_time")

    live_event_id = str(
        event.get("live_event_id") or f"{wallet}:{signature}"
    )
    idempotency_key = str(
        event.get("idempotency_key") or f"{wallet}:{signature}"
    )

    return {
        "live_event_id": live_event_id,
        "idempotency_key": idempotency_key,
        "wallet": wallet,
        "signature": signature,
        "chain": event.get("chain") or "solana",
        "event_type": event.get("event_type"),
        "side": event.get("side"),
        "base_asset": event.get("base_asset"),
        "quote_asset": event.get("quote_asset"),
        "base_amount": event.get("base_amount"),
        "quote_amount": event.get("quote_amount"),
        "usd_notional": event.get("usd_notional"),
        "execution_price": event.get("execution_price_quote"),
        "block_time_unix": int(block_time),
        "slot": event.get("slot"),
        "primary_segment": event.get("primary_segment"),
        "qualifying_segments": list(
            event.get("qualifying_segments") or []
        ),
        "meme_hunter_evidence": event.get("meme_hunter_evidence"),
        "special_labels": dict(event.get("special_labels") or {}),
        "registry_snapshot_id": event.get("registry_snapshot_id"),
        "registry_snapshot_fingerprint": event.get(
            "registry_snapshot_fingerprint"
        ),
        "registry_record_fingerprint": event.get(
            "registry_record_fingerprint"
        ),
        "normalized_payload": event,
    }


def signal_snapshot_row(snapshot: dict[str, Any]) -> dict[str, Any]:
    if str(snapshot.get("version") or "") != "wallet-s9-v1":
        raise ValueError("unsupported Stage-9 snapshot version")
    fingerprint = str(snapshot.get("snapshot_fingerprint") or "")
    if not fingerprint:
        raise ValueError("Stage-9 snapshot requires fingerprint")
    return {
        "snapshot_fingerprint": fingerprint,
        "stage9_version": snapshot["version"],
        "chain": snapshot.get("chain") or "solana",
        "as_of_unix": int(snapshot["as_of"]),
        "signal_count": int(snapshot.get("signal_count") or 0),
        "source_payload": snapshot,
    }


def signal_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    parent = signal_snapshot_row(snapshot)
    rows: list[dict[str, Any]] = []
    for signal in snapshot.get("signals") or []:
        if str(signal.get("version") or "") != "wallet-s9-v1":
            raise ValueError("unsupported Stage-9 signal version")
        if int(signal.get("as_of")) != int(snapshot["as_of"]):
            raise ValueError(
                "Stage-9 signal timestamp must equal snapshot timestamp"
            )
        fingerprint = str(signal.get("signal_fingerprint") or "")
        if not fingerprint:
            raise ValueError("Stage-9 signal requires fingerprint")

        activity = signal.get("qualified_wallet_activity") or {}
        usd = signal.get("validated_usd_flow") or {}
        persistence = signal.get("persistence") or {}
        meme = signal.get("meme_hunter_evidence") or {}
        coverage = str(usd.get("coverage") or "UNAVAILABLE")
        usd_net = (
            usd.get("validated_usd_net_notional")
            if coverage != "UNAVAILABLE"
            else None
        )

        rows.append({
            "signal_fingerprint": fingerprint,
            "snapshot_fingerprint": parent["snapshot_fingerprint"],
            "stage9_version": signal["version"],
            "chain": signal.get("chain") or "solana",
            "base_asset": signal["base_asset"],
            "as_of_unix": int(signal["as_of"]),
            "state": signal["state"],
            "state_basis_window": signal["state_basis_window"],
            "unique_wallet_count": int(
                activity.get("unique_wallet_count") or 0
            ),
            "buy_wallet_count": int(
                activity.get("buy_wallet_count") or 0
            ),
            "sell_wallet_count": int(
                activity.get("sell_wallet_count") or 0
            ),
            "wallet_net_count": int(
                activity.get("wallet_net_count") or 0
            ),
            "net_base_amount": (
                signal.get("base_flow") or {}
            ).get("net_base_amount"),
            "usd_coverage": coverage,
            "validated_usd_net_notional": usd_net,
            "usd_direction": str(
                usd.get("direction") or "UNAVAILABLE"
            ),
            "spans_15m_directionally": bool(
                persistence.get("spans_15m_directionally")
            ),
            "spans_1h_directionally": bool(
                persistence.get("spans_1h_directionally")
            ),
            "meme_evidence_wallet_count": int(
                meme.get("evidence_wallet_count") or 0
            ),
            "source_payload": signal,
        })
    return rows


def price_bar_row(row: dict[str, Any]) -> dict[str, Any]:
    token = str(row.get("base_asset") or "")
    source = str(row.get("source") or "")
    venue = str(row.get("venue") or "")
    if not token or not source or not venue:
        raise ValueError(
            "price bar requires base_asset, source, and venue"
        )
    return {
        "base_asset": token,
        "venue": venue,
        "source": source,
        "source_kind": str(row.get("source_kind") or "REAL"),
        "quote_asset": row.get("quote_asset"),
        "interval_seconds": int(row["interval_seconds"]),
        "timestamp_unix": int(row["timestamp_unix"]),
        "open": str(row["open"]),
        "high": str(row["high"]),
        "low": str(row["low"]),
        "close": str(row["close"]),
        "volume": (
            None if row.get("volume") is None else str(row["volume"])
        ),
    }


class SupabaseRestClient:
    """Minimal server-side PostgREST client for Wallet Detector persistence."""

    def __init__(
        self,
        *,
        url: str,
        secret_key: str,
        transport: Transport | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        url = str(url or "").strip().rstrip("/")
        secret_key = str(secret_key or "").strip()
        if not url.startswith("https://"):
            raise ValueError("Supabase URL must be HTTPS")
        if not secret_key:
            raise ValueError("Supabase server secret key is required")
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")

        self.url = url
        self.secret_key = secret_key
        self.transport = transport or _default_transport
        self.batch_size = int(batch_size)

    @classmethod
    def from_env(cls) -> "SupabaseRestClient":
        url = os.environ.get("WALLET_SUPABASE_URL") or os.environ.get(
            "SUPABASE_URL"
        )
        secret = (
            os.environ.get("WALLET_SUPABASE_SECRET_KEY")
            or os.environ.get("SUPABASE_SECRET_KEY")
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        )
        if not url:
            raise RuntimeError(
                "WALLET_SUPABASE_URL or SUPABASE_URL is required"
            )
        if not secret:
            raise RuntimeError(
                "WALLET_SUPABASE_SECRET_KEY, SUPABASE_SECRET_KEY, "
                "or SUPABASE_SERVICE_ROLE_KEY is required"
            )
        return cls(url=url, secret_key=secret)

    def _headers(self, *, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.secret_key,
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str] | None = None,
        payload: Any = None,
        prefer: str | None = None,
    ) -> bytes:
        suffix = ""
        if query:
            suffix = "?" + urlencode(query, safe=",.*()")
        url = f"{self.url}{path}{suffix}"
        body = None if payload is None else _json_bytes(payload)
        status, raw = self.transport(
            method,
            url,
            self._headers(prefer=prefer),
            body,
        )
        if not 200 <= int(status) < 300:
            detail = raw.decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Supabase request failed {status}: {detail}"
            )
        return raw

    def upsert_rows(
        self,
        table: str,
        rows: Iterable[dict[str, Any]],
        *,
        on_conflict: str,
    ) -> int:
        materialized = [dict(row) for row in rows]
        if not materialized:
            return 0
        count = 0
        for batch in _chunks(materialized, self.batch_size):
            self._request(
                "POST",
                f"/rest/v1/{table}",
                query={"on_conflict": on_conflict},
                payload=batch,
                prefer="resolution=merge-duplicates,return=minimal",
            )
            count += len(batch)
        return count

    def persist_candidate_universe(
        self,
        universe: dict[str, Any],
    ) -> dict[str, int]:
        snapshot, candidates, evidence = candidate_universe_rows(universe)
        snapshot_count = self.upsert_rows(
            "wallet_universe_snapshots",
            [snapshot],
            on_conflict="universe_fingerprint",
        )
        candidate_count = self.upsert_rows(
            "wallet_universe_candidates",
            candidates,
            on_conflict="universe_fingerprint,wallet",
        )
        evidence_count = self.upsert_rows(
            "wallet_universe_evidence",
            evidence,
            on_conflict="universe_fingerprint,wallet,signature",
        )
        return {
            "wallet_universe_snapshot_rows": snapshot_count,
            "wallet_universe_candidate_rows": candidate_count,
            "wallet_universe_evidence_rows": evidence_count,
        }

    def persist_candidate_refinement(
        self,
        universe: dict[str, Any],
        refinement: dict[str, Any],
    ) -> dict[str, int]:
        snapshot, candidates, evidence = candidate_refinement_rows(
            universe,
            refinement,
        )
        snapshot_count = self.upsert_rows(
            "wallet_universe_snapshots",
            [snapshot],
            on_conflict="universe_fingerprint",
        )
        candidate_count = self.upsert_rows(
            "wallet_universe_candidates",
            candidates,
            on_conflict="universe_fingerprint,wallet",
        )
        evidence_count = self.upsert_rows(
            "wallet_universe_evidence",
            evidence,
            on_conflict="universe_fingerprint,wallet,signature",
        )
        return {
            "wallet_universe_snapshot_rows": snapshot_count,
            "wallet_universe_candidate_rows": candidate_count,
            "wallet_universe_evidence_rows": evidence_count,
        }

    def persist_historical_raw(
        self,
        raw_by_wallet: dict[str, Iterable[dict[str, Any]]],
    ) -> int:
        rows = [
            raw_wallet_transaction_row(wallet, tx)
            for wallet, transactions in sorted(raw_by_wallet.items())
            for tx in transactions
        ]
        return self.upsert_rows(
            "historical_wallet_transactions",
            rows,
            on_conflict="wallet,signature",
        )

    def persist_normalized_history(
        self,
        normalized_by_wallet: dict[str, Iterable[dict[str, Any]]],
    ) -> int:
        rows = [
            normalized_history_row(event)
            for _wallet, events in sorted(normalized_by_wallet.items())
            for event in events
        ]
        return self.upsert_rows(
            "normalized_wallet_history",
            rows,
            on_conflict="wallet,signature",
        )

    def persist_registry_snapshots(
        self,
        snapshots: Iterable[dict[str, Any]],
    ) -> dict[str, int]:
        materialized = [dict(row) for row in snapshots]
        snapshot_rows = [
            _registry_snapshot_row(row) for row in materialized
        ]
        record_rows = [
            record
            for snapshot in materialized
            for record in _registry_record_rows(snapshot)
        ]
        snapshot_count = self.upsert_rows(
            "registry_snapshots",
            snapshot_rows,
            on_conflict="snapshot_id",
        )
        record_count = self.upsert_rows(
            "wallet_registry",
            record_rows,
            on_conflict="snapshot_id,wallet",
        )
        return {
            "registry_snapshot_rows": snapshot_count,
            "wallet_registry_rows": record_count,
        }

    def persist_registry_snapshot(
        self,
        snapshot: dict[str, Any],
    ) -> dict[str, int]:
        return self.persist_registry_snapshots([snapshot])

    def persist_wallet_events(
        self,
        events: Iterable[dict[str, Any]],
    ) -> int:
        return self.upsert_rows(
            "wallet_events",
            [wallet_event_row(row) for row in events],
            on_conflict="wallet,signature",
        )

    def persist_signal_snapshots(
        self,
        snapshots: Iterable[dict[str, Any]],
    ) -> dict[str, int]:
        snapshots_list = [dict(row) for row in snapshots]
        snapshot_rows = [
            signal_snapshot_row(row) for row in snapshots_list
        ]
        signals = [
            signal
            for snapshot in snapshots_list
            for signal in signal_rows(snapshot)
        ]
        snapshot_count = self.upsert_rows(
            "smart_money_signal_snapshots",
            snapshot_rows,
            on_conflict="snapshot_fingerprint",
        )
        signal_count = self.upsert_rows(
            "smart_money_signals",
            signals,
            on_conflict="signal_fingerprint",
        )
        return {
            "signal_snapshot_rows": snapshot_count,
            "smart_money_signal_rows": signal_count,
        }

    def persist_price_bars(
        self,
        rows: Iterable[dict[str, Any]],
    ) -> int:
        return self.upsert_rows(
            "token_price_bars",
            [price_bar_row(row) for row in rows],
            on_conflict=(
                "base_asset,venue,interval_seconds,timestamp_unix"
            ),
        )
