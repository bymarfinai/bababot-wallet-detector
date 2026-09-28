# BabaBot Wallet Detector — Stage 6 Meme / Explosion Hunter — Result

**Date:** 2026-09-28  
**Repository:** `bymarfinai/bababot-wallet-detector`

## Result

```text
WALLET_STAGE6_MEME_EXPLOSION_HUNTER = PASS
```

Stage 6 now measures whether a wallet repeatedly buys before large token expansions.

## Primary Evidence

For every eligible BUY:

```text
2x within 6h?
2x within 24h?
2x within 72h?

5x within 6h?
5x within 24h?
5x within 72h?

10x within 6h?
10x within 24h?
10x within 72h?
```

Each bucket records:

```text
eligible buys
hits
misses
incomplete history
buy hit rate
distinct eligible tokens
distinct hit tokens
token hit rate
lead time
```

## Why This Matters

A wallet with:

```text
10 BUYs
1 lucky 10x
9 misses
```

is distinguishable from a wallet with:

```text
10 BUYs
6 independent 2x hits
3 independent 5x hits
2 independent 10x hits
across multiple tokens
```

Repeated averaging into the same token also cannot fake distinct-token repeatability.

## Truncated Data Safety

A BUY whose historical data ends before the requested horizon becomes:

```text
INCOMPLETE
```

not `MISS`.

This prevents dataset truncation from lowering wallet hit rates.

## Explosion-Centric Evidence

Stage 6 can also consume validated historical explosion events.

BUYs are matched only when:

```text
event start <= BUY < trigger
```

Multiple BUYs by one wallet before the same explosion count as **one matched explosion event**, while preserving:

- buy count
- earliest entry
- latest entry
- first-entry lead
- last-entry lead

This prevents DCA spam from inflating repeatability.

## Final Label

Stage 6 does not yet hardcode an arbitrary final Meme Hunter threshold.

Current output:

```text
EVIDENCE_PROFILE_ONLY
```

This is intentional.

The evidence is now rich enough for population calibration before freezing a production label threshold.

## Test Result

```text
Stage 1 =  5 /  5
Stage 2 =  9 /  9
Stage 3 = 11 / 11
Stage 4 = 13 / 13
Stage 5 = 12 / 12
Stage 6 = 15 / 15
-------------------
TOTAL   = 65 / 65 PASS
```

GitHub Actions passed the final Stage-6 multi-wallet regression.

## Next Stage

```text
Stage 7 — Qualified Wallet Registry
```

Stage 7 can now combine:

- S1/S2/S3 classification
- Stage-4 historical performance
- Stage-6 explosion evidence
- readiness / quality flags

into one durable wallet registry.
