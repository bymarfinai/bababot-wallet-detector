import unittest
from unittest.mock import patch

from research.wallet_s3_position_reconstruction import reconstruct_positions
from research.wallet_s3_streaming_reconstruction import (
    consume_stream_page,
    empty_stream_state,
)
from research.wallet_s10a1b_streaming_backfill import backfill_wallet
from research.wallet_supabase_adapter import SupabaseRestClient

WALLET = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
TOKEN = "A1111111111111111111111111111111111111111111"
SOL = "SOL_NATIVE"
UNIVERSE = "u" * 64


def trade(
    signature,
    block_time,
    side,
    base_amount,
    quote_amount,
    *,
    slot=None,
):
    return {
        "wallet": WALLET,
        "signature": signature,
        "slot": slot or block_time,
        "block_time": block_time,
        "event_type": "SWAP",
        "side": side,
        "base_asset": TOKEN,
        "quote_asset": SOL,
        "base_amount": str(base_amount),
        "quote_amount": str(quote_amount),
        "quote_is_usd": False,
        "network_fee_lamports": 5000,
    }


class FakeClient:
    def __init__(self):
        self.tables = {
            "wallet_history_scan_state": [],
            "wallet_historical_trade_summaries": [],
            "wallet_historical_profiles": [],
        }
        self.touched = []

    def select_rows(self, table, *, query):
        self.touched.append(("select", table))
        rows = list(self.tables.get(table, []))
        for key, value in query.items():
            if key in {"select", "limit", "offset", "order"}:
                continue
            if value.startswith("eq."):
                expected = value[3:]
                rows = [row for row in rows if str(row.get(key)) == expected]
        limit = int(query.get("limit", len(rows) or 1))
        offset = int(query.get("offset", 0))
        return [dict(row) for row in rows[offset:offset + limit]]

    def select_all_rows(self, table, *, query, page_size=1000):
        self.touched.append(("select_all", table))
        rows = list(self.tables.get(table, []))
        for key, value in query.items():
            if key in {"select", "limit", "offset", "order"}:
                continue
            if value.startswith("eq."):
                expected = value[3:]
                rows = [row for row in rows if str(row.get(key)) == expected]
        rows.sort(
            key=lambda row: (
                int(row.get("closed_at") or 0),
                int(row.get("close_slot") or 0),
                str(row.get("episode_id") or ""),
            )
        )
        return [dict(row) for row in rows]

    def upsert_rows(self, table, rows, *, on_conflict):
        self.touched.append(("upsert", table))
        target = self.tables.setdefault(table, [])
        keys = on_conflict.split(",")
        count = 0
        for raw in rows:
            row = dict(raw)
            match = None
            for existing in target:
                if all(existing.get(key) == row.get(key) for key in keys):
                    match = existing
                    break
            if match is None:
                target.append(row)
            else:
                match.update(row)
            count += 1
        return count


class StreamingStage3Tests(unittest.TestCase):
    def test_page_split_matches_stage3_closed_trade(self):
        events = [
            trade("sig1", 100, "BUY", 10, 20),
            trade("sig2", 200, "SELL", 4, 12),
            trade("sig3", 300, "SELL", 6, 18),
        ]
        baseline = reconstruct_positions(events, wallet=WALLET)
        expected = baseline["scorable_closed_episodes"]

        state = empty_stream_state(WALLET)
        first = consume_stream_page(state, events[:2], wallet=WALLET)
        self.assertEqual(first["closed_episodes"], [])
        second = consume_stream_page(
            first["state"],
            events[2:],
            wallet=WALLET,
        )
        actual = second["closed_episodes"]

        self.assertEqual(len(expected), 1)
        self.assertEqual(len(actual), 1)
        fields = [
            "episode_id",
            "wallet",
            "base_asset",
            "quote_asset",
            "status",
            "opened_at",
            "closed_at",
            "realized_cost_quote",
            "realized_proceeds_quote",
            "realized_pnl_quote",
            "realized_roi_pct",
            "buy_count",
            "sell_count",
            "network_fee_lamports",
        ]
        self.assertEqual(
            {key: expected[0][key] for key in fields},
            {key: actual[0][key] for key in fields},
        )
        self.assertEqual(second["state"]["open_positions"], [])


class StreamingBackfillTests(unittest.TestCase):
    def test_backfill_is_compact_and_idempotent(self):
        client = FakeClient()
        raw_pages = [
            {
                "result": {
                    "data": [{"transaction": {"signatures": ["sig1"]}}],
                    "paginationToken": "cursor-2",
                }
            },
            {
                "result": {
                    "data": [{"transaction": {"signatures": ["sig2"]}}],
                    "paginationToken": None,
                }
            },
        ]
        normalized_by_signature = {
            "sig1": trade("sig1", 100, "BUY", 10, 20),
            "sig2": trade("sig2", 200, "SELL", 10, 30),
        }

        def fake_normalize(raw_by_wallet):
            raw_rows = list(raw_by_wallet[WALLET])
            rows = [
                normalized_by_signature[
                    row["transaction"]["signatures"][0]
                ]
                for row in raw_rows
            ]
            return {WALLET: rows}, {
                "wallet_count": 1,
                "normalized_event_count": len(rows),
                "normalization_error_count": 0,
                "normalization_errors": [],
            }

        with patch(
            "research.wallet_s10a1b_streaming_backfill."
            "_fetch_indexed_gtfa_page",
            side_effect=raw_pages,
        ) as fetch, patch(
            "research.wallet_s10a1b_streaming_backfill."
            "normalize_wallet_histories",
            side_effect=fake_normalize,
        ):
            report = backfill_wallet(
                client=client,
                endpoint="https://example.invalid/v2/key",
                source_label="test-indexed",
                universe_fp=UNIVERSE,
                wallet=WALLET,
                as_of=999,
                page_limit=100,
                max_pages=10,
                request_delay_seconds=0,
            )

        self.assertTrue(report["history_complete"])
        self.assertEqual(report["pages_fetched_this_run"], 2)
        self.assertEqual(
            len(client.tables["wallet_historical_trade_summaries"]),
            1,
        )
        self.assertEqual(
            len(client.tables["wallet_historical_profiles"]),
            1,
        )
        state = client.tables["wallet_history_scan_state"][0]
        self.assertTrue(state["scan_exhausted"])
        self.assertTrue(state["history_complete"])
        self.assertEqual(state["transactions_scanned_total"], 2)
        self.assertEqual(state["normalized_events_total"], 2)

        touched_tables = {table for _op, table in client.touched}
        self.assertNotIn("historical_wallet_transactions", touched_tables)
        self.assertNotIn("normalized_wallet_history", touched_tables)
        self.assertEqual(fetch.call_count, 2)
        for call in fetch.call_args_list:
            self.assertEqual(call.kwargs["sort_order"], "asc")

        with patch(
            "research.wallet_s10a1b_streaming_backfill."
            "_fetch_indexed_gtfa_page"
        ) as fetch_again:
            skipped = backfill_wallet(
                client=client,
                endpoint="https://example.invalid/v2/key",
                source_label="test-indexed",
                universe_fp=UNIVERSE,
                wallet=WALLET,
                as_of=999,
                page_limit=100,
                max_pages=10,
                request_delay_seconds=0,
            )
        self.assertTrue(skipped["skipped_complete"])
        fetch_again.assert_not_called()


class SupabaseRetryTests(unittest.TestCase):
    def test_retryable_503_is_retried(self):
        attempts = []

        def transport(method, url, headers, body):
            attempts.append(url)
            if len(attempts) == 1:
                return 503, b"temporary"
            return 200, b"[]"

        client = SupabaseRestClient(
            url="https://example.supabase.co",
            secret_key="server-secret",
            transport=transport,
        )
        with patch("research.wallet_supabase_adapter.time.sleep"):
            rows = client.select_rows(
                "wallet_history_scan_state",
                query={"select": "*"},
            )
        self.assertEqual(rows, [])
        self.assertEqual(len(attempts), 2)


if __name__ == "__main__":
    unittest.main()
