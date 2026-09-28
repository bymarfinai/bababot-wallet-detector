# BabaBot Wallet Detector — Stage 5 Wallet Classification V1

**Status:** IMPLEMENTED / RULE CONTRACT FROZEN  
**Date:** 2026-09-28  
**Repository:** `bymarfinai/bababot-wallet-detector`

## 1. Objective

Classify a wallet from the net historical performance profile produced by Stage 4.

Stage 5 is deliberately small.

It does **not** contain:

- ML
- LLM
- weighted score
- 0–100 ranking
- arbitrary confidence formula
- Meme Hunter logic
- Whale logic
- live monitoring
- MCD integration

Those belong to later stages.

## 2. Required Comparable Net Basis

Stage 5 only classifies when net performance is comparable.

Preferred basis:

```text
all clean trades are verified USD-stable quotes
+ complete fee-adjusted metrics
→ USD_STABLE_AGGREGATE
```

Alternative:

```text
all clean trades use one quote currency
+ complete fee-adjusted metrics
→ SINGLE_QUOTE
```

Examples:

- USDC + USDT can use the USD-stable aggregate.
- SOL-only history can use the SOL quote bucket.
- USDC + SOL mixed history is not directly combined and remains `NOT_READY`.

No currency conversion is invented.

## 3. V1 Classification Rules

### S1 — Consistent Wallet

All required:

```text
closed clean trades >= 50
net median ROI >= +1%
net win rate >= 60%
net total realized PnL > 0
```

### S2 — Momentum Wallet

All required:

```text
closed clean trades >= 50
net median ROI >= +5%
net total realized PnL > 0
```

Win rate is recorded, but no extra S2 win-rate threshold is invented because the concept did not define one.

### S3 — High-Velocity Wallet

All required:

```text
closed clean trades >= 50
net median ROI >= +10%
net total realized PnL > 0
```

Win rate is recorded, but no extra S3 win-rate threshold is invented.

## 4. Overlapping Labels

The rules are threshold labels, so a wallet may satisfy more than one.

Example:

```text
net median ROI = 12%
net WR         = 70%
positive PnL
50+ trades

→ S1 = true
→ S2 = true
→ S3 = true
```

For compact operational output, `primary_segment` is the highest-velocity matching label:

```text
S3 → S2 → S1
```

This is **not a quality ranking**. S3 is not declared better than S1; it describes a different return habitat.

The full list remains available in:

```text
qualifying_segments
```

## 5. Drawdown

Stage 4 records drawdown.

The original concept says S1 drawdown should be “reasonable”, but no empirically validated threshold exists yet.

Therefore Stage 5 V1:

```text
records drawdown reference
does NOT gate classification on drawdown
```

No arbitrary threshold is invented.

A drawdown gate can only be added after historical validation.

## 6. Statuses

### QUALIFIED

At least one S1/S2/S3 rule passes.

### UNQUALIFIED

Net comparable metrics exist, but none of the segment rules pass.

### NOT_READY

Examples:

- no clean historical profile
- incomplete fee adjustment
- multiple non-comparable quote currencies
- required net metrics missing

`NOT_READY` is intentionally different from `UNQUALIFIED`.

## 7. Deferred Labels

### Meme Hunter

Deferred to Stage 6 because it requires explosion-event history and lead-time analysis.

### Whale

Deferred until reliable capital / transaction-size data is available.

Large transaction size is not used as a substitute for wallet performance quality.

## 8. Implemented Files

- `research/wallet_s5_classification.py`
- `tests/test_wallet_s5_classification.py`

Stage 4 was minimally extended to expose aggregate:

- net median ROI for USD-comparable trades
- net win rate for USD-comparable trades

No other Stage-4 behavior was changed.

## 9. Acceptance Tests

Stage 5 covers:

1. exact S1 boundary
2. S1 win-rate gate
3. S2 +5% threshold without invented WR gate
4. S3 +10% threshold
5. overlapping S1/S2/S3 labels
6. positive ROI but negative total PnL
7. 49-trade sample rejection
8. incomplete fee adjustment
9. SOL single-quote classification
10. mixed non-comparable quote rejection
11. no-performance profile
12. no invented drawdown / special-label rule

## 10. Stage 5 Decision Rule

Stage 5 can be marked PASS only after the repository CI passes all Stage 1–5 regression tests.

Expected cumulative test inventory:

```text
Stage 1 =  5
Stage 2 =  9
Stage 3 = 11
Stage 4 = 13
Stage 5 = 12
----------------
TOTAL   = 50 tests
```
