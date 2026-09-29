# BabaBot Wallet Detector — Stage 10A-1A Candidate Refinement

**Date:** 2026-09-29  
**Status:** PASS

## Result

```text
WALLET_STAGE10A1A_CANDIDATE_REFINEMENT = PASS
stage2_prefilter_reused = true
performance_filter = none
future_return_filter = none
real_mainnet_smoke = PASS
```

Stage 10A-1A reduces raw activity noise before expensive full historical backfill. It does **not** decide whether a wallet is smart money.

```text
Stage 10A-0 ACTIVITY_CANDIDATE
        ↓
Stage-2 normalization
        ↓
SWAP + directional BUY/SELL?
├── NO  → NON_TRADER_ACTIVITY
└── YES → TRADER_CANDIDATE
          ├── BUY  → MEME_BUY_CANDIDATE
          └── SELL → normal trader candidate
```

Frozen V1 trader rule: `event_type = SWAP` and `side ∈ {BUY, SELL}`.

Frozen V1 meme-track seed: `TRADER_CANDIDATE` plus at least one Stage-2 BUY event. `MEME_BUY_CANDIDATE` is only a causal seed for later Stage-6 explosion analysis; it is **not** a Meme Hunter label.

No Stage-3/4/5 performance criteria are used here: no win-rate threshold, no ROI threshold, no realized-PnL threshold, no minimum-50-trade threshold, and no future token return.

## Implementation

New module:

```text
research/wallet_s10a1_candidate_refinement.py
```

The module refetches the exact finalized slots recorded by Stage 10A-0 and requires every discovery evidence signature to be present. Missing evidence fails closed. Every evidence transaction is normalized through the existing frozen Stage-2 normalizer.

Wallet-level output preserves candidate status, trader/meme-buy flags, historical-backfill eligibility, BUY/SELL counts, observed base assets, and deterministic fingerprints. Per-signature output preserves Stage-2 event type/side/assets/confidence, refinement reason, normalized evidence, and fingerprint.

## Supabase

Stage 10A-1A enriches the existing discovery tables instead of creating a competing universe:

```text
wallet_universe_snapshots
wallet_universe_candidates
wallet_universe_evidence
```

Migration:

```text
supabase/migrations/20260929072000_wallet_detector_stage10a1a_candidate_refinement.sql
```

## Handoff

The historical backfill runner now accepts `--refinement-file`. Only records with `trader_candidate = true` are handed to full historical backfill.

```text
Stage 10A-0 discovery
        ↓
Stage 10A-1A refinement
        ↓
TRADER_CANDIDATE only
        ↓
Stage 10A-1B full historical backfill
        ↓
Stage 3 → Stage 4 → Stage 5
```

Orthogonal meme path:

```text
TRADER_CANDIDATE
        ↓
BUY event
        ↓
MEME_BUY_CANDIDATE
        ↓
future causal Stage-6 price-path analysis
        ↓
2x / 5x / 10x / 20x / 50x / 100x evidence
```

## Real Solana mainnet validation

```text
GitHub Actions run: 36507032007
finalized blocks: 2
transactions observed: 2,270
activity candidate wallets: 250
trader candidate wallets: 212
non-trader activity wallets: 38
meme-buy candidate wallets: 130
BUY events: 133
SELL events: 89
```

This is a different live two-block sample from the earlier Stage-10A-0 smoke, so its raw candidate count should not be compared as if it were the same 205-wallet cohort. No wallet list was supplied.

Latest full Python regression:

```text
220 / 220 PASS
```

## Next

```text
Stage 10A-0  automatic universe discovery = PASS
Stage 10A-1A trader/meme candidate refinement = PASS
Stage 10A-1B real causal historical backfill = NEXT
Stage 10A-1C Stage 3-5 qualification = follows 10A-1B
Stage 10B    real OHLC = PENDING
Stage 10C    empirical replay = PENDING
```
