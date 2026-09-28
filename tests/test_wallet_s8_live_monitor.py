import unittest

from research.wallet_s7_qualified_registry import (
    build_registry_record,
    build_registry_snapshot,
)
from research.wallet_s8_live_monitor import (
    LiveWalletMonitor,
    aggregate_live_events,
    build_live_subscription_plan,
    live_event_to_persistence_row,
    transaction_touches_wallet,
)

WALLET_A = "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY"
WALLET_B = "22222222222222222222222222222222"
WALLET_C = "33333333333333333333333333333333"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
TOKEN_A = "A1111111111111111111111111111111111111111111"
TOKEN_B = "B1111111111111111111111111111111111111111111"


def performance(wallet):
    return {
        "version": "wallet-s4-v1",
        "wallet": wallet,
        "performance_available": True,
        "closed_trade_count": 60,
        "win_rate_pct": "65",
        "median_roi_pct": "2",
        "median_holding_seconds": "3600",
        "distinct_base_assets": 10,
        "quote_assets": [USDC],
        "usd_comparable": {
            "net_metrics_complete": True,
            "net_median_roi_pct": "2",
            "net_win_rate_pct": "65",
            "net_total_realized_pnl_usd_stable": "100",
        },
        "activity": {
            "active_days": 20,
            "trades_per_active_day": "3",
        },
        "qualification_readiness": {
            "net_classification_ready": True,
        },
    }


def classification(wallet, *, qualified=True, segments=None, primary="S1"):
    if segments is None:
        segments = ["S1"] if qualified else []
    return {
        "version": "wallet-s5-v1",
        "wallet": wallet,
        "status": "QUALIFIED" if qualified else "UNQUALIFIED",
        "primary_segment": primary if qualified else None,
        "qualifying_segments": segments,
        "basis": {
            "kind": "USD_STABLE_AGGREGATE",
            "quote_asset": "USD_STABLE",
            "closed_trade_count": 60,
            "net_median_roi_pct": "2",
            "net_win_rate_pct": "65",
            "net_total_realized_pnl": "100",
        },
        "segments": {
            "S1": {"qualified": "S1" in segments},
            "S2": {"qualified": "S2" in segments},
            "S3": {"qualified": "S3" in segments},
        },
        "thresholds": {"minimum_closed_trades": 50},
        "risk_note": "drawdown reference only",
    }


def meme_profile(wallet):
    return {
        "version": "wallet-s6-v1",
        "wallet": wallet,
        "profile_available": True,
        "label_status": "EVIDENCE_PROFILE_ONLY",
        "input_buy_count": 12,
        "evaluated_buy_count": 10,
        "distinct_tokens_bought": 6,
        "buckets": {},
    }


def explosion_profile(wallet):
    return {
        "version": "wallet-s6-v1",
        "wallet": wallet,
        "matched_explosion_events": 3,
        "matched_distinct_tokens": 2,
        "median_first_entry_lead_seconds": 7200,
        "median_last_entry_lead_seconds": 1800,
    }


def registry_record(
    wallet,
    *,
    qualified=True,
    segments=None,
    primary="S1",
    with_meme=False,
):
    return build_registry_record(
        wallet=wallet,
        performance=performance(wallet),
        classification=classification(
            wallet,
            qualified=qualified,
            segments=segments,
            primary=primary,
        ),
        meme_profile=meme_profile(wallet) if with_meme else None,
        explosion_profile=explosion_profile(wallet) if with_meme else None,
    )


def snapshot(*records, snapshot_id="live-1"):
    return build_registry_snapshot(records, snapshot_id=snapshot_id)


def token_balance(wallet, mint, amount, decimals=6):
    return {
        "owner": wallet,
        "mint": mint,
        "uiTokenAmount": {
            "amount": str(amount),
            "decimals": decimals,
        },
    }


def swap_tx(signature, block_time, changes, *, fee=5000, account_wallets=None):
    """changes = [(wallet, side, token, base_ui, usd_ui), ...]."""
    pre_tokens = []
    post_tokens = []

    for wallet, side, token, base_ui, usd_ui in changes:
        base_raw = int(base_ui * 1_000_000)
        usd_raw = int(usd_ui * 1_000_000)
        if side == "BUY":
            pre_tokens += [
                token_balance(wallet, USDC, usd_raw),
                token_balance(wallet, token, 0),
            ]
            post_tokens += [
                token_balance(wallet, USDC, 0),
                token_balance(wallet, token, base_raw),
            ]
        else:
            pre_tokens += [
                token_balance(wallet, token, base_raw),
                token_balance(wallet, USDC, 0),
            ]
            post_tokens += [
                token_balance(wallet, token, 0),
                token_balance(wallet, USDC, usd_raw),
            ]

    wallets = list(account_wallets if account_wallets is not None else [x[0] for x in changes])
    account_keys = wallets + ["11111111111111111111111111111111"]
    pre_balances = [2_000_000_000 for _ in wallets] + [0]
    post_balances = list(pre_balances)
    if wallets:
        post_balances[0] -= fee

    return {
        "slot": block_time,
        "blockTime": block_time,
        "transaction": {
            "signatures": [signature],
            "message": {"accountKeys": account_keys},
        },
        "meta": {
            "err": None,
            "fee": fee,
            "preBalances": pre_balances,
            "postBalances": post_balances,
            "preTokenBalances": pre_tokens,
            "postTokenBalances": post_tokens,
        },
    }


def sol_buy_tx(signature, block_time, wallet, *, token=TOKEN_A, token_ui=100, sol_ui=1):
    token_raw = int(token_ui * 1_000_000)
    fee = 5000
    pre_sol = 3_000_000_000
    economic_lamports = int(sol_ui * 1_000_000_000)
    post_sol = pre_sol - economic_lamports - fee
    return {
        "slot": block_time,
        "blockTime": block_time,
        "transaction": {
            "signatures": [signature],
            "message": {
                "accountKeys": [
                    wallet,
                    "11111111111111111111111111111111",
                ]
            },
        },
        "meta": {
            "err": None,
            "fee": fee,
            "preBalances": [pre_sol, 0],
            "postBalances": [post_sol, 0],
            "preTokenBalances": [
                token_balance(wallet, token, 0),
            ],
            "postTokenBalances": [
                token_balance(wallet, token, token_raw),
            ],
        },
    }


class Stage8LiveMonitorTests(unittest.TestCase):
    def setUp(self):
        self.record_a = registry_record(
            WALLET_A,
            segments=["S1", "S2"],
            primary="S2",
        )
        self.record_b = registry_record(
            WALLET_B,
            segments=["S1"],
            primary="S1",
        )
        self.snapshot = snapshot(self.record_a, self.record_b)
        self.monitor = LiveWalletMonitor(self.snapshot)

    def test_subscription_plan_uses_only_active_wallets_and_chunks(self):
        plan = build_live_subscription_plan(
            self.snapshot,
            max_addresses_per_subscription=1,
        )
        self.assertEqual(plan["address_count"], 2)
        self.assertEqual(plan["batch_count"], 2)
        self.assertEqual(
            [x["address_count"] for x in plan["batches"]],
            [1, 1],
        )
        self.assertTrue(
            plan["delivery_contract"]["auth_header_required"]
        )
        self.assertEqual(
            plan["delivery_contract"]["idempotency_key"],
            "wallet+signature",
        )

    def test_subscription_plan_rejects_tampered_snapshot(self):
        bad = dict(self.snapshot)
        bad["active_wallet_count"] = 99
        with self.assertRaises(ValueError):
            build_live_subscription_plan(bad)

    def test_touch_detection_works_from_account_keys(self):
        tx = swap_tx(
            "sig-a",
            1000,
            [(WALLET_A, "BUY", TOKEN_A, 100, 10)],
        )
        self.assertTrue(transaction_touches_wallet(tx, WALLET_A))
        self.assertFalse(transaction_touches_wallet(tx, WALLET_C))

    def test_touch_detection_works_from_token_owner_metadata(self):
        tx = swap_tx(
            "sig-a",
            1000,
            [(WALLET_A, "BUY", TOKEN_A, 100, 10)],
            account_wallets=[WALLET_B],
        )
        self.assertTrue(transaction_touches_wallet(tx, WALLET_A))

    def test_active_wallet_buy_is_normalized_and_enriched(self):
        tx = swap_tx(
            "sig-a",
            1000,
            [(WALLET_A, "BUY", TOKEN_A, 100, 10)],
        )
        result = self.monitor.ingest_rpc_transaction(tx, received_at=1002)
        row = result["accepted_events"][0]

        self.assertEqual(result["status"], "ACCEPTED")
        self.assertEqual(row["side"], "BUY")
        self.assertEqual(row["base_asset"], TOKEN_A)
        self.assertEqual(row["usd_notional"], "10")
        self.assertEqual(row["primary_segment"], "S2")
        self.assertEqual(row["qualifying_segments"], ["S1", "S2"])
        self.assertEqual(row["received_at"], 1002)
        self.assertEqual(row["idempotency_key"], f"{WALLET_A}:sig-a")

    def test_live_event_carries_stage6_specialty_evidence(self):
        record = registry_record(
            WALLET_A,
            segments=["S1", "S2"],
            primary="S2",
            with_meme=True,
        )
        monitor = LiveWalletMonitor(snapshot(record, snapshot_id="meme-live"))
        result = monitor.ingest_rpc_transaction(
            swap_tx(
                "meme-evidence",
                1000,
                [(WALLET_A, "BUY", TOKEN_A, 100, 10)],
            )
        )
        row = result["accepted_events"][0]

        self.assertEqual(
            row["special_labels"]["meme_hunter"],
            "EVIDENCE_PROFILE_ONLY",
        )
        self.assertTrue(
            row["meme_hunter_evidence"]["evidence_profile_available"]
        )
        self.assertEqual(
            row["meme_hunter_evidence"]["matched_explosion_events"],
            3,
        )

        persisted = live_event_to_persistence_row(row)
        self.assertEqual(
            persisted["special_labels"]["meme_hunter"],
            "EVIDENCE_PROFILE_ONLY",
        )
        self.assertEqual(
            persisted["meme_hunter_evidence"]["matched_distinct_tokens"],
            2,
        )

    def test_one_transaction_can_emit_events_for_two_active_wallets(self):
        tx = swap_tx(
            "sig-two",
            1000,
            [
                (WALLET_A, "BUY", TOKEN_A, 100, 10),
                (WALLET_B, "BUY", TOKEN_B, 20, 5),
            ],
        )
        result = self.monitor.ingest_rpc_transaction(tx)

        self.assertEqual(result["status"], "ACCEPTED")
        self.assertEqual(len(result["accepted_events"]), 2)
        self.assertEqual(
            {x["wallet"] for x in result["accepted_events"]},
            {WALLET_A, WALLET_B},
        )

    def test_duplicate_delivery_is_idempotent_per_wallet_signature(self):
        tx = swap_tx(
            "sig-dup",
            1000,
            [(WALLET_A, "BUY", TOKEN_A, 100, 10)],
        )
        first = self.monitor.ingest_rpc_transaction(tx)
        second = self.monitor.ingest_rpc_transaction(tx)

        self.assertEqual(first["status"], "ACCEPTED")
        self.assertEqual(second["status"], "DUPLICATE")
        self.assertEqual(second["duplicates"], [WALLET_A])
        self.assertEqual(len(self.monitor.events), 1)

    def test_missing_signature_is_invalid_without_crashing(self):
        tx = swap_tx(
            "sig",
            1000,
            [(WALLET_A, "BUY", TOKEN_A, 100, 10)],
        )
        tx["transaction"]["signatures"] = []
        result = self.monitor.ingest_rpc_transaction(tx)

        self.assertEqual(result["status"], "INVALID")
        self.assertEqual(result["reason"], "MISSING_SIGNATURE")

    def test_transaction_without_active_wallet_is_ignored(self):
        tx = swap_tx(
            "sig-c",
            1000,
            [(WALLET_C, "BUY", TOKEN_A, 100, 10)],
        )
        result = self.monitor.ingest_rpc_transaction(tx)

        self.assertEqual(result["status"], "IGNORED")
        self.assertEqual(len(self.monitor.events), 0)

    def test_normalization_error_does_not_poison_idempotency_key(self):
        tx = swap_tx(
            "sig-bad",
            1000,
            [(WALLET_A, "BUY", TOKEN_A, 100, 10)],
        )
        tx["meta"]["postTokenBalances"][1]["uiTokenAmount"]["decimals"] = 5
        bad = self.monitor.ingest_rpc_transaction(tx)

        self.assertEqual(bad["status"], "ERROR")
        self.assertEqual(len(bad["errors"]), 1)

        fixed = swap_tx(
            "sig-bad",
            1000,
            [(WALLET_A, "BUY", TOKEN_A, 100, 10)],
        )
        good = self.monitor.ingest_rpc_transaction(fixed)
        self.assertEqual(good["status"], "ACCEPTED")

    def test_batch_reports_accept_duplicate_and_error_counts(self):
        good = swap_tx(
            "sig-good",
            1000,
            [(WALLET_A, "BUY", TOKEN_A, 100, 10)],
        )
        duplicate = good
        bad = swap_tx(
            "sig-bad2",
            1001,
            [(WALLET_B, "BUY", TOKEN_B, 20, 5)],
        )
        bad["meta"]["postTokenBalances"][1]["uiTokenAmount"]["decimals"] = 5

        result = self.monitor.ingest_rpc_batch([good, duplicate, bad])

        self.assertEqual(result["delivery_count"], 3)
        self.assertEqual(result["accepted_event_count"], 1)
        self.assertEqual(result["duplicate_wallet_event_count"], 1)
        self.assertEqual(result["normalization_error_count"], 1)

    def test_rolling_window_lower_boundary_is_exclusive(self):
        events = [
            {
                "event_type": "SWAP",
                "side": "BUY",
                "wallet": WALLET_A,
                "base_asset": TOKEN_A,
                "base_amount": "1",
                "quote_asset": USDC,
                "usd_notional": "1",
                "block_time": 700,
                "slot": 700,
                "qualifying_segments": ["S1"],
            },
            {
                "event_type": "SWAP",
                "side": "BUY",
                "wallet": WALLET_A,
                "base_asset": TOKEN_A,
                "base_amount": "1",
                "quote_asset": USDC,
                "usd_notional": "1",
                "block_time": 701,
                "slot": 701,
                "qualifying_segments": ["S1"],
            },
        ]
        agg = aggregate_live_events(events, as_of=1000)

        self.assertEqual(agg["windows"]["5m"]["trade_event_count"], 1)

    def test_rolling_aggregation_separates_events_from_distinct_wallets(self):
        self.monitor.ingest_rpc_transaction(
            swap_tx(
                "a1",
                990,
                [(WALLET_A, "BUY", TOKEN_A, 100, 10)],
            )
        )
        self.monitor.ingest_rpc_transaction(
            swap_tx(
                "a2",
                995,
                [(WALLET_A, "BUY", TOKEN_A, 50, 5)],
            )
        )
        self.monitor.ingest_rpc_transaction(
            swap_tx(
                "b1",
                999,
                [(WALLET_B, "BUY", TOKEN_A, 20, 2)],
            )
        )
        symbol = self.monitor.aggregate(as_of=1000)["windows"]["5m"]["symbols"][0]

        self.assertEqual(symbol["buy_event_count"], 3)
        self.assertEqual(symbol["buy_wallet_count"], 2)
        self.assertEqual(symbol["unique_wallet_count"], 2)
        self.assertEqual(symbol["buy_base_amount"], "170")
        self.assertEqual(symbol["usd_buy_notional"], "17")
        self.assertEqual(symbol["flow_state"], "ACCUMULATION")

    def test_buy_sell_flow_and_usd_notional_are_directional(self):
        self.monitor.ingest_rpc_transaction(
            swap_tx(
                "buy",
                990,
                [(WALLET_A, "BUY", TOKEN_A, 100, 10)],
            )
        )
        self.monitor.ingest_rpc_transaction(
            swap_tx(
                "sell",
                995,
                [(WALLET_B, "SELL", TOKEN_A, 40, 8)],
            )
        )
        symbol = self.monitor.aggregate(as_of=1000)["windows"]["5m"]["symbols"][0]

        self.assertEqual(symbol["net_base_amount"], "60")
        self.assertEqual(symbol["usd_buy_notional"], "10")
        self.assertEqual(symbol["usd_sell_notional"], "8")
        self.assertEqual(symbol["usd_net_notional"], "2")
        self.assertEqual(symbol["flow_state"], "ACCUMULATION")

    def test_sol_quote_trade_is_counted_but_not_fake_usd_priced(self):
        self.monitor.ingest_rpc_transaction(
            sol_buy_tx("sol-buy", 990, WALLET_A)
        )
        symbol = self.monitor.aggregate(as_of=1000)["windows"]["5m"]["symbols"][0]

        self.assertEqual(symbol["event_count"], 1)
        self.assertEqual(symbol["usd_priced_event_count"], 0)
        self.assertEqual(symbol["unpriced_event_count"], 1)
        self.assertEqual(symbol["usd_buy_notional"], "0")

    def test_segment_membership_counts_do_not_hide_overlap(self):
        self.monitor.ingest_rpc_transaction(
            swap_tx(
                "seg-a",
                990,
                [(WALLET_A, "BUY", TOKEN_A, 100, 10)],
            )
        )
        self.monitor.ingest_rpc_transaction(
            swap_tx(
                "seg-b",
                995,
                [(WALLET_B, "SELL", TOKEN_A, 20, 4)],
            )
        )
        symbol = self.monitor.aggregate(as_of=1000)["windows"]["5m"]["symbols"][0]
        segments = symbol["segment_membership_wallet_counts"]

        self.assertEqual(segments["S1"]["buy_wallet_count"], 1)
        self.assertEqual(segments["S1"]["sell_wallet_count"], 1)
        self.assertEqual(segments["S2"]["buy_wallet_count"], 1)
        self.assertEqual(segments["S2"]["sell_wallet_count"], 0)

    def test_out_of_order_ingestion_uses_block_time_for_aggregation(self):
        self.monitor.ingest_rpc_transaction(
            swap_tx(
                "late-arrival-newer",
                999,
                [(WALLET_A, "BUY", TOKEN_A, 10, 1)],
            )
        )
        self.monitor.ingest_rpc_transaction(
            swap_tx(
                "late-arrival-older",
                950,
                [(WALLET_B, "BUY", TOKEN_A, 10, 1)],
            )
        )
        symbol = self.monitor.aggregate(as_of=1000)["windows"]["5m"]["symbols"][0]

        self.assertEqual(symbol["event_count"], 2)
        self.assertEqual(symbol["last_activity_time"], 999)

    def test_registry_refresh_stops_future_ingestion_for_removed_wallet(self):
        self.monitor.ingest_rpc_transaction(
            swap_tx(
                "before-refresh",
                900,
                [(WALLET_A, "BUY", TOKEN_A, 10, 1)],
            )
        )
        inactive_a = registry_record(WALLET_A, qualified=False)
        new_snapshot = snapshot(
            inactive_a,
            self.record_b,
            snapshot_id="live-2",
        )
        self.monitor.refresh_registry(new_snapshot)

        result = self.monitor.ingest_rpc_transaction(
            swap_tx(
                "after-refresh",
                1000,
                [(WALLET_A, "BUY", TOKEN_A, 10, 1)],
            )
        )
        self.assertEqual(result["status"], "IGNORED")
        self.assertEqual(len(self.monitor.events), 1)
        self.assertEqual(self.monitor.active_wallets, [WALLET_B])

    def test_persistence_row_exposes_unique_idempotency_key(self):
        result = self.monitor.ingest_rpc_transaction(
            swap_tx(
                "persist",
                1000,
                [(WALLET_A, "BUY", TOKEN_A, 100, 10)],
            )
        )
        row = live_event_to_persistence_row(result["accepted_events"][0])

        self.assertEqual(
            row["idempotency_key"],
            f"{WALLET_A}:persist",
        )
        self.assertEqual(row["side"], "BUY")
        self.assertEqual(row["payload"]["base_asset"], TOKEN_A)

    def test_pruning_removes_old_event_payloads_but_not_seen_keys(self):
        old_tx = swap_tx(
            "old",
            100,
            [(WALLET_A, "BUY", TOKEN_A, 10, 1)],
        )
        self.monitor.ingest_rpc_transaction(old_tx)
        removed = self.monitor.prune_events_before(500)

        self.assertEqual(removed, 1)
        self.assertEqual(len(self.monitor.events), 0)

        replay = self.monitor.ingest_rpc_transaction(old_tx)
        self.assertEqual(replay["status"], "DUPLICATE")

    def test_monitor_status_reports_operational_counters(self):
        tx = swap_tx(
            "status",
            1000,
            [(WALLET_A, "BUY", TOKEN_A, 100, 10)],
        )
        self.monitor.ingest_rpc_transaction(tx)
        self.monitor.ingest_rpc_transaction(tx)
        status = self.monitor.status()

        self.assertEqual(status["active_wallet_count"], 2)
        self.assertEqual(status["ingest_attempts"], 2)
        self.assertEqual(status["stored_event_count"], 1)
        self.assertEqual(status["stored_trade_event_count"], 1)
        self.assertEqual(status["duplicate_wallet_event_count"], 1)
        self.assertEqual(status["latest_block_time"], 1000)


if __name__ == "__main__":
    unittest.main()
