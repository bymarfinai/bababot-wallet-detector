# Wallet Detector — Stage 10A-1B V2 Streaming Historical Scanner

**Date:** 2026-10-01  
**Status:** IMPLEMENTED; production rerun blocked only by Supabase database recovery.

## Objective

Replace the previous raw-history warehouse with an IN → PROCESS → OUT scanner.

```text
Indexed Solana provider
        ↓
oldest → newest page (max 100 full tx)
        ↓
Stage 2 normalize in memory
        ↓
Stage 3 streaming position reconstruction
        ↓
persist compact closed-trade summaries
+ persist minimal open-position checkpoint
        ↓
discard raw + normalized page
        ↓
next page
```

No full raw Solana transaction payload and no normalized transaction history is
persisted by V2.

## Durable data

### wallet_history_scan_state

One compact checkpoint per universe + wallet:

- provider/cutoff provenance
- next pagination token
- pages/transaction counters
- scan exhausted / history complete
- minimal Stage-3 open-position state
- latest profile-finalization status

### wallet_historical_trade_summaries

One compact row per **clean closed trade** only. It retains only the fields needed
by Stage 4 performance reconstruction, including quote PnL/ROI, timestamps,
base/quote assets, fees, and buy/sell counts.

### wallet_historical_profiles

Compact final Stage-4 performance payload plus Stage-5 classification payload.
Formal cohort-wide qualification/registry remains Stage 10A-1C.

## Crash / resume semantics

For each page:

1. Fetch full transactions in ascending chronological order.
2. Normalize and consume the page in memory.
3. Upsert compact closed-trade summaries.
4. Persist the new Stage-3 state + provider pagination token.
5. Discard raw and normalized page data.

The write order deliberately persists compact trade outputs **before** advancing
the checkpoint. If checkpoint persistence fails, replaying that page is safe
because trade summaries are idempotent on
`(universe_fingerprint, wallet, episode_id)`.

If the provider scan is already exhausted but profile finalization failed, the
next run finalizes from compact trade summaries without another provider call.

## Storage policy

Legacy tables:

- `historical_wallet_transactions`
- `normalized_wallet_history`

are truncated by the V2 migration and are not populated by the V2 scanner.

## Provider policy

Alchemy `getTransactionsForAddress` is called with `sortOrder=asc` and the
frozen `blockTime <= history_as_of_unix` cutoff. The opaque pagination token is
stored in the compact checkpoint, so the scanner can continue from the next page.

## Reliability

The Supabase REST client now retries transient:

- 429
- 500
- 502
- 503
- 504
- URL/network timeout failures

with exponential backoff.

## Validation

Automated tests cover:

- streaming Stage-3 parity with the existing Stage-3 reconstruction engine
  across page boundaries;
- no writes to raw/normalized historical tables;
- compact persistence and completed-scan idempotency;
- retry of a transient Supabase HTTP 503.

Wallet Detector Tests run #207: **PASS**.

## Current blocker

The existing Supabase project filled its physical database disk during the V1
raw backfill. PostgreSQL is still in crash recovery and currently rejects SQL and
PostgREST connections with SQLSTATE 57P03.

The V2 schema migration is committed, but cannot be applied until PostgreSQL is
writable again. A recovery action (platform recovery / pause+restore / paid disk
expansion) is required before the V2 population rerun can start.
