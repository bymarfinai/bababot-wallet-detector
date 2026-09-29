import json
import tempfile
import unittest
from pathlib import Path

from research.wallet_s2_transaction_normalizer import USDC_MINT
from research.wallet_s10a0_wallet_universe_discovery import (
    build_candidate_universe,
)
from research.wallet_s10a1_candidate_refinement import (
    build_candidate_refinement,
    verify_candidate_refinement,
    wallet_addresses_from_refinement,
)
from research.wallet_s10a_historical_backfill import _load_wallets
from research.wallet_supabase_adapter import (
    SupabaseRestClient,
    candidate_refinement_rows,
)

WALLET_A = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
WALLET_B = "77777777777777777777777777777777777777777777"
MINT_A = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
MINT_B = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"


def swap_tx(signature, wallet, side="BUY", token=MINT_A):
    if side == "BUY":
        pre_usdc, post_usdc = 1_000_000, 500_000
        pre_token, post_token = 0, 100_000
    else:
        pre_usdc, post_usdc = 500_000, 1_000_000
        pre_token, post_token = 100_000, 0

    return {
        "transaction": {
            "signatures": [signature],
            "message": {
                "accountKeys": [
                    {"pubkey": wallet, "signer": True, "writable": True},
                    {"pubkey": MINT_A, "signer": False, "writable": True},
                    {"pubkey": MINT_B, "signer": False, "writable": True},
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
                        "amount": str(pre_usdc),
                        "decimals": 6,
                    },
                },
                {
                    "accountIndex": 2,
                    "mint": token,
                    "owner": wallet,
                    "uiTokenAmount": {
                        "amount": str(pre_token),
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
                        "amount": str(post_usdc),
                        "decimals": 6,
                    },
                },
                {
                    "accountIndex": 2,
                    "mint": token,
                    "owner": wallet,
                    "uiTokenAmount": {
                        "amount": str(post_token),
                        "decimals": 6,
                    },
                },
            ],
        },
    }


def transfer_tx(signature, wallet):
    return {
        "transaction": {
            "signatures": [signature],
            "message": {
                "accountKeys": [
                    {"pubkey": wallet, "signer": True, "writable": True},
                    {"pubkey": MINT_A, "signer": False, "writable": True},
                ],
            },
        },
        "meta": {
            "err": None,
            "fee": 5000,
            "preTokenBalances": [{
                "accountIndex": 1,
                "mint": MINT_A,
                "owner": wallet,
                "uiTokenAmount": {"amount": "0", "decimals": 6},
            }],
            "postTokenBalances": [{
                "accountIndex": 1,
                "mint": MINT_A,
                "owner": wallet,
                "uiTokenAmount": {"amount": "100000", "decimals": 6},
            }],
        },
    }


def block(slot, block_time, txs):
    return {
        "slot": slot,
        "block": {
            "blockTime": block_time,
            "transactions": txs,
        },
    }


def universe_for(blocks):
    slots = [row["slot"] for row in blocks]
    return build_candidate_universe(
        blocks,
        source_label="rpc",
        source_origin="https://rpc.example/",
        requested_start_slot=min(slots),
        requested_end_slot=max(slots),
    )


class Stage10A1ACandidateRefinementTests(unittest.TestCase):
    def test_buy_is_trader_and_meme_buy_candidate(self):
        blocks = [block(100, 1000, [swap_tx("buy", WALLET_A, "BUY")])]
        refinement = build_candidate_refinement(
            universe_for(blocks),
            blocks,
            source_label="rpc",
            source_origin="https://rpc.example/",
        )
        record = refinement["records"][0]
        self.assertTrue(record["trader_candidate"])
        self.assertTrue(record["meme_buy_candidate"])
        self.assertEqual(record["buy_event_count"], 1)
        self.assertEqual(record["sell_event_count"], 0)
        self.assertEqual(record["candidate_status"], "TRADER_CANDIDATE")
        self.assertTrue(verify_candidate_refinement(refinement))

    def test_sell_is_trader_but_not_meme_buy_candidate(self):
        blocks = [block(100, 1000, [swap_tx("sell", WALLET_A, "SELL")])]
        refinement = build_candidate_refinement(
            universe_for(blocks),
            blocks,
            source_label="rpc",
            source_origin="https://rpc.example/",
        )
        record = refinement["records"][0]
        self.assertTrue(record["trader_candidate"])
        self.assertFalse(record["meme_buy_candidate"])
        self.assertEqual(record["sell_event_count"], 1)

    def test_transfer_is_non_trader_activity(self):
        blocks = [block(100, 1000, [transfer_tx("transfer", WALLET_A)])]
        refinement = build_candidate_refinement(
            universe_for(blocks),
            blocks,
            source_label="rpc",
            source_origin="https://rpc.example/",
        )
        record = refinement["records"][0]
        self.assertFalse(record["trader_candidate"])
        self.assertFalse(record["historical_backfill_eligible"])
        self.assertEqual(record["candidate_status"], "NON_TRADER_ACTIVITY")
        self.assertEqual(
            record["events"][0]["event_type"],
            "TRANSFER_IN",
        )

    def test_mixed_wallets_produce_expected_counts(self):
        blocks = [block(100, 1000, [
            swap_tx("buy", WALLET_A, "BUY"),
            transfer_tx("noise", WALLET_B),
        ])]
        refinement = build_candidate_refinement(
            universe_for(blocks),
            blocks,
            source_label="rpc",
            source_origin="https://rpc.example/",
        )
        self.assertEqual(refinement["activity_candidate_wallet_count"], 2)
        self.assertEqual(refinement["trader_candidate_wallet_count"], 1)
        self.assertEqual(refinement["non_trader_activity_wallet_count"], 1)
        self.assertEqual(refinement["meme_buy_candidate_wallet_count"], 1)
        self.assertEqual(
            wallet_addresses_from_refinement(refinement),
            [WALLET_A],
        )

    def test_missing_discovery_signature_fails_closed(self):
        discovery_blocks = [
            block(100, 1000, [swap_tx("buy", WALLET_A, "BUY")])
        ]
        universe = universe_for(discovery_blocks)
        refetch_blocks = [block(100, 1000, [])]
        with self.assertRaises(RuntimeError):
            build_candidate_refinement(
                universe,
                refetch_blocks,
                source_label="rpc",
                source_origin="https://rpc.example/",
            )

    def test_refinement_is_deterministic(self):
        blocks = [block(100, 1000, [
            swap_tx("buy", WALLET_A, "BUY"),
            swap_tx("sell", WALLET_B, "SELL", token=MINT_B),
        ])]
        universe = universe_for(blocks)
        one = build_candidate_refinement(
            universe,
            blocks,
            source_label="rpc",
            source_origin="https://rpc.example/?secret=1",
        )
        two = build_candidate_refinement(
            universe,
            blocks,
            source_label="rpc",
            source_origin="https://rpc.example/",
        )
        self.assertEqual(
            one["refinement_fingerprint"],
            two["refinement_fingerprint"],
        )

    def test_supabase_mapping_enriches_existing_rows(self):
        blocks = [block(100, 1000, [swap_tx("buy", WALLET_A, "BUY")])]
        universe = universe_for(blocks)
        refinement = build_candidate_refinement(
            universe,
            blocks,
            source_label="rpc",
            source_origin="https://rpc.example/",
        )
        snapshot, candidates, evidence = candidate_refinement_rows(
            universe,
            refinement,
        )
        self.assertEqual(snapshot["trader_candidate_wallet_count"], 1)
        self.assertTrue(candidates[0]["trader_candidate"])
        self.assertTrue(candidates[0]["meme_buy_candidate"])
        self.assertEqual(evidence[0]["event_type"], "SWAP")
        self.assertEqual(evidence[0]["side"], "BUY")

    def test_supabase_persistence_writes_snapshot_candidate_evidence(self):
        blocks = [block(100, 1000, [swap_tx("buy", WALLET_A, "BUY")])]
        universe = universe_for(blocks)
        refinement = build_candidate_refinement(
            universe,
            blocks,
            source_label="rpc",
            source_origin="https://rpc.example/",
        )
        requests = []

        def transport(method, url, headers, body):
            requests.append(url)
            return 201, b""

        client = SupabaseRestClient(
            url="https://project.supabase.co",
            secret_key="secret",
            transport=transport,
        )
        result = client.persist_candidate_refinement(
            universe,
            refinement,
        )
        self.assertEqual(result["wallet_universe_snapshot_rows"], 1)
        self.assertEqual(result["wallet_universe_candidate_rows"], 1)
        self.assertEqual(result["wallet_universe_evidence_rows"], 1)
        self.assertEqual(len(requests), 3)

    def test_backfill_refinement_file_loads_only_traders(self):
        blocks = [block(100, 1000, [
            swap_tx("buy", WALLET_A, "BUY"),
            transfer_tx("noise", WALLET_B),
        ])]
        universe = universe_for(blocks)
        refinement = build_candidate_refinement(
            universe,
            blocks,
            source_label="rpc",
            source_origin="https://rpc.example/",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "refinement.json"
            path.write_text(
                json.dumps({"refinement": refinement}),
                encoding="utf-8",
            )
            wallets = _load_wallets(
                [],
                None,
                None,
                str(path),
            )
        self.assertEqual(wallets, [WALLET_A])


if __name__ == "__main__":
    unittest.main()
