from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from statistics import median
from typing import Any, Iterable

from research.wallet_s2_transaction_normalizer import NATIVE_SOL, WSOL_MINT

STAGE4_VERSION = "wallet-s4-v1"
ZERO = Decimal("0")
LAMPORTS_PER_SOL = Decimal("1000000000")


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


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == ZERO:
        return None
    return numerator / denominator * Decimal("100")


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, ZERO) / Decimal(len(values))


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return Decimal(median(values))


def _profit_factor(pnls: list[Decimal]) -> str | None:
    gross_profit = sum((x for x in pnls if x > ZERO), ZERO)
    gross_loss = abs(sum((x for x in pnls if x < ZERO), ZERO))
    if gross_loss == ZERO:
        return "INF" if gross_profit > ZERO else None
    return _s(gross_profit / gross_loss)


def _max_drawdown(pnls: list[Decimal]) -> Decimal:
    cumulative = ZERO
    peak = ZERO
    max_dd = ZERO
    for pnl in pnls:
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
        drawdown = peak - cumulative
        if drawdown > max_dd:
            max_dd = drawdown
    return max_dd


def _max_streak(values: list[Decimal], *, win: bool) -> int:
    best = 0
    current = 0
    for value in values:
        hit = value > ZERO if win else value < ZERO
        if hit:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def _utc_day(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()


def _extract_episodes(
    source: dict[str, Any] | Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(source, dict):
        if "scorable_closed_episodes" in source:
            rows = list(source.get("scorable_closed_episodes") or [])
        elif "episodes" in source:
            rows = list(source.get("episodes") or [])
        else:
            rows = []
    else:
        rows = list(source)

    clean = [
        row
        for row in rows
        if bool(row.get("eligible_for_performance_metrics"))
        and str(row.get("status") or "") == "CLOSED"
        and row.get("realized_roi_pct") is not None
        and row.get("realized_pnl_quote") is not None
    ]
    return sorted(
        clean,
        key=lambda row: (
            int(row.get("closed_at"))
            if row.get("closed_at") is not None
            else 2**63 - 1,
            int(row.get("close_slot"))
            if row.get("close_slot") is not None
            else 2**63 - 1,
            str(row.get("episode_id") or ""),
        ),
    )


def _fee_adjusted_values(
    episode: dict[str, Any],
) -> tuple[Decimal | None, Decimal | None, str]:
    gross_pnl = _d(episode.get("realized_pnl_quote"))
    realized_cost = _d(episode.get("realized_cost_quote"))

    if episode.get("net_realized_pnl_quote") is not None:
        net_pnl = _d(episode.get("net_realized_pnl_quote"))
        source = "EPISODE_NET_PNL"
    elif episode.get("fee_cost_quote") is not None:
        net_pnl = gross_pnl - _d(episode.get("fee_cost_quote"))
        source = "EXPLICIT_FEE_COST_QUOTE"
    elif str(episode.get("quote_asset") or "") in {NATIVE_SOL, WSOL_MINT}:
        fee_sol = Decimal(int(episode.get("network_fee_lamports") or 0)) / LAMPORTS_PER_SOL
        net_pnl = gross_pnl - fee_sol
        source = "SOL_NETWORK_FEE_DIRECT"
    else:
        return None, None, "UNAVAILABLE"

    net_roi = _pct(net_pnl, realized_cost)
    return net_pnl, net_roi, source


def _quote_metrics(
    quote_asset: str,
    episodes: list[dict[str, Any]],
) -> dict[str, Any]:
    rois = [_d(row["realized_roi_pct"]) for row in episodes]
    pnls = [_d(row["realized_pnl_quote"]) for row in episodes]
    holdings = [
        Decimal(int(row["holding_seconds"]))
        for row in episodes
        if row.get("holding_seconds") is not None
    ]

    net_rows: list[tuple[Decimal, Decimal | None, str]] = []
    for row in episodes:
        net_pnl, net_roi, source = _fee_adjusted_values(row)
        if net_pnl is not None:
            net_rows.append((net_pnl, net_roi, source))

    net_pnls = [row[0] for row in net_rows]
    net_rois = [row[1] for row in net_rows if row[1] is not None]
    net_complete = len(net_rows) == len(episodes) and bool(episodes)

    return {
        "quote_asset": quote_asset,
        "quote_is_usd": all(bool(row.get("quote_is_usd")) for row in episodes),
        "closed_trade_count": len(episodes),
        "wins": sum(1 for x in pnls if x > ZERO),
        "losses": sum(1 for x in pnls if x < ZERO),
        "breakeven": sum(1 for x in pnls if x == ZERO),
        "win_rate_pct": _s(
            Decimal(sum(1 for x in pnls if x > ZERO))
            / Decimal(len(pnls))
            * Decimal("100")
        ),
        "median_roi_pct": _s(_median(rois)),
        "mean_roi_pct": _s(_mean(rois)),
        "total_realized_pnl_quote": _s(sum(pnls, ZERO)),
        "gross_profit_quote": _s(sum((x for x in pnls if x > ZERO), ZERO)),
        "gross_loss_quote_abs": _s(
            abs(sum((x for x in pnls if x < ZERO), ZERO))
        ),
        "profit_factor": _profit_factor(pnls),
        "max_drawdown_quote": _s(_max_drawdown(pnls)),
        "median_holding_seconds": _s(_median(holdings)),
        "net_fee_adjusted_episode_count": len(net_rows),
        "net_metrics_complete": net_complete,
        "net_total_realized_pnl_quote": (
            _s(sum(net_pnls, ZERO)) if net_complete else None
        ),
        "net_median_roi_pct": _s(_median(net_rois)),
        "net_win_rate_pct": (
            _s(
                Decimal(sum(1 for x in net_pnls if x > ZERO))
                / Decimal(len(net_pnls))
                * Decimal("100")
            )
            if net_pnls
            else None
        ),
        "net_profit_factor": _profit_factor(net_pnls),
        "fee_adjustment_sources": sorted({row[2] for row in net_rows}),
    }


def _recent_metrics(
    episodes: list[dict[str, Any]],
    recent_window: int,
) -> dict[str, Any]:
    if recent_window < 1:
        raise ValueError("recent_window must be >= 1")

    recent = episodes[-recent_window:]
    prior = episodes[:-recent_window]

    def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {
                "count": 0,
                "median_roi_pct": None,
                "win_rate_pct": None,
            }
        rois = [_d(row["realized_roi_pct"]) for row in rows]
        wins = sum(1 for row in rows if _d(row["realized_pnl_quote"]) > ZERO)
        return {
            "count": len(rows),
            "median_roi_pct": _s(_median(rois)),
            "win_rate_pct": _s(
                Decimal(wins) / Decimal(len(rows)) * Decimal("100")
            ),
        }

    recent_metrics = metrics(recent)
    prior_metrics = metrics(prior)

    recent_median = (
        _d(recent_metrics["median_roi_pct"])
        if recent_metrics["median_roi_pct"] is not None
        else None
    )
    prior_median = (
        _d(prior_metrics["median_roi_pct"])
        if prior_metrics["median_roi_pct"] is not None
        else None
    )
    recent_wr = (
        _d(recent_metrics["win_rate_pct"])
        if recent_metrics["win_rate_pct"] is not None
        else None
    )
    prior_wr = (
        _d(prior_metrics["win_rate_pct"])
        if prior_metrics["win_rate_pct"] is not None
        else None
    )

    return {
        "window_size": recent_window,
        "recent": recent_metrics,
        "prior": prior_metrics,
        "median_roi_delta_pct_points": (
            _s(recent_median - prior_median)
            if recent_median is not None and prior_median is not None
            else None
        ),
        "win_rate_delta_pct_points": (
            _s(recent_wr - prior_wr)
            if recent_wr is not None and prior_wr is not None
            else None
        ),
        "trend_comparable": bool(recent and prior),
    }


def compute_wallet_performance(
    source: dict[str, Any] | Iterable[dict[str, Any]],
    *,
    recent_window: int = 20,
) -> dict[str, Any]:
    episodes = _extract_episodes(source)

    wallets = sorted({str(row.get("wallet") or "") for row in episodes if row.get("wallet")})
    if len(wallets) > 1:
        raise ValueError("performance input contains multiple wallets")
    wallet = wallets[0] if wallets else (
        str(source.get("wallet") or "") if isinstance(source, dict) else ""
    )

    if not episodes:
        return {
            "version": STAGE4_VERSION,
            "wallet": wallet,
            "closed_trade_count": 0,
            "meets_50_trade_sample": False,
            "performance_available": False,
            "metric_basis": "NO_CLEAN_CLOSED_EPISODES",
            "quote_metrics": {},
            "recent_performance": _recent_metrics([], recent_window),
        }

    rois = [_d(row["realized_roi_pct"]) for row in episodes]
    pnls = [_d(row["realized_pnl_quote"]) for row in episodes]
    holdings = [
        Decimal(int(row["holding_seconds"]))
        for row in episodes
        if row.get("holding_seconds") is not None
    ]
    wins = sum(1 for pnl in pnls if pnl > ZERO)
    losses = sum(1 for pnl in pnls if pnl < ZERO)
    breakeven = len(pnls) - wins - losses

    quote_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in episodes:
        quote_groups[str(row.get("quote_asset") or "")].append(row)
    quote_metrics = {
        quote: _quote_metrics(quote, rows)
        for quote, rows in sorted(quote_groups.items())
    }

    usd_episodes = [row for row in episodes if bool(row.get("quote_is_usd"))]
    usd_pnls = [_d(row["realized_pnl_quote"]) for row in usd_episodes]
    usd_net_rows = [_fee_adjusted_values(row) for row in usd_episodes]
    usd_net_pnls = [row[0] for row in usd_net_rows if row[0] is not None]
    usd_net_rois = [row[1] for row in usd_net_rows if row[1] is not None]
    usd_net_complete = bool(usd_episodes) and len(usd_net_pnls) == len(usd_episodes)

    close_times = [
        int(row["closed_at"])
        for row in episodes
        if row.get("closed_at") is not None
    ]
    active_days = sorted({_utc_day(ts) for ts in close_times})
    if close_times:
        first_ts = min(close_times)
        last_ts = max(close_times)
        calendar_span_days = (
            datetime.fromtimestamp(last_ts, tz=timezone.utc).date()
            - datetime.fromtimestamp(first_ts, tz=timezone.utc).date()
        ).days + 1
    else:
        first_ts = None
        last_ts = None
        calendar_span_days = 0

    distinct_bases = sorted({str(row.get("base_asset") or "") for row in episodes})
    distinct_quotes = sorted({str(row.get("quote_asset") or "") for row in episodes})

    overall_pf = (
        quote_metrics[distinct_quotes[0]]["profit_factor"]
        if len(distinct_quotes) == 1
        else None
    )

    return {
        "version": STAGE4_VERSION,
        "wallet": wallet,
        "performance_available": True,
        "metric_basis": "CLEAN_CLOSED_EPISODES_GROSS_EXECUTION",
        "closed_trade_count": len(episodes),
        "meets_50_trade_sample": len(episodes) >= 50,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "win_rate_pct": _s(
            Decimal(wins) / Decimal(len(episodes)) * Decimal("100")
        ),
        "median_roi_pct": _s(_median(rois)),
        "mean_roi_pct": _s(_mean(rois)),
        "largest_win_roi_pct": _s(max(rois)),
        "largest_loss_roi_pct": _s(min(rois)),
        "max_win_streak": _max_streak(pnls, win=True),
        "max_loss_streak": _max_streak(pnls, win=False),
        "median_holding_seconds": _s(_median(holdings)),
        "mean_holding_seconds": _s(_mean(holdings)),
        "distinct_base_assets": len(distinct_bases),
        "base_assets": distinct_bases,
        "distinct_quote_assets": len(distinct_quotes),
        "quote_assets": distinct_quotes,
        "overall_profit_factor": overall_pf,
        "overall_profit_factor_available": len(distinct_quotes) == 1,
        "overall_profit_factor_note": (
            None
            if len(distinct_quotes) == 1
            else "not aggregated across different quote currencies"
        ),
        "quote_metrics": quote_metrics,
        "usd_comparable": {
            "closed_trade_count": len(usd_episodes),
            "gross_total_realized_pnl_usd_stable": _s(sum(usd_pnls, ZERO)),
            "gross_profit_factor": _profit_factor(usd_pnls),
            "max_drawdown_usd_stable": _s(_max_drawdown(usd_pnls)),
            "net_fee_adjusted_episode_count": len(usd_net_pnls),
            "net_metrics_complete": usd_net_complete,
            "net_total_realized_pnl_usd_stable": (
                _s(sum(usd_net_pnls, ZERO)) if usd_net_complete else None
            ),
            "net_median_roi_pct": _s(_median(usd_net_rois)),
            "net_win_rate_pct": (
                _s(
                    Decimal(sum(1 for x in usd_net_pnls if x > ZERO))
                    / Decimal(len(usd_net_pnls))
                    * Decimal("100")
                )
                if usd_net_pnls
                else None
            ),
            "net_profit_factor": (
                _profit_factor(usd_net_pnls) if usd_net_pnls else None
            ),
        },
        "activity": {
            "first_closed_at": first_ts,
            "last_closed_at": last_ts,
            "active_days": len(active_days),
            "active_day_dates_utc": active_days,
            "calendar_span_days": calendar_span_days,
            "active_day_ratio_pct": (
                _s(
                    Decimal(len(active_days))
                    / Decimal(calendar_span_days)
                    * Decimal("100")
                )
                if calendar_span_days
                else None
            ),
            "trades_per_active_day": (
                _s(Decimal(len(episodes)) / Decimal(len(active_days)))
                if active_days
                else None
            ),
            "trades_per_calendar_day": (
                _s(
                    Decimal(len(episodes))
                    / Decimal(calendar_span_days)
                )
                if calendar_span_days
                else None
            ),
        },
        "recent_performance": _recent_metrics(episodes, recent_window),
        "qualification_readiness": {
            "minimum_trade_sample_50_met": len(episodes) >= 50,
            "gross_behavior_metrics_ready": True,
            "usd_net_fee_metrics_complete": usd_net_complete,
            "net_classification_ready": (
                len(episodes) >= 50
                and len(usd_episodes) == len(episodes)
                and usd_net_complete
            ),
            "note": (
                "Stage 5 may use gross behavior metrics provisionally, but final "
                "S1/S2/S3 qualification requiring net returns should only use "
                "episodes with complete fee-adjusted quote PnL."
            ),
        },
    }
