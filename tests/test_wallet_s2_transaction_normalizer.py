import unittest

from research.wallet_s2_transaction_normalizer import (
    NATIVE_SOL,
    USDC_MINT,
    WSOL_MINT,
    normalize_transaction,
)

WALLET = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
TOKEN_A = "A1111111111111111111111111111111111111111111"
TOKEN_B = "B1111111111111111111111111111111111111111111"


def token_balance(mint, amount, decimals=6):
    return {
        "owner": WALLET,
        "mint": mint,
        "uiTokenAmount": {"amount": str(amount), "decimals": decimals},
    }


def tx(pre_tokens=None, post_tokens=None, pre_sol=2_000_000_000, post_sol=1_999_995_000,
       fee=5_000, err=None):
    return {
        "slot": 123,
        "blockTime": 1700000000,
        "transaction": {
            "signatures": ["sig-1"],
            "message": {"accountKeys": [WALLET, "11111111111111111111111111111111"]},
        },
        "meta": {
            "err": err,
            "fee": fee,
            "preBalances": [pre_sol, 0],
            "postBalances": [post_sol, 0],
            "preTokenBalances": pre_tokens or [],
            "postTokenBalances": post_tokens or [],
        },
    }


class Stage2NormalizerTests(unittest.TestCase):
    def test_usdc_buy_becomes_buy_with_direct_usd_price(self):
        raw = tx(
            [token_balance(USDC_MINT, 10_000_000), token_balance(TOKEN_A, 0)],
            [token_balance(USDC_MINT, 0), token_balance(TOKEN_A, 100_000_000)],
        )
        row = normalize_transaction(raw, WALLET)
        self.assertEqual(row["event_type"], "SWAP")
        self.assertEqual(row["side"], "BUY")
        self.assertEqual(row["base_asset"], TOKEN_A)
        self.assertEqual(row["quote_asset"], USDC_MINT)
        self.assertEqual(row["execution_price_quote"], "0.1")
        self.assertEqual(row["usd_notional"], "10")
        self.assertEqual(row["pricing_quality"], "DIRECT_USD_EXECUTION")

    def test_token_sell_to_usdc_becomes_sell(self):
        raw = tx(
            [token_balance(TOKEN_A, 50_000_000), token_balance(USDC_MINT, 0)],
            [token_balance(TOKEN_A, 0), token_balance(USDC_MINT, 10_000_000)],
        )
        row = normalize_transaction(raw, WALLET)
        self.assertEqual(row["event_type"], "SWAP")
        self.assertEqual(row["side"], "SELL")
        self.assertEqual(row["execution_price_quote"], "0.2")
        self.assertEqual(row["usd_notional"], "10")

    def test_native_sol_buy_removes_network_fee(self):
        raw = tx(
            [token_balance(TOKEN_A, 0)],
            [token_balance(TOKEN_A, 100_000_000)],
            pre_sol=2_000_000_000,
            post_sol=999_995_000,
            fee=5_000,
        )
        row = normalize_transaction(raw, WALLET)
        self.assertEqual(row["event_type"], "SWAP")
        self.assertEqual(row["side"], "BUY")
        self.assertEqual(row["quote_asset"], NATIVE_SOL)
        self.assertEqual(row["quote_amount"], "1")
        self.assertEqual(row["execution_price_quote"], "0.01")
        self.assertEqual(row["pricing_quality"], "NET_NATIVE_SOL_EXECUTION")

    def test_inbound_token_is_transfer_in(self):
        raw = tx([], [token_balance(TOKEN_A, 25_000_000)])
        row = normalize_transaction(raw, WALLET)
        self.assertEqual(row["event_type"], "TRANSFER_IN")
        self.assertEqual(row["asset"], TOKEN_A)
        self.assertEqual(row["amount"], "25")

    def test_outbound_token_ignores_pure_network_fee(self):
        raw = tx([token_balance(TOKEN_A, 25_000_000)], [])
        row = normalize_transaction(raw, WALLET)
        self.assertEqual(row["event_type"], "TRANSFER_OUT")
        self.assertEqual(len(row["asset_deltas"]), 1)
        self.assertEqual(row["asset"], TOKEN_A)

    def test_sol_to_wsol_is_wrap_not_trade(self):
        raw = tx(
            [token_balance(WSOL_MINT, 0, 9)],
            [token_balance(WSOL_MINT, 1_000_000_000, 9)],
            pre_sol=2_000_000_000,
            post_sol=999_995_000,
        )
        row = normalize_transaction(raw, WALLET)
        self.assertEqual(row["event_type"], "WRAP")
        self.assertEqual(row["side"], "NONE")

    def test_unquoted_token_to_token_preserves_swap_without_fake_buy_sell(self):
        raw = tx(
            [token_balance(TOKEN_A, 10_000_000), token_balance(TOKEN_B, 0)],
            [token_balance(TOKEN_A, 0), token_balance(TOKEN_B, 20_000_000)],
        )
        row = normalize_transaction(raw, WALLET)
        self.assertEqual(row["event_type"], "SWAP")
        self.assertEqual(row["side"], "SWAP")
        self.assertEqual(row["input_asset"], TOKEN_A)
        self.assertEqual(row["output_asset"], TOKEN_B)

    def test_multi_leg_transaction_is_ambiguous(self):
        raw = tx(
            [
                token_balance(USDC_MINT, 10_000_000),
                token_balance(TOKEN_A, 0),
                token_balance(TOKEN_B, 0),
            ],
            [
                token_balance(USDC_MINT, 0),
                token_balance(TOKEN_A, 50_000_000),
                token_balance(TOKEN_B, 1_000_000),
            ],
        )
        row = normalize_transaction(raw, WALLET)
        self.assertEqual(row["event_type"], "AMBIGUOUS")
        self.assertEqual(row["confidence"], "LOW")

    def test_failed_transaction_is_not_reconstructed(self):
        raw = tx(err={"InstructionError": [0, "Custom"]})
        row = normalize_transaction(raw, WALLET)
        self.assertEqual(row["event_type"], "FAILED")
        self.assertEqual(row["asset_deltas"], [])


if __name__ == "__main__":
    unittest.main()
