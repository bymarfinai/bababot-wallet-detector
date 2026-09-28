import unittest

from research.wallet_s1_data_foundation import (
    build_helius_gtfa_payload,
    extract_wallet_native_delta,
    extract_wallet_token_deltas,
    stage1_sufficiency_report,
)

WALLET = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
TOKEN = "So11111111111111111111111111111111111111112"

TX = {
    "slot": 123,
    "blockTime": 1700000000,
    "transaction": {
        "signatures": ["sig-1"],
        "message": {
            "accountKeys": [WALLET, "11111111111111111111111111111111"]
        },
    },
    "meta": {
        "preBalances": [2_000_000_000, 0],
        "postBalances": [1_999_995_000, 0],
        "preTokenBalances": [
            {
                "owner": WALLET,
                "mint": USDC,
                "uiTokenAmount": {"amount": "10000000", "decimals": 6},
            },
            {
                "owner": WALLET,
                "mint": TOKEN,
                "uiTokenAmount": {"amount": "0", "decimals": 6},
            },
        ],
        "postTokenBalances": [
            {
                "owner": WALLET,
                "mint": USDC,
                "uiTokenAmount": {"amount": "0", "decimals": 6},
            },
            {
                "owner": WALLET,
                "mint": TOKEN,
                "uiTokenAmount": {"amount": "100000000", "decimals": 6},
            },
        ],
    },
}


class Stage1DataFoundationTests(unittest.TestCase):
    def test_gtfa_payload_is_wallet_centric_and_all_token_balance_changes(self):
        payload = build_helius_gtfa_payload(WALLET)
        options = payload["params"][1]
        self.assertEqual(payload["method"], "getTransactionsForAddress")
        self.assertEqual(options["transactionDetails"], "full")
        self.assertEqual(options["sortOrder"], "asc")
        self.assertEqual(options["filters"]["tokenAccounts"], "balanceChanged")
        self.assertNotIn("token", options)
        self.assertNotIn("symbol", options)

    def test_extract_token_deltas(self):
        rows = {row.mint: row for row in extract_wallet_token_deltas(TX, WALLET)}
        self.assertEqual(rows[USDC].raw_delta, -10_000_000)
        self.assertEqual(str(rows[USDC].ui_delta), "-10")
        self.assertEqual(rows[TOKEN].raw_delta, 100_000_000)
        self.assertEqual(str(rows[TOKEN].ui_delta), "100")

    def test_extract_native_delta(self):
        native = extract_wallet_native_delta(TX, WALLET)
        self.assertIsNotNone(native)
        self.assertEqual(native.lamport_delta, -5_000)
        self.assertEqual(str(native.sol_delta), "-0.000005")

    def test_sufficiency_report(self):
        report = stage1_sufficiency_report(TX, WALLET)
        self.assertTrue(report["sufficient_for_stage2"])
        self.assertEqual(report["signature"], "sig-1")
        self.assertEqual(report["token_delta_count"], 2)

    def test_token_account_missing_from_post_is_treated_as_zero(self):
        raw = {
            "meta": {
                "preTokenBalances": [{
                    "owner": WALLET,
                    "mint": USDC,
                    "uiTokenAmount": {"amount": "25000000", "decimals": 6},
                }],
                "postTokenBalances": [],
            }
        }
        rows = extract_wallet_token_deltas(raw, WALLET)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].raw_delta, -25_000_000)


if __name__ == "__main__":
    unittest.main()
