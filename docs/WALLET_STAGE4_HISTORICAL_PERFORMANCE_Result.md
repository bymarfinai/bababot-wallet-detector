# BabaBot Wallet Detector — Stage 4 Historical Performance — Result

**Date:** 2026-09-28  
**Repository:** `bymarfinai/bababot-wallet-detector`

## Result

```text
WALLET_STAGE4_HISTORICAL_PERFORMANCE_ENGINE = PASS
```

Wallet Detector can now turn Stage-3 clean closed episodes into a historical wallet profile without mixing incompatible monetary units.

## Example

For clean episodes:

```text
Trade 1: +10
Trade 2:  -4
Trade 3:  -3
Trade 4:  +8
```

Stage 4 produces:

```text
trades          = 4
wins            = 2
losses          = 2
win rate        = 50%
median ROI      = 2.5%
max loss streak = 2
gross profit    = 18
gross loss      = 7
profit factor   = 2.571428...
max drawdown    = 7 quote units
```

## Quote Safety

If a wallet has:

```text
USDC PnL = +10
SOL PnL  = +2
```

Stage 4 does **not** report +12 aggregate PnL.

Instead it stores separate quote metrics and disables the fake overall monetary aggregate.

## Net Performance

Stage 4 now understands three safe fee-adjustment paths:

- upstream validated net PnL
- explicit fee cost in quote currency
- direct SOL/WSOL fee deduction

If quote-fee conversion is unavailable, net totals remain null rather than guessed.

This means Stage 5 can distinguish:

```text
gross-performance available
vs
net-classification ready
```

## Activity and Consistency

Wallet profiles now include:

- first/last closed trade
- active UTC days
- activity span
- active-day ratio
- trades per active day
- trades per calendar day
- recent performance trend

## Sample-Size Gate

Stage 4 exposes:

```text
meets_50_trade_sample
```

which aligns with the current S1/S2/S3 minimum sample concept.

## Test Result

```text
Stage 4 = 13 / 13 PASS
```

Frozen cumulative inventory:

```text
Stage 1 =  5
Stage 2 =  9
Stage 3 = 11
Stage 4 = 13
----------------
TOTAL   = 38 tests
```

No known failing deterministic test remains.

## Next Stage

```text
Stage 5 — Wallet Classification V1
```

Stage 5 can now classify wallets from measured historical performance instead of raw transaction counts.
