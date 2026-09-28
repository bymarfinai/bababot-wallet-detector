import unittest

from research.wallet_s7_qualified_registry import (
    build_registry_record,
    build_registry_snapshot,
)
from research.wallet_s8_5_dashboard_contract import build_dashboard_payload
from research.wallet_s8_live_monitor import LiveWalletMonitor

WALLET = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
TOKEN = "A1111111111111111111111111111111111111111111"


def performance():
    return {
        "version": "wallet-s4-v1",
        "wallet": WALLET,
        "performance_available": True,
        "closed_trade_count": 60,
        "quote_assets": [USDC],
        "usd_comparable": {
            "net_metrics_complete": True,
            "net_median_roi_pct": "2",
            "net_win_rate_pct": "65",
            "net_total_realized_pnl_usd_stable": "100",
        },
        "activity": {},
        "qualification_readiness": {"net_classification_ready": True},
    }


def classification():
    return {
        "version": "wallet-s5-v1",
        "wallet": WALLET,
        "status": "QUALIFIED",
        "primary_segment": "S1",
        "qualifying_segments": ["S1"],
        "basis": {},
        "segments": {"S1": {"qualified": True}},
        "thresholds": {},
        "risk_note": "reference only",
    }


def token_balance(mint, amount):
    return {
        "owner": WALLET,
        "mint": mint,
        "uiTokenAmount": {"amount": str(amount), "decimals": 6},
    }


def buy_tx(signature, block_time, token=TOKEN):
    return {
        "slot": block_time,
        "blockTime": block_time,
        "transaction": {
            "signatures": [signature],
            "message": {
                "accountKeys": [
                    WALLET,
                    "11111111111111111111111111111111",
                ]
            },
        },
        "meta": {
            "err": None,
            "fee": 5000,
            "preBalances": [2_000_000_000, 0],
            "postBalances": [1_999_995_000, 0],
            "preTokenBalances": [
                token_balance(USDC, 10_000_000),
                token_balance(token, 0),
            ],
            "postTokenBalances": [
                token_balance(USDC, 0),
                token_balance(token, 100_000_000),
            ],
        },
    }


class Stage85DashboardContractTests(unittest.TestCase):
    def setUp(self):
        record = build_registry_record(
            wallet=WALLET,
            performance=performance(),
            classification=classification(),
        )
        self.snapshot = build_registry_snapshot(
            [record],
            snapshot_id="ui-snapshot",
        )
        self.monitor = LiveWalletMonitor(self.snapshot)
        self.monitor.ingest_rpc_transaction(buy_tx("one", 1000))
        self.monitor.ingest_rpc_transaction(buy_tx("two", 1100))

    def build(self, **kwargs):
        return build_dashboard_payload(
            registry_snapshot=self.snapshot,
            monitor_status=self.monitor.status(),
            aggregation=self.monitor.aggregate(as_of=1200),
            events=self.monitor.events,
            generated_at=1200,
            **kwargs,
        )

    def test_live_contract_carries_registry_and_monitor_health(self):
        row = self.build()
        self.assertEqual(row["mode"], "LIVE")
        self.assertEqual(row["registry"]["snapshotId"], "ui-snapshot")
        self.assertEqual(row["registry"]["activeWalletCount"], 1)
        self.assertEqual(row["monitor"]["storedTradeEventCount"], 2)

    def test_required_rolling_windows_are_exported(self):
        row = self.build()
        self.assertEqual(set(row["windows"]), {"5m", "15m", "1h"})
        self.assertEqual(row["windows"]["5m"]["tradeEventCount"], 2)

    def test_symbol_resolver_maps_mint_without_changing_identity(self):
        row = self.build(symbol_resolver={TOKEN: "TEST"})
        symbol = row["windows"]["5m"]["symbols"][0]
        self.assertEqual(symbol["symbol"], "TEST")
        self.assertEqual(symbol["baseAsset"], TOKEN)

    def test_unknown_symbol_falls_back_to_mint_prefix(self):
        row = self.build()
        self.assertEqual(
            row["windows"]["5m"]["symbols"][0]["symbol"],
            TOKEN[:6],
        )

    def test_recent_events_are_newest_first_and_keep_unpriced_nullable(self):
        row = self.build(symbol_resolver={TOKEN: "TEST"})
        self.assertEqual(
            [event["id"] for event in row["recentEvents"]],
            [f"{WALLET}:two", f"{WALLET}:one"],
        )
        self.assertEqual(row["recentEvents"][0]["usdNotional"], "10")

    def test_recent_limit_is_respected(self):
        row = self.build(recent_limit=1)
        self.assertEqual(len(row["recentEvents"]), 1)

    def test_registry_provenance_mismatch_is_rejected(self):
        bad_status = dict(self.monitor.status())
        bad_status["registry_snapshot_id"] = "other"
        with self.assertRaises(ValueError):
            build_dashboard_payload(
                registry_snapshot=self.snapshot,
                monitor_status=bad_status,
                aggregation=self.monitor.aggregate(as_of=1200),
                events=self.monitor.events,
            )

    def test_missing_required_window_is_rejected(self):
        aggregation = self.monitor.aggregate(as_of=1200)
        del aggregation["windows"]["15m"]
        with self.assertRaises(ValueError):
            build_dashboard_payload(
                registry_snapshot=self.snapshot,
                monitor_status=self.monitor.status(),
                aggregation=aggregation,
                events=self.monitor.events,
            )

    def test_invalid_runtime_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            self.build(mode="MAYBE")


if __name__ == "__main__":
    unittest.main()
