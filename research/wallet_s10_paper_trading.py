from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from statistics import median
from typing import Any, Iterable, Mapping

STAGE10_VERSION = "wallet-s10-v1"
ZERO = Decimal("0")
ONE = Decimal("1")
BPS = Decimal("10000")

EVALUATION_HORIZONS_SECONDS = {
    "30m": 30 * 60,
    "1h": 60 * 60,
    "4h": 4 * 60 * 60,
    "12h": 12 * 60 * 60,
    "24h": 24 * 60 * 60,
}
RULE_IDS = ("A", "B", "C", "D", "E")
HIGHER_TIERS = ("S2", "S3", "S4", "S5")


@dataclass(frozen=True)
class PaperTradingConfig:
    fee_bps_per_side: Decimal
    slippage_bps_per_side: Decimal
    tp_pct: Decimal = Decimal("1")
    sl_pct: Decimal = Decimal("1")
    max_holding_seconds: int = 24 * 60 * 60
    max_entry_delay_seconds: int | None = None

    def __post_init__(self) -> None:
        fee = Decimal(str(self.fee_bps_per_side))
        slippage = Decimal(str(self.slippage_bps_per_side))
        tp = Decimal(str(self.tp_pct))
        sl = Decimal(str(self.sl_pct))

        if fee < ZERO or slippage < ZERO:
            raise ValueError("fee/slippage bps must be >= 0")
        if fee >= BPS or slippage >= BPS:
            raise ValueError("fee/slippage bps must be < 10000")
        if tp <= ZERO or sl <= ZERO:
            raise ValueError("TP/SL percentages must be > 0")
        if self.max_holding_seconds <= 0:
            raise ValueError("max_holding_seconds must be > 0")
        if (
            self.max_entry_delay_seconds is not None
            and self.max_entry_delay_seconds < 0
        ):
            raise ValueError("max_entry_delay_seconds must be >= 0")


def _d(value: Any) -> Decimal:
    return Decimal(str(value))


def _s(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if value == ZERO:
        return "0"
    return format(value.normalize(), "f")


def _pct(numerator: int, denominator: int) -> str | None:
    if denominator <= 0:
        return None
    return _s(
        Decimal(numerator) / Decimal(denominator) * Decimal("100")
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _direction_side(state: str) -> str | None:
    if state == "ACCUMULATION":
        return "LONG"
    if state == "DISTRIBUTION":
        return "SHORT"
    return None


def _side_wallet_count(signal: dict[str, Any], side: str) -> int:
    activity = signal.get("qualified_wallet_activity") or {}
    key = "buy_wallet_count" if side == "LONG" else "sell_wallet_count"
    return int(activity.get(key) or 0)


def _wallet_net(signal: dict[str, Any], side: str) -> int:
    net = int(
        (signal.get("qualified_wallet_activity") or {}).get(
            "wallet_net_count"
        )
        or 0
    )
    return net if side == "LONG" else -net


def _tier_side_count(
    signal: dict[str, Any],
    tier: str,
    side: str,
) -> int:
    tiers = (
        (signal.get("qualified_wallet_activity") or {}).get(
            "segment_membership_wallet_counts"
        )
        or {}
    )
    row = tiers.get(tier) or {}
    key = "buy_wallet_count" if side == "LONG" else "sell_wallet_count"
    return int(row.get(key) or 0)


def _rule_evidence(signal: dict[str, Any], rule_id: str) -> dict[str, Any]:
    side = _direction_side(str(signal.get("state") or ""))
    if side is None:
        return {
            "eligible": False,
            "side": None,
            "reason": "NON_DIRECTIONAL_SIGNAL",
        }

    directional_wallets = _side_wallet_count(signal, side)
    higher_tier_wallets = sum(
        _tier_side_count(signal, tier, side) for tier in HIGHER_TIERS
    )
    aligned_event_side = "BUY" if side == "LONG" else "SELL"
    aligned_meme_wallets = {
        str(row.get("wallet") or "")
        for row in signal.get("contributors") or []
        if row.get("wallet")
        and aligned_event_side in set(row.get("sides") or [])
        and bool(row.get("meme_evidence_available"))
    }
    meme_evidence_wallets = len(aligned_meme_wallets)
    wallet_net_aligned = _wallet_net(signal, side)
    usd = signal.get("validated_usd_flow") or {}
    usd_coverage = str(usd.get("coverage") or "UNAVAILABLE")
    usd_direction = str(usd.get("direction") or "UNAVAILABLE")
    expected_usd_direction = "POSITIVE" if side == "LONG" else "NEGATIVE"
    usd_aligned = (
        usd_coverage in {"COMPLETE", "PARTIAL"}
        and usd_direction == expected_usd_direction
    )

    checks: dict[str, bool]
    if rule_id == "A":
        checks = {
            "directional_wallets_gte_2": directional_wallets >= 2,
        }
    elif rule_id == "B":
        checks = {
            "directional_wallets_gte_3": directional_wallets >= 3,
        }
    elif rule_id == "C":
        checks = {
            "directional_wallets_gte_3": directional_wallets >= 3,
            "higher_tier_participation": higher_tier_wallets >= 1,
        }
    elif rule_id == "D":
        checks = {
            "directional_wallets_gte_3": directional_wallets >= 3,
            "meme_evidence_participation": meme_evidence_wallets >= 1,
        }
    elif rule_id == "E":
        checks = {
            "directional_wallets_gte_3": directional_wallets >= 3,
            "wallet_net_advantage_gte_2": wallet_net_aligned >= 2,
            "validated_usd_flow_aligned": usd_aligned,
        }
    else:
        raise ValueError(f"unsupported rule_id: {rule_id}")

    return {
        "eligible": all(checks.values()),
        "side": side,
        "checks": checks,
        "failed_checks": [
            name for name, passed in checks.items() if not passed
        ],
        "features": {
            "directional_wallet_count": directional_wallets,
            "wallet_net_aligned": wallet_net_aligned,
            "higher_tier_membership_count": higher_tier_wallets,
            "meme_evidence_wallet_count": meme_evidence_wallets,
            "usd_coverage": usd_coverage,
            "usd_direction": usd_direction,
        },
    }


def evaluate_candidate_rule(
    signal: dict[str, Any],
    rule_id: str,
) -> dict[str, Any]:
    """Evaluate one preregistered Stage-10 candidate rule."""
    evidence = _rule_evidence(signal, rule_id)
    return {
        "rule_id": rule_id,
        "eligible": bool(evidence["eligible"]),
        "side": evidence.get("side"),
        "checks": evidence.get("checks", {}),
        "failed_checks": evidence.get("failed_checks", []),
        "features": evidence.get("features", {}),
        "policy": "CANDIDATE_ONLY_NOT_PRODUCTION_WINNER",
    }


def _prepare_bars(
    price_bars: Mapping[str, Iterable[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}

    for token, raw_rows in price_bars.items():
        by_time: dict[int, dict[str, Any]] = {}
        for raw in raw_rows:
            ts = int(raw["timestamp"])
            if ts in by_time:
                raise ValueError(
                    f"duplicate price-bar timestamp for {token}: {ts}"
                )
            o = _d(raw["open"])
            h = _d(raw["high"])
            low = _d(raw["low"])
            close = _d(raw["close"])
            if min(o, h, low, close) <= ZERO:
                raise ValueError(
                    f"non-positive OHLC price for {token} at {ts}"
                )
            if h < max(o, close, low):
                raise ValueError(
                    f"invalid high for {token} at {ts}"
                )
            if low > min(o, close, h):
                raise ValueError(
                    f"invalid low for {token} at {ts}"
                )

            by_time[ts] = {
                "timestamp": ts,
                "open": o,
                "high": h,
                "low": low,
                "close": close,
            }

        output[str(token)] = [
            by_time[ts] for ts in sorted(by_time)
        ]

    return output


def _flatten_signals(
    signal_snapshots: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: dict[tuple[int, str], str] = {}

    for snapshot in signal_snapshots:
        if str(snapshot.get("version") or "") != "wallet-s9-v1":
            raise ValueError("unsupported Stage-9 snapshot version")
        as_of = int(snapshot["as_of"])
        for raw in snapshot.get("signals") or []:
            signal = dict(raw)
            if str(signal.get("version") or "") != "wallet-s9-v1":
                raise ValueError("unsupported Stage-9 signal version")
            token = str(signal.get("base_asset") or "")
            if not token:
                continue
            signal_time = int(signal.get("as_of", as_of))
            if signal_time != as_of:
                raise ValueError(
                    "signal as_of must match containing snapshot as_of"
                )
            key = (signal_time, token)
            fingerprint = str(
                signal.get("signal_fingerprint")
                or _fingerprint(signal)
            )
            previous = seen.get(key)
            if previous is not None:
                if previous != fingerprint:
                    raise ValueError(
                        f"conflicting duplicate signal for {token} at {signal_time}"
                    )
                continue
            seen[key] = fingerprint
            rows.append(signal)

    return sorted(
        rows,
        key=lambda row: (
            int(row["as_of"]),
            str(row["base_asset"]),
            str(row.get("signal_fingerprint") or ""),
        ),
    )


def _entry_bar(
    bars: list[dict[str, Any]],
    *,
    signal_time: int,
    max_delay_seconds: int | None,
) -> dict[str, Any] | None:
    for bar in bars:
        ts = int(bar["timestamp"])
        if ts <= int(signal_time):
            continue
        if (
            max_delay_seconds is not None
            and ts - int(signal_time) > max_delay_seconds
        ):
            return None
        return bar
    return None


def _apply_entry_slippage(
    raw_price: Decimal,
    side: str,
    slippage_bps: Decimal,
) -> Decimal:
    slip = slippage_bps / BPS
    if side == "LONG":
        return raw_price * (ONE + slip)
    return raw_price * (ONE - slip)


def _apply_exit_slippage(
    raw_price: Decimal,
    side: str,
    slippage_bps: Decimal,
) -> Decimal:
    slip = slippage_bps / BPS
    if side == "LONG":
        return raw_price * (ONE - slip)
    return raw_price * (ONE + slip)


def _barrier_prices(
    entry_price: Decimal,
    *,
    side: str,
    tp_pct: Decimal,
    sl_pct: Decimal,
) -> tuple[Decimal, Decimal]:
    tp = tp_pct / Decimal("100")
    sl = sl_pct / Decimal("100")
    if side == "LONG":
        return (
            entry_price * (ONE + tp),
            entry_price * (ONE - sl),
        )
    return (
        entry_price * (ONE - tp),
        entry_price * (ONE + sl),
    )


def _barrier_touch(
    bar: dict[str, Any],
    *,
    side: str,
    tp_price: Decimal,
    sl_price: Decimal,
) -> tuple[bool, bool]:
    if side == "LONG":
        return (
            bar["high"] >= tp_price,
            bar["low"] <= sl_price,
        )
    return (
        bar["low"] <= tp_price,
        bar["high"] >= sl_price,
    )


def _net_return_pct(
    *,
    side: str,
    entry_fill: Decimal,
    exit_fill: Decimal,
    fee_bps_per_side: Decimal,
) -> tuple[Decimal, Decimal]:
    fee = fee_bps_per_side / BPS

    if side == "LONG":
        gross = exit_fill / entry_fill - ONE
        net = (
            exit_fill * (ONE - fee)
            / (entry_fill * (ONE + fee))
            - ONE
        )
    else:
        gross = (entry_fill - exit_fill) / entry_fill
        exit_ratio = exit_fill / entry_fill
        net = gross - fee - (fee * exit_ratio)

    return (
        gross * Decimal("100"),
        net * Decimal("100"),
    )


def _path_metrics(
    bars: list[dict[str, Any]],
    *,
    entry_time: int,
    entry_price: Decimal,
    side: str,
    horizon_seconds: int,
    tp_price: Decimal,
    sl_price: Decimal,
) -> dict[str, Any]:
    horizon_end = int(entry_time) + int(horizon_seconds)
    future = [
        bar
        for bar in bars
        if int(entry_time) <= int(bar["timestamp"]) <= horizon_end
    ]
    later_exists = any(
        int(bar["timestamp"]) >= horizon_end for bar in bars
    )
    coverage_complete = later_exists

    if not future:
        return {
            "coverage_complete": False,
            "bar_count": 0,
            "mfe_pct": None,
            "mae_pct": None,
            "first_tp_time": None,
            "first_sl_time": None,
            "tp_before_sl": "INCOMPLETE",
        }

    if side == "LONG":
        best = max(bar["high"] for bar in future)
        worst = min(bar["low"] for bar in future)
        mfe = (best / entry_price - ONE) * Decimal("100")
        mae = (worst / entry_price - ONE) * Decimal("100")
    else:
        best_low = min(bar["low"] for bar in future)
        worst_high = max(bar["high"] for bar in future)
        mfe = (ONE - best_low / entry_price) * Decimal("100")
        mae = (ONE - worst_high / entry_price) * Decimal("100")

    first_tp: int | None = None
    first_sl: int | None = None
    outcome: str | None = None

    for bar in future:
        tp_hit, sl_hit = _barrier_touch(
            bar,
            side=side,
            tp_price=tp_price,
            sl_price=sl_price,
        )
        ts = int(bar["timestamp"])
        if tp_hit and first_tp is None:
            first_tp = ts
        if sl_hit and first_sl is None:
            first_sl = ts

        if tp_hit and sl_hit:
            outcome = "SL_FIRST_TIE_CONSERVATIVE"
            break
        if tp_hit:
            outcome = "TP_FIRST"
            break
        if sl_hit:
            outcome = "SL_FIRST"
            break

    if outcome is None:
        outcome = "NEITHER" if coverage_complete else "INCOMPLETE"

    return {
        "coverage_complete": coverage_complete,
        "bar_count": len(future),
        "mfe_pct": _s(mfe),
        "mae_pct": _s(mae),
        "first_tp_time": first_tp,
        "first_sl_time": first_sl,
        "tp_before_sl": outcome,
    }


def _trade_feature_snapshot(signal: dict[str, Any]) -> dict[str, Any]:
    activity = signal.get("qualified_wallet_activity") or {}
    tiers = activity.get("segment_membership_wallet_counts") or {}
    side = _direction_side(str(signal.get("state") or ""))
    side_key = "buy_wallet_count" if side == "LONG" else "sell_wallet_count"

    tier_counts = {
        tier: int((tiers.get(tier) or {}).get(side_key) or 0)
        for tier in ("S1", "S2", "S3", "S4", "S5")
    }

    meme = signal.get("meme_hunter_evidence") or {}
    return {
        "qualified_wallet_count": _side_wallet_count(signal, side or "LONG"),
        "buy_wallet_count": int(activity.get("buy_wallet_count") or 0),
        "sell_wallet_count": int(activity.get("sell_wallet_count") or 0),
        "wallet_net_count": int(activity.get("wallet_net_count") or 0),
        "tier_counts_directional": tier_counts,
        "meme_evidence_wallet_count": int(
            meme.get("evidence_wallet_count") or 0
        ),
        "meme_calibration_status": meme.get("calibration_status"),
        "meme_historical_matched_explosion_events_sum": int(
            meme.get("historical_matched_explosion_events_sum") or 0
        ),
        "meme_historical_matched_explosion_distinct_tokens_sum": int(
            meme.get(
                "historical_matched_explosion_distinct_tokens_sum"
            )
            or 0
        ),
        "net_base_amount": str(
            (signal.get("base_flow") or {}).get("net_base_amount") or "0"
        ),
        "validated_usd_flow": dict(
            signal.get("validated_usd_flow") or {}
        ),
        "freshness": dict(signal.get("freshness") or {}),
        "persistence": {
            "directional_agreement_windows": list(
                (signal.get("persistence") or {}).get(
                    "directional_agreement_windows"
                )
                or []
            ),
            "spans_15m_directionally": bool(
                (signal.get("persistence") or {}).get(
                    "spans_15m_directionally"
                )
            ),
            "spans_1h_directionally": bool(
                (signal.get("persistence") or {}).get(
                    "spans_1h_directionally"
                )
            ),
        },
    }


def _simulate_one_trade(
    *,
    signal: dict[str, Any],
    bars: list[dict[str, Any]],
    rule_id: str,
    rule_evidence: dict[str, Any],
    config: PaperTradingConfig,
) -> dict[str, Any] | None:
    signal_time = int(signal["as_of"])
    side = str(rule_evidence["side"])
    entry_bar = _entry_bar(
        bars,
        signal_time=signal_time,
        max_delay_seconds=config.max_entry_delay_seconds,
    )
    if entry_bar is None:
        return None

    raw_entry = entry_bar["open"]
    entry_fill = _apply_entry_slippage(
        raw_entry,
        side,
        Decimal(str(config.slippage_bps_per_side)),
    )
    entry_time = int(entry_bar["timestamp"])
    tp_price, sl_price = _barrier_prices(
        entry_fill,
        side=side,
        tp_pct=Decimal(str(config.tp_pct)),
        sl_pct=Decimal(str(config.sl_pct)),
    )
    timeout_time = entry_time + int(config.max_holding_seconds)

    eligible_bars = [
        bar
        for bar in bars
        if entry_time <= int(bar["timestamp"]) <= timeout_time
    ]
    coverage_complete = any(
        int(bar["timestamp"]) >= timeout_time for bar in bars
    )

    exit_reason: str | None = None
    exit_time: int | None = None
    raw_exit: Decimal | None = None
    same_bar_tie = False
    first_tp_time: int | None = None
    first_sl_time: int | None = None

    for bar in eligible_bars:
        tp_hit, sl_hit = _barrier_touch(
            bar,
            side=side,
            tp_price=tp_price,
            sl_price=sl_price,
        )
        ts = int(bar["timestamp"])

        if tp_hit and first_tp_time is None:
            first_tp_time = ts
        if sl_hit and first_sl_time is None:
            first_sl_time = ts

        if tp_hit and sl_hit:
            exit_reason = "SL_FIRST_TIE_CONSERVATIVE"
            exit_time = ts
            raw_exit = sl_price
            same_bar_tie = True
            break
        if tp_hit:
            exit_reason = "TP_FIRST"
            exit_time = ts
            raw_exit = tp_price
            break
        if sl_hit:
            exit_reason = "SL_FIRST"
            exit_time = ts
            raw_exit = sl_price
            break

    if exit_reason is None:
        if coverage_complete and eligible_bars:
            exit_reason = "TIMEOUT"
            exit_bar = eligible_bars[-1]
            exit_time = int(exit_bar["timestamp"])
            raw_exit = exit_bar["close"]
        else:
            exit_reason = "INCOMPLETE_DATA"

    exit_fill: Decimal | None = None
    gross_return: Decimal | None = None
    net_return: Decimal | None = None
    if raw_exit is not None:
        exit_fill = _apply_exit_slippage(
            raw_exit,
            side,
            Decimal(str(config.slippage_bps_per_side)),
        )
        gross_return, net_return = _net_return_pct(
            side=side,
            entry_fill=entry_fill,
            exit_fill=exit_fill,
            fee_bps_per_side=Decimal(str(config.fee_bps_per_side)),
        )

    horizon_metrics = {
        name: _path_metrics(
            bars,
            entry_time=entry_time,
            entry_price=entry_fill,
            side=side,
            horizon_seconds=seconds,
            tp_price=tp_price,
            sl_price=sl_price,
        )
        for name, seconds in EVALUATION_HORIZONS_SECONDS.items()
    }

    actual_path_end = (
        int(exit_time)
        if exit_time is not None
        else min(timeout_time, int(bars[-1]["timestamp"]))
    )
    complete_path_bars = [
        bar
        for bar in bars
        if entry_time <= int(bar["timestamp"]) <= actual_path_end
    ]
    if complete_path_bars:
        if side == "LONG":
            mfe = (
                max(bar["high"] for bar in complete_path_bars)
                / entry_fill
                - ONE
            ) * Decimal("100")
            mae = (
                min(bar["low"] for bar in complete_path_bars)
                / entry_fill
                - ONE
            ) * Decimal("100")
        else:
            mfe = (
                ONE
                - min(bar["low"] for bar in complete_path_bars)
                / entry_fill
            ) * Decimal("100")
            mae = (
                ONE
                - max(bar["high"] for bar in complete_path_bars)
                / entry_fill
            ) * Decimal("100")
    else:
        mfe = None
        mae = None

    trade_core = {
        "version": STAGE10_VERSION,
        "rule_id": rule_id,
        "base_asset": str(signal["base_asset"]),
        "side": side,
        "signal_time": signal_time,
        "signal_fingerprint": signal.get("signal_fingerprint"),
        "entry_time": entry_time,
        "entry_delay_seconds": entry_time - signal_time,
        "raw_entry_price": _s(raw_entry),
        "entry_fill_price": _s(entry_fill),
        "tp_trigger_price": _s(tp_price),
        "sl_trigger_price": _s(sl_price),
        "timeout_time": timeout_time,
        "exit_time": exit_time,
        "exit_reason": exit_reason,
        "raw_exit_price": _s(raw_exit),
        "exit_fill_price": _s(exit_fill),
        "same_bar_tp_sl_tie": same_bar_tie,
        "first_tp_time": first_tp_time,
        "first_sl_time": first_sl_time,
        "time_to_tp_seconds": (
            first_tp_time - entry_time
            if first_tp_time is not None
            else None
        ),
        "time_to_sl_seconds": (
            first_sl_time - entry_time
            if first_sl_time is not None
            else None
        ),
        "gross_return_pct": _s(gross_return),
        "net_return_pct_after_fees_slippage": _s(net_return),
        "mfe_pct": _s(mfe),
        "mae_pct": _s(mae),
        "execution_costs": {
            "fee_bps_per_side": _s(
                Decimal(str(config.fee_bps_per_side))
            ),
            "slippage_bps_per_side": _s(
                Decimal(str(config.slippage_bps_per_side))
            ),
        },
        "feature_snapshot": _trade_feature_snapshot(signal),
        "rule_evidence": rule_evidence,
        "evaluation_horizons": horizon_metrics,
        "coverage_complete_to_timeout": coverage_complete,
    }
    return {
        **trade_core,
        "trade_fingerprint": _fingerprint(trade_core),
    }


def _rule_summary(
    rule_id: str,
    trades: list[dict[str, Any]],
    *,
    candidate_signal_count: int,
    skipped_active_position: int,
    no_entry_price_count: int,
) -> dict[str, Any]:
    complete = [
        row for row in trades
        if row["exit_reason"] != "INCOMPLETE_DATA"
    ]
    incomplete = [
        row for row in trades
        if row["exit_reason"] == "INCOMPLETE_DATA"
    ]
    tp = [row for row in complete if row["exit_reason"] == "TP_FIRST"]
    sl = [
        row
        for row in complete
        if row["exit_reason"]
        in {"SL_FIRST", "SL_FIRST_TIE_CONSERVATIVE"}
    ]
    timeout = [
        row for row in complete if row["exit_reason"] == "TIMEOUT"
    ]
    net_returns = [
        _d(row["net_return_pct_after_fees_slippage"])
        for row in complete
        if row.get("net_return_pct_after_fees_slippage") is not None
    ]

    barrier_resolved = len(tp) + len(sl)
    return {
        "rule_id": rule_id,
        "candidate_signal_count": candidate_signal_count,
        "opened_trade_count": len(trades),
        "complete_trade_count": len(complete),
        "incomplete_trade_count": len(incomplete),
        "skipped_active_position_count": skipped_active_position,
        "no_entry_price_count": no_entry_price_count,
        "tp_first_count": len(tp),
        "sl_first_count": len(sl),
        "timeout_count": len(timeout),
        "barrier_resolved_count": barrier_resolved,
        "p_tp_before_sl_pct_resolved": _pct(
            len(tp),
            barrier_resolved,
        ),
        "p_tp_before_sl_pct_complete": _pct(
            len(tp),
            len(complete),
        ),
        "mean_net_return_pct": (
            _s(sum(net_returns, ZERO) / Decimal(len(net_returns)))
            if net_returns
            else None
        ),
        "median_net_return_pct": (
            _s(Decimal(str(median(net_returns))))
            if net_returns
            else None
        ),
        "total_normalized_net_return_pct": (
            _s(sum(net_returns, ZERO))
            if net_returns
            else None
        ),
        "winner_selected": False,
        "selection_policy": "STAGE11_VALIDATION_REQUIRED",
    }


def run_wallet_only_paper_trading(
    signal_snapshots: Iterable[dict[str, Any]],
    price_bars: Mapping[str, Iterable[dict[str, Any]]],
    *,
    config: PaperTradingConfig,
    rule_ids: Iterable[str] = RULE_IDS,
) -> dict[str, Any]:
    """Run causal, independent paper trading for Stage-9 signal snapshots."""
    prepared_bars = _prepare_bars(price_bars)
    signals = _flatten_signals(signal_snapshots)
    requested_rules = list(rule_ids)

    if len(set(requested_rules)) != len(requested_rules):
        raise ValueError("duplicate rule_id requested")
    for rule_id in requested_rules:
        if rule_id not in RULE_IDS:
            raise ValueError(f"unsupported rule_id: {rule_id}")

    results: dict[str, Any] = {}
    for rule_id in requested_rules:
        trades: list[dict[str, Any]] = []
        active_until: dict[str, int | None] = {}
        candidate_signal_count = 0
        skipped_active = 0
        no_entry = 0

        for signal in signals:
            evidence = evaluate_candidate_rule(signal, rule_id)
            if not evidence["eligible"]:
                continue

            candidate_signal_count += 1
            token = str(signal["base_asset"])
            signal_time = int(signal["as_of"])
            prior_exit = active_until.get(token)
            if prior_exit is None and token in active_until:
                skipped_active += 1
                continue
            if prior_exit is not None and signal_time < prior_exit:
                skipped_active += 1
                continue

            bars = prepared_bars.get(token) or []
            trade = _simulate_one_trade(
                signal=signal,
                bars=bars,
                rule_id=rule_id,
                rule_evidence=evidence,
                config=config,
            )
            if trade is None:
                no_entry += 1
                continue

            trades.append(trade)
            if trade["exit_time"] is None:
                active_until[token] = None
            else:
                active_until[token] = int(trade["exit_time"])

        results[rule_id] = {
            "summary": _rule_summary(
                rule_id,
                trades,
                candidate_signal_count=candidate_signal_count,
                skipped_active_position=skipped_active,
                no_entry_price_count=no_entry,
            ),
            "trades": trades,
        }

    config_payload = {
        "tp_pct": _s(Decimal(str(config.tp_pct))),
        "sl_pct": _s(Decimal(str(config.sl_pct))),
        "fee_bps_per_side": _s(
            Decimal(str(config.fee_bps_per_side))
        ),
        "slippage_bps_per_side": _s(
            Decimal(str(config.slippage_bps_per_side))
        ),
        "max_holding_seconds": int(config.max_holding_seconds),
        "max_entry_delay_seconds": config.max_entry_delay_seconds,
        "same_bar_tp_sl_policy": "SL_FIRST_CONSERVATIVE",
        "entry_policy": "FIRST_BAR_OPEN_STRICTLY_AFTER_SIGNAL",
    }
    result_core = {
        "version": STAGE10_VERSION,
        "config": config_payload,
        "evaluation_horizons_seconds": dict(
            EVALUATION_HORIZONS_SECONDS
        ),
        "rules": results,
        "experiment_policy": {
            "wallet_detector_only": True,
            "mcd_required": False,
            "winner_selected": False,
            "winner_selection_stage": "STAGE11",
            "primary_benchmark": "P(+1% before -1%)",
        },
    }
    return {
        **result_core,
        "result_fingerprint": _fingerprint(result_core),
    }
