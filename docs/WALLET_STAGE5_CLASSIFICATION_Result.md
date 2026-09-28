# BabaBot Wallet Detector — Stage 5 Wallet Classification V1 — Result

**Date:** 2026-09-28  
**Repository:** `bymarfinai/bababot-wallet-detector`

## Result

```text
WALLET_STAGE5_CLASSIFICATION_V1 = PASS
```

Stage 5 now classifies historical wallet profiles using a small deterministic rule set.

## V1 Rules

### S1 — Consistent

```text
clean closed trades >= 50
net median ROI >= +1%
net win rate >= 60%
net total realized PnL > 0
```

### S2 — Momentum

```text
clean closed trades >= 50
net median ROI >= +5%
net total realized PnL > 0
```

### S3 — High-Velocity

```text
clean closed trades >= 50
net median ROI >= +10%
net total realized PnL > 0
```

No extra S2/S3 win-rate threshold was invented.

## Classification Output

```text
QUALIFIED
UNQUALIFIED
NOT_READY
```

A qualified wallet receives:

- `primary_segment`
- `qualifying_segments`
- exact pass/fail checks
- classification basis
- threshold snapshot

There is no weighted score.

## Comparable Net Basis

Stage 5 accepts:

```text
USD_STABLE_AGGREGATE
or
SINGLE_QUOTE
```

It refuses to combine non-comparable quote currencies.

Example:

```text
USDC history + SOL history
→ NOT_READY for one combined classifier
```

unless a validated common valuation layer is added later.

## Overlapping Labels

A wallet can satisfy multiple rule labels.

Example:

```text
50+ trades
net median ROI = 12%
net WR = 70%
net PnL > 0

S1 = PASS
S2 = PASS
S3 = PASS

primary_segment = S3
```

`primary_segment` means highest-velocity matching label, not quality rank.

## Explicitly Not Added

To keep Stage 5 simple:

- no AI
- no ML
- no scoring 0–100
- no discretionary weights
- no invented drawdown cutoff
- no Meme Hunter logic
- no Whale logic
- no live wallet logic

## Drawdown

Drawdown remains visible as a reference metric.

It is not used as a V1 gate because “reasonable drawdown” has not yet been empirically calibrated.

## Special Labels

```text
Meme Hunter → Stage 6
Whale       → deferred until reliable capital data
```

## Test Result

GitHub Actions run covering the Stage 5 implementation and test suite:

```text
Stage 1 =  5 /  5
Stage 2 =  9 /  9
Stage 3 = 11 / 11
Stage 4 = 13 / 13
Stage 5 = 12 / 12
-------------------
TOTAL   = 50 / 50 PASS
```

No known deterministic regression remains.

## Next Stage

```text
Stage 6 — Meme / Explosion Hunter Discovery
```

Stage 6 will be a separate specialty-label detector and will not modify the S1/S2/S3 rules.
