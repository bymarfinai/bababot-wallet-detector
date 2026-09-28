import json
import tempfile
import unittest
from pathlib import Path

from research.wallet_s10a0_wallet_universe_discovery import (
    STAGE10A0_VERSION,
    SolanaJsonRpcBlockSource,
    _safe_rpc_origin,
    build_candidate_universe,
    extract_transaction_candidate_evidence,
    scan_candidate_universe,
    verify_candidate_universe,
    wallet_addresses_from_universe,
)
from research.wallet_s10a_historical_backfill import _load_wallets
from research.wallet_supabase_adapter import (
    SupabaseRestClient,
    candidate_universe_rows,
)

WALLET_A = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
WALLET_B = "77777777777777777777777777777777777777777777"
NON_SIGNER = "88888888888888888888888888888888888888888888"
MINT_A = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
MINT_B = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"


def tx_entry(
    signature,
    wallet,
    *,
    pre_amount=100,
    post_amount=200,
    mint=MINT_A,
    signer=True,
    failed=False,
    account_keys_mode="parsed",
    owner=None,
):
    owner = owner or wallet
    if account_keys_mode == "parsed":
        account_keys = [
            {"pubkey": wallet, "signer": signer, "writable": True},
            {"pubkey": NON_SIGNER, "signer": False, "writable": True},
        ]
        message = {"accountKeys": account_keys}
    else:
        message = {
            "accountKeys": [wallet, NON_SIGNER],
            "header": {"numRequiredSignatures": 1 if signer else 0},
        }

    return {
        "transaction": {
            "signatures": [signature],
            "message": message,
        },
        "meta": {
            "err": {"code": 1} if failed else None,
            "preTokenBalances": [{
                "accountIndex": 1,
                "mint": mint,
                "owner": owner,
                "uiTokenAmount": {
                    "amount": str(pre_amount),
                    "decimals": 6,
                },
            }],
            "postTokenBalances": [{
                "accountIndex": 1,
                "mint": mint,
                "owner": owner,
                "uiTokenAmount": {
                    "amount": str(post_amount),
                    "decimals": 6,
                },
            }],
        },
    }


def block(slot, block_time, transactions):
    return {
        "slot": slot,
        "block": {
            "blockTime": block_time,
            "blockhash": f"block-{slot}",
            "transactions": transactions,
        },
    }


class Stage10A0WalletDiscoveryTests(unittest.TestCase):
    def test_signer_with_changed_token_balance_is_candidate(self):
        rows = extract_transaction_candidate_evidence(
            tx_entry("sig-a", WALLET_A),
            slot=100,
            block_time=1000,
            source_label="rpc",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["wallet"], WALLET_A)
        self.assertEqual(rows[0]["changed_mints"], [MINT_A])
        self.assertEqual(
            rows[0]["discovery_reason"],
            "SIGNER_WITH_TOKEN_BALANCE_CHANGE",
        )

    def test_non_signer_token_owner_is_not_candidate(self):
        rows = extract_transaction_candidate_evidence(
            tx_entry(
                "sig-a",
                WALLET_A,
                owner=NON_SIGNER,
            ),
            slot=100,
            block_time=1000,
            source_label="rpc",
        )
        self.assertEqual(rows, [])

    def test_unchanged_token_balance_is_not_candidate(self):
        rows = extract_transaction_candidate_evidence(
            tx_entry(
                "sig-a",
                WALLET_A,
                pre_amount=100,
                post_amount=100,
            ),
            slot=100,
            block_time=1000,
            source_label="rpc",
        )
        self.assertEqual(rows, [])

    def test_failed_transaction_is_not_candidate(self):
        rows = extract_transaction_candidate_evidence(
            tx_entry("sig-a", WALLET_A, failed=True),
            slot=100,
            block_time=1000,
            source_label="rpc",
        )
        self.assertEqual(rows, [])

    def test_raw_account_keys_header_signer_is_supported(self):
        rows = extract_transaction_candidate_evidence(
            tx_entry(
                "sig-a",
                WALLET_A,
                account_keys_mode="raw",
            ),
            slot=100,
            block_time=1000,
            source_label="rpc",
        )
        self.assertEqual([row["wallet"] for row in rows], [WALLET_A])

    def test_cutoff_excludes_future_blocks(self):
        universe = build_candidate_universe(
            [
                block(100, 1000, [tx_entry("old", WALLET_A)]),
                block(101, 1100, [tx_entry("future", WALLET_B)]),
            ],
            source_label="rpc",
            source_origin="https://rpc.example/",
            requested_start_slot=100,
            requested_end_slot=101,
            cutoff_unix=1050,
        )
        self.assertEqual(
            wallet_addresses_from_universe(universe),
            [WALLET_A],
        )
        self.assertEqual(universe["scan"]["scanned_slots"], [100])

    def test_duplicate_signature_does_not_inflate_activity(self):
        duplicate = tx_entry("same-sig", WALLET_A)
        universe = build_candidate_universe(
            [block(100, 1000, [duplicate, duplicate])],
            source_label="rpc",
            source_origin="https://rpc.example/",
            requested_start_slot=100,
            requested_end_slot=100,
        )
        record = universe["records"][0]
        self.assertEqual(record["activity_count"], 1)
        self.assertEqual(record["evidence_signature_count"], 1)

    def test_universe_is_deterministic_across_block_order(self):
        blocks_a = [
            block(100, 1000, [tx_entry("a", WALLET_A)]),
            block(101, 1010, [
                tx_entry("b", WALLET_B, mint=MINT_B),
            ]),
        ]
        one = build_candidate_universe(
            blocks_a,
            source_label="rpc",
            source_origin="https://rpc.example/?api-key=secret",
            requested_start_slot=100,
            requested_end_slot=101,
        )
        two = build_candidate_universe(
            list(reversed(blocks_a)),
            source_label="rpc",
            source_origin="https://rpc.example/",
            requested_start_slot=100,
            requested_end_slot=101,
        )
        self.assertEqual(
            one["universe_fingerprint"],
            two["universe_fingerprint"],
        )
        self.assertTrue(verify_candidate_universe(one))

    def test_rpc_origin_strips_query_credentials(self):
        self.assertEqual(
            _safe_rpc_origin(
                "https://mainnet.helius-rpc.com/?api-key=SUPERSECRET"
            ),
            "https://mainnet.helius-rpc.com/",
        )

    def test_rpc_source_scans_getblocks_then_blocks(self):
        calls = []

        def transport(method, url, headers, body):
            request = json.loads(body.decode("utf-8"))
            calls.append(request["method"])
            method_name = request["method"]
            if method_name == "getSlot":
                result = 101
            elif method_name == "getBlocks":
                result = [100, 101]
            elif method_name == "getBlock":
                self.assertEqual(
                    request["params"][1]["maxSupportedTransactionVersion"],
                    1,
                )
                slot = request["params"][0]
                result = block(
                    slot,
                    1000 + slot,
                    [tx_entry(f"sig-{slot}", WALLET_A)],
                )["block"]
            else:
                raise AssertionError(method_name)
            return 200, json.dumps({
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": result,
            }).encode("utf-8")

        source = SolanaJsonRpcBlockSource(
            "https://rpc.example/?token=secret",
            transport=transport,
        )
        universe = scan_candidate_universe(
            source,
            lookback_slots=2,
        )
        self.assertEqual(
            calls,
            ["getSlot", "getBlocks", "getBlock", "getBlock"],
        )
        self.assertEqual(universe["candidate_wallet_count"], 1)
        self.assertEqual(
            universe["source"]["origin"],
            "https://rpc.example/",
        )

    def test_rpc_null_block_fails_closed(self):
        def transport(method, url, headers, body):
            request = json.loads(body.decode("utf-8"))
            if request["method"] == "getBlocks":
                result = [100]
            elif request["method"] == "getBlock":
                result = None
            else:
                result = 100
            return 200, json.dumps({
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": result,
            }).encode("utf-8")

        source = SolanaJsonRpcBlockSource(
            "https://rpc.example/",
            transport=transport,
            attempts=1,
        )
        with self.assertRaises(RuntimeError):
            scan_candidate_universe(
                source,
                start_slot=100,
                end_slot=100,
            )

    def test_supabase_mapping_preserves_universe_and_evidence(self):
        universe = build_candidate_universe(
            [block(100, 1000, [tx_entry("sig-a", WALLET_A)])],
            source_label="rpc",
            source_origin="https://rpc.example/",
            requested_start_slot=100,
            requested_end_slot=100,
        )
        snapshot, candidates, evidence = candidate_universe_rows(
            universe
        )
        self.assertEqual(
            snapshot["universe_fingerprint"],
            universe["universe_fingerprint"],
        )
        self.assertEqual(candidates[0]["wallet"], WALLET_A)
        self.assertEqual(evidence[0]["signature"], "sig-a")
        self.assertEqual(evidence[0]["changed_mints"], [MINT_A])

    def test_supabase_persists_parent_before_children(self):
        universe = build_candidate_universe(
            [block(100, 1000, [tx_entry("sig-a", WALLET_A)])],
            source_label="rpc",
            source_origin="https://rpc.example/",
            requested_start_slot=100,
            requested_end_slot=100,
        )
        requests = []

        def transport(method, url, headers, body):
            requests.append(url)
            return 201, b""

        client = SupabaseRestClient(
            url="https://project.supabase.co",
            secret_key="server-secret",
            transport=transport,
        )
        result = client.persist_candidate_universe(universe)
        self.assertEqual(
            result["wallet_universe_snapshot_rows"],
            1,
        )
        self.assertEqual(
            result["wallet_universe_candidate_rows"],
            1,
        )
        self.assertEqual(
            result["wallet_universe_evidence_rows"],
            1,
        )
        self.assertIn(
            "/wallet_universe_snapshots",
            requests[0],
        )
        self.assertIn(
            "/wallet_universe_candidates",
            requests[1],
        )
        self.assertIn(
            "/wallet_universe_evidence",
            requests[2],
        )

    def test_discovery_artifact_hands_off_to_stage10a1(self):
        universe = build_candidate_universe(
            [block(100, 1000, [tx_entry("sig-a", WALLET_A)])],
            source_label="rpc",
            source_origin="https://rpc.example/",
            requested_start_slot=100,
            requested_end_slot=100,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "universe.json"
            path.write_text(
                json.dumps({"universe": universe}),
                encoding="utf-8",
            )
            wallets = _load_wallets([], None, str(path))
        self.assertEqual(wallets, [WALLET_A])

    def test_tampered_record_fingerprint_is_rejected(self):
        universe = build_candidate_universe(
            [block(100, 1000, [tx_entry("sig-a", WALLET_A)])],
            source_label="rpc",
            source_origin="https://rpc.example/",
            requested_start_slot=100,
            requested_end_slot=100,
        )
        universe["records"][0]["activity_count"] = 999
        with self.assertRaises(ValueError):
            verify_candidate_universe(universe)


if __name__ == "__main__":
    unittest.main()
