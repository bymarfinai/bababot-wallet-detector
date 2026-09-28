# BabaBot Wallet Detector — Stage 3 Position / Trade Reconstruction — Result

**Date:** 2026-09-28  
**Repository:** `bymarfinai/bababot-wallet-detector`

## Result

```text
WALLET_STAGE3_POSITION_TRADE_RECONSTRUCTION = PASS
```

Stage 3 now reconstructs transaction streams into actual wallet trading episodes.

## Core Example

Input:

```text
BUY  10 TOKEN for 10 USDC
BUY  20 TOKEN for 24 USDC
BUY  30 TOKEN for 42 USDC
SELL 15 TOKEN for 21 USDC
SELL 45 TOKEN for 67.5 USDC
```

Output:

```text
episodes            = 1
BUY count           = 3
SELL count          = 2
total bought        = 60 TOKEN
total entry cost    = 76 USDC
total exit proceeds = 88.5 USDC
realized PnL        = +12.5 USDC
realized ROI        = +16.447368421...%
status              = CLOSED
eligible            = true
```

This is the behavior required by the Wallet Detector concept: multiple blockchain transactions forming one economic position are not counted as independent trades.

## Conservative Data Policy

Stage 3 refuses to manufacture performance when inventory provenance is uncertain.

Automatically excluded from clean wallet scoring:

- orphan sells
- token transfer-in during an open position
- token transfer-out episodes
- oversells
- simultaneous mixed-quote inventory
- unresolved external-flow situations

These remain auditable through anomaly and contamination labels.

## Output Buckets

```text
episodes
terminal_episodes
open_positions
scorable_closed_episodes
anomalies
```

Stage 4 should build baseline wallet-performance statistics primarily from:

```text
scorable_closed_episodes
```

## Test Result

```text
Stage 1 =  5 /  5 PASS
Stage 2 =  9 /  9 PASS
Stage 3 = 11 / 11 PASS
--------------------------
TOTAL   = 25 deterministic tests
PASS    = 25
FAIL    = 0
```

Stage 3 tests were executed against the same implementation content committed to the repository.

## Next Stage

```text
Stage 4 — Historical Wallet Performance Engine
```

The project can now calculate wallet performance from reconstructed **episodes**, rather than raw transactions.
