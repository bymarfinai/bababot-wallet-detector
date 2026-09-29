import json
import unittest

from research.wallet_s2_transaction_normalizer import USDC_MINT
from research.wallet_s10a0_wallet_universe_discovery import (
    build_candidate_universe,
)
from research.wallet_s10a1_candidate_refinement import (
    build_candidate_refinement,
)
from research.wallet_s10a1b_real_historical_backfill import (
    SolanaWalletHistoryRpc,
    build_refinement_subset,
    build_stage10a1b_report,
    collect_solana_rpc_histories,
    refinement_effective_after_unix,
)
from research.wallet_s10a_historical_backfill import (
    build_causal_historical_replay,
)
from research.wallet_supabase_adapter import raw_wallet_transaction_row

WALLET_A = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
TOKEN_A = "A1111111111111111111111111111111111111111111"
SOL = "SOL_NATIVE"


def discovery_swap(signature, block_time=1000):
    return {
        "slot": block_time,
        "blockTime": block_time,
        "transaction": {
            "signatures": [signature],
            "message": {
                "accountKeys": [
                    {"pubkey": WALLET_A, "signer": True, "writable": True},
                    {"pubkey": TOKEN_A, "signer": False, "writable": True},
                ],
            },
        },
        "meta": {
            "err": None,
            "fee": 5000,
            "preTokenBalances": [
                {
                    "accountIndex": 1,
                    "mint": USDC_MINT,
                    "owner": WALLET_A,
                    "uiTokenAmount": {
                        "amount": "1000000",
                        "decimals": 6,
                    },
                },
                {
                    "accountIndex": 2,
                    "mint": TOKEN_A,
                    "owner": WALLET_A,
                    "uiTokenAmount": {
                        "amount": "0",
                        "decimals": 6,
                    },
                },
            ],
            "postTokenBalances": [
                {
                    "accountIndex": 1,
                    "mint": USDC_MINT,
                    "owner": WALLET_A,
                    "uiTokenAmount": {
                        "amount": "500000",
                        "decimals": 6,
                    },
                },
                {
                    "accountIndex": 2,
                    "mint": TOKEN_A,
                    "owner": WALLET_A,
                    "uiTokenAmount": {
                        "amount": "100000",
                        "decimals": 6,
                    },
                },
            ],
        },
    }


def refinement_fixture():
    tx = discovery_swap("discover", 1000)
    block = {
        "slot": 1000,
        "block": {
            "blockTime": 1000,
            "transactions": [tx],
        },
    }
    universe = build_candidate_universe(
        [block],
        source_label="rpc",
        source_origin="https://rpc.example/",
        requested_start_slot=1000,
        requested_end_slot=1000,
    )
    return build_candidate_refinement(
        universe,
        [block],
        source_label="rpc",
        source_origin="https://rpc.example/",
    )


def raw_tx(signature, block_time):
    return {
        "slot": block_time,
        "blockTime": block_time,
        "transaction": {
            "signatures": [signature],
            "message": {"accountKeys": []},
        },
        "meta": {
            "err": None,
            "fee": 0,
            "preBalances": [],
            "postBalances": [],
            "preTokenBalances": [],
            "postTokenBalances": [],
        },
    }


def normalized_swap(signature, block_time, side):
    quote_amount = "1" if side == "BUY" else "1.02"
    return {
        "version": "wallet-s2-v1",
        "chain": "solana",
        "wallet": WALLET_A,
        "signature": signature,
        "slot": block_time,
        "block_time": block_time,
        "network_fee_lamports": 0,
        "fee_payer_is_wallet": True,
        "asset_deltas": [],
        "event_type": "SWAP",
        "side": side,
        "input_asset": SOL if side == "BUY" else TOKEN_A,
        "input_amount": quote_amount if side == "BUY" else "1",
        "output_asset": TOKEN_A if side == "BUY" else SOL,
        "output_amount": "1" if side == "BUY" else quote_amount,
        "base_asset": TOKEN_A,
        "base_amount": "1",
        "quote_asset": SOL,
        "quote_amount": quote_amount,
        "execution_price_quote": quote_amount,
        "quote_is_usd": False,
        "usd_notional": None,
        "pricing_quality": "NET_NATIVE_SOL_EXECUTION",
        "confidence": "MEDIUM",
        "notes": [],
    }


def profitable_round_trips(count, start=100):
    rows = []
    ts = start
    for i in range(count):
        rows.append(normalized_swap(f"buy-{i}", ts, "BUY"))
        ts += 10
        rows.append(normalized_swap(f"sell-{i}", ts, "SELL"))
        ts += 10
    return rows


class Stage10A1BRealBackfillTests(unittest.TestCase):
    def test_refinement_activation_uses_latest_discovery_event(self):
        refinement = refinement_fixture()
        self.assertEqual(
            refinement_effective_after_unix(refinement),
            1000,
        )

    def test_universe_activation_blocks_pre_discovery_smart_money_events(self):
        rows = profitable_round_trips(50, start=100)
        qualified_at = rows[-1]["block_time"]
        self.assertLess(qualified_at, 1200)
        rows.extend([
            normalized_swap("pre-cutoff", 1500, "BUY"),
            normalized_swap("post-cutoff", 2001, "BUY"),
        ])
        replay = build_causal_historical_replay(
            {WALLET_A: rows},
            universe_effective_after_unix=2000,
        )
        self.assertEqual(replay["signal_from_unix"], 2001)
        self.assertEqual(
            [row["signature"] for row in replay["wallet_events"]],
            ["post-cutoff"],
        )
        self.assertEqual(
            replay["methodology"]["universe_activation_policy"],
            "SMART_MONEY_EVENTS_STRICTLY_AFTER_DISCOVERY_UNIVERSE",
        )

    def test_signal_from_must_be_strictly_after_universe_activation(self):
        with self.assertRaises(ValueError):
            build_causal_historical_replay(
                {WALLET_A: profitable_round_trips(1)},
                signal_from_unix=1000,
                universe_effective_after_unix=1000,
            )

    def test_native_rpc_collects_complete_history_and_filters_as_of(self):
        calls = []

        def transport(method, url, headers, body):
            payload = json.loads(body.decode("utf-8"))
            calls.append(payload)
            if isinstance(payload, list):
                response = []
                for item in payload:
                    signature = item["params"][0]
                    block_time = 900 if signature == "old" else 1000
                    response.append({
                        "jsonrpc": "2.0",
                        "id": item["id"],
                        "result": raw_tx(signature, block_time),
                    })
                return 200, json.dumps(response).encode("utf-8")

            rpc_method = payload["method"]
            if rpc_method == "getFirstAvailableBlock":
                result = 0
            elif rpc_method == "getSignaturesForAddress":
                before = payload["params"][1].get("before")
                if before is None:
                    result = [
                        {
                            "signature": "future",
                            "slot": 1100,
                            "blockTime": 1100,
                            "err": None,
                        },
                        {
                            "signature": "old",
                            "slot": 900,
                            "blockTime": 900,
                            "err": None,
                        },
                    ]
                else:
                    result = []
            else:
                raise AssertionError(rpc_method)
            return 200, json.dumps({
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": result,
            }).encode("utf-8")

        source = SolanaWalletHistoryRpc(
            "https://rpc.example/?secret=1",
            transport=transport,
        )
        raw, report = collect_solana_rpc_histories(
            source,
            [WALLET_A],
            as_of_unix=1000,
            signature_page_limit=2,
        )
        self.assertTrue(report["qualification_grade"])
        self.assertTrue(report["provider_archive_from_genesis"])
        self.assertEqual(report["source_origin"], "https://rpc.example/")
        self.assertEqual(
            [tx["transaction"]["signatures"][0] for tx in raw[WALLET_A]],
            ["old"],
        )

    def test_native_rpc_retention_gap_fails_closed_for_qualification(self):
        def transport(method, url, headers, body):
            payload = json.loads(body.decode("utf-8"))
            return 200, json.dumps({
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": 123 if payload["method"] == "getFirstAvailableBlock" else [],
            }).encode("utf-8")

        source = SolanaWalletHistoryRpc(
            "https://rpc.example/",
            transport=transport,
        )
        with self.assertRaises(RuntimeError):
            collect_solana_rpc_histories(
                source,
                [WALLET_A],
                as_of_unix=1000,
            )

    def test_native_rpc_retention_gap_can_only_be_non_qualification_grade(self):
        def transport(method, url, headers, body):
            payload = json.loads(body.decode("utf-8"))
            if isinstance(payload, list):
                return 200, b"[]"
            result = (
                123
                if payload["method"] == "getFirstAvailableBlock"
                else []
            )
            return 200, json.dumps({
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": result,
            }).encode("utf-8")

        source = SolanaWalletHistoryRpc(
            "https://rpc.example/",
            transport=transport,
        )
        raw, report = collect_solana_rpc_histories(
            source,
            [WALLET_A],
            as_of_unix=1000,
            require_archive_from_genesis=False,
        )
        self.assertEqual(raw[WALLET_A], [])
        self.assertFalse(report["qualification_grade"])

    def test_native_rpc_page_cap_fails_closed(self):
        def transport(method, url, headers, body):
            payload = json.loads(body.decode("utf-8"))
            rpc_method = payload["method"]
            result = (
                0
                if rpc_method == "getFirstAvailableBlock"
                else [{
                    "signature": f"sig-{payload['id']}",
                    "slot": 900,
                    "blockTime": 900,
                    "err": None,
                }]
            )
            return 200, json.dumps({
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": result,
            }).encode("utf-8")

        source = SolanaWalletHistoryRpc(
            "https://rpc.example/",
            transport=transport,
        )
        with self.assertRaises(RuntimeError):
            collect_solana_rpc_histories(
                source,
                [WALLET_A],
                as_of_unix=1000,
                signature_page_limit=1,
                max_signature_pages_per_wallet=1,
            )

    def test_null_get_transaction_fails_closed(self):
        def transport(method, url, headers, body):
            payload = json.loads(body.decode("utf-8"))
            if isinstance(payload, list):
                return 200, json.dumps([
                    {
                        "jsonrpc": "2.0",
                        "id": item["id"],
                        "result": None,
                    }
                    for item in payload
                ]).encode("utf-8")
            if payload["method"] == "getFirstAvailableBlock":
                result = 0
            else:
                result = [{
                    "signature": "sig",
                    "slot": 900,
                    "blockTime": 900,
                    "err": None,
                }]
            return 200, json.dumps({
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": result,
            }).encode("utf-8")

        source = SolanaWalletHistoryRpc(
            "https://rpc.example/",
            transport=transport,
        )
        with self.assertRaises(RuntimeError):
            collect_solana_rpc_histories(
                source,
                [WALLET_A],
                as_of_unix=1000,
                signature_page_limit=1000,
            )

    def test_stage10a1b_report_carries_causal_activation(self):
        refinement = refinement_fixture()
        raw = {WALLET_A: [raw_tx("old", 900)]}
        report, normalized, replay = build_stage10a1b_report(
            refinement,
            raw_by_wallet=raw,
            fetch_report={
                "provider": "solana_json_rpc",
                "qualification_grade": True,
                "wallet_count": 1,
            },
            history_as_of_unix=1100,
        )
        self.assertEqual(report["universe_effective_after_unix"], 1000)
        self.assertEqual(replay["signal_from_unix"], 1001)
        self.assertEqual(report["source_kind"], "REAL")
        self.assertIn(WALLET_A, normalized)

    def test_refinement_subset_is_explicit_and_deterministic(self):
        refinement = refinement_fixture()
        subset = build_refinement_subset(
            refinement,
            [WALLET_A],
        )
        self.assertEqual(subset["trader_candidate_wallet_count"], 1)
        self.assertEqual(subset["non_trader_activity_wallet_count"], 0)
        self.assertEqual(
            subset["parent_refinement_fingerprint"],
            refinement["refinement_fingerprint"],
        )
        self.assertEqual(
            subset["refinement_fingerprint"],
            build_refinement_subset(
                refinement,
                [WALLET_A],
            )["refinement_fingerprint"],
        )

    def test_report_rejects_partial_cohort_coverage(self):
        refinement = refinement_fixture()
        with self.assertRaises(ValueError):
            build_stage10a1b_report(
                refinement,
                raw_by_wallet={},
                fetch_report={
                    "provider": "solana_json_rpc",
                    "qualification_grade": True,
                    "wallet_count": 0,
                },
                history_as_of_unix=1100,
            )

    def test_raw_history_source_is_provider_neutral(self):
        tx = raw_tx("sig", 900)
        row = raw_wallet_transaction_row(
            WALLET_A,
            tx,
            source="solana_json_rpc",
        )
        self.assertEqual(row["source"], "solana_json_rpc")
        with self.assertRaises(ValueError):
            raw_wallet_transaction_row(
                WALLET_A,
                tx,
                source="",
            )


if __name__ == "__main__":
    unittest.main()
