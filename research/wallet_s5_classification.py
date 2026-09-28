from __future__ import annotations

from decimal import Decimal
from typing import Any

STAGE5_VERSION = "wallet-s5-v1"

MIN_CLOSED_TRADES = 50
S1_MIN_NET_MEDIAN_ROI_PCT = Decimal("1")
S1_MIN_NET_WIN_RATE_PCT = Decimal("60")
S2_MIN_NET_MEDIAN_ROI_PCT = Decimal("5")
S3_MIN_NET_MEDIAN_ROI_PCT = Decimal("10")
ZERO = Decimal("0")


def _d(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _basis_from_profile(profile: dict[str, Any]) -> dict[str, Any] | None:
    """Choose one comparable net-performance basis without mixing currencies."""
    total_trades = int(profile.get("closed_trade_count") or 0)
    usd = profile.get("usd_comparable") or {}

    if (
        total_trades > 0
        and int(usd.get("closed_trade_count") or 0) == total_trades
        and bool(usd.get("net_metrics_complete"))
        and usd.get("net_median_roi_pct") is not None
        and usd.get("net_win_rate_pct") is not None
        and usd.get("net_total_realized_pnl_usd_stable") is not None
    ):
        return {
            "kind": "USD_STABLE_AGGREGATE",
            "quote_asset": "USD_STABLE",
            "closed_trade_count": total_trades,
            "net_median_roi_pct": str(usd["net_median_roi_pct"]),
            "net_win_rate_pct": str(usd["net_win_rate_pct"]),
            "net_total_realized_pnl": str(
                usd["net_total_realized_pnl_usd_stable"]
            ),
            "net_profit_factor": usd.get("net_profit_factor"),
            "max_drawdown_reference": usd.get("max_drawdown_usd_stable"),
        }

    quotes = list(profile.get("quote_assets") or [])
    quote_metrics = profile.get("quote_metrics") or {}
    if len(quotes) == 1:
        quote = str(quotes[0])
        metrics = quote_metrics.get(quote) or {}
        if (
            bool(metrics.get("net_metrics_complete"))
            and metrics.get("net_median_roi_pct") is not None
            and metrics.get("net_win_rate_pct") is not None
            and metrics.get("net_total_realized_pnl_quote") is not None
        ):
            return {
                "kind": "SINGLE_QUOTE",
                "quote_asset": quote,
                "closed_trade_count": total_trades,
                "net_median_roi_pct": str(metrics["net_median_roi_pct"]),
                "net_win_rate_pct": str(metrics["net_win_rate_pct"]),
                "net_total_realized_pnl": str(
                    metrics["net_total_realized_pnl_quote"]
                ),
                "net_profit_factor": metrics.get("net_profit_factor"),
                "max_drawdown_reference": metrics.get("max_drawdown_quote"),
            }

    return None


def _check(
    *,
    trades: int,
    roi: Decimal,
    win_rate: Decimal,
    pnl: Decimal,
    min_roi: Decimal,
    min_win_rate: Decimal | None,
) -> dict[str, Any]:
    checks = {
        "closed_trades_gte_50": trades >= MIN_CLOSED_TRADES,
        "net_median_roi_met": roi >= min_roi,
        "net_total_pnl_positive": pnl > ZERO,
    }
    if min_win_rate is not None:
        checks["net_win_rate_met"] = win_rate >= min_win_rate

    return {
        "qualified": all(checks.values()),
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
    }


def classify_wallet(profile: dict[str, Any]) -> dict[str, Any]:
    """Apply the frozen V1 rules only. No score, ML, or discretionary weighting."""
    wallet = str(profile.get("wallet") or "")
    basis = _basis_from_profile(profile)

    if not bool(profile.get("performance_available")):
        return {
            "version": STAGE5_VERSION,
            "wallet": wallet,
            "status": "NOT_READY",
            "primary_segment": None,
            "qualifying_segments": [],
            "reason": "NO_CLEAN_PERFORMANCE_PROFILE",
            "basis": None,
        }

    if basis is None:
        return {
            "version": STAGE5_VERSION,
            "wallet": wallet,
            "status": "NOT_READY",
            "primary_segment": None,
            "qualifying_segments": [],
            "reason": "NO_COMPARABLE_COMPLETE_NET_BASIS",
            "basis": None,
        }

    trades = int(basis["closed_trade_count"])
    roi = _d(basis["net_median_roi_pct"])
    win_rate = _d(basis["net_win_rate_pct"])
    pnl = _d(basis["net_total_realized_pnl"])
    if roi is None or win_rate is None or pnl is None:
        return {
            "version": STAGE5_VERSION,
            "wallet": wallet,
            "status": "NOT_READY",
            "primary_segment": None,
            "qualifying_segments": [],
            "reason": "MISSING_REQUIRED_NET_METRICS",
            "basis": basis,
        }

    s1 = _check(
        trades=trades,
        roi=roi,
        win_rate=win_rate,
        pnl=pnl,
        min_roi=S1_MIN_NET_MEDIAN_ROI_PCT,
        min_win_rate=S1_MIN_NET_WIN_RATE_PCT,
    )
    s2 = _check(
        trades=trades,
        roi=roi,
        win_rate=win_rate,
        pnl=pnl,
        min_roi=S2_MIN_NET_MEDIAN_ROI_PCT,
        min_win_rate=None,
    )
    s3 = _check(
        trades=trades,
        roi=roi,
        win_rate=win_rate,
        pnl=pnl,
        min_roi=S3_MIN_NET_MEDIAN_ROI_PCT,
        min_win_rate=None,
    )

    segments = {"S1": s1, "S2": s2, "S3": s3}
    qualifying = [name for name in ("S1", "S2", "S3") if segments[name]["qualified"]]

    primary = None
    for candidate in ("S3", "S2", "S1"):
        if segments[candidate]["qualified"]:
            primary = candidate
            break

    return {
        "version": STAGE5_VERSION,
        "wallet": wallet,
        "status": "QUALIFIED" if primary else "UNQUALIFIED",
        "primary_segment": primary,
        "primary_segment_note": (
            "highest-velocity matching label; not a quality ranking"
            if primary
            else None
        ),
        "qualifying_segments": qualifying,
        "basis": basis,
        "segments": segments,
        "thresholds": {
            "minimum_closed_trades": MIN_CLOSED_TRADES,
            "S1": {
                "min_net_median_roi_pct": str(S1_MIN_NET_MEDIAN_ROI_PCT),
                "min_net_win_rate_pct": str(S1_MIN_NET_WIN_RATE_PCT),
                "requires_positive_net_pnl": True,
            },
            "S2": {
                "min_net_median_roi_pct": str(S2_MIN_NET_MEDIAN_ROI_PCT),
                "requires_positive_net_pnl": True,
            },
            "S3": {
                "min_net_median_roi_pct": str(S3_MIN_NET_MEDIAN_ROI_PCT),
                "requires_positive_net_pnl": True,
            },
        },
        "risk_note": (
            "drawdown is recorded but not a V1 classification gate; "
            "no arbitrary 'reasonable drawdown' threshold is invented"
        ),
        "special_labels": {
            "meme_hunter": "DEFERRED_TO_STAGE_6",
            "whale": "DEFERRED_UNTIL_RELIABLE_CAPITAL_DATA",
        },
    }
