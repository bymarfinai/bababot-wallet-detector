# BabaBot Wallet Detector — Stage 8 Live Wallet Monitor — Result

**Date:** 2026-09-28  
**Repository:** `bymarfinai/bababot-wallet-detector`

## Result

```text
WALLET_STAGE8_LIVE_WALLET_MONITOR = PASS
```

The repository now has a provider-neutral live wallet monitoring core.

## Live Path

```text
Qualified Registry
      ↓
ACTIVE wallets
      ↓
subscription plan
      ↓
new Solana transaction
      ↓
wallet touch detection
      ↓
Stage-2 normalization
      ↓
idempotent live event
      ↓
5m / 15m / 1h aggregation
```

## At-Least-Once Safety

Canonical live idempotency:

```text
wallet + signature
```

Repeated webhook delivery does not double-count activity.

A single transaction touching two monitored wallets correctly creates two wallet-level events.

## Rolling Smart-Money Output

For each token mint:

```text
BUY events / SELL events
BUY wallets / SELL wallets
unique wallets
net base flow
USD buy/sell notional when valid
priced vs unpriced event coverage
S1/S2/S3 membership activity
last activity time / slot
```

Descriptive flow state:

```text
ACCUMULATION
DISTRIBUTION
BALANCED
```

No arbitrary signal score was added.

## Currency Safety

SOL-quoted trades remain visible as wallet activity but do not receive invented USD notional.

Only directly validated USD-notional events contribute to USD aggregation.

## Registry Refresh

A wallet removed from ACTIVE status stops generating new live events after snapshot refresh.

This allows Stage-7 historical re-evaluation to control the live subscription universe without duplicating qualification logic in Stage 8.

## Storage Contract

Stage 8 emits storage-neutral rows with:

```text
idempotency_key = wallet:signature
```

Production database requirement:

```text
UNIQUE(wallet, signature)
```

The in-memory engine used by deterministic tests is not presented as durable production persistence.

## Regression Result

```text
Stage 1 =  5 /  5
Stage 2 =  9 /  9
Stage 3 = 11 / 11
Stage 4 = 13 / 13
Stage 5 = 12 / 12
Stage 6 = 15 / 15
Stage 7 = 19 / 19
Stage 8 = 21 / 21
-------------------
TOTAL   = 105 / 105 PASS
```

GitHub Actions final Stage-8 implementation run:

```text
Ran 105 tests
OK
```

## Runtime Status

Implementation is complete, but no external live webhook is claimed yet.

Pending runtime activation:

- public authenticated receiver endpoint
- real Helius webhook provisioning
- durable event persistence
- end-to-end mainnet delivery probe

These require deployment/provider credentials.

## Next Stage

```text
Stage 8.5 — Vercel Dashboard / UI
```

The UI can now be built against a stable live-data contract instead of mock dashboard assumptions.
