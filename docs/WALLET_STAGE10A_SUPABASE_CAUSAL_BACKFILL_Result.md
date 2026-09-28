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

## Historical universe policy

The current Stage-10A-1 runner accepts explicit wallet identities as a **test/bootstrap interface**, but this is not the final production discovery design.

Production activation is now gated by **Stage 10A-0 — Automatic Wallet Universe Discovery**.

The production input should be a deterministic candidate-wallet universe discovered from real Solana activity with as-of provenance.

If a universe is selected only from wallets known today to be successful, the replay still has survivor-selection bias even though each wallet's qualification timeline is reconstructed causally. Such results remain research-only.

Required production flow:

```text
Solana blockchain
        ↓
Stage 10A-0 automatic wallet discovery
        ↓
causal candidate universe
        ↓
Stage 10A-1 historical qualification/backfill
```

Manual wallet lists remain permitted for unit tests, debugging, provider probes, and controlled bootstrap comparisons only.

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

The Stage-10A-1 code path and Supabase schema are ready.

Real production population is intentionally **not** activated from a hand-picked wallet list. The next required activation step is:

```text
Stage 10A-0 — Automatic Wallet Universe Discovery
```

After Stage 10A-0 produces a causal candidate universe, that output feeds this Stage-10A-1 backfill engine directly.

Provider credentials depend on the chosen transport. If Helius is used, `HELIUS_API_KEY` is required for Helius access; native RPC or another verified provider may use a different access model.

The server-side Supabase secret remains required for direct Python persistence.

Next sequence:

```text
Stage 10A-0 — automatic wallet universe discovery
Stage 10A-1 — real causal backfill population
Stage 10B   — real OHLC ingestion
Stage 10C   — empirical A/B/C/E replay
Rule D      — only after causal Stage-6 reconstruction
```
