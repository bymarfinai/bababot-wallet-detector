import json
import unittest

from research.wallet_s9_smart_money_signal import (
    build_smart_money_signal_snapshot,
    serialize_signal_snapshot,
)

WALLET_A = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
WALLET_B = "22222222222222222222222222222222"
TOKEN_A = "A1111111111111111111111111111111111111111111"
TOKEN_B = "B1111111111111111111111111111111111111111111"


def event(
    wallet,
    signature,
    block_time,
    side,
    *,
    token=TOKEN_A,
    base_amount="1",
    usd_notional="1",
    segments=None,
    primary="S1",
    snapshot_id="snap-1",
    snapshot_fingerprint="fp-1",
    meme_evidence=None,
    meme_label=None,
):
    if segments is None:
        segments = ["S1"]
    return {
        "event_type": "SWAP",
        "side": side,
        "wallet": wallet,
        "signature": signature,
        "block_time": block_time,
        "slot": block_time,
        "base_asset": token,
        "base_amount": str(base_amount),
        "quote_asset": "USD_STABLE" if usd_notional is not None else "SOL_NATIVE",
        "usd_notional": (
            str(usd_notional) if usd_notional is not None else None
        ),
        "primary_segment": primary,
        "qualifying_segments": list(segments),
        "meme_hunter_evidence": meme_evidence,
        "special_labels": (
            {"meme_hunter": meme_label} if meme_label else {}
        ),
        "registry_snapshot_id": snapshot_id,
        "registry_snapshot_fingerprint": snapshot_fingerprint,
        "registry_record_fingerprint": f"record-{wallet}",
        "live_event_id": f"{wallet}:{signature}",
        "idempotency_key": f"{wallet}:{signature}",
    }


def meme_evidence(matches=3, tokens=2):
    return {
        "evidence_profile_available": True,
        "label_status": "EVIDENCE_PROFILE_ONLY",
        "matched_explosion_events": matches,
        "matched_distinct_tokens": tokens,
    }


class Stage9SmartMoneySignalTests(unittest.TestCase):
    def test_accumulation_signal_uses_freshest_active_window(self):
        snapshot = build_smart_money_signal_snapshot(
            [
                event(WALLET_A, "a", 990, "BUY", base_amount=10),
                event(WALLET_B, "b", 995, "BUY", base_amount=5),
                event(WALLET_B, "c", 998, "SELL", base_amount=2),
            ],
            as_of=1000,
        )
        signal = snapshot["signals"][0]

        self.assertEqual(signal["state"], "ACCUMULATION")
        self.assertEqual(signal["state_basis_window"], "5m")
        self.assertEqual(
            signal["qualified_wallet_activity"]["buy_wallet_count"],
            2,
        )
        self.assertEqual(
            signal["qualified_wallet_activity"]["sell_wallet_count"],
            1,
        )
        self.assertEqual(signal["base_flow"]["net_base_amount"], "13")

    def test_distribution_signal(self):
        signal = build_smart_money_signal_snapshot(
            [
                event(WALLET_A, "a", 990, "BUY", base_amount=2),
                event(WALLET_B, "b", 995, "SELL", base_amount=10),
            ],
            as_of=1000,
        )["signals"][0]

        self.assertEqual(signal["state"], "DISTRIBUTION")
        self.assertEqual(signal["base_flow"]["direction"], "DISTRIBUTION")

    def test_balanced_stage8_flow_becomes_neutral_external_state(self):
        signal = build_smart_money_signal_snapshot(
            [
                event(WALLET_A, "a", 990, "BUY", base_amount=5),
                event(WALLET_B, "b", 995, "SELL", base_amount=5),
            ],
            as_of=1000,
        )["signals"][0]

        self.assertEqual(signal["state"], "NEUTRAL")
        self.assertEqual(signal["base_flow"]["direction"], "NEUTRAL")

    def test_exact_five_minute_boundary_is_not_within_5m(self):
        signal = build_smart_money_signal_snapshot(
            [event(WALLET_A, "a", 700, "BUY")],
            as_of=1000,
        )["signals"][0]

        self.assertEqual(signal["state_basis_window"], "15m")
        self.assertEqual(signal["freshness"]["age_seconds"], 300)
        self.assertEqual(signal["freshness"]["bucket"], "WITHIN_15M")

    def test_event_older_than_one_hour_is_excluded(self):
        snapshot = build_smart_money_signal_snapshot(
            [event(WALLET_A, "old", 100, "BUY")],
            as_of=4000,
        )
        self.assertEqual(snapshot["signal_count"], 0)

    def test_future_event_is_excluded(self):
        snapshot = build_smart_money_signal_snapshot(
            [event(WALLET_A, "future", 1001, "BUY")],
            as_of=1000,
        )
        self.assertEqual(snapshot["signal_count"], 0)

    def test_nested_window_agreement_does_not_fake_temporal_persistence(self):
        signal = build_smart_money_signal_snapshot(
            [event(WALLET_A, "recent", 950, "BUY")],
            as_of=1000,
        )["signals"][0]
        persistence = signal["persistence"]

        self.assertEqual(
            persistence["directional_agreement_windows"],
            ["5m", "15m", "1h"],
        )
        self.assertTrue(persistence["all_active_windows_agree"])
        self.assertFalse(persistence["spans_15m_directionally"])
        self.assertFalse(persistence["spans_1h_directionally"])

    def test_directional_activity_can_span_15m_without_spanning_1h(self):
        signal = build_smart_money_signal_snapshot(
            [
                event(WALLET_A, "recent", 950, "BUY"),
                event(WALLET_B, "older", 500, "BUY"),
            ],
            as_of=1000,
        )["signals"][0]
        persistence = signal["persistence"]

        self.assertTrue(persistence["spans_15m_directionally"])
        self.assertFalse(persistence["spans_1h_directionally"])

    def test_directional_activity_can_span_all_three_time_bands(self):
        signal = build_smart_money_signal_snapshot(
            [
                event(WALLET_A, "recent", 950, "BUY"),
                event(WALLET_B, "mid", 500, "BUY"),
                event(WALLET_A, "old", -500, "BUY"),
            ],
            as_of=1000,
        )["signals"][0]
        persistence = signal["persistence"]

        self.assertTrue(persistence["spans_15m_directionally"])
        self.assertTrue(persistence["spans_1h_directionally"])
        self.assertEqual(
            persistence["directional_time_bands_matching_current"],
            ["0_5m", "5_15m", "15_60m"],
        )

    def test_partial_usd_coverage_is_explicit(self):
        signal = build_smart_money_signal_snapshot(
            [
                event(WALLET_A, "priced", 990, "BUY", usd_notional="10"),
                event(WALLET_B, "unpriced", 995, "BUY", usd_notional=None),
            ],
            as_of=1000,
        )["signals"][0]
        usd = signal["validated_usd_flow"]

        self.assertEqual(usd["coverage"], "PARTIAL")
        self.assertEqual(usd["priced_event_count"], 1)
        self.assertEqual(usd["unpriced_event_count"], 1)
        self.assertEqual(usd["validated_usd_net_notional"], "10")

    def test_unpriced_flow_never_gets_fake_usd_direction(self):
        signal = build_smart_money_signal_snapshot(
            [
                event(WALLET_A, "u", 990, "BUY", usd_notional=None),
            ],
            as_of=1000,
        )["signals"][0]
        usd = signal["validated_usd_flow"]

        self.assertEqual(usd["coverage"], "UNAVAILABLE")
        self.assertEqual(usd["direction"], "UNAVAILABLE")
        self.assertEqual(usd["validated_usd_net_notional"], "0")

    def test_base_flow_and_validated_usd_flow_can_disagree_without_override(self):
        signal = build_smart_money_signal_snapshot(
            [
                event(
                    WALLET_A,
                    "buy",
                    990,
                    "BUY",
                    base_amount=100,
                    usd_notional=1,
                ),
                event(
                    WALLET_B,
                    "sell",
                    995,
                    "SELL",
                    base_amount=50,
                    usd_notional=10,
                ),
            ],
            as_of=1000,
        )["signals"][0]

        self.assertEqual(signal["state"], "ACCUMULATION")
        self.assertEqual(
            signal["validated_usd_flow"]["direction"],
            "NEGATIVE",
        )
        self.assertEqual(
            signal["validated_usd_flow"]["validated_usd_net_notional"],
            "-9",
        )

    def test_overlapping_performance_tier_membership_is_preserved(self):
        signal = build_smart_money_signal_snapshot(
            [
                event(
                    WALLET_A,
                    "a",
                    990,
                    "BUY",
                    segments=["S1", "S2"],
                    primary="S2",
                ),
                event(
                    WALLET_B,
                    "b",
                    995,
                    "SELL",
                    segments=["S1"],
                    primary="S1",
                ),
            ],
            as_of=1000,
        )["signals"][0]
        tiers = signal["qualified_wallet_activity"][
            "segment_membership_wallet_counts"
        ]

        self.assertEqual(tiers["S1"]["buy_wallet_count"], 1)
        self.assertEqual(tiers["S1"]["sell_wallet_count"], 1)
        self.assertEqual(tiers["S2"]["buy_wallet_count"], 1)
        self.assertEqual(tiers["S2"]["sell_wallet_count"], 0)

    def test_future_s4_s5_membership_passes_through_generically(self):
        signal = build_smart_money_signal_snapshot(
            [
                event(
                    WALLET_A,
                    "a",
                    990,
                    "BUY",
                    segments=["S4", "S5"],
                    primary="S5",
                )
            ],
            as_of=1000,
        )["signals"][0]
        tiers = signal["qualified_wallet_activity"][
            "segment_membership_wallet_counts"
        ]

        self.assertEqual(tiers["S4"]["buy_wallet_count"], 1)
        self.assertEqual(tiers["S5"]["buy_wallet_count"], 1)

    def test_repeated_events_from_one_wallet_do_not_duplicate_contributor(self):
        signal = build_smart_money_signal_snapshot(
            [
                event(WALLET_A, "a1", 990, "BUY"),
                event(WALLET_A, "a2", 995, "BUY"),
            ],
            as_of=1000,
        )["signals"][0]

        self.assertEqual(len(signal["contributors"]), 1)
        self.assertEqual(signal["contributors"][0]["event_count"], 2)
        self.assertEqual(
            signal["qualified_wallet_activity"]["buy_wallet_count"],
            1,
        )

    def test_one_wallet_can_have_both_buy_and_sell_sides(self):
        signal = build_smart_money_signal_snapshot(
            [
                event(WALLET_A, "a1", 990, "BUY", base_amount=2),
                event(WALLET_A, "a2", 995, "SELL", base_amount=1),
            ],
            as_of=1000,
        )["signals"][0]

        self.assertEqual(signal["contributors"][0]["sides"], ["BUY", "SELL"])
        self.assertEqual(
            signal["qualified_wallet_activity"]["unique_wallet_count"],
            1,
        )

    def test_meme_evidence_is_counted_by_distinct_contributing_wallet(self):
        evidence = meme_evidence(matches=4, tokens=3)
        signal = build_smart_money_signal_snapshot(
            [
                event(
                    WALLET_A,
                    "a1",
                    990,
                    "BUY",
                    meme_evidence=evidence,
                    meme_label="EVIDENCE_PROFILE_ONLY",
                ),
                event(
                    WALLET_A,
                    "a2",
                    995,
                    "BUY",
                    meme_evidence=evidence,
                    meme_label="EVIDENCE_PROFILE_ONLY",
                ),
                event(
                    WALLET_B,
                    "b1",
                    998,
                    "BUY",
                    meme_evidence=meme_evidence(matches=2, tokens=1),
                    meme_label="EVIDENCE_PROFILE_ONLY",
                ),
            ],
            as_of=1000,
        )["signals"][0]
        meme = signal["meme_hunter_evidence"]

        self.assertEqual(meme["evidence_wallet_count"], 2)
        self.assertEqual(
            meme["label_status_counts"]["EVIDENCE_PROFILE_ONLY"],
            2,
        )
        self.assertEqual(
            meme["historical_matched_explosion_events_sum"],
            6,
        )
        self.assertEqual(
            meme["historical_matched_explosion_distinct_tokens_sum"],
            4,
        )

    def test_meme_profile_is_not_promoted_to_calibrated_label(self):
        signal = build_smart_money_signal_snapshot(
            [
                event(
                    WALLET_A,
                    "a",
                    990,
                    "BUY",
                    meme_evidence=meme_evidence(),
                    meme_label="EVIDENCE_PROFILE_ONLY",
                ),
            ],
            as_of=1000,
        )["signals"][0]

        self.assertEqual(
            signal["meme_hunter_evidence"]["calibration_status"],
            "EVIDENCE_ONLY_STAGE6_V1",
        )
        self.assertNotIn(
            "meme_hunter_wallet_count",
            signal["meme_hunter_evidence"],
        )

    def test_mixed_registry_snapshots_are_exposed_not_hidden(self):
        signal = build_smart_money_signal_snapshot(
            [
                event(
                    WALLET_A,
                    "old",
                    950,
                    "BUY",
                    snapshot_id="snap-old",
                    snapshot_fingerprint="fp-old",
                ),
                event(
                    WALLET_B,
                    "new",
                    995,
                    "BUY",
                    snapshot_id="snap-new",
                    snapshot_fingerprint="fp-new",
                ),
            ],
            as_of=1000,
        )["signals"][0]
        provenance = signal["registry_provenance"]

        self.assertTrue(provenance["mixed_snapshot_ids"])
        self.assertTrue(provenance["mixed_snapshot_fingerprints"])
        self.assertEqual(
            provenance["snapshot_ids"],
            ["snap-new", "snap-old"],
        )

    def test_signal_fingerprint_is_deterministic_across_input_order(self):
        rows = [
            event(WALLET_A, "a", 990, "BUY", base_amount=2),
            event(WALLET_B, "b", 995, "SELL", base_amount=1),
        ]
        one = build_smart_money_signal_snapshot(rows, as_of=1000)
        two = build_smart_money_signal_snapshot(
            list(reversed(rows)),
            as_of=1000,
        )

        self.assertEqual(
            one["signals"][0]["signal_fingerprint"],
            two["signals"][0]["signal_fingerprint"],
        )
        self.assertEqual(
            one["snapshot_fingerprint"],
            two["snapshot_fingerprint"],
        )

    def test_external_snapshot_has_no_strength_score_or_entry_rule(self):
        snapshot = build_smart_money_signal_snapshot(
            [event(WALLET_A, "a", 990, "BUY")],
            as_of=1000,
        )
        signal = snapshot["signals"][0]

        self.assertIsNone(signal["scoring"]["strength_score"])
        self.assertIsNone(snapshot["contract"]["strength_score"])
        self.assertIsNone(snapshot["contract"]["entry_rule"])
        self.assertTrue(snapshot["contract"]["descriptive_only"])

    def test_json_handoff_round_trips(self):
        snapshot = build_smart_money_signal_snapshot(
            [event(WALLET_A, "a", 990, "BUY")],
            as_of=1000,
        )
        raw = serialize_signal_snapshot(snapshot)
        decoded = json.loads(raw)

        self.assertEqual(
            decoded["snapshot_fingerprint"],
            snapshot["snapshot_fingerprint"],
        )
        self.assertEqual(decoded["signals"][0]["base_asset"], TOKEN_A)

    def test_multiple_tokens_generate_independent_sorted_signals(self):
        snapshot = build_smart_money_signal_snapshot(
            [
                event(WALLET_A, "b", 990, "BUY", token=TOKEN_B),
                event(WALLET_A, "a", 995, "BUY", token=TOKEN_A),
            ],
            as_of=1000,
        )

        self.assertEqual(snapshot["signal_count"], 2)
        self.assertEqual(
            [row["base_asset"] for row in snapshot["signals"]],
            [TOKEN_A, TOKEN_B],
        )

    def test_neutral_state_never_claims_directional_persistence(self):
        signal = build_smart_money_signal_snapshot(
            [
                event(WALLET_A, "b", 950, "BUY", base_amount=1),
                event(WALLET_B, "s", 960, "SELL", base_amount=1),
                event(WALLET_A, "b2", 500, "BUY", base_amount=1),
                event(WALLET_B, "s2", 510, "SELL", base_amount=1),
            ],
            as_of=1000,
        )["signals"][0]

        self.assertEqual(signal["state"], "NEUTRAL")
        self.assertFalse(signal["persistence"]["spans_15m_directionally"])
        self.assertFalse(signal["persistence"]["spans_1h_directionally"])


if __name__ == "__main__":
    unittest.main()
