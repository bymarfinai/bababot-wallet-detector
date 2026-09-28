# BabaBot Wallet Detector — Stage 10A Supabase Causal Historical Backfill

**Date:** 2026-09-28  
**Status:** IMPLEMENTED / ACTIVATION-READY

## Result

```text
WALLET_STAGE10A_SUPABASE_ADAPTER = PASS
WALLET_STAGE10A_CAUSAL_BACKFILL_ENGINE = PASS
WALLET_STAGE10A_REAL_POPULATION = PENDING_RUNTIME_INPUTS
```

## Supabase

Project:

```text
bababot-wallet-detector
region = ap-southeast-1
```

Persisted evidence layers:

```text
historical_wallet_transactions
        ↓
normalized_wallet_history
        ↓
causal Stage-3 / Stage-4 / Stage-5 reconstruction
        ↓
registry_snapshots + wallet_registry
        ↓
wallet_events
        ↓
smart_money_signal_snapshots + smart_money_signals
```

Stage-10 OHLC and replay tables remain available:

```text
token_price_bars
replay_runs
paper_trades
```

## Causality policy

Historical qualification is not copied backward from a current registry snapshot.

For every wallet:

1. transactions are processed chronologically;
2. positions/performance/classification use only history already observed;
3. a status change caused by a transaction at timestamp T becomes effective strictly after T;
4. the transaction that caused qualification is therefore not retroactively treated as smart money.

This prevents a direct qualification lookahead leak.

## Historical universe warning

The wallet identities themselves are external input.

If the universe is selected only from wallets known to be successful today, the replay still has survivor-selection bias even though each wallet's qualification timeline is reconstructed causally.

Such results must remain research-only until wallet-universe provenance is suitable for validation.

## Stage-6 policy

Stage-6 Meme / Explosion Hunter evidence is deliberately disabled in historical Stage-10A signals until an as-of-safe reconstruction exists.

```text
Rule A historical readiness = yes
Rule B historical readiness = yes
Rule C historical readiness = yes
Rule D historical readiness = no
Rule E historical readiness = yes
```

No future explosion information is allowed to leak backward into a historical signal.

## Helius backfill

The runner uses the frozen Stage-1 Helius `getTransactionsForAddress` boundary.

It fetches complete filtered history per wallet and fails closed when the configured page cap is reached before pagination is exhausted.

No partial wallet history is silently treated as complete.

## Supabase adapter

Server-side persistence uses PostgREST with batched upserts and explicit conflict keys.

Secrets remain environment-only:

```text
WALLET_SUPABASE_URL
WALLET_SUPABASE_SECRET_KEY
HELIUS_API_KEY
```

No Supabase secret or Helius API key is committed.

## CLI

Example:

```bash
python research/wallet_s10a_historical_backfill.py \
  --wallets-file wallets.json \
  --signal-from-unix <timestamp> \
  --signal-to-unix <timestamp> \
  --out outputs/stage10a/backfill-report.json
```

Use `--dry-run` to build and audit the causal replay without writing Supabase.

## Verification

Stage-10A coverage includes:

- complete Helius pagination
- fail-closed page cap
- raw evidence preservation
- Stage-2 normalized evidence preservation
- causal qualification
- no retroactive qualifying transaction
- one-hour Stage-9 warmup context
- Stage-6 historical disablement
- Supabase server-auth contract
- batched upserts
- Stage-8 mapping
- Stage-9 mapping

Latest full Python regression:

```text
196 / 196 PASS
```

## Activation boundary

The code path is ready, but a real backfill has not been executed from this session because these runtime inputs are not currently available to the runner:

```text
HELIUS_API_KEY
real wallet universe
WALLET_SUPABASE_SECRET_KEY (for direct Python persistence)
```

The Supabase project and schema themselves are already live.

Next after real Stage-10A population:

```text
Stage 10B — real OHLC ingestion
Stage 10C — empirical A/B/C/E replay
Rule D only after causal Stage-6 reconstruction
```
