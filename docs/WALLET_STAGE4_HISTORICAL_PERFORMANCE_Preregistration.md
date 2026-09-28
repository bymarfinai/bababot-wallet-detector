# BabaBot Wallet Detector — Stage 4 Historical Wallet Performance Engine

**Status:** IMPLEMENTED / PERFORMANCE CONTRACT FROZEN  
**Date:** 2026-09-28  
**Repository:** `bymarfinai/bababot-wallet-detector`

## 1. Objective

Stage 4 converts **clean closed trading episodes** from Stage 3 into a historical wallet performance profile.

The engine does not score raw transactions. It only uses episodes with:

```text
status = CLOSED
eligible_for_performance_metrics = true
```

This preserves the economic meaning of one position = one trade episode.

## 2. Core Metrics

Overall wallet behavior:

- closed trade count
- wins / losses / breakeven
- win rate
- median ROI
- mean ROI
- largest win ROI
- largest loss ROI
- max win streak
- max loss streak
- median holding time
- mean holding time
- distinct traded assets
- active days
- calendar activity span
- trades per active day
- trades per calendar day
- recent-vs-prior performance trend
- minimum 50-trade sample readiness

## 3. Quote-Currency Safety

Monetary PnL is **not** aggregated across unrelated quote currencies.

Example:

```text
+100 USDC
+2 SOL
```

must not become:

```text
+102 total PnL
```

Instead Stage 4 creates independent quote buckets:

```text
USDC metrics
SOL metrics
USDT metrics
...
```

Each quote bucket has:

- total realized PnL
- gross profit
- gross loss
- profit factor
- maximum realized-PnL drawdown
- median ROI
- mean ROI
- win rate
- holding time
- fee-adjusted coverage

If all episodes share one quote, an overall profit factor may be surfaced.

If multiple quote currencies exist:

```text
overall_profit_factor = null
```

with an explicit note explaining why.

## 4. USD-Comparable Bucket

Verified USD stablecoin episodes may be grouped into a nominal USD-comparable bucket.

This currently includes episodes already tagged by Stage 2/3 as:

```text
quote_is_usd = true
```

Examples include verified USDC / USDT mint-address quotes.

The USD-comparable bucket exposes:

- gross stablecoin PnL
- gross profit factor
- stablecoin PnL drawdown
- net-fee coverage
- net stablecoin PnL only when fee adjustment is complete

## 5. Gross vs Net Performance

Stage 4 separates gross execution performance from net fee-adjusted performance.

Gross metrics are always available for clean episodes:

```text
metric_basis = CLEAN_CLOSED_EPISODES_GROSS_EXECUTION
```

Execution slippage is already embedded in the actual wallet input/output amounts from Stage 2.

Network fees require quote conversion.

### Fee adjustment hierarchy

1. `net_realized_pnl_quote` already supplied by a validated upstream process
2. explicit `fee_cost_quote`
3. SOL/WSOL quote: lamport fee can be converted directly to SOL
4. otherwise net quote PnL remains unavailable

Stage 4 does not invent historical SOL/USD prices just to fill missing net metrics.

## 6. Qualification Readiness

Stage 5 S1/S2/S3 concepts require net performance.

Stage 4 therefore exposes:

```text
minimum_trade_sample_50_met
gross_behavior_metrics_ready
usd_net_fee_metrics_complete
net_classification_ready
```

A wallet is `net_classification_ready` only when:

- clean closed trades >= 50
- all scored episodes are USD-comparable
- fee-adjusted net PnL is complete

This is deliberately conservative.

## 7. Drawdown Definition

Quote-specific `max_drawdown_quote` is computed on the chronological cumulative realized-PnL curve:

```text
cumulative realized PnL
        ↓
running peak
        ↓
largest peak-to-trough loss
```

It is denominated in that quote currency.

Stage 4 does not fabricate a capital/equity drawdown percentage when historical wallet capital allocation is unknown.

## 8. Activity Consistency

Activity uses UTC close dates.

Metrics:

```text
active_days
calendar_span_days
active_day_ratio_pct
trades_per_active_day
trades_per_calendar_day
```

This allows Stage 5/ML to distinguish wallets with the same ROI but very different consistency.

## 9. Recent Performance

Default recent window:

```text
20 clean closed episodes
```

Stage 4 compares:

```text
latest N episodes
vs
all prior clean episodes
```

Output:

- recent median ROI
- prior median ROI
- delta in percentage points
- recent win rate
- prior win rate
- delta in percentage points
- whether the trend is actually comparable

No trend is invented when there is no prior sample.

## 10. Data Integrity

Stage 4 rejects mixed-wallet inputs.

If more than one wallet address appears in the clean input:

```text
ValueError
```

This prevents accidental profile merging.

Contaminated Stage-3 episodes are filtered out automatically.

## 11. Implemented Files

- `research/wallet_s4_historical_performance.py`
- `tests/test_wallet_s4_historical_performance.py`
- `.github/workflows/tests.yml`

## 12. Deterministic Tests

Stage 4 test coverage:

1. contaminated episode filtering
2. core WR / median ROI / streak metrics
3. quote-specific profit factor and drawdown
4. mixed-quote aggregate protection
5. USDC + USDT USD-comparable aggregation
6. direct SOL network-fee adjustment
7. explicit quote-fee adjustment
8. incomplete net-fee coverage
9. UTC activity consistency
10. recent-vs-prior trend
11. 50-trade net classification readiness
12. no-clean-episode profile
13. multi-wallet rejection

Result:

```text
Stage 4 tests = 13 / 13 PASS
```

Previously frozen deterministic coverage:

```text
Stage 1 =  5 /  5 PASS
Stage 2 =  9 /  9 PASS
Stage 3 = 11 / 11 PASS
```

Cumulative test inventory:

```text
38 tests
38 PASS at their frozen stage checkpoints
0 known FAIL
```

## 13. Stage 4 Decision

```text
WALLET_STAGE4_HISTORICAL_PERFORMANCE_ENGINE = PASS
```

Next:

```text
Stage 5 — Wallet Classification V1
performance profile
        ↓
S1 Consistent
S2 Momentum
S3 High-Velocity
+ capital / specialty metadata
```
