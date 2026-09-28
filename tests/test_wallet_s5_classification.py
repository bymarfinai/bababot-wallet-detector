import unittest

from research.wallet_s5_classification import classify_wallet

WALLET = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL = "SOL_NATIVE"


def usd_profile(
    *,
    trades=50,
    roi="1",
    win_rate="60",
    pnl="1",
    performance_available=True,
    net_complete=True,
):
    return {
        "wallet": WALLET,
        "performance_available": performance_available,
        "closed_trade_count": trades,
        "quote_assets": [USDC],
        "quote_metrics": {
            USDC: {
                "net_metrics_complete": net_complete,
                "net_median_roi_pct": roi if net_complete else None,
                "net_win_rate_pct": win_rate if net_complete else None,
                "net_total_realized_pnl_quote": pnl if net_complete else None,
                "net_profit_factor": "2",
                "max_drawdown_quote": "5",
            }
        },
        "usd_comparable": {
            "closed_trade_count": trades,
            "net_metrics_complete": net_complete,
            "net_median_roi_pct": roi if net_complete else None,
            "net_win_rate_pct": win_rate if net_complete else None,
            "net_total_realized_pnl_usd_stable": pnl if net_complete else None,
            "net_profit_factor": "2",
            "max_drawdown_usd_stable": "5",
        },
    }


def sol_profile(*, trades=50, roi="5", win_rate="55", pnl="2"):
    return {
        "wallet": WALLET,
        "performance_available": True,
        "closed_trade_count": trades,
        "quote_assets": [SOL],
        "quote_metrics": {
            SOL: {
                "net_metrics_complete": True,
                "net_median_roi_pct": roi,
                "net_win_rate_pct": win_rate,
                "net_total_realized_pnl_quote": pnl,
                "net_profit_factor": "1.8",
                "max_drawdown_quote": "0.5",
            }
        },
        "usd_comparable": {
            "closed_trade_count": 0,
            "net_metrics_complete": False,
        },
    }


class Stage5ClassificationTests(unittest.TestCase):
    def test_exact_s1_boundary_qualifies(self):
        result = classify_wallet(
            usd_profile(trades=50, roi="1", win_rate="60", pnl="0.01")
        )
        self.assertEqual(result["status"], "QUALIFIED")
        self.assertEqual(result["primary_segment"], "S1")
        self.assertEqual(result["qualifying_segments"], ["S1"])

    def test_s1_requires_sixty_percent_net_win_rate(self):
        result = classify_wallet(
            usd_profile(trades=50, roi="2", win_rate="59.99", pnl="10")
        )
        self.assertEqual(result["status"], "UNQUALIFIED")
        self.assertFalse(result["segments"]["S1"]["qualified"])
        self.assertIn(
            "net_win_rate_met",
            result["segments"]["S1"]["failed_checks"],
        )

    def test_s2_qualifies_at_five_percent_without_invented_wr_gate(self):
        result = classify_wallet(
            usd_profile(trades=50, roi="5", win_rate="40", pnl="10")
        )
        self.assertEqual(result["primary_segment"], "S2")
        self.assertEqual(result["qualifying_segments"], ["S2"])

    def test_s3_qualifies_at_ten_percent(self):
        result = classify_wallet(
            usd_profile(trades=50, roi="10", win_rate="40", pnl="10")
        )
        self.assertEqual(result["primary_segment"], "S3")
        self.assertEqual(result["qualifying_segments"], ["S2", "S3"])

    def test_high_velocity_can_also_match_consistency_rule(self):
        result = classify_wallet(
            usd_profile(trades=50, roi="12", win_rate="70", pnl="10")
        )
        self.assertEqual(result["primary_segment"], "S3")
        self.assertEqual(result["qualifying_segments"], ["S1", "S2", "S3"])
        self.assertIn("not a quality ranking", result["primary_segment_note"])

    def test_positive_roi_but_negative_total_pnl_does_not_qualify(self):
        result = classify_wallet(
            usd_profile(trades=50, roi="12", win_rate="70", pnl="-1")
        )
        self.assertEqual(result["status"], "UNQUALIFIED")
        self.assertIsNone(result["primary_segment"])
        self.assertFalse(result["segments"]["S3"]["qualified"])

    def test_49_trades_is_not_enough(self):
        result = classify_wallet(
            usd_profile(trades=49, roi="12", win_rate="70", pnl="10")
        )
        self.assertEqual(result["status"], "UNQUALIFIED")
        self.assertIn(
            "closed_trades_gte_50",
            result["segments"]["S3"]["failed_checks"],
        )

    def test_incomplete_fee_adjustment_is_not_ready(self):
        result = classify_wallet(
            usd_profile(
                trades=100,
                roi="12",
                win_rate="70",
                pnl="10",
                net_complete=False,
            )
        )
        self.assertEqual(result["status"], "NOT_READY")
        self.assertEqual(
            result["reason"],
            "NO_COMPARABLE_COMPLETE_NET_BASIS",
        )

    def test_single_sol_quote_can_classify_without_usd_conversion(self):
        result = classify_wallet(
            sol_profile(trades=60, roi="6", win_rate="55", pnl="3")
        )
        self.assertEqual(result["status"], "QUALIFIED")
        self.assertEqual(result["primary_segment"], "S2")
        self.assertEqual(result["basis"]["kind"], "SINGLE_QUOTE")
        self.assertEqual(result["basis"]["quote_asset"], SOL)

    def test_mixed_noncomparable_quotes_are_not_ready(self):
        profile = sol_profile()
        profile["quote_assets"] = [SOL, USDC]
        profile["quote_metrics"][USDC] = {
            "net_metrics_complete": True,
            "net_median_roi_pct": "6",
            "net_win_rate_pct": "60",
            "net_total_realized_pnl_quote": "10",
        }
        result = classify_wallet(profile)
        self.assertEqual(result["status"], "NOT_READY")

    def test_no_performance_profile_is_not_ready(self):
        result = classify_wallet(
            usd_profile(performance_available=False)
        )
        self.assertEqual(result["status"], "NOT_READY")
        self.assertEqual(result["reason"], "NO_CLEAN_PERFORMANCE_PROFILE")

    def test_v1_does_not_invent_drawdown_or_special_label_rules(self):
        result = classify_wallet(
            usd_profile(trades=50, roi="5", win_rate="60", pnl="10")
        )
        self.assertIn("not a V1 classification gate", result["risk_note"])
        self.assertEqual(
            result["special_labels"]["meme_hunter"],
            "DEFERRED_TO_STAGE_6",
        )
        self.assertEqual(
            result["special_labels"]["whale"],
            "DEFERRED_UNTIL_RELIABLE_CAPITAL_DATA",
        )


if __name__ == "__main__":
    unittest.main()
