import tempfile
import unittest
from pathlib import Path

from research.wallet_s10_replay_activation import (
    build_replay_preflight,
    load_replay_bundle,
    run_empirical_replay,
    validate_replay_manifest,
    write_json,
)

TOKEN = "A1111111111111111111111111111111111111111111"


def manifest(**overrides):
    row = {
        "version": "wallet-s10-replay-v1",
        "source_kind": "REAL",
        "dataset_id": "dataset-real-001",
        "signal_source": "stage9-archive",
        "price_source": "venue-ohlc-export",
        "venue": "TEST_REAL_VENUE",
        "fee_bps_per_side": "5",
        "slippage_bps_per_side": "5",
        "max_holding_seconds": 3600,
        "max_entry_delay_seconds": 300,
    }
    row.update(overrides)
    return row


def signal_snapshot(as_of=1000, state="ACCUMULATION"):
    return {
        "version": "wallet-s9-v1",
        "chain": "solana",
        "as_of": as_of,
        "signal_count": 1,
        "signals": [
            {
                "version": "wallet-s9-v1",
                "chain": "solana",
                "base_asset": TOKEN,
                "as_of": as_of,
                "state": state,
                "state_basis_window": "5m",
                "freshness": {
                    "last_activity_time": as_of,
                    "age_seconds": 0,
                    "bucket": "WITHIN_5M",
                },
                "qualified_wallet_activity": {
                    "unique_wallet_count": 3,
                    "buy_wallet_count": 3 if state == "ACCUMULATION" else 0,
                    "sell_wallet_count": 0 if state == "ACCUMULATION" else 3,
                    "wallet_net_count": 3 if state == "ACCUMULATION" else -3,
                    "segment_membership_wallet_counts": {
                        "S1": {
                            "buy_wallet_count": 3 if state == "ACCUMULATION" else 0,
                            "sell_wallet_count": 0 if state == "ACCUMULATION" else 3,
                        }
                    },
                },
                "base_flow": {
                    "net_base_amount": "10" if state == "ACCUMULATION" else "-10",
                    "direction": state,
                },
                "validated_usd_flow": {
                    "coverage": "COMPLETE",
                    "priced_event_count": 3,
                    "unpriced_event_count": 0,
                    "validated_usd_buy_notional": "30",
                    "validated_usd_sell_notional": "0",
                    "validated_usd_net_notional": "30" if state == "ACCUMULATION" else "-30",
                    "direction": "POSITIVE" if state == "ACCUMULATION" else "NEGATIVE",
                },
                "window_metrics": {},
                "persistence": {
                    "directional_agreement_windows": ["5m", "15m", "1h"],
                    "spans_15m_directionally": True,
                    "spans_1h_directionally": False,
                },
                "meme_hunter_evidence": {
                    "evidence_wallet_count": 0,
                    "label_status_counts": {},
                    "historical_matched_explosion_events_sum": 0,
                    "historical_matched_explosion_distinct_tokens_sum": 0,
                    "calibration_status": "EVIDENCE_ONLY_STAGE6_V1",
                },
                "contributors": [
                    {
                        "wallet": "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY",
                        "sides": ["BUY" if state == "ACCUMULATION" else "SELL"],
                        "event_count": 1,
                        "latest_activity_time": as_of,
                        "primary_segments_observed": ["S1"],
                        "qualifying_segments": ["S1"],
                        "meme_label_statuses": [],
                        "meme_evidence_available": False,
                        "matched_explosion_events": 0,
                        "matched_explosion_distinct_tokens": 0,
                        "registry_snapshot_ids": ["snap-1"],
                    }
                ],
                "registry_provenance": {
                    "snapshot_ids": ["snap-1"],
                    "snapshot_fingerprints": ["fp-1"],
                    "mixed_snapshot_ids": False,
                    "mixed_snapshot_fingerprints": False,
                    "policy": "EVENT_TIME_QUALIFICATION_PROVENANCE",
                },
                "scoring": {"strength_score": None},
                "signal_fingerprint": f"sig-{as_of}",
            }
        ],
        "contract": {"type": "SMART_MONEY_SIGNAL_SNAPSHOT"},
        "snapshot_fingerprint": f"snap-{as_of}",
    }


def price_row(ts=1060, o="100", h="102", l="99.5", c="101"):
    return {
        "base_asset": TOKEN,
        "timestamp": ts,
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "source": "venue-ohlc-export",
        "venue": "TEST_REAL_VENUE",
    }


class Stage10ReplayActivationTests(unittest.TestCase):
    def test_manifest_requires_real_source_kind(self):
        with self.assertRaises(ValueError):
            validate_replay_manifest(manifest(source_kind="DEMO"))

    def test_manifest_requires_execution_costs(self):
        bad = manifest()
        del bad["fee_bps_per_side"]
        with self.assertRaises(Exception):
            validate_replay_manifest(bad)

    def test_preflight_accepts_real_signal_with_post_signal_bar(self):
        row = build_replay_preflight(
            [signal_snapshot()],
            [price_row()],
            manifest=manifest(),
        )
        self.assertTrue(row["ready_for_replay"])
        self.assertEqual(row["directional_signal_count"], 1)
        self.assertEqual(row["missing_price_tokens"], [])

    def test_preflight_rejects_missing_price_token(self):
        row = build_replay_preflight(
            [signal_snapshot()],
            [dict(price_row(), base_asset="OTHER")],
            manifest=manifest(),
        )
        self.assertFalse(row["ready_for_replay"])
        self.assertEqual(row["missing_price_tokens"], [TOKEN])

    def test_preflight_rejects_only_pre_signal_bars(self):
        row = build_replay_preflight(
            [signal_snapshot()],
            [price_row(ts=900)],
            manifest=manifest(),
        )
        self.assertFalse(row["ready_for_replay"])
        self.assertEqual(row["no_post_signal_bar_tokens"], [TOKEN])

    def test_price_rows_require_source_provenance(self):
        bad = price_row()
        bad["source"] = ""
        with self.assertRaises(ValueError):
            build_replay_preflight(
                [signal_snapshot()],
                [bad],
                manifest=manifest(),
            )

    def test_duplicate_price_rows_are_rejected(self):
        with self.assertRaises(ValueError):
            build_replay_preflight(
                [signal_snapshot()],
                [price_row(), price_row()],
                manifest=manifest(),
            )

    def test_duplicate_snapshot_timestamp_is_rejected(self):
        with self.assertRaises(ValueError):
            build_replay_preflight(
                [signal_snapshot(), signal_snapshot()],
                [price_row()],
                manifest=manifest(),
            )

    def test_empirical_replay_runs_candidate_rules_without_selecting_winner(self):
        result = run_empirical_replay(
            [signal_snapshot()],
            [
                price_row(),
                price_row(ts=4600, o="101", h="101.2", l="100.8", c="101"),
            ],
            manifest=manifest(),
            rule_ids=["A", "B"],
        )
        self.assertEqual(result["claims"]["data_source_kind"], "REAL")
        self.assertFalse(result["claims"]["production_rule_selected"])
        self.assertFalse(result["claims"]["edge_validated"])
        self.assertEqual(
            result["paper_trading_result"]["rules"]["A"]["summary"]["opened_trade_count"],
            1,
        )

    def test_empirical_replay_blocks_incomplete_preflight(self):
        with self.assertRaises(ValueError):
            run_empirical_replay(
                [signal_snapshot()],
                [price_row(ts=900)],
                manifest=manifest(),
                rule_ids=["A"],
            )

    def test_bundle_loader_reads_manifest_and_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root / "manifest.json", manifest())
            (root / "signals.jsonl").write_text(
                __import__("json").dumps(signal_snapshot()) + "\n",
                encoding="utf-8",
            )
            (root / "prices.jsonl").write_text(
                __import__("json").dumps(price_row()) + "\n",
                encoding="utf-8",
            )
            loaded_manifest, signals, prices = load_replay_bundle(root)
            self.assertEqual(loaded_manifest["dataset_id"], "dataset-real-001")
            self.assertEqual(len(signals), 1)
            self.assertEqual(len(prices), 1)

    def test_preflight_fingerprint_is_deterministic(self):
        one = build_replay_preflight(
            [signal_snapshot()],
            [price_row()],
            manifest=manifest(),
        )
        two = build_replay_preflight(
            [signal_snapshot()],
            [price_row()],
            manifest=manifest(),
        )
        self.assertEqual(
            one["preflight_fingerprint"],
            two["preflight_fingerprint"],
        )


if __name__ == "__main__":
    unittest.main()
