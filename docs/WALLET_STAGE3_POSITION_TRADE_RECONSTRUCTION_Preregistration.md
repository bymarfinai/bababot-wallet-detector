# BabaBot Wallet Detector — Stage 3 Position / Trade Reconstruction

**Status:** IMPLEMENTED / RECONSTRUCTION CONTRACT FROZEN  
**Date:** 2026-09-28  
**Repository:** `bymarfinai/bababot-wallet-detector`

## 1. Objective

Transform Stage-2 normalized wallet BUY/SELL events into real trading episodes.

Critical rule:

```text
BUY 10
BUY 20
BUY 30
SELL 15
SELL 45
```

is **one trading episode**, not five independent trades.

Stage 3 exists to prevent fake win-rate and ROI statistics caused by transaction-level counting.

## 2. Cost Basis

V1 uses **weighted-average cost**.

For every BUY:

```text
open_qty        += buy_qty
open_cost_quote += quote_spent
avg_cost         = open_cost_quote / open_qty
```

For every partial SELL:

```text
realized_cost     = avg_cost × sold_qty
realized_proceeds = actual quote received
realized_pnl      = realized_proceeds - realized_cost
```

The remaining inventory keeps the same weighted-average unit cost.

## 3. Episode Boundary

A clean episode:

```text
first BUY
   ↓
one or more BUY / partial SELL
   ↓
tracked open quantity reaches zero
   ↓
CLOSED
```

A later BUY after a full close starts a **new episode**.

Episode identity is deterministic by:

```text
wallet + base_asset + quote_asset + sequence
```

## 4. Quote Consistency

Positions are tracked by `base_asset + quote_asset`.

If the same fungible token is simultaneously accumulated with different quote assets, for example:

```text
BUY TOKEN with USDC
BUY TOKEN with SOL
```

both open positions are marked:

```text
MIXED_QUOTE_INVENTORY
```

and become ineligible for clean performance scoring.

Reason: the inventory is fungible and Stage 3 cannot truthfully know which quote-denominated lot a later sell consumed without additional cost normalization.

## 5. External Transfers

### TRANSFER_IN during an open position

The token may have arrived with unknown acquisition cost.

Result:

```text
TRANSFER_IN_DURING_POSITION
eligible_for_performance_metrics = false
```

The external quantity is not assigned a fabricated zero cost.

### TRANSFER_OUT during an open position

Tracked inventory is reduced at its weighted-average cost, but:

- no realized PnL is created;
- episode is contaminated;
- if all tracked inventory leaves, status becomes `TRANSFERRED_OUT`.

This prevents wallet-to-wallet movements from being treated as profitable sales.

## 6. Orphan Sell

If a SELL exists without a tracked matching BUY position:

```text
ORPHAN_SELL
```

No synthetic entry price is invented and no episode is created.

This can happen when:

- history begins after the original acquisition;
- inventory came from another wallet;
- a previous transaction was unresolved.

## 7. Oversell

If sell quantity exceeds tracked open quantity:

- only the known tracked quantity is costed;
- proceeds are prorated to the covered quantity;
- excess becomes `OVERSELL`;
- episode is `CLOSED_CONTAMINATED`;
- episode is excluded from performance scoring.

## 8. Causal Ordering and Idempotency

Input is ordered by:

```text
block_time
→ slot
→ original stable input order
```

Duplicate Solana signatures are ignored and recorded as:

```text
DUPLICATE_SIGNATURE
```

Stage 2 currently emits one normalized wallet event per transaction, therefore transaction signature is sufficient for V1 deduplication.

## 9. Episode Outputs

Every episode exposes:

- wallet
- base asset
- quote asset
- status
- open/close timestamp
- open/close slot
- holding seconds
- open quantity
- open cost
- weighted average entry
- total buy quantity/cost
- total sell quantity/proceeds
- average exit
- realized cost
- realized proceeds
- realized PnL
- realized ROI %
- BUY count
- SELL count
- accumulated network fee lamports
- transaction signatures
- contamination reasons
- `eligible_for_performance_metrics`

## 10. Performance Eligibility

Only an episode satisfying all of these is clean:

```text
status = CLOSED
no contamination reason
buy quantity > 0
sell quantity > 0
remaining tracked quantity = 0
```

Then:

```text
eligible_for_performance_metrics = true
```

Stage 4 must use this clean set for baseline wallet statistics.

## 11. Fee Interpretation

Stage 3 preserves accumulated `network_fee_lamports`, but does **not** pretend those SOL fees are already denominated in the episode quote currency.

Therefore Stage-3 `realized_pnl_quote` and `realized_roi_pct` are execution-level metrics.

Stage 4 is responsible for historical fee conversion / net performance policy before S1/S2/S3 qualification.

## 12. Implemented Files

- `research/wallet_s3_position_reconstruction.py`
- `tests/test_wallet_s3_position_reconstruction.py`

## 13. Deterministic Tests

Stage 3 covers:

1. multiple BUY + partial SELL + full close = one episode
2. partial SELL preserves weighted average cost
3. full close then later BUY creates a new episode
4. orphan SELL is rejected
5. transfer-in contamination
6. transfer-out inventory reduction without fake PnL
7. oversell contamination
8. mixed quote contamination on both positions
9. causal sorting
10. duplicate signature deduplication
11. non-trade events ignored

Result:

```text
Stage 3 tests = 11 / 11 PASS
```

Previously frozen Stage 1–2 regression coverage remains:

```text
Stage 1 = 5 / 5 PASS
Stage 2 = 9 / 9 PASS
```

Cumulative deterministic coverage:

```text
25 tests
25 PASS
0 FAIL
```

## 14. Stage 3 Decision

```text
WALLET_STAGE3_POSITION_TRADE_RECONSTRUCTION = PASS
```

Next:

```text
Stage 4 — Historical Wallet Performance Engine
clean closed episodes
        ↓
median ROI
win rate
realized PnL
profit factor
drawdown
holding time
activity consistency
sample size
        ↓
wallet performance profile
```
