# BabaBot Wallet Detector — Stage 2 Transaction Normalization — Result

**Date:** 2026-09-28  
**Repository:** `bymarfinai/bababot-wallet-detector`

## Result

```text
WALLET_STAGE2_TRANSACTION_NORMALIZATION = PASS
```

Stage 2 now converts raw wallet transaction evidence into deterministic economic events suitable for Stage 3 position reconstruction.

## Implemented Output Classes

```text
SWAP
TRANSFER_IN
TRANSFER_OUT
WRAP
UNWRAP
OTHER
FAILED
AMBIGUOUS
```

Directional trade side:

```text
BUY
SELL
SWAP
NONE
```

BUY/SELL is only assigned when a trusted quote asset exists.

## Pricing

For direct stablecoin pairs:

```text
USDC -10
TOKEN +100

side                  = BUY
execution_price_quote = 0.1
usd_notional          = 10
pricing_quality       = DIRECT_USD_EXECUTION
confidence            = HIGH
```

For native SOL:

```text
raw SOL balance change
+ explicit network fee when wallet is fee payer
= economic SOL change
```

This prevents the network fee from becoming a fake trade leg.

## Safety Against False Reconstruction

Stage 2 deliberately outputs `AMBIGUOUS` when multiple unresolved economic legs remain.

It does not infer a fake trade just to maximize coverage.

Token-to-token swaps without a trusted quote retain exact input/output endpoints but use:

```text
side = SWAP
```

rather than inventing BUY/SELL.

## Regression Fix

Stage 2 testing exposed and fixed a Stage-1 edge case where a token mint could exist only in pre-balances and disappear from post-balances.

The parser now correctly treats the missing post balance as zero.

## Test Result

```text
Stage 1 regression tests = 5 PASS
Stage 2 tests            = 9 PASS
--------------------------------
TOTAL                    = 14 PASS
FAIL                     = 0
```

## Next Stage

```text
Stage 3 — Position / Trade Reconstruction
```

The normalized event stream is now ready to be grouped into real trading episodes with averaging, partial sells, realized PnL, ROI, and holding time.
