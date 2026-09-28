import unittest

from research.wallet_s3_position_reconstruction import reconstruct_positions

WALLET = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
TOKEN_A = "A1111111111111111111111111111111111111111111"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL = "SOL_NATIVE"


def trade(
    signature,
    block_time,
    side,
    *,
    base=TOKEN_A,
    quote=USDC,
    base_amount="1",
    quote_amount="1",
    usd=True,
    fee=5_000,
):
    return {
        "wallet": WALLET,
        "signature": signature,
        "block_time": block_time,
        "slot": block_time,
        "event_type": "SWAP",
        "side": side,
        "base_asset": base,
        "quote_asset": quote,
        "base_amount": str(base_amount),
        "quote_amount": str(quote_amount),
        "quote_is_usd": usd,
        "network_fee_lamports": fee,
    }


def transfer(signature, block_time, event_type, *, asset=TOKEN_A, amount="1"):
    return {
        "wallet": WALLET,
        "signature": signature,
        "block_time": block_time,
        "slot": block_time,
        "event_type": event_type,
        "side": "NONE",
        "asset": asset,
        "amount": str(amount),
        "network_fee_lamports": 5_000,
    }


class Stage3PositionReconstructionTests(unittest.TestCase):
    def test_multiple_buys_and_partial_sells_are_one_episode(self):
        result = reconstruct_positions([
            trade("b1", 1, "BUY", base_amount=10, quote_amount=10),
            trade("b2", 2, "BUY", base_amount=20, quote_amount=24),
            trade("b3", 3, "BUY", base_amount=30, quote_amount=42),
            trade("s1", 4, "SELL", base_amount=15, quote_amount=21),
            trade("s2", 5, "SELL", base_amount=45, quote_amount="67.5"),
        ])
        episode = result["terminal_episodes"][0]

        self.assertEqual(result["episode_count"], 1)
        self.assertEqual(result["scorable_closed_episode_count"], 1)
        self.assertEqual(episode["buy_count"], 3)
        self.assertEqual(episode["sell_count"], 2)
        self.assertEqual(episode["total_buy_qty"], "60")
        self.assertEqual(episode["total_buy_cost_quote"], "76")
        self.assertEqual(episode["realized_pnl_quote"], "12.5")
        self.assertEqual(episode["holding_seconds"], 4)
        self.assertTrue(episode["eligible_for_performance_metrics"])

    def test_partial_sell_keeps_weighted_average_cost(self):
        result = reconstruct_positions([
            trade("b1", 1, "BUY", base_amount=100, quote_amount=100),
            trade("s1", 2, "SELL", base_amount=40, quote_amount=60),
        ])
        position = result["open_positions"][0]

        self.assertEqual(position["open_qty"], "60")
        self.assertEqual(position["open_cost_quote"], "60")
        self.assertEqual(position["open_avg_cost_quote"], "1")
        self.assertEqual(position["realized_pnl_quote"], "20")

    def test_clean_full_close_then_new_buy_starts_new_episode(self):
        result = reconstruct_positions([
            trade("b1", 1, "BUY", base_amount=10, quote_amount=10),
            trade("s1", 2, "SELL", base_amount=10, quote_amount=12),
            trade("b2", 3, "BUY", base_amount=5, quote_amount=10),
            trade("s2", 4, "SELL", base_amount=5, quote_amount=9),
        ])

        self.assertEqual(result["terminal_episode_count"], 2)
        self.assertEqual(
            [row["realized_pnl_quote"] for row in result["terminal_episodes"]],
            ["2", "-1"],
        )
        self.assertTrue(
            all(
                row["eligible_for_performance_metrics"]
                for row in result["terminal_episodes"]
            )
        )

    def test_orphan_sell_is_not_invented_as_trade(self):
        result = reconstruct_positions([
            trade("s1", 1, "SELL", base_amount=10, quote_amount=10),
        ])

        self.assertEqual(result["episode_count"], 0)
        self.assertEqual(result["anomalies"][0]["type"], "ORPHAN_SELL")

    def test_transfer_in_contaminates_episode(self):
        result = reconstruct_positions([
            trade("b1", 1, "BUY", base_amount=10, quote_amount=10),
            transfer("t1", 2, "TRANSFER_IN", amount=5),
            trade("s1", 3, "SELL", base_amount=10, quote_amount=20),
        ])
        episode = result["terminal_episodes"][0]

        self.assertEqual(episode["status"], "CLOSED_CONTAMINATED")
        self.assertFalse(episode["eligible_for_performance_metrics"])
        self.assertIn(
            "TRANSFER_IN_DURING_POSITION",
            episode["contamination_reasons"],
        )

    def test_transfer_out_reduces_tracked_inventory_without_realizing_pnl(self):
        result = reconstruct_positions([
            trade("b1", 1, "BUY", base_amount=10, quote_amount=10),
            transfer("t1", 2, "TRANSFER_OUT", amount=10),
        ])
        episode = result["terminal_episodes"][0]

        self.assertEqual(episode["status"], "TRANSFERRED_OUT")
        self.assertEqual(episode["open_qty"], "0")
        self.assertEqual(episode["realized_pnl_quote"], "0")
        self.assertFalse(episode["eligible_for_performance_metrics"])

    def test_oversell_closes_known_inventory_but_marks_contamination(self):
        result = reconstruct_positions([
            trade("b1", 1, "BUY", base_amount=10, quote_amount=10),
            trade("s1", 2, "SELL", base_amount=15, quote_amount=30),
        ])
        episode = result["terminal_episodes"][0]

        self.assertEqual(episode["status"], "CLOSED_CONTAMINATED")
        self.assertEqual(episode["realized_pnl_quote"], "10")
        self.assertTrue(
            any(row["type"] == "OVERSELL" for row in result["anomalies"])
        )

    def test_mixed_quote_inventory_contaminates_both_positions(self):
        result = reconstruct_positions([
            trade("b1", 1, "BUY", base_amount=10, quote_amount=10),
            trade(
                "b2",
                2,
                "BUY",
                quote=SOL,
                base_amount=10,
                quote_amount=1,
                usd=False,
            ),
        ])

        self.assertEqual(result["open_position_count"], 2)
        self.assertTrue(
            all(
                "MIXED_QUOTE_INVENTORY" in row["contamination_reasons"]
                for row in result["open_positions"]
            )
        )

    def test_input_is_sorted_causally_before_reconstruction(self):
        result = reconstruct_positions([
            trade("s1", 3, "SELL", base_amount=10, quote_amount=20),
            trade("b1", 1, "BUY", base_amount=10, quote_amount=10),
        ])
        episode = result["terminal_episodes"][0]

        self.assertEqual(episode["status"], "CLOSED")
        self.assertEqual(episode["realized_pnl_quote"], "10")

    def test_duplicate_signature_is_deduplicated(self):
        result = reconstruct_positions([
            trade("dup", 1, "BUY", base_amount=10, quote_amount=10),
            trade("dup", 2, "BUY", base_amount=10, quote_amount=10),
        ])

        self.assertEqual(result["open_position_count"], 1)
        self.assertEqual(result["open_positions"][0]["total_buy_qty"], "10")
        self.assertTrue(
            any(
                row["type"] == "DUPLICATE_SIGNATURE"
                for row in result["anomalies"]
            )
        )

    def test_non_trade_event_does_not_create_episode(self):
        result = reconstruct_positions([
            {
                "wallet": WALLET,
                "signature": "other",
                "block_time": 1,
                "slot": 1,
                "event_type": "OTHER",
                "side": "NONE",
            },
            trade("b1", 2, "BUY", base_amount=10, quote_amount=10),
        ])

        self.assertEqual(result["episode_count"], 1)
        self.assertEqual(result["open_position_count"], 1)


if __name__ == "__main__":
    unittest.main()
