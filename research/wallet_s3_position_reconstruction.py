from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable

STAGE3_VERSION = "wallet-s3-v1"
ZERO = Decimal("0")
EPS = Decimal("1e-18")


def _d(value: Any) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(str(value))


def _s(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if value == ZERO:
        return "0"
    return format(value.normalize(), "f")


@dataclass
class PositionEpisode:
    wallet: str
    base_asset: str
    quote_asset: str
    sequence: int
    opened_at: int | None
    opened_slot: int | None
    quote_is_usd: bool = False

    open_qty: Decimal = ZERO
    open_cost_quote: Decimal = ZERO
    total_buy_qty: Decimal = ZERO
    total_buy_cost_quote: Decimal = ZERO
    total_sell_qty: Decimal = ZERO
    total_sell_proceeds_quote: Decimal = ZERO
    realized_cost_quote: Decimal = ZERO
    realized_proceeds_quote: Decimal = ZERO
    realized_pnl_quote: Decimal = ZERO
    buy_count: int = 0
    sell_count: int = 0
    network_fee_lamports: int = 0
    last_time: int | None = None
    closed_at: int | None = None
    close_slot: int | None = None
    status: str = "OPEN"
    signatures: list[str] = field(default_factory=list)
    contamination_reasons: list[str] = field(default_factory=list)

    @property
    def episode_id(self) -> str:
        return f"{self.wallet}:{self.base_asset}:{self.quote_asset}:{self.sequence}"

    def contaminate(self, reason: str) -> None:
        if reason not in self.contamination_reasons:
            self.contamination_reasons.append(reason)

    def add_signature(self, signature: str) -> None:
        if signature and signature not in self.signatures:
            self.signatures.append(signature)

    @property
    def avg_entry_price_quote(self) -> Decimal | None:
        return (
            self.total_buy_cost_quote / self.total_buy_qty
            if self.total_buy_qty > ZERO
            else None
        )

    @property
    def avg_exit_price_quote(self) -> Decimal | None:
        return (
            self.total_sell_proceeds_quote / self.total_sell_qty
            if self.total_sell_qty > ZERO
            else None
        )

    @property
    def open_avg_cost_quote(self) -> Decimal | None:
        return self.open_cost_quote / self.open_qty if self.open_qty > ZERO else None

    @property
    def realized_roi_pct(self) -> Decimal | None:
        if self.realized_cost_quote <= ZERO:
            return None
        return self.realized_pnl_quote / self.realized_cost_quote * Decimal("100")

    @property
    def holding_seconds(self) -> int | None:
        if self.opened_at is None or self.closed_at is None:
            return None
        return max(0, int(self.closed_at) - int(self.opened_at))

    @property
    def eligible_for_performance_metrics(self) -> bool:
        return (
            self.status == "CLOSED"
            and not self.contamination_reasons
            and self.total_buy_qty > ZERO
            and self.total_sell_qty > ZERO
            and self.open_qty <= EPS
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": STAGE3_VERSION,
            "episode_id": self.episode_id,
            "wallet": self.wallet,
            "base_asset": self.base_asset,
            "quote_asset": self.quote_asset,
            "quote_is_usd": self.quote_is_usd,
            "status": self.status,
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
            "opened_slot": self.opened_slot,
            "close_slot": self.close_slot,
            "holding_seconds": self.holding_seconds,
            "open_qty": _s(self.open_qty),
            "open_cost_quote": _s(self.open_cost_quote),
            "open_avg_cost_quote": _s(self.open_avg_cost_quote),
            "total_buy_qty": _s(self.total_buy_qty),
            "total_buy_cost_quote": _s(self.total_buy_cost_quote),
            "avg_entry_price_quote": _s(self.avg_entry_price_quote),
            "total_sell_qty": _s(self.total_sell_qty),
            "total_sell_proceeds_quote": _s(self.total_sell_proceeds_quote),
            "avg_exit_price_quote": _s(self.avg_exit_price_quote),
            "realized_cost_quote": _s(self.realized_cost_quote),
            "realized_proceeds_quote": _s(self.realized_proceeds_quote),
            "realized_pnl_quote": _s(self.realized_pnl_quote),
            "realized_roi_pct": _s(self.realized_roi_pct),
            "buy_count": self.buy_count,
            "sell_count": self.sell_count,
            "network_fee_lamports": self.network_fee_lamports,
            "signatures": list(self.signatures),
            "contamination_reasons": list(self.contamination_reasons),
            "eligible_for_performance_metrics": self.eligible_for_performance_metrics,
        }


def _event_order(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = list(enumerate(events))

    def key(item: tuple[int, dict[str, Any]]) -> tuple[int, int, int]:
        i, row = item
        ts = row.get("block_time")
        slot = row.get("slot")
        return (
            int(ts) if ts is not None else 2**63 - 1,
            int(slot) if slot is not None else 2**63 - 1,
            i,
        )

    return [row for _, row in sorted(indexed, key=key)]


def reconstruct_positions(
    events: Iterable[dict[str, Any]],
    *,
    wallet: str | None = None,
) -> dict[str, Any]:
    rows = _event_order(events)
    inferred_wallet = wallet or next(
        (str(row.get("wallet")) for row in rows if row.get("wallet")), ""
    )
    open_positions: dict[tuple[str, str], PositionEpisode] = {}
    terminal: list[PositionEpisode] = []
    anomalies: list[dict[str, Any]] = []
    sequence: dict[tuple[str, str], int] = {}
    seen_signatures: set[str] = set()

    def anomaly(kind: str, event: dict[str, Any], **extra: Any) -> None:
        anomalies.append(
            {
                "type": kind,
                "signature": event.get("signature"),
                "slot": event.get("slot"),
                "block_time": event.get("block_time"),
                **extra,
            }
        )

    def open_for_base(base: str) -> list[PositionEpisode]:
        return [
            position
            for (candidate_base, _quote), position in open_positions.items()
            if candidate_base == base
        ]

    for event in rows:
        signature = str(event.get("signature") or "")
        if signature:
            if signature in seen_signatures:
                anomaly("DUPLICATE_SIGNATURE", event)
                continue
            seen_signatures.add(signature)

        event_wallet = str(event.get("wallet") or inferred_wallet)
        if wallet is not None and event_wallet and event_wallet != wallet:
            anomaly("WALLET_MISMATCH", event, event_wallet=event_wallet)
            continue

        event_type = str(event.get("event_type") or "")
        side = str(event.get("side") or "NONE")

        if event_type in {"TRANSFER_IN", "TRANSFER_OUT"}:
            asset = str(event.get("asset") or "")
            amount = abs(_d(event.get("amount")))
            affected = open_for_base(asset)
            if not affected:
                continue

            if len(affected) > 1:
                for position in affected:
                    position.contaminate("MIXED_QUOTE_EXTERNAL_FLOW")
                anomaly("MIXED_QUOTE_EXTERNAL_FLOW", event, asset=asset)
                continue

            position = affected[0]
            position.contaminate(event_type + "_DURING_POSITION")
            position.add_signature(signature)
            position.network_fee_lamports += int(
                event.get("network_fee_lamports") or 0
            )
            position.last_time = event.get("block_time")

            if event_type == "TRANSFER_IN":
                anomaly(
                    "TRANSFER_IN_DURING_POSITION",
                    event,
                    episode_id=position.episode_id,
                )
                continue

            if amount <= ZERO or position.open_qty <= ZERO:
                continue

            reduction = min(amount, position.open_qty)
            avg_cost = position.open_cost_quote / position.open_qty
            position.open_qty -= reduction
            position.open_cost_quote -= avg_cost * reduction
            anomaly(
                "TRANSFER_OUT_DURING_POSITION",
                event,
                episode_id=position.episode_id,
                tracked_qty_reduced=_s(reduction),
            )

            if amount - reduction > EPS:
                position.contaminate("TRANSFER_OUT_EXCEEDS_TRACKED_QTY")
                anomaly(
                    "TRANSFER_OUT_EXCEEDS_TRACKED_QTY",
                    event,
                    episode_id=position.episode_id,
                    excess_qty=_s(amount - reduction),
                )

            if position.open_qty <= EPS:
                position.open_qty = ZERO
                position.open_cost_quote = ZERO
                position.status = "TRANSFERRED_OUT"
                position.closed_at = event.get("block_time")
                position.close_slot = event.get("slot")
                terminal.append(position)
                del open_positions[(position.base_asset, position.quote_asset)]
            continue

        if event_type != "SWAP" or side not in {"BUY", "SELL"}:
            continue

        base = str(event.get("base_asset") or "")
        quote = str(event.get("quote_asset") or "")
        base_qty = abs(_d(event.get("base_amount")))
        quote_amount = abs(_d(event.get("quote_amount")))
        if not base or not quote or base_qty <= ZERO or quote_amount <= ZERO:
            anomaly("INVALID_TRADE_EVENT", event)
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
                anomaly(
                    "MIXED_QUOTE_INVENTORY",
                    event,
                    base_asset=base,
                    existing_quotes=[
                        position.quote_asset for position in other_quotes
                    ],
                    new_quote=quote,
                )

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
            position.add_signature(signature)
            continue

        position = open_positions.get(key)
        if position is None:
            others = open_for_base(base)
            if others:
                for other in others:
                    other.contaminate("SELL_WITH_DIFFERENT_QUOTE")
            anomaly(
                "ORPHAN_SELL",
                event,
                base_asset=base,
                quote_asset=quote,
                open_quotes=[other.quote_asset for other in others],
            )
            continue

        cover_qty = min(base_qty, position.open_qty)
        if cover_qty <= ZERO:
            anomaly("ORPHAN_SELL", event, base_asset=base, quote_asset=quote)
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
        position.add_signature(signature)

        excess = base_qty - cover_qty
        if excess > EPS:
            position.contaminate("OVERSELL")
            anomaly(
                "OVERSELL",
                event,
                episode_id=position.episode_id,
                excess_qty=_s(excess),
            )

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
            terminal.append(position)
            del open_positions[key]

    all_episodes = terminal + list(open_positions.values())
    all_episodes.sort(
        key=lambda position: (
            position.opened_at
            if position.opened_at is not None
            else 2**63 - 1,
            position.opened_slot
            if position.opened_slot is not None
            else 2**63 - 1,
            position.episode_id,
        )
    )
    terminal_dicts = [position.to_dict() for position in terminal]
    open_dicts = [position.to_dict() for position in open_positions.values()]
    all_dicts = [position.to_dict() for position in all_episodes]
    scorable = [
        row
        for row in terminal_dicts
        if row["eligible_for_performance_metrics"]
    ]

    return {
        "version": STAGE3_VERSION,
        "wallet": inferred_wallet,
        "episode_count": len(all_dicts),
        "terminal_episode_count": len(terminal_dicts),
        "open_position_count": len(open_dicts),
        "scorable_closed_episode_count": len(scorable),
        "episodes": all_dicts,
        "terminal_episodes": terminal_dicts,
        "open_positions": open_dicts,
        "scorable_closed_episodes": scorable,
        "anomalies": anomalies,
    }
