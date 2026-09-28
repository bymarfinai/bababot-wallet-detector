# BabaBot Wallet Detector — Stage 10 Wallet-Only Paper Trading

**Status:** ENGINE IMPLEMENTED / EXPERIMENT CONTRACT FROZEN  
**Date:** 2026-09-28  
**Repository:** bymarfinai/bababot-wallet-detector

## 1. Objective

Stage 10 tests Wallet Detector independently.

No Market Radar / MCD input is required.

The engine consumes Stage-9 smart-money signal snapshots plus causal OHLC price bars and simulates paper trades under a frozen baseline execution contract.

Primary benchmark:

```text
P(+1% before -1%)
```

The paper trader does not select a production winner. Stage 11 is responsible for empirical validation and rule selection after a real dataset exists.

## 2. Baseline Direction

Stage-9 descriptive state maps to paper-trade direction:

```text
ACCUMULATION → LONG
DISTRIBUTION → SHORT
NEUTRAL      → no trade
```

No directional override is taken from MCD or another external system.

## 3. Baseline TP / SL

Frozen defaults:

```text
TP = +1.0%
SL = -1.0%
RR = 1:1
```

For SHORT, direction is mirrored.

TP/SL are price-path barriers relative to the executed entry reference.

Fees and slippage are applied separately to realized paper-return calculations.

## 4. Fees and Slippage

Stage 10 does not invent one universal market-cost assumption.

The caller must supply:

```text
fee_bps_per_side
slippage_bps_per_side
```

This keeps the engine valid across exchanges, venues, token liquidity regimes, and later calibration.

Execution policy:

```text
LONG entry  → adverse upward slippage
LONG exit   → adverse downward slippage

SHORT entry → adverse downward slippage
SHORT exit  → adverse upward slippage
```

Net paper return is then adjusted for entry and exit fees.

## 5. Causal Entry

Entry rule:

```text
first OHLC bar open with timestamp strictly greater than signal_time
```

A bar with:

```text
timestamp == signal_time
```

is not a valid entry bar.

This prevents same-timestamp lookahead.

Optional:

```text
max_entry_delay_seconds
```

can reject stale market data.

No arbitrary default entry-delay cutoff is forced.

## 6. One Active Position per Symbol

Each candidate rule is simulated independently.

Within one rule:

```text
one active position per base_asset
```

A later qualifying signal on the same token is skipped while the previous paper position remains active.

Re-entry is allowed only after the prior position closes.

Different tokens maintain independent position state.

## 7. Same-Candle TP / SL Ambiguity

OHLC bars do not reveal intrabar path ordering.

If both TP and SL are touched in the same bar:

```text
SL_FIRST_TIE_CONSERVATIVE
```

is used.

This intentionally avoids optimistic backtest bias.

## 8. Timeout vs Incomplete Data

Configured holding timeout:

```text
max_holding_seconds
```

If neither TP nor SL is touched:

- if price history proves coverage through timeout → TIMEOUT
- if data ends before timeout → INCOMPLETE_DATA

INCOMPLETE_DATA is not forced into a win, loss, or timeout.

## 9. Required Evaluation Horizons

Each opened trade records independent path evaluation at:

```text
30m
1h
4h
12h
24h
```

Each horizon preserves:

- coverage completeness
- bar count
- MFE
- MAE
- first TP touch time
- first SL touch time
- TP-before-SL outcome

These horizon paths may continue beyond the actual trade exit.

This allows Stage 11 to study alternative holding horizons without rewriting the execution engine.

## 10. Trade-Level MFE / MAE

Top-level trade MFE and MAE are calculated only over the actual paper-trade lifetime:

```text
entry → actual exit
```

They are intentionally separate from counterfactual horizon MFE / MAE.

## 11. Candidate Rules

Stage 10 preregisters five candidate variants.

They are experiments, not production decisions.

### Rule A

```text
>= 2 directional qualified wallets
```

LONG uses BUY-wallet breadth.

SHORT uses SELL-wallet breadth.

### Rule B

```text
>= 3 directional qualified wallets
```

### Rule C

```text
>= 3 directional qualified wallets
+ >= 1 same-side higher-tier membership
```

Higher-tier membership currently means:

```text
S2 / S3
```

and the contract is future-compatible with documented S4 / S5.

### Rule D

```text
>= 3 directional qualified wallets
+ >= 1 same-side wallet carrying Stage-6 Meme Hunter evidence
```

Current Meme Hunter state remains evidence-only.

Rule D does not pretend Stage-6 EVIDENCE_PROFILE_ONLY is already a calibrated production specialty label.

Evidence from a wallet on the opposite side does not qualify the rule.

### Rule E

```text
>= 3 directional qualified wallets
+ same-side wallet breadth advantage >= 2
+ validated USD flow exists
+ validated USD flow agrees with signal direction
```

Accepted USD coverage:

```text
COMPLETE
PARTIAL
```

UNAVAILABLE does not qualify.

Rule E is a candidate interpretation of stronger independent flow, not a frozen production winner.

## 12. Preserved Trade Features

Every paper trade preserves:

- token mint
- side
- signal time
- signal fingerprint
- entry time
- entry delay
- raw entry price
- slippage-adjusted entry fill
- TP / SL trigger prices
- exit time
- exit reason
- raw exit price
- slippage-adjusted exit fill
- fee / slippage assumptions
- gross return
- net return after costs
- trade MFE / MAE
- time to TP / SL when observed before trade exit
- 30m / 1h / 4h / 12h / 24h path metrics
- directional qualified-wallet count
- BUY / SELL wallet counts
- wallet-net breadth
- S1 / S2 / S3 / future S4 / S5 membership counts
- Stage-6 Meme Hunter evidence summary
- validated USD flow
- freshness
- Stage-9 persistence evidence
- rule checks
- deterministic trade fingerprint

## 13. Rule Summary Metrics

Per candidate rule:

- candidate signal count
- opened trades
- complete trades
- incomplete trades
- signals skipped because a position was already active
- signals with no causal entry price
- TP-first count
- SL-first count
- timeout count
- barrier-resolved count
- P(TP before SL) among barrier-resolved trades
- P(TP before SL) among complete trades
- mean net return
- median net return
- normalized cumulative net return

No rule is marked winner in Stage 10.

Output explicitly carries:

```text
winner_selected = false
selection_policy = STAGE11_VALIDATION_REQUIRED
```

## 14. Input Integrity

Stage 10 rejects:

- incompatible Stage-9 snapshot versions
- incompatible Stage-9 signal versions
- conflicting duplicate token signals at the same timestamp
- duplicate rule requests
- duplicate OHLC timestamps
- invalid OHLC structure
- non-positive prices
- invalid fee / slippage configuration

## 15. Deterministic Result

Stage 10 adds 31 deterministic tests.

Coverage includes:

1. candidate A threshold
2. candidate B threshold
3. candidate C higher-tier requirement
4. candidate D same-side Meme evidence
5. candidate E wallet breadth + USD alignment
6. neutral-signal exclusion
7. strict post-signal entry
8. LONG TP-first
9. LONG SL-first
10. same-bar conservative SL
11. SHORT TP-first
12. fee/slippage impact
13. no-price handling
14. stale entry-delay rejection
15. incomplete history
16. real timeout
17. one active position per symbol
18. re-entry after close
19. all required evaluation horizons
20. horizon incompleteness
21. actual trade MFE/MAE lifetime
22. P(+1% before -1%) summary
23. no Stage-10 winner selection
24. future S4/S5 feature preservation
25. independent multi-token position state
26. conflicting duplicate-signal rejection
27. incompatible Stage-9 schema rejection
28. invalid OHLC rejection
29. duplicate rule rejection
30. deterministic experiment fingerprint
31. invalid negative-cost rejection

Current full Python regression:

```text
Ran 170 tests
OK
```

GitHub Actions also passed the existing TypeScript, Next.js production build, and dashboard smoke-test gate.

## 16. Empirical Activation Status

The Stage-10 engine is complete.

A real edge claim is not yet possible because the repository does not yet contain a sufficiently populated historical dataset of:

```text
real Stage-9 signal snapshots
+
causal token OHLC coverage
+
explicit venue-specific fee/slippage assumptions
```

Therefore:

```text
paper-trading engine = PASS
experiment contract  = PASS
real A–E comparison  = PENDING DATA
edge claim           = NOT YET MADE
```

The next work item is to populate and replay a real signal/price dataset through this frozen engine.

## 17. Stage 10 Decision

```text
WALLET_STAGE10_PAPER_TRADING_ENGINE = PASS
WALLET_STAGE10_EMPIRICAL_REPLAY = PENDING_REAL_DATA
```

Stage 11 must not begin rule optimization from synthetic unit-test outcomes.

Stage 11 can begin only after real Stage-10 replay results exist.
