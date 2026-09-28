import unittest

from research.wallet_s4_historical_performance import compute_wallet_performance

WALLET = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
OTHER_WALLET = "7YWHMfk9JZe0LMVx7uL8b2NBG7oAqZ3M5Gx8E6JxSk3N"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
SOL = "SOL_NATIVE"


def episode(
    i,
    pnl,
    roi,
    *,
    wallet=WALLET,
    quote=USDC,
    usd=True,
    closed_at=None,
    holding=3600,
    eligible=True,
    status="CLOSED",
    fee_lamports=0,
    fee_cost_quote=None,
):
    row = {
        "episode_id": f"ep-{i}",
        "wallet": wallet,
        "base_asset": f"TOKEN-{i % 3}",
        "quote_asset": quote,
        "quote_is_usd": usd,
        "status": status,
        "opened_at": (closed_at if closed_at is not None else i * 86400) - holding,
        "closed_at": closed_at if closed_at is not None else i * 86400,
        "close_slot": i,
        "holding_seconds": holding,
        "realized_cost_quote": "100",
        "realized_pnl_quote": str(pnl),
        "realized_roi_pct": str(roi),
        "network_fee_lamports": fee_lamports,
        "eligible_for_performance_metrics": eligible,
    }
    if fee_cost_quote is not None:
        row["fee_cost_quote"] = str(fee_cost_quote)
    return row


class Stage4HistoricalPerformanceTests(unittest.TestCase):
    def test_filters_non_scorable_episodes(self):
        result = compute_wallet_performance([
            episode(1, 10, 10),
            episode(2, 50, 50, eligible=False, status="CLOSED_CONTAMINATED"),
        ])
        self.assertEqual(result["closed_trade_count"], 1)
        self.assertEqual(result["median_roi_pct"], "10")

    def test_core_behavior_metrics(self):
        result = compute_wallet_performance([
            episode(1, 10, 10),
            episode(2, -4, -4),
            episode(3, -3, -3),
            episode(4, 8, 8),
        ])
        self.assertEqual(result["closed_trade_count"], 4)
        self.assertEqual(result["wins"], 2)
        self.assertEqual(result["losses"], 2)
        self.assertEqual(result["win_rate_pct"], "50")
        self.assertEqual(result["median_roi_pct"], "2.5")
        self.assertEqual(result["max_loss_streak"], 2)
        self.assertEqual(result["max_win_streak"], 1)

    def test_profit_factor_and_drawdown_are_quote_specific(self):
        result = compute_wallet_performance([
            episode(1, 10, 10),
            episode(2, -4, -4),
            episode(3, -3, -3),
            episode(4, 8, 8),
        ])
        metrics = result["quote_metrics"][USDC]
        self.assertEqual(metrics["total_realized_pnl_quote"], "11")
        self.assertEqual(metrics["gross_profit_quote"], "18")
        self.assertEqual(metrics["gross_loss_quote_abs"], "7")
        self.assertEqual(metrics["profit_factor"], "2.571428571428571428571428571")
        self.assertEqual(metrics["max_drawdown_quote"], "7")

    def test_mixed_quotes_do_not_get_fake_overall_profit_factor(self):
        result = compute_wallet_performance([
            episode(1, 10, 10, quote=USDC, usd=True),
            episode(2, 2, 2, quote=SOL, usd=False),
        ])
        self.assertFalse(result["overall_profit_factor_available"])
        self.assertIsNone(result["overall_profit_factor"])
        self.assertEqual(set(result["quote_metrics"]), {USDC, SOL})

    def test_usdc_and_usdt_are_combined_only_in_usd_comparable_bucket(self):
        result = compute_wallet_performance([
            episode(1, 10, 10, quote=USDC, usd=True),
            episode(2, -4, -4, quote=USDT, usd=True),
        ])
        usd = result["usd_comparable"]
        self.assertEqual(usd["closed_trade_count"], 2)
        self.assertEqual(usd["gross_total_realized_pnl_usd_stable"], "6")
        self.assertEqual(usd["gross_profit_factor"], "2.5")

    def test_sol_quote_gets_direct_network_fee_adjustment(self):
        result = compute_wallet_performance([
            episode(
                1,
                1,
                1,
                quote=SOL,
                usd=False,
                fee_lamports=100_000_000,
            ),
        ])
        metrics = result["quote_metrics"][SOL]
        self.assertTrue(metrics["net_metrics_complete"])
        self.assertEqual(metrics["net_total_realized_pnl_quote"], "0.9")
        self.assertEqual(metrics["net_median_roi_pct"], "0.9")
        self.assertIn("SOL_NETWORK_FEE_DIRECT", metrics["fee_adjustment_sources"])

    def test_explicit_fee_cost_quote_enables_net_usd_metrics(self):
        result = compute_wallet_performance([
            episode(1, 10, 10, fee_cost_quote="1"),
            episode(2, -4, -4, fee_cost_quote="1"),
        ])
        metrics = result["quote_metrics"][USDC]
        self.assertTrue(metrics["net_metrics_complete"])
        self.assertEqual(metrics["net_total_realized_pnl_quote"], "4")
        self.assertEqual(result["usd_comparable"]["net_total_realized_pnl_usd_stable"], "4")
        self.assertEqual(result["usd_comparable"]["net_median_roi_pct"], "2")
        self.assertEqual(result["usd_comparable"]["net_win_rate_pct"], "50")

    def test_missing_fee_conversion_keeps_net_total_unavailable(self):
        result = compute_wallet_performance([
            episode(1, 10, 10, fee_cost_quote="1"),
            episode(2, -4, -4),
        ])
        metrics = result["quote_metrics"][USDC]
        self.assertFalse(metrics["net_metrics_complete"])
        self.assertIsNone(metrics["net_total_realized_pnl_quote"])
        self.assertFalse(result["usd_comparable"]["net_metrics_complete"])

    def test_activity_consistency_uses_utc_close_days(self):
        result = compute_wallet_performance([
            episode(1, 1, 1, closed_at=0),
            episode(2, 1, 1, closed_at=2 * 86400),
            episode(3, 1, 1, closed_at=2 * 86400 + 1),
        ])
        activity = result["activity"]
        self.assertEqual(activity["active_days"], 2)
        self.assertEqual(activity["calendar_span_days"], 3)
        self.assertEqual(activity["active_day_ratio_pct"], "66.66666666666666666666666667")
        self.assertEqual(activity["trades_per_active_day"], "1.5")

    def test_recent_performance_compares_recent_window_to_prior(self):
        result = compute_wallet_performance([
            episode(1, -10, -10),
            episode(2, -5, -5),
            episode(3, 5, 5),
            episode(4, 10, 10),
        ], recent_window=2)
        trend = result["recent_performance"]
        self.assertTrue(trend["trend_comparable"])
        self.assertEqual(trend["prior"]["median_roi_pct"], "-7.5")
        self.assertEqual(trend["recent"]["median_roi_pct"], "7.5")
        self.assertEqual(trend["median_roi_delta_pct_points"], "15")
        self.assertEqual(trend["win_rate_delta_pct_points"], "100")

    def test_fifty_clean_fee_adjusted_trades_are_classification_ready(self):
        rows = [
            episode(i + 1, 1, 1, fee_cost_quote="0.1")
            for i in range(50)
        ]
        result = compute_wallet_performance(rows)
        self.assertTrue(result["meets_50_trade_sample"])
        self.assertTrue(
            result["qualification_readiness"]["net_classification_ready"]
        )

    def test_no_clean_episode_returns_unavailable_profile(self):
        result = compute_wallet_performance([
            episode(
                1,
                10,
                10,
                eligible=False,
                status="CLOSED_CONTAMINATED",
            )
        ])
        self.assertFalse(result["performance_available"])
        self.assertEqual(result["closed_trade_count"], 0)

    def test_multiple_wallets_raise_instead_of_merging_profiles(self):
        with self.assertRaises(ValueError):
            compute_wallet_performance([
                episode(1, 10, 10, wallet=WALLET),
                episode(2, 10, 10, wallet=OTHER_WALLET),
            ])


if __name__ == "__main__":
    unittest.main()
