from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping

from research.wallet_s7_qualified_registry import verify_registry_snapshot

STAGE8_5_VERSION = "wallet-s8.5-v1"
VALID_MODES = {"LIVE", "DEMO", "OFFLINE"}
WINDOWS = ("5m", "15m", "1h")


def _iso_utc(timestamp: int | None = None) -> str:
    if timestamp is None:
        return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
    return (
        datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _symbol_for(
    mint: str,
    resolver: Mapping[str, str] | Callable[[str], str | None] | None,
) -> str:
    if resolver is None:
        return mint[:6] if mint else "UNKNOWN"

    if callable(resolver):
        value = resolver(mint)
    else:
        value = resolver.get(mint)

    return str(value).strip() if value else (mint[:6] if mint else "UNKNOWN")


def _camel_symbol(
    row: dict[str, Any],
    *,
    symbol_resolver: Mapping[str, str] | Callable[[str], str | None] | None,
) -> dict[str, Any]:
    mint = str(row.get("base_asset") or "")
    segments = {}
    for segment, counts in sorted(
        (row.get("segment_membership_wallet_counts") or {}).items()
    ):
        segments[str(segment)] = {
            "buyWalletCount": int(counts.get("buy_wallet_count") or 0),
            "sellWalletCount": int(counts.get("sell_wallet_count") or 0),
        }

    return {
        "symbol": _symbol_for(mint, symbol_resolver),
        "baseAsset": mint,
        "flowState": str(row.get("flow_state") or "BALANCED"),
        "eventCount": int(row.get("event_count") or 0),
        "buyEventCount": int(row.get("buy_event_count") or 0),
        "sellEventCount": int(row.get("sell_event_count") or 0),
        "uniqueWalletCount": int(row.get("unique_wallet_count") or 0),
        "buyWalletCount": int(row.get("buy_wallet_count") or 0),
        "sellWalletCount": int(row.get("sell_wallet_count") or 0),
        "netBaseAmount": str(row.get("net_base_amount") or "0"),
        "usdBuyNotional": str(row.get("usd_buy_notional") or "0"),
        "usdSellNotional": str(row.get("usd_sell_notional") or "0"),
        "usdNetNotional": str(row.get("usd_net_notional") or "0"),
        "unpricedEventCount": int(row.get("unpriced_event_count") or 0),
        "lastActivityTime": (
            int(row["last_activity_time"])
            if row.get("last_activity_time") is not None
            else None
        ),
        "segmentMembership": segments,
    }


def _window_payload(
    row: dict[str, Any],
    *,
    symbol_resolver: Mapping[str, str] | Callable[[str], str | None] | None,
) -> dict[str, Any]:
    return {
        "windowSeconds": int(row.get("window_seconds") or 0),
        "tradeEventCount": int(row.get("trade_event_count") or 0),
        "symbolCount": int(row.get("symbol_count") or 0),
        "symbols": [
            _camel_symbol(symbol, symbol_resolver=symbol_resolver)
            for symbol in row.get("symbols") or []
        ],
    }


def _recent_event(
    event: dict[str, Any],
    *,
    symbol_resolver: Mapping[str, str] | Callable[[str], str | None] | None,
) -> dict[str, Any]:
    mint = str(event.get("base_asset") or "")
    return {
        "id": str(
            event.get("live_event_id")
            or event.get("idempotency_key")
            or f"{event.get('wallet')}:{event.get('signature')}"
        ),
        "blockTime": int(event["block_time"]),
        "wallet": str(event.get("wallet") or ""),
        "side": str(event.get("side") or ""),
        "symbol": _symbol_for(mint, symbol_resolver),
        "baseAsset": mint,
        "usdNotional": (
            str(event["usd_notional"])
            if event.get("usd_notional") is not None
            else None
        ),
        "primarySegment": event.get("primary_segment"),
        "qualifyingSegments": list(event.get("qualifying_segments") or []),
    }


def build_dashboard_payload(
    *,
    registry_snapshot: dict[str, Any],
    monitor_status: dict[str, Any],
    aggregation: dict[str, Any],
    events: Iterable[dict[str, Any]],
    mode: str = "LIVE",
    source_message: str = "Connected to Stage 8 runtime backend.",
    generated_at: int | None = None,
    recent_limit: int = 50,
    symbol_resolver: Mapping[str, str] | Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    """Convert Stage-7/8 runtime output into the Stage-8.5 UI JSON contract."""
    verify_registry_snapshot(registry_snapshot)

    mode = str(mode).upper()
    if mode not in VALID_MODES:
        raise ValueError(f"unsupported dashboard mode: {mode}")
    if recent_limit < 0:
        raise ValueError("recent_limit must be >= 0")

    snapshot_id = str(registry_snapshot.get("snapshot_id") or "")
    snapshot_fingerprint = str(
        registry_snapshot.get("snapshot_fingerprint") or ""
    )
    if str(monitor_status.get("registry_snapshot_id") or "") != snapshot_id:
        raise ValueError("monitor status registry snapshot id mismatch")
    if (
        str(monitor_status.get("registry_snapshot_fingerprint") or "")
        != snapshot_fingerprint
    ):
        raise ValueError("monitor status registry fingerprint mismatch")

    windows = aggregation.get("windows") or {}
    missing_windows = [key for key in WINDOWS if key not in windows]
    if missing_windows:
        raise ValueError(
            f"aggregation missing required windows: {missing_windows}"
        )

    recent = [
        dict(row)
        for row in events
        if row.get("event_type") == "SWAP"
        and row.get("side") in {"BUY", "SELL"}
        and row.get("block_time") is not None
        and row.get("base_asset")
    ]
    recent.sort(
        key=lambda row: (
            int(row["block_time"]),
            int(row.get("slot") or 0),
            str(row.get("idempotency_key") or ""),
        ),
        reverse=True,
    )
    if recent_limit:
        recent = recent[:recent_limit]
    else:
        recent = []

    return {
        "version": STAGE8_5_VERSION,
        "mode": mode,
        "generatedAt": _iso_utc(generated_at),
        "sourceMessage": str(source_message),
        "registry": {
            "snapshotId": snapshot_id,
            "activeWalletCount": int(
                registry_snapshot.get("active_wallet_count") or 0
            ),
            "statusCounts": dict(
                registry_snapshot.get("status_counts") or {}
            ),
            "segmentCounts": dict(
                registry_snapshot.get("segment_counts") or {}
            ),
        },
        "monitor": {
            "activeWalletCount": int(
                monitor_status.get("active_wallet_count") or 0
            ),
            "ingestAttempts": int(
                monitor_status.get("ingest_attempts") or 0
            ),
            "storedEventCount": int(
                monitor_status.get("stored_event_count") or 0
            ),
            "storedTradeEventCount": int(
                monitor_status.get("stored_trade_event_count") or 0
            ),
            "duplicateWalletEventCount": int(
                monitor_status.get("duplicate_wallet_event_count") or 0
            ),
            "normalizationErrorCount": int(
                monitor_status.get("normalization_error_count") or 0
            ),
            "latestBlockTime": (
                int(monitor_status["latest_block_time"])
                if monitor_status.get("latest_block_time") is not None
                else None
            ),
        },
        "windows": {
            key: _window_payload(
                windows[key],
                symbol_resolver=symbol_resolver,
            )
            for key in WINDOWS
        },
        "recentEvents": [
            _recent_event(row, symbol_resolver=symbol_resolver)
            for row in recent
        ],
    }
