# BabaBot Wallet Detector — Stage 6 Meme / Explosion Hunter Discovery

**Status:** IMPLEMENTED / DISCOVERY CONTRACT FROZEN  
**Date:** 2026-09-28  
**Repository:** `bymarfinai/bababot-wallet-detector`

## 1. Objective

Identify wallets that repeatedly enter tokens before large forward price expansions.

Stage 6 is an **orthogonal specialty detector**. It does not change S1/S2/S3.

The core question is:

> Does this wallet repeatedly buy before 2x / 5x / 10x moves, across distinct tokens, with meaningful lead time, rather than merely getting lucky once?

## 2. Two-Sided Evidence Model

Stage 6 uses two complementary views.

### A. Buy-Centric Forward Outcome

Every valid BUY is evaluated against future token price data.

For each BUY:

```text
entry
  ↓
6h / 24h / 72h
  ↓
2x / 5x / 10x
```

This creates a denominator of **eligible buys**, so misses and false positives are measurable.

### B. Explosion-Centric Event Matching

A validated historical explosion catalog can be supplied:

```text
event start
   ↓
wallet BUY
   ↓
explosion trigger
```

All BUYs by the same wallet within one event are collapsed into one wallet-event match.

This measures repeatability and entry lead time against actual explosion events.

## 3. Forward Horizons

Frozen V1 horizons:

```text
6h
24h
72h
```

Frozen V1 return multiples:

```text
2x
5x
10x
```

These correspond to:

- +100%
- +400%
- +900%

## 4. Entry Price

Preferred entry reference:

1. actual wallet execution price when Stage 2 provides a verified USD-stable quote;
2. otherwise the first market-price observation at or after entry within 5 minutes.

No stale pre-entry price is used by default.

If no acceptable price exists:

```text
NO_ENTRY_PRICE
```

and the BUY is excluded from hit-rate denominators.

## 5. Outcome Status

For each multiple × horizon:

### HIT

Threshold was actually observed inside the horizon.

### MISS

Threshold was not observed and the historical price series fully covers the requested horizon.

### INCOMPLETE

No hit was observed, but the historical series ends before the horizon finishes.

This is critical:

```text
truncated data != false negative
```

## 6. False-Positive Accounting

Every bucket exposes:

- eligible buys
- hit buys
- miss buys
- incomplete buys
- buy-level hit rate
- eligible distinct tokens
- hit distinct tokens
- token-level hit rate

Repeated BUYs of the same token do not inflate distinct-token hit counts.

## 7. Lead Time

For every HIT:

```text
lead_seconds = first threshold hit time - wallet entry time
```

Profiles expose:

- median hit lead time
- minimum hit lead time
- maximum hit lead time

Explosion-event matches additionally expose:

- earliest pre-trigger entry
- latest pre-trigger entry
- first-entry lead time
- last-entry lead time

## 8. Explosion Event Schema

Explosion matching requires validated events with:

```text
event_id
token
start_time
trigger_time
threshold_multiple
horizon
```

Rules:

- `trigger_time > start_time`
- `event_id` must be unique
- wallet BUY must satisfy:

```text
start_time <= buy_time < trigger_time
```

Stage 6 intentionally does not invent a noisy universal price-event detector from arbitrary bars.

The buy-centric engine can operate independently from an explosion catalog.

The explosion-centric path accepts a validated catalog when available.

## 9. Multi-Wallet Idempotency

BUY deduplication key:

```text
wallet + transaction signature
```

not signature alone.

This preserves independent tracked-wallet evidence when multiple monitored wallets appear in the same transaction.

## 10. Meme Hunter Label Policy

Stage 6 produces an evidence profile:

```text
label_status = EVIDENCE_PROFILE_ONLY
```

No arbitrary final Meme Hunter threshold is invented yet.

Reason:

A final threshold should be calibrated against the real wallet population, including:

- eligible buy count
- distinct-token hit count
- false-positive rate
- 2x/5x/10x hit distribution
- lead-time distribution
- repeatability across independent explosions

Stage 7 may carry the evidence profile into the registry.

Final production qualification can be frozen after empirical population calibration.

## 11. Implemented Files

- `research/wallet_s6_meme_explosion_hunter.py`
- `tests/test_wallet_s6_meme_explosion_hunter.py`

## 12. Deterministic Coverage

Stage 6 tests cover:

1. 2x / 5x / 10x forward hits
2. incomplete horizon handling
3. full-horizon MISS
4. missing market entry price
5. false-positive denominator
6. repeated BUY token dedup at token level
7. duplicate wallet-signature BUY dedup
8. mixed-wallet profile rejection
9. pre-trigger explosion matching
10. multi-BUY collapse inside one event
11. different wallets matching the same event independently
12. duplicate event-id rejection
13. invalid event-time rejection
14. repeatability across multiple explosion events
15. same signature preserved across different tracked wallets

Stage 6:

```text
15 / 15 PASS
```

Cumulative deterministic inventory:

```text
Stage 1 =  5
Stage 2 =  9
Stage 3 = 11
Stage 4 = 13
Stage 5 = 12
Stage 6 = 15
----------------
TOTAL   = 65 tests
```

GitHub Actions passed the Stage-6 regression suite.

## 13. Stage 6 Decision

```text
WALLET_STAGE6_MEME_EXPLOSION_HUNTER = PASS
```

Next:

```text
Stage 7 — Qualified Wallet Registry
```
