import unittest
from decimal import Decimal

from research.wallet_s10_paper_trading import (
    PaperTradingConfig,
    evaluate_candidate_rule,
    run_wallet_only_paper_trading,
)

TOKEN_A = "A1111111111111111111111111111111111111111111"
TOKEN_B = "B1111111111111111111111111111111111111111111"
WALLET_A = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
WALLET_B = "22222222222222222222222222222222"
WALLET_C = "33333333333333333333333333333333"


def contributor(wallet, side, *, meme=False):
    return {
        "wallet": wallet,
        "sides": [side],
        "event_count": 1,
        "latest_activity_time": 1000,
        "primary_segments_observed": ["S1"],
        "qualifying_segments": ["S1"],
        "meme_label_statuses": ["EVIDENCE_PROFILE_ONLY"] if meme else [],
        "meme_evidence_available": meme,
        "matched_explosion_events": 3 if meme else 0,
        "matched_explosion_distinct_tokens": 2 if meme else 0,
        "registry_snapshot_ids": ["snap-1"],
    }


def signal(
    *,
    token=TOKEN_A,
    as_of=1000,
    state="ACCUMULATION",
    buy_wallets=3,
    sell_wallets=0,
    wallet_net=None,
    tiers=None,
    usd_coverage="COMPLETE",
    usd_direction=None,
    meme_buy=False,
    meme_sell=False,
):
    if wallet_net is None:
        wallet_net = buy_wallets - sell_wallets
    if tiers is None:
        tiers = {
            "S1": {
                "buy_wallet_count": buy_wallets,
                "sell_wallet_count": sell_wallets,
            }
        }
    if usd_direction is None:
        usd_direction = "POSITIVE" if state == "ACCUMULATION" else "NEGATIVE"

    contributors = []
    buy_ids = [WALLET_A, WALLET_B, WALLET_C][:buy_wallets]
    sell_ids = [WALLET_A, WALLET_B, WALLET_C][:sell_wallets]
    for i, wallet in enumerate(buy_ids):
        contributors.append(
            contributor(wallet, "BUY", meme=(meme_buy and i == 0))
        )
    for i, wallet in enumerate(sell_ids):
        contributors.append(
            contributor(wallet, "SELL", meme=(meme_sell and i == 0))
        )

    return {
        "version": "wallet-s9-v1",
        "chain": "solana",
        "base_asset": token,
        "as_of": as_of,
        "state": state,
        "state_basis_window": "5m",
        "freshness": {
            "last_activity_time": as_of,
            "age_seconds": 0,
            "bucket": "WITHIN_5M",
        },
        "qualified_wallet_activity": {
            "unique_wallet_count": len(set(buy_ids + sell_ids)),
            "buy_wallet_count": buy_wallets,
            "sell_wallet_count": sell_wallets,
            "wallet_net_count": wallet_net,
            "segment_membership_wallet_counts": tiers,
        },
        "base_flow": {
            "net_base_amount": "10" if state == "ACCUMULATION" else "-10",
            "direction": state,
        },
        "validated_usd_flow": {
            "coverage": usd_coverage,
            "priced_event_count": 3 if usd_coverage != "UNAVAILABLE" else 0,
            "unpriced_event_count": 0 if usd_coverage == "COMPLETE" else 1,
            "validated_usd_buy_notional": "30",
            "validated_usd_sell_notional": "0",
            "validated_usd_net_notional": "30" if usd_direction == "POSITIVE" else "-30",
            "direction": usd_direction,
        },
        "window_metrics": {},
        "persistence": {
            "directional_agreement_windows": ["5m", "15m", "1h"],
            "spans_15m_directionally": True,
            "spans_1h_directionally": False,
        },
        "meme_hunter_evidence": {
            "evidence_wallet_count": int(meme_buy or meme_sell),
            "label_status_counts": (
                {"EVIDENCE_PROFILE_ONLY": 1}
                if (meme_buy or meme_sell)
                else {}
            ),
            "historical_matched_explosion_events_sum": 3 if (meme_buy or meme_sell) else 0,
            "historical_matched_explosion_distinct_tokens_sum": 2 if (meme_buy or meme_sell) else 0,
            "calibration_status": "EVIDENCE_ONLY_STAGE6_V1",
        },
        "contributors": contributors,
        "registry_provenance": {
            "snapshot_ids": ["snap-1"],
            "snapshot_fingerprints": ["fp-1"],
            "mixed_snapshot_ids": False,
            "mixed_snapshot_fingerprints": False,
            "policy": "EVENT_TIME_QUALIFICATION_PROVENANCE",
        },
        "scoring": {"strength_score": None},
        "signal_fingerprint": f"sig-{token}-{as_of}-{state}",
    }


def snapshot(*signals, as_of=None):
    if as_of is None:
        as_of = signals[0]["as_of"] if signals else 1000
    return {
        "version": "wallet-s9-v1",
        "chain": "solana",
        "as_of": as_of,
        "signal_count": len(signals),
        "signals": list(signals),
        "contract": {"type": "SMART_MONEY_SIGNAL_SNAPSHOT"},
        "snapshot_fingerprint": f"snap-{as_of}",
    }


def bar(ts, o, h=None, l=None, c=None):
    o = Decimal(str(o))
    if h is None:
        h = o
    if l is None:
        l = o
    if c is None:
        c = o
    return {
        "timestamp": ts,
        "open": str(o),
        "high": str(h),
        "low": str(l),
        "close": str(c),
    }


def config(**kwargs):
    base = dict(
        fee_bps_per_side=Decimal("5"),
        slippage_bps_per_side=Decimal("5"),
    )
    base.update(kwargs)
    return PaperTradingConfig(**base)


class Stage10PaperTradingTests(unittest.TestCase):
    def test_rule_a_requires_two_directional_wallets(self):
        self.assertTrue(evaluate_candidate_rule(signal(buy_wallets=2), "A")["eligible"])
        self.assertFalse(evaluate_candidate_rule(signal(buy_wallets=1), "A")["eligible"])

    def test_rule_b_requires_three_directional_wallets(self):
        self.assertTrue(evaluate_candidate_rule(signal(buy_wallets=3), "B")["eligible"])
        self.assertFalse(evaluate_candidate_rule(signal(buy_wallets=2), "B")["eligible"])

    def test_rule_c_requires_higher_tier_participation(self):
        tiers = {
            "S1": {"buy_wallet_count": 3, "sell_wallet_count": 0},
            "S2": {"buy_wallet_count": 1, "sell_wallet_count": 0},
        }
        self.assertTrue(evaluate_candidate_rule(signal(tiers=tiers), "C")["eligible"])
        self.assertFalse(evaluate_candidate_rule(signal(), "C")["eligible"])

    def test_rule_d_requires_side_aligned_meme_evidence(self):
        self.assertTrue(evaluate_candidate_rule(signal(meme_buy=True), "D")["eligible"])
        self.assertFalse(evaluate_candidate_rule(signal(meme_sell=True), "D")["eligible"])

    def test_rule_e_requires_wallet_advantage_and_usd_alignment(self):
        self.assertTrue(
            evaluate_candidate_rule(
                signal(buy_wallets=3, sell_wallets=1, wallet_net=2),
                "E",
            )["eligible"]
        )
        self.assertFalse(
            evaluate_candidate_rule(
                signal(
                    buy_wallets=3,
                    sell_wallets=1,
                    wallet_net=2,
                    usd_direction="NEGATIVE",
                ),
                "E",
            )["eligible"]
        )

    def test_neutral_signal_never_qualifies(self):
        row = signal(state="NEUTRAL", buy_wallets=3, sell_wallets=3, wallet_net=0)
        self.assertFalse(evaluate_candidate_rule(row, "A")["eligible"])
        self.assertIsNone(evaluate_candidate_rule(row, "A")["side"])

    def test_entry_is_first_bar_strictly_after_signal(self):
        result = run_wallet_only_paper_trading(
            [snapshot(signal(buy_wallets=2))],
            {
                TOKEN_A: [
                    bar(1000, 100, 100, 100, 100),
                    bar(1060, 101, 103, 99, 102),
                ]
            },
            config=config(),
            rule_ids=["A"],
        )
        trade = result["rules"]["A"]["trades"][0]
        self.assertEqual(trade["entry_time"], 1060)
        self.assertEqual(trade["raw_entry_price"], "101")

    def test_long_tp_first(self):
        result = run_wallet_only_paper_trading(
            [snapshot(signal(buy_wallets=2))],
            {TOKEN_A: [bar(1060, 100, 102, 99.5, 101)]},
            config=config(),
            rule_ids=["A"],
        )
        trade = result["rules"]["A"]["trades"][0]
        self.assertEqual(trade["side"], "LONG")
        self.assertEqual(trade["exit_reason"], "TP_FIRST")
        self.assertIsNotNone(trade["net_return_pct_after_fees_slippage"])

    def test_long_sl_first(self):
        result = run_wallet_only_paper_trading(
            [snapshot(signal(buy_wallets=2))],
            {TOKEN_A: [bar(1060, 100, 100.2, 98, 99)]},
            config=config(),
            rule_ids=["A"],
        )
        self.assertEqual(result["rules"]["A"]["trades"][0]["exit_reason"], "SL_FIRST")

    def test_same_bar_tp_sl_tie_is_conservative_stop(self):
        result = run_wallet_only_paper_trading(
            [snapshot(signal(buy_wallets=2))],
            {TOKEN_A: [bar(1060, 100, 102, 98, 100)]},
            config=config(),
            rule_ids=["A"],
        )
        trade = result["rules"]["A"]["trades"][0]
        self.assertEqual(trade["exit_reason"], "SL_FIRST_TIE_CONSERVATIVE")
        self.assertTrue(trade["same_bar_tp_sl_tie"])

    def test_short_tp_first(self):
        short = signal(
            state="DISTRIBUTION",
            buy_wallets=0,
            sell_wallets=2,
            wallet_net=-2,
        )
        result = run_wallet_only_paper_trading(
            [snapshot(short)],
            {TOKEN_A: [bar(1060, 100, 100.3, 98, 99)]},
            config=config(),
            rule_ids=["A"],
        )
        trade = result["rules"]["A"]["trades"][0]
        self.assertEqual(trade["side"], "SHORT")
        self.assertEqual(trade["exit_reason"], "TP_FIRST")

    def test_costs_reduce_net_return(self):
        result = run_wallet_only_paper_trading(
            [snapshot(signal(buy_wallets=2))],
            {TOKEN_A: [bar(1060, 100, 102, 99.5, 101)]},
            config=config(
                fee_bps_per_side=Decimal("10"),
                slippage_bps_per_side=Decimal("10"),
            ),
            rule_ids=["A"],
        )
        trade = result["rules"]["A"]["trades"][0]
        self.assertLess(
            Decimal(trade["net_return_pct_after_fees_slippage"]),
            Decimal(trade["gross_return_pct"]),
        )

    def test_missing_price_series_counts_no_entry(self):
        result = run_wallet_only_paper_trading(
            [snapshot(signal(buy_wallets=2))],
            {},
            config=config(),
            rule_ids=["A"],
        )
        summary = result["rules"]["A"]["summary"]
        self.assertEqual(summary["opened_trade_count"], 0)
        self.assertEqual(summary["no_entry_price_count"], 1)

    def test_max_entry_delay_rejects_stale_price(self):
        result = run_wallet_only_paper_trading(
            [snapshot(signal(buy_wallets=2))],
            {TOKEN_A: [bar(2000, 100, 102, 98, 100)]},
            config=config(max_entry_delay_seconds=300),
            rule_ids=["A"],
        )
        self.assertEqual(result["rules"]["A"]["summary"]["no_entry_price_count"], 1)

    def test_incomplete_data_is_not_forced_to_timeout(self):
        result = run_wallet_only_paper_trading(
            [snapshot(signal(buy_wallets=2))],
            {TOKEN_A: [bar(1060, 100, 100.2, 99.8, 100)]},
            config=config(max_holding_seconds=3600),
            rule_ids=["A"],
        )
        trade = result["rules"]["A"]["trades"][0]
        self.assertEqual(trade["exit_reason"], "INCOMPLETE_DATA")
        self.assertIsNone(trade["net_return_pct_after_fees_slippage"])

    def test_timeout_requires_known_full_coverage(self):
        result = run_wallet_only_paper_trading(
            [snapshot(signal(buy_wallets=2))],
            {
                TOKEN_A: [
                    bar(1060, 100, 100.2, 99.8, 100),
                    bar(4600, 100.1, 100.3, 99.9, 100.2),
                    bar(4700, 100.2, 100.3, 100, 100.2),
                ]
            },
            config=config(max_holding_seconds=3600),
            rule_ids=["A"],
        )
        trade = result["rules"]["A"]["trades"][0]
        self.assertEqual(trade["exit_reason"], "TIMEOUT")
        self.assertTrue(trade["coverage_complete_to_timeout"])

    def test_one_active_position_per_symbol_skips_overlap(self):
        s1 = signal(as_of=1000, buy_wallets=2)
        s2 = signal(as_of=1100, buy_wallets=2)
        result = run_wallet_only_paper_trading(
            [snapshot(s1), snapshot(s2)],
            {
                TOKEN_A: [
                    bar(1060, 100, 100.2, 99.8, 100),
                    bar(1200, 100, 102, 99.5, 101),
                ]
            },
            config=config(),
            rule_ids=["A"],
        )
        summary = result["rules"]["A"]["summary"]
        self.assertEqual(summary["opened_trade_count"], 1)
        self.assertEqual(summary["skipped_active_position_count"], 1)

    def test_reentry_is_allowed_after_prior_trade_closes(self):
        s1 = signal(as_of=1000, buy_wallets=2)
        s2 = signal(as_of=1200, buy_wallets=2)
        result = run_wallet_only_paper_trading(
            [snapshot(s1), snapshot(s2)],
            {
                TOKEN_A: [
                    bar(1060, 100, 102, 99.5, 101),
                    bar(1260, 100, 102, 99.5, 101),
                ]
            },
            config=config(),
            rule_ids=["A"],
        )
        self.assertEqual(result["rules"]["A"]["summary"]["opened_trade_count"], 2)

    def test_all_required_evaluation_horizons_are_recorded(self):
        result = run_wallet_only_paper_trading(
            [snapshot(signal(buy_wallets=2))],
            {TOKEN_A: [bar(1060, 100, 102, 99.5, 101)]},
            config=config(),
            rule_ids=["A"],
        )
        horizons = result["rules"]["A"]["trades"][0]["evaluation_horizons"]
        self.assertEqual(set(horizons), {"30m", "1h", "4h", "12h", "24h"})

    def test_horizon_data_can_remain_incomplete_after_trade_exit(self):
        result = run_wallet_only_paper_trading(
            [snapshot(signal(buy_wallets=2))],
            {TOKEN_A: [bar(1060, 100, 102, 99.5, 101)]},
            config=config(),
            rule_ids=["A"],
        )
        horizon = result["rules"]["A"]["trades"][0]["evaluation_horizons"]["24h"]
        self.assertFalse(horizon["coverage_complete"])

    def test_actual_mfe_mae_stop_at_trade_exit(self):
        result = run_wallet_only_paper_trading(
            [snapshot(signal(buy_wallets=2))],
            {
                TOKEN_A: [
                    bar(1060, 100, 102, 99.5, 101),
                    bar(1120, 101, 150, 50, 100),
                ]
            },
            config=config(),
            rule_ids=["A"],
        )
        trade = result["rules"]["A"]["trades"][0]
        self.assertLess(Decimal(trade["mfe_pct"]), Decimal("5"))
        self.assertGreater(Decimal(trade["mae_pct"]), Decimal("-5"))

    def test_summary_reports_tp_before_sl_benchmark(self):
        s1 = signal(token=TOKEN_A, buy_wallets=2)
        s2 = signal(token=TOKEN_B, buy_wallets=2)
        result = run_wallet_only_paper_trading(
            [snapshot(s1, s2)],
            {
                TOKEN_A: [bar(1060, 100, 102, 99.5, 101)],
                TOKEN_B: [bar(1060, 100, 100.2, 98, 99)],
            },
            config=config(),
            rule_ids=["A"],
        )
        summary = result["rules"]["A"]["summary"]
        self.assertEqual(summary["tp_first_count"], 1)
        self.assertEqual(summary["sl_first_count"], 1)
        self.assertEqual(summary["p_tp_before_sl_pct_resolved"], "50")

    def test_no_winner_is_selected_in_stage10(self):
        result = run_wallet_only_paper_trading(
            [snapshot(signal(buy_wallets=3))],
            {TOKEN_A: [bar(1060, 100, 102, 99, 101)]},
            config=config(),
            rule_ids=["A", "B"],
        )
        self.assertFalse(result["experiment_policy"]["winner_selected"])
        self.assertEqual(
            result["experiment_policy"]["winner_selection_stage"],
            "STAGE11",
        )
        self.assertFalse(result["rules"]["A"]["summary"]["winner_selected"])

    def test_future_s4_s5_counts_are_preserved_in_trade_features(self):
        tiers = {
            "S1": {"buy_wallet_count": 3, "sell_wallet_count": 0},
            "S4": {"buy_wallet_count": 1, "sell_wallet_count": 0},
            "S5": {"buy_wallet_count": 1, "sell_wallet_count": 0},
        }
        result = run_wallet_only_paper_trading(
            [snapshot(signal(buy_wallets=3, tiers=tiers))],
            {TOKEN_A: [bar(1060, 100, 102, 99.5, 101)]},
            config=config(),
            rule_ids=["B"],
        )
        counts = result["rules"]["B"]["trades"][0]["feature_snapshot"][
            "tier_counts_directional"
        ]
        self.assertEqual(counts["S4"], 1)
        self.assertEqual(counts["S5"], 1)

    def test_multiple_tokens_have_independent_position_state(self):
        result = run_wallet_only_paper_trading(
            [snapshot(
                signal(token=TOKEN_A, buy_wallets=2),
                signal(token=TOKEN_B, buy_wallets=2),
            )],
            {
                TOKEN_A: [bar(1060, 100, 102, 99.5, 101)],
                TOKEN_B: [bar(1060, 50, 51, 49.5, 50.5)],
            },
            config=config(),
            rule_ids=["A"],
        )
        self.assertEqual(result["rules"]["A"]["summary"]["opened_trade_count"], 2)

    def test_conflicting_duplicate_signal_is_rejected(self):
        a = signal(as_of=1000, buy_wallets=2)
        b = dict(a)
        b["state"] = "DISTRIBUTION"
        b["signal_fingerprint"] = "different"
        with self.assertRaises(ValueError):
            run_wallet_only_paper_trading(
                [snapshot(a), snapshot(b)],
                {TOKEN_A: []},
                config=config(),
                rule_ids=["A"],
            )

    def test_unsupported_stage9_version_is_rejected(self):
        bad = snapshot(signal(buy_wallets=2))
        bad["version"] = "wallet-s9-v999"
        with self.assertRaises(ValueError):
            run_wallet_only_paper_trading(
                [bad],
                {TOKEN_A: []},
                config=config(),
                rule_ids=["A"],
            )

    def test_invalid_ohlc_is_rejected(self):
        with self.assertRaises(ValueError):
            run_wallet_only_paper_trading(
                [snapshot(signal(buy_wallets=2))],
                {TOKEN_A: [bar(1060, 100, 99, 98, 100)]},
                config=config(),
                rule_ids=["A"],
            )

    def test_duplicate_rule_request_is_rejected(self):
        with self.assertRaises(ValueError):
            run_wallet_only_paper_trading(
                [],
                {},
                config=config(),
                rule_ids=["A", "A"],
            )

    def test_result_fingerprint_is_deterministic(self):
        snaps = [snapshot(signal(buy_wallets=2))]
        bars = {TOKEN_A: [bar(1060, 100, 102, 99.5, 101)]}
        one = run_wallet_only_paper_trading(
            snaps,
            bars,
            config=config(),
            rule_ids=["A"],
        )
        two = run_wallet_only_paper_trading(
            list(reversed(snaps)),
            bars,
            config=config(),
            rule_ids=["A"],
        )
        self.assertEqual(one["result_fingerprint"], two["result_fingerprint"])

    def test_config_rejects_negative_costs(self):
        with self.assertRaises(ValueError):
            PaperTradingConfig(
                fee_bps_per_side=Decimal("-1"),
                slippage_bps_per_side=Decimal("0"),
            )


if __name__ == "__main__":
    unittest.main()
