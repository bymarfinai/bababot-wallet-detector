from __future__ import annotations

from collections import deque
from typing import Any, Iterable

from research.wallet_s3_position_reconstruction import (
    EPS,
    ZERO,
    PositionEpisode,
    _d,
    _event_order,
    _s,
)

STREAM_STAGE3_VERSION = "wallet-s3-stream-v1"
RECENT_SIGNATURE_WINDOW = 256


def empty_stream_state(wallet: str) -> dict[str, Any]:
    return {
        "version": STREAM_STAGE3_VERSION,
        "wallet": str(wallet),
        "sequence": [],
        "open_positions": [],
        "terminal_episode_count": 0,
        "scorable_closed_episode_count": 0,
        "anomaly_count": 0,
        "recent_signatures": [],
        "last_event_block_time": None,
        "last_event_slot": None,
    }


def _position_to_state(position: PositionEpisode) -> dict[str, Any]:
    return {
        "wallet": position.wallet,
        "base_asset": position.base_asset,
        "quote_asset": position.quote_asset,
        "sequence": int(position.sequence),
        "opened_at": position.opened_at,
        "opened_slot": position.opened_slot,
        "quote_is_usd": bool(position.quote_is_usd),
        "open_qty": _s(position.open_qty),
        "open_cost_quote": _s(position.open_cost_quote),
        "total_buy_qty": _s(position.total_buy_qty),
        "total_buy_cost_quote": _s(position.total_buy_cost_quote),
        "total_sell_qty": _s(position.total_sell_qty),
        "total_sell_proceeds_quote": _s(position.total_sell_proceeds_quote),
        "realized_cost_quote": _s(position.realized_cost_quote),
        "realized_proceeds_quote": _s(position.realized_proceeds_quote),
        "realized_pnl_quote": _s(position.realized_pnl_quote),
        "buy_count": int(position.buy_count),
        "sell_count": int(position.sell_count),
        "network_fee_lamports": int(position.network_fee_lamports),
        "last_time": position.last_time,
        "closed_at": position.closed_at,
        "close_slot": position.close_slot,
        "status": position.status,
        "contamination_reasons": list(position.contamination_reasons),
    }


def _position_from_state(row: dict[str, Any]) -> PositionEpisode:
    position = PositionEpisode(
        wallet=str(row["wallet"]),
        base_asset=str(row["base_asset"]),
        quote_asset=str(row["quote_asset"]),
        sequence=int(row["sequence"]),
        opened_at=row.get("opened_at"),
        opened_slot=row.get("opened_slot"),
        quote_is_usd=bool(row.get("quote_is_usd")),
    )
    position.open_qty = _d(row.get("open_qty"))
    position.open_cost_quote = _d(row.get("open_cost_quote"))
    position.total_buy_qty = _d(row.get("total_buy_qty"))
    position.total_buy_cost_quote = _d(row.get("total_buy_cost_quote"))
    position.total_sell_qty = _d(row.get("total_sell_qty"))
    position.total_sell_proceeds_quote = _d(
        row.get("total_sell_proceeds_quote")
    )
    position.realized_cost_quote = _d(row.get("realized_cost_quote"))
    position.realized_proceeds_quote = _d(
        row.get("realized_proceeds_quote")
    )
    position.realized_pnl_quote = _d(row.get("realized_pnl_quote"))
    position.buy_count = int(row.get("buy_count") or 0)
    position.sell_count = int(row.get("sell_count") or 0)
    position.network_fee_lamports = int(
        row.get("network_fee_lamports") or 0
    )
    position.last_time = row.get("last_time")
    position.closed_at = row.get("closed_at")
    position.close_slot = row.get("close_slot")
    position.status = str(row.get("status") or "OPEN")
    position.contamination_reasons = [
        str(x) for x in (row.get("contamination_reasons") or [])
    ]
    # Signatures are deliberately not retained in streaming state. They are
    # evidence transport, not required to reconstruct inventory or PnL.
    position.signatures = []
    return position


def _restore(
    state: dict[str, Any],
    wallet: str,
) -> tuple[
    dict[tuple[str, str], PositionEpisode],
    dict[tuple[str, str], int],
    deque[str],
]:
    if str(state.get("version") or "") != STREAM_STAGE3_VERSION:
        raise ValueError("unsupported streaming Stage-3 state version")
    if str(state.get("wallet") or "") != str(wallet):
        raise ValueError("streaming Stage-3 wallet mismatch")

    open_positions: dict[tuple[str, str], PositionEpisode] = {}
    for row in state.get("open_positions") or []:
        position = _position_from_state(dict(row))
        key = (position.base_asset, position.quote_asset)
        if key in open_positions:
            raise ValueError(f"duplicate open-position key in state: {key}")
        open_positions[key] = position

    sequence = {
        (str(row["base_asset"]), str(row["quote_asset"])): int(
            row["sequence"]
        )
        for row in (state.get("sequence") or [])
    }
    recent = deque(
        (str(x) for x in (state.get("recent_signatures") or [])),
        maxlen=RECENT_SIGNATURE_WINDOW,
    )
    return open_positions, sequence, recent


def consume_stream_page(
    state: dict[str, Any],
    events: Iterable[dict[str, Any]],
    *,
    wallet: str,
) -> dict[str, Any]:
    """Consume one chronological normalized page and emit only closed trades.

    Raw transactions and normalized events are intentionally not retained.
    Only the minimal open-position state needed for the next page survives.
    """

    open_positions, sequence, recent = _restore(state, wallet)
    recent_set = set(recent)
    rows = _event_order(events)
    emitted: list[dict[str, Any]] = []
    terminal_total = int(state.get("terminal_episode_count") or 0)
    scorable_total = int(state.get("scorable_closed_episode_count") or 0)
    anomaly_total = int(state.get("anomaly_count") or 0)
    anomalies_added = 0

    def anomaly() -> None:
        nonlocal anomaly_total, anomalies_added
        anomaly_total += 1
        anomalies_added += 1

    def open_for_base(base: str) -> list[PositionEpisode]:
        return [
            position
            for (candidate_base, _quote), position in open_positions.items()
            if candidate_base == base
        ]

    last_block_time = state.get("last_event_block_time")
    last_slot = state.get("last_event_slot")

    for event in rows:
        signature = str(event.get("signature") or "")
        if signature and signature in recent_set:
            anomaly()
            continue
        if signature:
            if len(recent) == RECENT_SIGNATURE_WINDOW:
                removed = recent[0]
                recent_set.discard(removed)
            recent.append(signature)
            recent_set.add(signature)

        event_wallet = str(event.get("wallet") or wallet)
        if event_wallet and event_wallet != wallet:
            anomaly()
            continue

        event_type = str(event.get("event_type") or "")
        side = str(event.get("side") or "NONE")

        if event.get("block_time") is not None:
            last_block_time = int(event["block_time"])
        if event.get("slot") is not None:
            last_slot = int(event["slot"])

        if event_type in {"TRANSFER_IN", "TRANSFER_OUT"}:
            asset = str(event.get("asset") or "")
            amount = abs(_d(event.get("amount")))
            affected = open_for_base(asset)
            if not affected:
                continue

            if len(affected) > 1:
                for position in affected:
                    position.contaminate("MIXED_QUOTE_EXTERNAL_FLOW")
                anomaly()
                continue

            position = affected[0]
            position.contaminate(event_type + "_DURING_POSITION")
            position.network_fee_lamports += int(
                event.get("network_fee_lamports") or 0
            )
            position.last_time = event.get("block_time")

            if event_type == "TRANSFER_IN":
                anomaly()
                continue

            if amount <= ZERO or position.open_qty <= ZERO:
                continue

            reduction = min(amount, position.open_qty)
            avg_cost = position.open_cost_quote / position.open_qty
            position.open_qty -= reduction
            position.open_cost_quote -= avg_cost * reduction
            anomaly()

            if amount - reduction > EPS:
                position.contaminate("TRANSFER_OUT_EXCEEDS_TRACKED_QTY")
                anomaly()

            if position.open_qty <= EPS:
                position.open_qty = ZERO
                position.open_cost_quote = ZERO
                position.status = "TRANSFERRED_OUT"
                position.closed_at = event.get("block_time")
                position.close_slot = event.get("slot")
                terminal_total += 1
                del open_positions[
                    (position.base_asset, position.quote_asset)
                ]
            continue

        if event_type != "SWAP" or side not in {"BUY", "SELL"}:
            continue

        base = str(event.get("base_asset") or "")
        quote = str(event.get("quote_asset") or "")
        base_qty = abs(_d(event.get("base_amount")))
        quote_amount = abs(_d(event.get("quote_amount")))
        if not base or not quote or base_qty <= ZERO or quote_amount <= ZERO:
            anomaly()
            continue

        key = (base, quote)

        if side == "BUY":
            other_quotes = [
                position
                for position in open_for_base(base)
                if position.quote_asset != quote
            ]
            if other_quotes:
                for position in other_quotes:
                    position.contaminate("MIXED_QUOTE_INVENTORY")
                anomaly()

            position = open_positions.get(key)
            if position is None:
                sequence[key] = sequence.get(key, 0) + 1
                position = PositionEpisode(
                    wallet=event_wallet,
                    base_asset=base,
                    quote_asset=quote,
                    sequence=sequence[key],
                    opened_at=event.get("block_time"),
                    opened_slot=event.get("slot"),
                    quote_is_usd=bool(event.get("quote_is_usd")),
                )
                open_positions[key] = position

            if other_quotes:
                position.contaminate("MIXED_QUOTE_INVENTORY")

            position.open_qty += base_qty
            position.open_cost_quote += quote_amount
            position.total_buy_qty += base_qty
            position.total_buy_cost_quote += quote_amount
            position.buy_count += 1
            position.network_fee_lamports += int(
                event.get("network_fee_lamports") or 0
            )
            position.last_time = event.get("block_time")
            continue

        position = open_positions.get(key)
        if position is None:
            others = open_for_base(base)
            if others:
                for other in others:
                    other.contaminate("SELL_WITH_DIFFERENT_QUOTE")
            anomaly()
            continue

        cover_qty = min(base_qty, position.open_qty)
        if cover_qty <= ZERO:
            anomaly()
            continue

        avg_cost = position.open_cost_quote / position.open_qty
        cost = avg_cost * cover_qty
        covered_proceeds = quote_amount * (cover_qty / base_qty)

        position.open_qty -= cover_qty
        position.open_cost_quote -= cost
        position.total_sell_qty += cover_qty
        position.total_sell_proceeds_quote += covered_proceeds
        position.realized_cost_quote += cost
        position.realized_proceeds_quote += covered_proceeds
        position.realized_pnl_quote += covered_proceeds - cost
        position.sell_count += 1
        position.network_fee_lamports += int(
            event.get("network_fee_lamports") or 0
        )
        position.last_time = event.get("block_time")

        excess = base_qty - cover_qty
        if excess > EPS:
            position.contaminate("OVERSELL")
            anomaly()

        if position.open_qty <= EPS:
            position.open_qty = ZERO
            position.open_cost_quote = ZERO
            has_external_cost_break = any(
                reason.startswith("TRANSFER")
                or reason == "MIXED_QUOTE_EXTERNAL_FLOW"
                for reason in position.contamination_reasons
            )
            if not has_external_cost_break:
                position.realized_cost_quote = position.total_buy_cost_quote
                position.realized_pnl_quote = (
                    position.realized_proceeds_quote
                    - position.realized_cost_quote
                )
            position.status = (
                "CLOSED"
                if not position.contamination_reasons
                else "CLOSED_CONTAMINATED"
            )
            position.closed_at = event.get("block_time")
            position.close_slot = event.get("slot")
            terminal_total += 1
            if position.eligible_for_performance_metrics:
                emitted.append(position.to_dict())
                scorable_total += 1
            del open_positions[key]

    next_state = {
        "version": STREAM_STAGE3_VERSION,
        "wallet": str(wallet),
        "sequence": [
            {
                "base_asset": base,
                "quote_asset": quote,
                "sequence": int(value),
            }
            for (base, quote), value in sorted(sequence.items())
        ],
        "open_positions": [
            _position_to_state(position)
            for _key, position in sorted(open_positions.items())
        ],
        "terminal_episode_count": terminal_total,
        "scorable_closed_episode_count": scorable_total,
        "anomaly_count": anomaly_total,
        "recent_signatures": list(recent),
        "last_event_block_time": last_block_time,
        "last_event_slot": last_slot,
    }
    return {
        "state": next_state,
        "closed_episodes": emitted,
        "events_consumed": len(rows),
        "anomalies_added": anomalies_added,
    }
