# BabaBot Wallet Detector — Stage 10 Wallet-Only Paper Trading — Result

**Date:** 2026-09-28  
**Repository:** bymarfinai/bababot-wallet-detector

## Result

```text
WALLET_STAGE10_PAPER_TRADING_ENGINE = PASS
```

Wallet Detector now has an independent causal paper-trading engine.

## Frozen Execution Contract

```text
Wallet Detector signal only
ACCUMULATION → LONG
DISTRIBUTION → SHORT

TP = +1%
SL = -1%

entry = first bar open strictly after signal
one active position per token
same-bar TP+SL = conservative SL-first
fees + slippage = explicit inputs
```

## Candidate Variants

```text
A  >=2 directional qualified wallets

B  >=3 directional qualified wallets

C  >=3
   + same-side higher-tier participation

D  >=3
   + same-side Stage-6 Meme evidence

E  >=3
   + wallet breadth advantage >=2
   + validated USD flow aligned
```

No candidate is selected as production winner.

## Main Benchmark

The engine directly reports:

```text
P(+1% before -1%)
```

both among barrier-resolved trades and among all complete trades.

## Causality / Bias Guards

Implemented:

- no same-timestamp entry
- no overlapping same-token position
- no optimistic same-candle TP/SL ordering
- no forced outcome on truncated data
- no fake USD conversion
- no invented fee/slippage assumption
- no MCD dependency
- no rule winner chosen from unit tests

## Multi-Horizon Evaluation

Every trade records:

```text
30m
1h
4h
12h
24h
```

with independent MFE, MAE, barrier touches, and coverage status.

## Regression

Stage 10:

```text
31 / 31 PASS
```

Full Python suite:

```text
170 / 170 PASS
```

Existing UI CI remains green:

```text
TypeScript = PASS
Next.js build = PASS
Production smoke = PASS
```

## Important Limitation

No real profitability or win-rate result is claimed yet.

The repository currently lacks a sufficiently populated real historical replay dataset consisting of:

```text
Stage-9 signals
+
causal token OHLC
+
chosen real execution-cost assumptions
```

So current status is:

```text
engine implementation       PASS
experiment methodology      PASS
real paper-trading replay   PENDING
A–E empirical comparison    PENDING
edge validation             PENDING
```

Synthetic deterministic tests prove execution correctness; they do not prove trading edge.

## Next Work

Populate a real Stage-10 replay dataset and run candidates A–E through the frozen engine.

Only after that should Stage 11 optimize or freeze a production rule.
