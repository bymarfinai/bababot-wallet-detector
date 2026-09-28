import unittest

from research.wallet_s6_meme_explosion_hunter import (
    build_explosion_match_profile,
    build_meme_hunter_profile,
    evaluate_buy_outcomes,
    match_buys_to_explosion_events,
)

WALLET = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
OTHER_WALLET = "7YWHMfk9JZe0LMVx7uL8b2NBG7oAqZ3M5Gx8E6JxSk3N"
TOKEN_A = "A1111111111111111111111111111111111111111111"
TOKEN_B = "B1111111111111111111111111111111111111111111"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def buy(
    signature,
    token,
    t,
    *,
    wallet=WALLET,
    execution_price="1",
    quote_is_usd=True,
):
    return {
        "wallet": wallet,
        "signature": signature,
        "block_time": t,
        "slot": t,
        "event_type": "SWAP",
        "side": "BUY",
        "base_asset": token,
        "quote_asset": USDC,
        "execution_price_quote": execution_price if quote_is_usd else None,
        "quote_is_usd": quote_is_usd,
    }


def points(*rows):
    return [{"timestamp": t, "price": str(price)} for t, price in rows]


class Stage6MemeExplosionHunterTests(unittest.TestCase):
    def test_forward_outcomes_detect_2x_5x_10x(self):
        buys = [buy("b1", TOKEN_A, 0)]
        prices = {
            TOKEN_A: points(
                (0, 1),
                (3600, 2.1),
                (10 * 3600, 5.2),
                (50 * 3600, 10.5),
                (72 * 3600, 10.5),
            )
        }
        row = evaluate_buy_outcomes(buys, prices)[0]

        self.assertEqual(
            row["horizons"]["6h"]["thresholds"]["2x"]["status"],
            "HIT",
        )
        self.assertEqual(
            row["horizons"]["24h"]["thresholds"]["5x"]["status"],
            "HIT",
        )
        self.assertEqual(
            row["horizons"]["72h"]["thresholds"]["10x"]["status"],
            "HIT",
        )
        self.assertEqual(
            row["horizons"]["6h"]["thresholds"]["2x"]["lead_seconds"],
            3600,
        )

    def test_incomplete_history_is_not_counted_as_miss(self):
        buys = [buy("b1", TOKEN_A, 0)]
        prices = {TOKEN_A: points((0, 1), (3 * 3600, 1.2))}
        row = evaluate_buy_outcomes(buys, prices)[0]

        self.assertEqual(
            row["horizons"]["6h"]["thresholds"]["2x"]["status"],
            "INCOMPLETE",
        )

    def test_full_horizon_without_hit_is_miss(self):
        buys = [buy("b1", TOKEN_A, 0)]
        prices = {TOKEN_A: points((0, 1), (6 * 3600, 1.9))}
        row = evaluate_buy_outcomes(buys, prices)[0]

        self.assertEqual(
            row["horizons"]["6h"]["thresholds"]["2x"]["status"],
            "MISS",
        )

    def test_non_usd_buy_requires_nearby_market_entry_price(self):
        buys = [
            buy(
                "b1",
                TOKEN_A,
                0,
                quote_is_usd=False,
            )
        ]
        prices = {TOKEN_A: points((600, 1), (6 * 3600, 2))}
        row = evaluate_buy_outcomes(buys, prices)[0]

        self.assertEqual(row["status"], "NO_ENTRY_PRICE")

    def test_profile_counts_false_positives_honestly(self):
        buys = [
            buy("hit", TOKEN_A, 0),
            buy("miss", TOKEN_B, 0),
        ]
        prices = {
            TOKEN_A: points((0, 1), (3600, 2.1), (72 * 3600, 2.1)),
            TOKEN_B: points((0, 1), (72 * 3600, 1.5)),
        }
        outcomes = evaluate_buy_outcomes(buys, prices)
        profile = build_meme_hunter_profile(outcomes)
        bucket = profile["buckets"]["2x@6h"]

        self.assertEqual(bucket["eligible_buys"], 2)
        self.assertEqual(bucket["hit_buys"], 1)
        self.assertEqual(bucket["miss_buys"], 1)
        self.assertEqual(bucket["hit_rate_buy_pct"], "50")

    def test_repeated_buys_do_not_inflate_distinct_token_hits(self):
        buys = [
            buy("b1", TOKEN_A, 0),
            buy("b2", TOKEN_A, 60),
        ]
        prices = {
            TOKEN_A: points(
                (0, 1),
                (60, 1),
                (3600, 2.1),
                (72 * 3600, 2.1),
            )
        }
        profile = build_meme_hunter_profile(
            evaluate_buy_outcomes(buys, prices)
        )
        bucket = profile["buckets"]["2x@6h"]

        self.assertEqual(bucket["eligible_buys"], 2)
        self.assertEqual(bucket["hit_buys"], 2)
        self.assertEqual(bucket["eligible_distinct_tokens"], 1)
        self.assertEqual(bucket["hit_distinct_tokens"], 1)

    def test_duplicate_buy_signature_is_deduplicated(self):
        buys = [
            buy("dup", TOKEN_A, 0),
            buy("dup", TOKEN_A, 60),
        ]
        prices = {
            TOKEN_A: points(
                (0, 1),
                (60, 1),
                (3600, 2.1),
                (72 * 3600, 2.1),
            )
        }
        outcomes = evaluate_buy_outcomes(buys, prices)

        self.assertEqual(len(outcomes), 1)

    def test_same_signature_different_wallets_are_not_deduplicated(self):
        buys = [
            buy("same", TOKEN_A, 120, wallet=WALLET),
            buy("same", TOKEN_A, 130, wallet=OTHER_WALLET),
        ]
        events = [{
            "event_id": "e1",
            "token": TOKEN_A,
            "start_time": 100,
            "trigger_time": 200,
            "threshold_multiple": "2x",
            "horizon": "6h",
        }]
        matches = match_buys_to_explosion_events(buys, events)

        self.assertEqual(len(matches), 2)
        self.assertEqual(
            {row["wallet"] for row in matches},
            {WALLET, OTHER_WALLET},
        )

    def test_profile_rejects_multiple_wallets(self):
        outcomes = [
            {
                "wallet": WALLET,
                "token": TOKEN_A,
                "status": "NO_ENTRY_PRICE",
                "horizons": {},
            },
            {
                "wallet": OTHER_WALLET,
                "token": TOKEN_B,
                "status": "NO_ENTRY_PRICE",
                "horizons": {},
            },
        ]
        with self.assertRaises(ValueError):
            build_meme_hunter_profile(outcomes)

    def test_explosion_match_requires_buy_between_start_and_trigger(self):
        buys = [
            buy("before", TOKEN_A, 90),
            buy("inside", TOKEN_A, 150),
            buy("after", TOKEN_A, 210),
        ]
        events = [{
            "event_id": "e1",
            "token": TOKEN_A,
            "start_time": 100,
            "trigger_time": 200,
            "threshold_multiple": "2x",
            "horizon": "24h",
        }]
        matches = match_buys_to_explosion_events(buys, events)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["signatures"], ["inside"])

    def test_multiple_buys_same_event_collapse_to_one_wallet_event(self):
        buys = [
            buy("b1", TOKEN_A, 120),
            buy("b2", TOKEN_A, 170),
        ]
        events = [{
            "event_id": "e1",
            "token": TOKEN_A,
            "start_time": 100,
            "trigger_time": 200,
            "threshold_multiple": "5x",
            "horizon": "24h",
        }]
        match = match_buys_to_explosion_events(buys, events)[0]

        self.assertEqual(match["buy_count_before_trigger"], 2)
        self.assertEqual(match["first_entry_lead_seconds"], 80)
        self.assertEqual(match["last_entry_lead_seconds"], 30)

    def test_same_event_can_match_different_wallets_independently(self):
        buys = [
            buy("b1", TOKEN_A, 120, wallet=WALLET),
            buy("b2", TOKEN_A, 130, wallet=OTHER_WALLET),
        ]
        events = [{
            "event_id": "e1",
            "token": TOKEN_A,
            "start_time": 100,
            "trigger_time": 200,
            "threshold_multiple": "2x",
            "horizon": "6h",
        }]
        matches = match_buys_to_explosion_events(buys, events)

        self.assertEqual(len(matches), 2)
        self.assertEqual(
            {row["wallet"] for row in matches},
            {WALLET, OTHER_WALLET},
        )

    def test_duplicate_explosion_event_id_is_rejected(self):
        buys = [buy("b1", TOKEN_A, 150)]
        event = {
            "event_id": "e1",
            "token": TOKEN_A,
            "start_time": 100,
            "trigger_time": 200,
            "threshold_multiple": "2x",
            "horizon": "6h",
        }
        with self.assertRaises(ValueError):
            match_buys_to_explosion_events(buys, [event, dict(event)])

    def test_invalid_explosion_time_range_is_rejected(self):
        buys = [buy("b1", TOKEN_A, 150)]
        events = [{
            "event_id": "e1",
            "token": TOKEN_A,
            "start_time": 200,
            "trigger_time": 100,
            "threshold_multiple": "2x",
            "horizon": "6h",
        }]
        with self.assertRaises(ValueError):
            match_buys_to_explosion_events(buys, events)

    def test_explosion_profile_measures_repeatability_across_events(self):
        buys = [
            buy("a1", TOKEN_A, 120),
            buy("a2", TOKEN_A, 320),
            buy("b1", TOKEN_B, 520),
        ]
        events = [
            {
                "event_id": "e1",
                "token": TOKEN_A,
                "start_time": 100,
                "trigger_time": 200,
                "threshold_multiple": "2x",
                "horizon": "6h",
            },
            {
                "event_id": "e2",
                "token": TOKEN_A,
                "start_time": 300,
                "trigger_time": 400,
                "threshold_multiple": "5x",
                "horizon": "24h",
            },
            {
                "event_id": "e3",
                "token": TOKEN_B,
                "start_time": 500,
                "trigger_time": 600,
                "threshold_multiple": "10x",
                "horizon": "72h",
            },
        ]
        matches = match_buys_to_explosion_events(buys, events)
        profile = build_explosion_match_profile(matches, wallet=WALLET)

        self.assertEqual(profile["matched_explosion_events"], 3)
        self.assertEqual(profile["matched_distinct_tokens"], 2)
        self.assertEqual(profile["events_by_threshold"]["2x"], 1)
        self.assertEqual(profile["events_by_threshold"]["5x"], 1)
        self.assertEqual(profile["events_by_threshold"]["10x"], 1)
        self.assertEqual(profile["median_first_entry_lead_seconds"], 80)


if __name__ == "__main__":
    unittest.main()
