import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.wallet_s2_transaction_normalizer import USDC_MINT
from research.wallet_s10a0_wallet_universe_discovery import (
    build_candidate_universe,
)
from research.wallet_s10a1_candidate_refinement import (
    build_candidate_refinement,
)
from research.wallet_s10a1b_real_historical_backfill import (
    SolanaWalletHistoryRpc,
    build_refinement_shard,
    build_refinement_subset,
    build_stage10a1b_evidence_report,
    build_stage10a1b_report,
    _fetch_indexed_gtfa_page,
    collect_indexed_histories_as_of,
    collect_solana_rpc_histories,
    plan_solana_rpc_history_capacity,
    refinement_effective_after_unix,
    write_stage10a1b_evidence_bundle,
)
from research.wallet_s10a_historical_backfill import (
    build_causal_historical_replay,
)
from research.wallet_supabase_adapter import raw_wallet_transaction_row

WALLET_A = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
WALLET_B = "77777777777777777777777777777777777777777777"
TOKEN_A = "A1111111111111111111111111111111111111111111"
SOL = "SOL_NATIVE"


def discovery_swap(
    signature,
    block_time=1000,
    wallet=WALLET_A,
):
    return {
        "slot": block_time,
        "blockTime": block_time,
        "transaction": {
            "signatures": [signature],
            "message": {
                "accountKeys": [
                    {"pubkey": wallet, "signer": True, "writable": True},
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
                    "owner": wallet,
                    "uiTokenAmount": {
                        "amount": "1000000",
                        "decimals": 6,
                    },
                },
                {
                    "accountIndex": 2,
                    "mint": TOKEN_A,
                    "owner": wallet,
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
                    "owner": wallet,
                    "uiTokenAmount": {
                        "amount": "500000",
                        "decimals": 6,
                    },
                },
                {
                    "accountIndex": 2,
                    "mint": TOKEN_A,
                    "owner": wallet,
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


def two_wallet_refinement_fixture():
    tx_a = discovery_swap("discover-a", 1000, WALLET_A)
    tx_b = discovery_swap("discover-b", 1000, WALLET_B)
    block = {
        "slot": 1000,
        "block": {
            "blockTime": 1000,
            "transactions": [tx_a, tx_b],
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

    def test_indexed_gtfa_requests_versioned_transactions(self):
        seen = {}

        def transport(method, url, headers, body):
            payload = json.loads(body.decode("utf-8"))
            seen["payload"] = payload
            return 200, json.dumps({
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {
                    "data": [],
                    "paginationToken": None,
                },
            }).encode("utf-8")

        _fetch_indexed_gtfa_page(
            "https://indexed.example/v2/SECRET",
            WALLET_A,
            100,
            None,
            attempts=1,
            transport=transport,
        )

        options = seen["payload"]["params"][1]
        self.assertEqual(
            options["maxSupportedTransactionVersion"],
            0,
        )

    def test_indexed_gtfa_collects_complete_history_and_redacts_secret(self):
        pages = []

        def fetch_page(_credential, wallet, limit, pagination_token):
            pages.append((wallet, limit, pagination_token))
            if pagination_token is None:
                return {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "data": [
                            raw_tx("future", 1100),
                            raw_tx("old", 900),
                        ],
                        "paginationToken": "next-page",
                    },
                }
            return {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "data": [raw_tx("older", 800)],
                    "paginationToken": None,
                },
            }

        raw, report = collect_indexed_histories_as_of(
            "https://solana-mainnet.g.alchemy.com/v2/SECRET_KEY",
            "alchemy-solana-gtfa",
            [WALLET_A],
            as_of_unix=1000,
            page_limit=100,
            fetch_page=fetch_page,
        )

        self.assertTrue(report["qualification_grade"])
        self.assertEqual(report["provider"], "indexed_gtfa")
        self.assertEqual(report["source_label"], "alchemy-solana-gtfa")
        self.assertEqual(
            report["source_origin"],
            "https://solana-mainnet.g.alchemy.com/",
        )
        self.assertNotIn("SECRET_KEY", json.dumps(report))
        self.assertEqual(
            [tx["transaction"]["signatures"][0] for tx in raw[WALLET_A]],
            ["older", "old"],
        )
        self.assertEqual(len(pages), 2)

    def test_indexed_gtfa_page_cap_fails_closed(self):
        def fetch_page(_credential, wallet, limit, pagination_token):
            return {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "data": [raw_tx("sig", 900)],
                    "paginationToken": "never-exhausts",
                },
            }

        with self.assertRaises(RuntimeError):
            collect_indexed_histories_as_of(
                "https://indexed.example/v2/SECRET",
                "indexed-provider",
                [WALLET_A],
                as_of_unix=1000,
                page_limit=100,
                max_pages_per_wallet=1,
                fetch_page=fetch_page,
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
            elif rpc_method == "getTransaction":
                signature = payload["params"][0]
                result = raw_tx(
                    signature,
                    900 if signature == "old" else 1000,
                )
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

    def test_public_rpc_request_pacing_waits_between_calls(self):
        calls = []

        def transport(method, url, headers, body):
            payload = json.loads(body.decode("utf-8"))
            calls.append(payload["method"])
            return 200, json.dumps({
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": 0,
            }).encode("utf-8")

        source = SolanaWalletHistoryRpc(
            "https://rpc.example/",
            transport=transport,
            attempts=1,
            min_request_interval_seconds=0.5,
        )
        with patch(
            "research.wallet_s10a1b_real_historical_backfill.time.monotonic",
            side_effect=[10.0, 10.0, 10.1, 10.1, 10.6],
        ), patch(
            "research.wallet_s10a1b_real_historical_backfill.time.sleep"
        ) as sleeper:
            self.assertEqual(source.first_available_block(), 0)
            self.assertEqual(source.first_available_block(), 0)

        self.assertEqual(calls, [
            "getFirstAvailableBlock",
            "getFirstAvailableBlock",
        ])
        sleeper.assert_called_once()
        self.assertAlmostEqual(sleeper.call_args.args[0], 0.4)
    def test_scalar_http_429_has_single_retry_loop(self):
        calls = 0

        def transport(method, url, headers, body):
            nonlocal calls
            calls += 1
            payload = json.loads(body.decode("utf-8"))
            if calls < 3:
                return 429, b"rate limited"
            return 200, json.dumps({
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": 0,
            }).encode("utf-8")

        source = SolanaWalletHistoryRpc(
            "https://rpc.example/",
            transport=transport,
            attempts=3,
        )
        with patch(
            "research.wallet_s10a1b_real_historical_backfill.time.sleep"
        ) as sleeper:
            self.assertEqual(source.first_available_block(), 0)

        self.assertEqual(calls, 3)
        self.assertEqual(sleeper.call_count, 2)

    def test_transaction_batch_rate_limit_falls_back_to_scalar_rpc(self):
        batch_calls = 0
        scalar_calls = []

        def transport(method, url, headers, body):
            nonlocal batch_calls
            payload = json.loads(body.decode("utf-8"))
            if isinstance(payload, list):
                batch_calls += 1
                return 200, json.dumps([
                    {
                        "jsonrpc": "2.0",
                        "id": item["id"],
                        "error": {
                            "code": 429,
                            "message": "Too many requests",
                        },
                    }
                    for item in payload
                ]).encode("utf-8")

            self.assertEqual(payload["method"], "getTransaction")
            signature = payload["params"][0]
            scalar_calls.append(signature)
            block_time = 900 + len(scalar_calls)
            return 200, json.dumps({
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": raw_tx(signature, block_time),
            }).encode("utf-8")

        source = SolanaWalletHistoryRpc(
            "https://rpc.example/",
            transport=transport,
            attempts=3,
        )
        rows = source.transactions(
            ["a", "b"],
            batch_size=2,
        )
        self.assertEqual(batch_calls, 1)
        self.assertEqual(scalar_calls, ["a", "b"])
        self.assertEqual(sorted(rows), ["a", "b"])

    def test_capacity_planner_separates_standard_and_high_volume(self):
        calls = {}

        def transport(method, url, headers, body):
            payload = json.loads(body.decode("utf-8"))
            rpc_method = payload["method"]
            if rpc_method == "getFirstAvailableBlock":
                result = 0
            elif rpc_method == "getSignaturesForAddress":
                wallet = payload["params"][0]
                before = payload["params"][1].get("before")
                key = (wallet, before)
                calls[key] = calls.get(key, 0) + 1

                if wallet == WALLET_A:
                    result = (
                        [{
                            "signature": "a-1",
                            "slot": 900,
                            "blockTime": 900,
                            "err": None,
                        }]
                        if before is None
                        else []
                    )
                else:
                    # With page_limit=1 and max_pages=2, WALLET_B
                    # deliberately keeps returning a next cursor.
                    suffix = "1" if before is None else "2"
                    result = [{
                        "signature": f"b-{suffix}",
                        "slot": 900,
                        "blockTime": 900,
                        "err": None,
                    }]
            else:
                raise AssertionError(rpc_method)

            return 200, json.dumps({
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": result,
            }).encode("utf-8")

        source = SolanaWalletHistoryRpc(
            "https://rpc.example/",
            transport=transport,
        )
        plan = plan_solana_rpc_history_capacity(
            source,
            [WALLET_B, WALLET_A],
            as_of_unix=1000,
            signature_page_limit=1,
            probe_max_pages_per_wallet=2,
        )
        self.assertEqual(plan["standard_wallets"], [WALLET_A])
        self.assertEqual(plan["high_volume_wallets"], [WALLET_B])
        self.assertEqual(plan["standard_wallet_count"], 1)
        self.assertEqual(plan["high_volume_wallet_count"], 1)
        self.assertTrue(plan["provider_archive_from_genesis"])
        self.assertIsNone(plan["policy"]["quality_filter"])
        self.assertFalse(plan["policy"]["high_volume_is_unqualified"])
        self.assertEqual(
            plan["policy"]["high_volume_action"],
            "REQUIRES_HIGH_CAPACITY_OR_INDEXED_HISTORY_PROVIDER",
        )

    def test_capacity_planner_is_deterministic(self):
        def transport(method, url, headers, body):
            payload = json.loads(body.decode("utf-8"))
            if payload["method"] == "getFirstAvailableBlock":
                result = 0
            elif payload["method"] == "getSignaturesForAddress":
                result = []
            else:
                raise AssertionError(payload["method"])
            return 200, json.dumps({
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": result,
            }).encode("utf-8")

        one = plan_solana_rpc_history_capacity(
            SolanaWalletHistoryRpc(
                "https://rpc.example/",
                transport=transport,
            ),
            [WALLET_B, WALLET_A],
            as_of_unix=1000,
            signature_page_limit=10,
            probe_max_pages_per_wallet=2,
        )
        two = plan_solana_rpc_history_capacity(
            SolanaWalletHistoryRpc(
                "https://rpc.example/",
                transport=transport,
            ),
            [WALLET_A, WALLET_B],
            as_of_unix=1000,
            signature_page_limit=10,
            probe_max_pages_per_wallet=2,
        )
        self.assertEqual(
            one["plan_fingerprint"],
            two["plan_fingerprint"],
        )
        self.assertEqual(
            one["standard_wallets"],
            [WALLET_B, WALLET_A] if WALLET_B < WALLET_A else [WALLET_A, WALLET_B],
        )
        self.assertEqual(one["high_volume_wallets"], [])

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
            elif payload["method"] == "getSignaturesForAddress":
                result = [{
                    "signature": "sig",
                    "slot": 900,
                    "blockTime": 900,
                    "err": None,
                }]
            elif payload["method"] == "getTransaction":
                result = None
            else:
                raise AssertionError(payload["method"])
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

    def test_evidence_report_stops_before_stage3_to5(self):
        refinement = refinement_fixture()
        raw = {WALLET_A: [raw_tx("old", 900)]}
        report, normalized = build_stage10a1b_evidence_report(
            refinement,
            raw_by_wallet=raw,
            fetch_report={
                "provider": "solana_json_rpc",
                "qualification_grade": True,
                "wallet_count": 1,
                "raw_transaction_rows_across_wallets": 1,
            },
            history_as_of_unix=1100,
        )
        self.assertEqual(
            report["mode"],
            "HISTORICAL_EVIDENCE_BACKFILL",
        )
        self.assertFalse(report["stage3_to_stage5_executed"])
        self.assertEqual(
            report["normalization"]["normalized_event_count"],
            1,
        )
        self.assertIn(WALLET_A, normalized)
        self.assertNotIn("causal_replay", report)

    def test_evidence_bundle_writes_auditable_files(self):
        refinement = refinement_fixture()
        raw = {WALLET_A: [raw_tx("old", 900)]}
        report, normalized = build_stage10a1b_evidence_report(
            refinement,
            raw_by_wallet=raw,
            fetch_report={
                "provider": "solana_json_rpc",
                "qualification_grade": True,
                "wallet_count": 1,
                "raw_transaction_rows_across_wallets": 1,
            },
            history_as_of_unix=1100,
        )
        with tempfile.TemporaryDirectory() as tmp:
            manifest = write_stage10a1b_evidence_bundle(
                tmp,
                report=report,
                raw_by_wallet=raw,
                normalized_by_wallet=normalized,
                raw_source="solana_json_rpc",
            )
            root = Path(tmp)
            self.assertTrue((root / "manifest.json").exists())
            self.assertTrue((root / "raw.jsonl").exists())
            self.assertTrue((root / "normalized.jsonl").exists())
            self.assertTrue((root / "report.json").exists())
            self.assertEqual(manifest["wallet_count"], 1)
            self.assertEqual(manifest["raw_transaction_rows"], 1)
            raw_line = json.loads(
                (root / "raw.jsonl").read_text().splitlines()[0]
            )
            self.assertEqual(raw_line["wallet"], WALLET_A)
            self.assertEqual(raw_line["source"], "solana_json_rpc")

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

    def test_refinement_shards_partition_all_trader_wallets(self):
        refinement = two_wallet_refinement_fixture()
        shard0 = build_refinement_shard(
            refinement,
            shard_index=0,
            shard_count=2,
        )
        shard1 = build_refinement_shard(
            refinement,
            shard_index=1,
            shard_count=2,
        )
        wallets0 = {
            row["wallet"] for row in shard0["records"]
        }
        wallets1 = {
            row["wallet"] for row in shard1["records"]
        }
        self.assertEqual(len(wallets0), 1)
        self.assertEqual(len(wallets1), 1)
        self.assertEqual(
            wallets0 | wallets1,
            {WALLET_A, WALLET_B},
        )
        self.assertFalse(wallets0 & wallets1)

    def test_refinement_shard_rejects_invalid_index(self):
        with self.assertRaises(ValueError):
            build_refinement_shard(
                refinement_fixture(),
                shard_index=1,
                shard_count=1,
            )

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
