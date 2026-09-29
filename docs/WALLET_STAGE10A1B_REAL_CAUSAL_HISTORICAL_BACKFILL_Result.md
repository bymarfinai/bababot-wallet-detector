# BabaBot Wallet Detector — Stage 10A-1B Real Causal Historical Backfill

**Date:** 2026-09-29  
**Status:** PASS_STANDARD_LANE / PARTIAL_REAL_POPULATION

## Result

```text
WALLET_STAGE10A1B_ENGINE = PASS
WALLET_STAGE10A1B_REAL_MAINNET_SMOKE = PASS
WALLET_STAGE10A1B_STANDARD_LANE = PASS
WALLET_STAGE10A1B_FULL_COHORT_POPULATION = PARTIAL
WALLET_STAGE10A1B_SUPABASE_PERSISTENCE = PENDING_SERVER_SECRET
WALLET_STAGE10A1B_HIGH_VOLUME_LANE = PENDING_HIGH_CAPACITY_HISTORY_PROVIDER
```

## Production flow

```text
Stage 10A-0 automatic discovery
        ↓
Stage 10A-1A Stage-2 trader refinement
        ↓
TRADER_CANDIDATE
        ↓
Stage 10A-1B historical evidence backfill
        ↓
raw real transactions
+ Stage-2 normalized historical evidence
        ↓
Stage 10A-1C Stage 3–5 qualification
```

Stage 10A-1B itself does not need to declare a wallet S1/S2/S3. The production population workflow uses evidence-only mode so Stage 3–5 qualification remains the next stage.

## Provider implementation

Dedicated module:

```text
research/wallet_s10a1b_real_historical_backfill.py
```

Supported providers:

```text
solana-rpc
helius
```

The native Solana path uses finalized `getSignaturesForAddress`, `getTransaction`, and `getFirstAvailableBlock`. Provider history is fail-closed when pagination is incomplete or a required transaction is unavailable.

High transaction volume is treated as an execution-capacity classification only. `HIGH_VOLUME` does **not** mean unqualified or low-quality.

## Causality

A population timestamp is frozen before historical collection. Only transactions at or before that timestamp may enter the historical evidence set.

The discovery/refinement effective time remains separate from prior historical evidence. Later Stage-10A-1C may use pre-discovery history for qualification as-of discovery, but smart-money events remain eligible only strictly after the discovery universe became observable.

## Real mainnet smoke

Latest successful smoke run:

```text
GitHub Actions run = 36512887798
provider first available slot = 0
provider archive from genesis = true
mode = FULL_SINGLE_WALLET_BACKFILL
qualification_grade = true
```

This proves a real automatically discovered/refined trader wallet can be fully backfilled using the native public Solana RPC path without a hand-picked wallet list.

## Real population run

Successful population run:

```text
GitHub Actions run = 36511958904
workflow = Wallet History Population
shards = 8

activity candidates = 92
trader candidates = 65
meme-buy candidates = 36

STANDARD wallets = 10
HIGH_VOLUME wallets = 55

STANDARD raw transaction rows = 187
STANDARD normalized event rows = 187
```

All 65 trader candidates were deterministically partitioned into exactly one capacity lane:

```text
10 STANDARD
+55 HIGH_VOLUME
=65 trader candidates
```

STANDARD-lane shard execution completed successfully and produced auditable evidence artifacts containing:

```text
capacity-plan.json
standard-refinement.json
evidence/manifest.json
evidence/raw.jsonl
evidence/normalized.jsonl
evidence/report.json
result.json
```

The population workflow does not silently discard HIGH_VOLUME wallets. Their policy is:

```text
REQUIRES_HIGH_CAPACITY_OR_INDEXED_HISTORY_PROVIDER
```

## Credential / persistence boundary

The population workflow reported:

```text
HELIUS_API_KEY configured = no
WALLET_SUPABASE_SECRET_KEY configured = no
```

Therefore the STANDARD evidence run was intentionally executed as dry-run artifacts rather than pretending production database persistence occurred.

Live Supabase row counts remain zero in `historical_wallet_transactions` and `normalized_wallet_history` as of this checkpoint.

This is a runtime credential/capacity boundary, not an engine failure.

## Supabase safety

Persistence code already exists and refuses to persist non-qualification-grade provider history as production evidence.

RLS remains enabled. No permissive anon policy is added for convenience.

## Verification

Latest repository regression after cleanup:

```text
239 / 239 Python tests PASS
TypeScript PASS
Next.js build PASS
production UI smoke PASS
```

## Status interpretation

Stage 10A-1B is proven end-to-end for the STANDARD capacity lane on real Solana mainnet data.

It is **not yet fully complete for the entire trader cohort** because 55 HIGH_VOLUME wallets require a higher-capacity/indexed history lane and real Supabase persistence still needs the server-side write secret.

## Next

```text
10A-1B-HV  complete HIGH_VOLUME historical evidence
           using Helius or another high-capacity/archive provider

+

10A-1B-PERSIST
           configure server-side Supabase write credential
           and persist qualification-grade evidence

then

10A-1C     Stage 3–5 real qualification
```
