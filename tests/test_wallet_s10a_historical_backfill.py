import json
import unittest
from decimal import Decimal

from research.wallet_s10a_historical_backfill import (
    build_causal_historical_replay,
    fetch_complete_wallet_history,
    normalize_wallet_histories,
)
from research.wallet_supabase_adapter import (
    SupabaseRestClient,
    signal_rows,
    signal_snapshot_row,
    wallet_event_row,
)

WALLET_A = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
TOKEN_A = "A1111111111111111111111111111111111111111111"
SOL = "SOL_NATIVE"


def normalized_swap(
    signature,
    block_time,
    side,
    *,
    buy_quote="1",
    sell_quote="1.02",
):
    quote_amount = buy_quote if side == "BUY" else sell_quote
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


def profitable_round_trips(count):
    rows = []
    ts = 1000
    for i in range(count):
        rows.append(normalized_swap(f"buy-{i}", ts, "BUY"))
        ts += 10
        rows.append(normalized_swap(f"sell-{i}", ts, "SELL"))
        ts += 10
    return rows


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


class Stage10AHistoricalBackfillTests(unittest.TestCase):
    def test_wallet_is_not_active_before_50th_closed_trade(self):
        rows = profitable_round_trips(49)
        replay = build_causal_historical_replay(
            {WALLET_A: rows},
            signal_from_unix=0,
        )
        active_transitions = [
            row
            for row in replay["qualification_transitions"]
            if row["to_status"] == "ACTIVE"
        ]
        self.assertEqual(active_transitions, [])
        self.assertEqual(replay["summary"]["stage9_signal_count"], 0)
        self.assertEqual(replay["summary"]["persisted_wallet_event_count"], 0)

    def test_qualifying_trade_is_not_retroactively_a_smart_money_event(self):
        rows = profitable_round_trips(50)
        qualifying_sell_time = rows[-1]["block_time"]
        rows.append(
            normalized_swap(
                "post-qualified-buy",
                qualifying_sell_time + 10,
                "BUY",
            )
        )
        replay = build_causal_historical_replay(
            {WALLET_A: rows},
            signal_from_unix=0,
        )

        transitions = replay["qualification_transitions"]
        qualified = [
            row for row in transitions
            if row["to_status"] == "ACTIVE"
        ]
        self.assertEqual(len(qualified), 1)
        self.assertEqual(
            qualified[0]["effective_strictly_after_unix"],
            qualifying_sell_time,
        )

        event_signatures = [
            row["signature"] for row in replay["wallet_events"]
        ]
        self.assertNotIn("sell-49", event_signatures)
        self.assertEqual(event_signatures, ["post-qualified-buy"])

        self.assertEqual(replay["summary"]["stage9_snapshot_count"], 1)
        signal = replay["signal_snapshots"][0]["signals"][0]
        self.assertEqual(signal["state"], "ACCUMULATION")
        self.assertEqual(
            signal["qualified_wallet_activity"]["buy_wallet_count"],
            1,
        )

    def test_stage6_is_disabled_in_historical_causal_replay(self):
        rows = profitable_round_trips(50)
        rows.append(
            normalized_swap(
                "post-qualified-buy",
                rows[-1]["block_time"] + 10,
                "BUY",
            )
        )
        replay = build_causal_historical_replay(
            {WALLET_A: rows},
            signal_from_unix=0,
        )
        self.assertFalse(
            replay["methodology"]["rule_d_historical_readiness"]
        )
        event = replay["wallet_events"][0]
        self.assertIsNone(event["meme_hunter_evidence"])
        self.assertEqual(
            event["special_labels"]["meme_hunter"],
            "NOT_AVAILABLE_CAUSALLY_STAGE10A",
        )

    def test_signal_range_keeps_one_hour_warmup_events_only_for_context(self):
        rows = profitable_round_trips(50)
        qualified_at = rows[-1]["block_time"]
        pre_range = normalized_swap(
            "context-buy",
            qualified_at + 10,
            "BUY",
        )
        in_range = normalized_swap(
            "range-buy",
            qualified_at + 400,
            "BUY",
        )
        rows.extend([pre_range, in_range])

        replay = build_causal_historical_replay(
            {WALLET_A: rows},
            signal_from_unix=in_range["block_time"],
        )

        persisted = [row["signature"] for row in replay["wallet_events"]]
        self.assertEqual(persisted, ["context-buy", "range-buy"])
        self.assertEqual(replay["summary"]["stage9_snapshot_count"], 1)
        signal = replay["signal_snapshots"][0]["signals"][0]
        self.assertEqual(
            signal["qualified_wallet_activity"]["buy_wallet_count"],
            1,
        )
        self.assertEqual(
            signal["window_metrics"]["15m"]["buy_event_count"],
            2,
        )

    def test_complete_history_paginates_and_deduplicates(self):
        page1 = {
            "result": {
                "data": [raw_tx("b", 200), raw_tx("a", 100)],
                "paginationToken": "next",
            }
        }
        page2 = {
            "result": {
                "data": [raw_tx("a", 100), raw_tx("c", 300)],
                "paginationToken": None,
            }
        }
        calls = []

        def fake_fetch(key, wallet, limit, token):
            calls.append(token)
            return page1 if token is None else page2

        rows, report = fetch_complete_wallet_history(
            "key",
            WALLET_A,
            fetch_page=fake_fetch,
        )
        self.assertEqual(calls, [None, "next"])
        self.assertEqual(
            [_tx["transaction"]["signatures"][0] for _tx in rows],
            ["a", "b", "c"],
        )
        self.assertTrue(report["history_complete"])
        self.assertEqual(report["pages_fetched"], 2)

    def test_history_fails_closed_at_page_cap(self):
        def endless(key, wallet, limit, token):
            return {
                "result": {
                    "data": [raw_tx(str(token or "first"), 100)],
                    "paginationToken": "still-more",
                }
            }

        with self.assertRaises(RuntimeError):
            fetch_complete_wallet_history(
                "key",
                WALLET_A,
                max_pages=1,
                fetch_page=endless,
            )

    def test_normalize_history_reports_missing_signature(self):
        good = raw_tx("ok", 100)
        bad = raw_tx("", 110)
        normalized, report = normalize_wallet_histories(
            {WALLET_A: [good, bad]}
        )
        self.assertEqual(len(normalized[WALLET_A]), 1)
        self.assertEqual(report["normalization_error_count"], 1)

    def test_wallet_event_row_maps_stage8_payload(self):
        event = {
            **normalized_swap("sig", 1000, "BUY"),
            "stage8_version": "wallet-s8-v1",
            "live_event_id": f"{WALLET_A}:sig",
            "idempotency_key": f"{WALLET_A}:sig",
            "registry_snapshot_id": "snap",
            "registry_snapshot_fingerprint": "snap-fp",
            "registry_record_fingerprint": "record-fp",
            "primary_segment": "S1",
            "qualifying_segments": ["S1"],
            "meme_hunter_evidence": None,
            "special_labels": {},
        }
        row = wallet_event_row(event)
        self.assertEqual(row["block_time_unix"], 1000)
        self.assertEqual(row["execution_price"], "1")
        self.assertEqual(row["registry_snapshot_fingerprint"], "snap-fp")

    def test_signal_mapping_keeps_unavailable_usd_as_null(self):
        snapshot = {
            "version": "wallet-s9-v1",
            "chain": "solana",
            "as_of": 1000,
            "signal_count": 1,
            "snapshot_fingerprint": "snapshot-fp",
            "signals": [{
                "version": "wallet-s9-v1",
                "chain": "solana",
                "base_asset": TOKEN_A,
                "as_of": 1000,
                "state": "ACCUMULATION",
                "state_basis_window": "5m",
                "signal_fingerprint": "signal-fp",
                "qualified_wallet_activity": {
                    "unique_wallet_count": 1,
                    "buy_wallet_count": 1,
                    "sell_wallet_count": 0,
                    "wallet_net_count": 1,
                },
                "base_flow": {"net_base_amount": "1"},
                "validated_usd_flow": {
                    "coverage": "UNAVAILABLE",
                    "direction": "UNAVAILABLE",
                    "validated_usd_net_notional": "0",
                },
                "persistence": {},
                "meme_hunter_evidence": {},
            }],
        }
        self.assertEqual(
            signal_snapshot_row(snapshot)["snapshot_fingerprint"],
            "snapshot-fp",
        )
        row = signal_rows(snapshot)[0]
        self.assertIsNone(row["validated_usd_net_notional"])

    def test_supabase_client_uses_server_auth_and_upsert_conflict(self):
        requests = []

        def transport(method, url, headers, body):
            requests.append((method, url, headers, body))
            return 201, b""

        client = SupabaseRestClient(
            url="https://project.supabase.co",
            secret_key="server-secret",
            transport=transport,
        )
        count = client.upsert_rows(
            "wallet_events",
            [{"wallet": WALLET_A, "signature": "sig"}],
            on_conflict="wallet,signature",
        )
        self.assertEqual(count, 1)
        method, url, headers, body = requests[0]
        self.assertEqual(method, "POST")
        self.assertIn(
            "on_conflict=wallet,signature",
            url,
        )
        self.assertEqual(headers["apikey"], "server-secret")
        self.assertEqual(
            headers["Prefer"],
            "resolution=merge-duplicates,return=minimal",
        )
        self.assertEqual(
            json.loads(body.decode("utf-8"))[0]["signature"],
            "sig",
        )

    def test_supabase_client_rejects_non_https_url(self):
        with self.assertRaises(ValueError):
            SupabaseRestClient(
                url="http://project.supabase.co",
                secret_key="x",
            )


if __name__ == "__main__":
    unittest.main()
