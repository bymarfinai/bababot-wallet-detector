import unittest

from research.wallet_s7_qualified_registry import (
    STAGE7_VERSION,
    build_registry_record,
    build_registry_snapshot,
    upsert_registry_records,
)

WALLET = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
OTHER_WALLET = "22222222222222222222222222222222"


def classification(
    *,
    wallet=WALLET,
    status="QUALIFIED",
    primary="S1",
    segments=None,
    reason=None,
):
    if segments is None:
        segments = ["S1"] if status == "QUALIFIED" else []
    row = {
        "version": "wallet-s5-v1",
        "wallet": wallet,
        "status": status,
        "primary_segment": primary if status == "QUALIFIED" else None,
        "qualifying_segments": segments,
        "basis": {
            "kind": "USD_STABLE_AGGREGATE",
            "quote_asset": "USD_STABLE",
            "closed_trade_count": 60,
            "net_median_roi_pct": "2",
            "net_win_rate_pct": "65",
            "net_total_realized_pnl": "120",
        } if status != "NOT_READY" else None,
        "segments": {
            "S1": {"qualified": status == "QUALIFIED"},
            "S2": {"qualified": False},
            "S3": {"qualified": False},
        },
        "thresholds": {"minimum_closed_trades": 50},
        "risk_note": "drawdown reference only",
    }
    if reason:
        row["reason"] = reason
    return row


def performance(*, wallet=WALLET):
    return {
        "version": "wallet-s4-v1",
        "wallet": wallet,
        "performance_available": True,
        "closed_trade_count": 60,
        "win_rate_pct": "65",
        "median_roi_pct": "2.2",
        "median_holding_seconds": "7200",
        "distinct_base_assets": 12,
        "quote_assets": ["USDC"],
        "usd_comparable": {
            "net_metrics_complete": True,
            "net_median_roi_pct": "2",
            "net_win_rate_pct": "65",
            "net_total_realized_pnl_usd_stable": "120",
        },
        "activity": {
            "active_days": 30,
            "trades_per_active_day": "2",
        },
        "qualification_readiness": {
            "net_classification_ready": True,
        },
    }


def meme(*, wallet=WALLET):
    return {
        "version": "wallet-s6-v1",
        "wallet": wallet,
        "profile_available": True,
        "label_status": "EVIDENCE_PROFILE_ONLY",
        "input_buy_count": 20,
        "evaluated_buy_count": 18,
        "distinct_tokens_bought": 10,
        "buckets": {
            "2x@24h": {
                "eligible_buys": 15,
                "hit_buys": 6,
                "miss_buys": 9,
                "incomplete_buys": 3,
                "hit_rate_buy_pct": "40",
                "eligible_distinct_tokens": 8,
                "hit_distinct_tokens": 4,
                "hit_rate_token_pct": "50",
                "median_hit_lead_seconds": 3600,
            }
        },
    }


def explosion(*, wallet=WALLET):
    return {
        "version": "wallet-s6-v1",
        "wallet": wallet,
        "matched_explosion_events": 4,
        "matched_distinct_tokens": 3,
        "median_first_entry_lead_seconds": 7200,
        "median_last_entry_lead_seconds": 1800,
    }


class Stage7QualifiedRegistryTests(unittest.TestCase):
    def test_qualified_wallet_becomes_active(self):
        row = build_registry_record(
            wallet=WALLET,
            classification=classification(),
            performance=performance(),
        )
        self.assertEqual(row["registry_status"], "ACTIVE")
        self.assertTrue(row["live_monitor_eligible"])
        self.assertEqual(row["eligibility_reason"], "STAGE5_QUALIFIED")
        self.assertEqual(row["primary_segment"], "S1")

    def test_unqualified_wallet_is_not_live_eligible(self):
        row = build_registry_record(
            wallet=WALLET,
            classification=classification(
                status="UNQUALIFIED",
                primary=None,
                segments=[],
            ),
            performance=performance(),
        )
        self.assertEqual(row["registry_status"], "UNQUALIFIED")
        self.assertFalse(row["live_monitor_eligible"])

    def test_not_ready_wallet_preserves_reason(self):
        row = build_registry_record(
            wallet=WALLET,
            classification=classification(
                status="NOT_READY",
                primary=None,
                segments=[],
                reason="NO_COMPARABLE_COMPLETE_NET_BASIS",
            ),
        )
        self.assertEqual(row["registry_status"], "NOT_READY")
        self.assertFalse(row["live_monitor_eligible"])
        self.assertEqual(
            row["eligibility_reason"],
            "NO_COMPARABLE_COMPLETE_NET_BASIS",
        )

    def test_stage6_evidence_never_promotes_unqualified_wallet(self):
        row = build_registry_record(
            wallet=WALLET,
            classification=classification(
                status="UNQUALIFIED",
                primary=None,
                segments=[],
            ),
            performance=performance(),
            meme_profile=meme(),
            explosion_profile=explosion(),
        )
        self.assertEqual(row["registry_status"], "UNQUALIFIED")
        self.assertFalse(row["live_monitor_eligible"])
        self.assertEqual(
            row["meme_hunter_evidence"]["matched_explosion_events"],
            4,
        )

    def test_meme_evidence_is_compacted_for_registry(self):
        row = build_registry_record(
            wallet=WALLET,
            classification=classification(),
            performance=performance(),
            meme_profile=meme(),
            explosion_profile=explosion(),
        )
        evidence = row["meme_hunter_evidence"]
        self.assertEqual(evidence["evaluated_buy_count"], 18)
        self.assertEqual(
            evidence["buckets"]["2x@24h"]["hit_distinct_tokens"],
            4,
        )
        self.assertEqual(
            row["special_labels"]["meme_hunter"],
            "EVIDENCE_PROFILE_ONLY",
        )

    def test_wallet_identity_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            build_registry_record(
                wallet=WALLET,
                classification=classification(),
                performance=performance(wallet=OTHER_WALLET),
            )

    def test_explosion_profile_identity_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            build_registry_record(
                wallet=WALLET,
                classification=classification(),
                explosion_profile=explosion(wallet=OTHER_WALLET),
            )

    def test_invalid_qualified_segment_structure_is_rejected(self):
        with self.assertRaises(ValueError):
            build_registry_record(
                wallet=WALLET,
                classification=classification(
                    status="QUALIFIED",
                    primary="S1",
                    segments=[],
                ),
            )

    def test_unsupported_classification_status_is_rejected(self):
        bad = classification()
        bad["status"] = "MAYBE"
        with self.assertRaises(ValueError):
            build_registry_record(
                wallet=WALLET,
                classification=bad,
            )

    def test_record_fingerprint_is_deterministic(self):
        a = build_registry_record(
            wallet=WALLET,
            classification=classification(),
            performance=performance(),
            meme_profile=meme(),
        )
        b = build_registry_record(
            wallet=WALLET,
            classification=classification(),
            performance=performance(),
            meme_profile=meme(),
        )
        self.assertEqual(
            a["record_fingerprint"],
            b["record_fingerprint"],
        )

    def test_record_fingerprint_changes_when_classification_changes(self):
        active = build_registry_record(
            wallet=WALLET,
            classification=classification(),
            performance=performance(),
        )
        inactive = build_registry_record(
            wallet=WALLET,
            classification=classification(
                status="UNQUALIFIED",
                primary=None,
                segments=[],
            ),
            performance=performance(),
        )
        self.assertNotEqual(
            active["record_fingerprint"],
            inactive["record_fingerprint"],
        )

    def test_snapshot_contains_only_active_wallets_for_live_monitor(self):
        active = build_registry_record(
            wallet=WALLET,
            classification=classification(),
            performance=performance(),
        )
        inactive = build_registry_record(
            wallet=OTHER_WALLET,
            classification=classification(
                wallet=OTHER_WALLET,
                status="UNQUALIFIED",
                primary=None,
                segments=[],
            ),
        )
        snapshot = build_registry_snapshot(
            [inactive, active],
            snapshot_id="snapshot-1",
        )
        self.assertEqual(snapshot["record_count"], 2)
        self.assertEqual(snapshot["active_wallet_count"], 1)
        self.assertEqual(snapshot["active_wallets"], [WALLET])
        self.assertEqual(snapshot["status_counts"]["ACTIVE"], 1)
        self.assertEqual(snapshot["status_counts"]["UNQUALIFIED"], 1)

    def test_snapshot_is_deterministic_regardless_of_input_order(self):
        a = build_registry_record(
            wallet=WALLET,
            classification=classification(),
            performance=performance(),
        )
        b = build_registry_record(
            wallet=OTHER_WALLET,
            classification=classification(
                wallet=OTHER_WALLET,
                status="UNQUALIFIED",
                primary=None,
                segments=[],
            ),
        )
        one = build_registry_snapshot(
            [a, b],
            snapshot_id="snapshot-1",
        )
        two = build_registry_snapshot(
            [b, a],
            snapshot_id="snapshot-1",
        )
        self.assertEqual(
            one["snapshot_fingerprint"],
            two["snapshot_fingerprint"],
        )
        self.assertEqual(one["records"], two["records"])

    def test_snapshot_rejects_duplicate_wallet(self):
        row = build_registry_record(
            wallet=WALLET,
            classification=classification(),
            performance=performance(),
        )
        with self.assertRaises(ValueError):
            build_registry_snapshot(
                [row, dict(row)],
                snapshot_id="snapshot-1",
            )

    def test_upsert_replaces_existing_record_by_wallet(self):
        old = build_registry_record(
            wallet=WALLET,
            classification=classification(),
            performance=performance(),
        )
        new = build_registry_record(
            wallet=WALLET,
            classification=classification(
                status="UNQUALIFIED",
                primary=None,
                segments=[],
            ),
        )
        merged = upsert_registry_records([old], [new])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["registry_status"], "UNQUALIFIED")
        self.assertEqual(
            merged[0]["record_fingerprint"],
            new["record_fingerprint"],
        )

    def test_active_wallet_requires_stage4_performance_provenance(self):
        with self.assertRaises(ValueError):
            build_registry_record(
                wallet=WALLET,
                classification=classification(),
            )

    def test_snapshot_rejects_tampered_record(self):
        row = build_registry_record(
            wallet=WALLET,
            classification=classification(),
            performance=performance(),
        )
        tampered = dict(row)
        tampered["registry_status"] = "UNQUALIFIED"
        with self.assertRaises(ValueError):
            build_registry_snapshot(
                [tampered],
                snapshot_id="snapshot-1",
            )

    def test_source_version_mismatch_is_rejected(self):
        bad = performance()
        bad["version"] = "wallet-s4-v999"
        with self.assertRaises(ValueError):
            build_registry_record(
                wallet=WALLET,
                classification=classification(),
                performance=bad,
            )

    def test_source_versions_are_preserved(self):
        row = build_registry_record(
            wallet=WALLET,
            classification=classification(),
            performance=performance(),
            meme_profile=meme(),
            explosion_profile=explosion(),
        )
        self.assertEqual(row["version"], STAGE7_VERSION)
        self.assertEqual(row["source_versions"]["stage4"], "wallet-s4-v1")
        self.assertEqual(row["source_versions"]["stage5"], "wallet-s5-v1")
        self.assertEqual(
            row["source_versions"]["stage6_meme"],
            "wallet-s6-v1",
        )


if __name__ == "__main__":
    unittest.main()
