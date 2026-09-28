# BabaBot Wallet Detector — Stage 8 Live Wallet Monitor

**Status:** IMPLEMENTED / LIVE CORE CONTRACT FROZEN  
**Date:** 2026-09-28  
**Repository:** `bymarfinai/bababot-wallet-detector`

## 1. Objective

Stage 8 turns the Stage-7 ACTIVE wallet registry into a real-time smart-money activity stream.

```text
Stage-7 Registry Snapshot
        ↓
ACTIVE wallets only
        ↓
provider subscription
        ↓
new Solana transaction
        ↓
Stage-2 normalization
        ↓
wallet BUY / SELL / non-trade event
        ↓
idempotent live event store
        ↓
5m / 15m / 1h rolling aggregation
        ↓
per-token smart-money activity
```

Stage 8 does not re-run historical wallet qualification.

## 2. Registry Boundary

The live monitor accepts only a complete Stage-7 snapshot that passes integrity verification.

Before subscription:

- snapshot version is checked
- every record fingerprint is checked
- snapshot fingerprint is recomputed
- ACTIVE wallet list must match ACTIVE records exactly

A tampered registry snapshot is rejected.

## 3. Live Subscription Plan

Stage 8 builds a provider-neutral subscription manifest from:

```text
snapshot.active_wallets
```

Current preferred transport:

```text
provider  = Helius
transport = Raw Webhook
```

Reason:

- Wallet Detector needs all transactions touching qualified wallets.
- Parsing remains inside the deterministic Stage-1/2 pipeline.
- Transport can later be replaced by LaserStream / WebSocket / another provider without changing the core live engine.

The provider limit is configurable. The current Helius-oriented default is:

```text
100,000 account addresses per subscription batch
```

No provider API key or webhook auth secret is stored in the repository.

## 4. Delivery Security Contract

Production receiver requirements:

```text
authenticated webhook request
        ↓
provider adapter
        ↓
standard Solana transaction shape
        ↓
LiveWalletMonitor
```

The subscription manifest marks authentication-header verification as required.

Transport auth belongs to the HTTP receiver/deployment layer, not the deterministic monitor core.

## 5. At-Least-Once Idempotency

Webhook/stream delivery may be repeated.

Canonical V1 key:

```text
wallet + transaction signature
```

One Solana transaction may legitimately affect multiple tracked wallets:

```text
Wallet A + same signature
Wallet B + same signature
```

are two independent live wallet events.

A replay for the same:

```text
Wallet A + same signature
```

is rejected as duplicate.

Normalization failures do not consume the idempotency key, so a corrected/retried payload can succeed later.

## 6. Wallet-Touch Detection

A monitored wallet is considered touched when it appears in:

1. transaction account keys; or
2. pre/post token-balance ownership metadata.

This avoids missing wallet token activity when token-account ownership is visible even if the owner address is not a direct account-key entry.

## 7. Normalization

Every touched ACTIVE wallet is normalized independently through Stage 2.

Stage 8 preserves:

- signature
- slot
- block time
- event type
- BUY / SELL / NONE
- base mint
- quote mint
- base amount
- quote amount
- USD notional when directly valid
- Stage-7 registry record fingerprint
- primary segment
- all qualifying S1/S2/S3 segment memberships
- registry snapshot provenance
- optional receiver timestamp

No live parser creates a second, conflicting BUY/SELL definition.

## 8. Stored Events

The deterministic reference core retains all accepted normalized events, including non-trade audit events.

Rolling smart-money aggregation uses only:

```text
event_type = SWAP
side = BUY or SELL
```

Production persistence contract should enforce:

```text
UNIQUE(wallet, signature)
```

Stage 8 exposes `live_event_to_persistence_row` so the storage implementation is not coupled to the analytics engine.

The in-process event list is a reference/runtime core, not a claim that process memory is sufficient durable production storage.

## 9. Rolling Windows

Frozen V1 windows:

```text
5m
15m
1h
```

For snapshot time `T`, a trailing window is:

```text
(T - window, T]
```

The lower boundary is exclusive and the upper boundary is inclusive.

Aggregation always uses on-chain `block_time`, not delivery arrival order.

Late or out-of-order delivery therefore remains analytically correct after ingestion.

## 10. Per-Token Live Metrics

For every token mint and rolling window:

- trade event count
- BUY event count
- SELL event count
- unique active wallet count
- unique BUY wallet count
- unique SELL wallet count
- BUY minus SELL wallet count
- total base-token BUY amount
- total base-token SELL amount
- net base-token flow
- directly USD-priced event count
- unpriced event count
- USD BUY notional
- USD SELL notional
- net USD notional
- quote assets observed
- segment-membership wallet counts
- latest activity block time
- latest slot

## 11. Flow State

No arbitrary smart-money score is introduced.

Per token:

```text
net base flow > 0  → ACCUMULATION
net base flow < 0  → DISTRIBUTION
net base flow = 0  → BALANCED
```

This is a descriptive state, not an entry signal.

Stage 9 is responsible for combining wallet activity with Market Radar.

## 12. USD Safety

Only Stage-2 events carrying a valid `usd_notional` contribute to USD notional metrics.

Example:

```text
USDC quote → USD notional included
SOL quote  → event counted, USD notional not invented
```

Therefore:

```text
usd_priced_event_count
unpriced_event_count
```

remain visible.

## 13. Segment Activity

Stage 8 preserves overlapping S1/S2/S3 membership.

A wallet that belongs to:

```text
S1 + S2
```

is represented in both membership counters.

These counters are explicitly named membership counts and are not expected to sum to unique wallet count.

## 14. Registry Refresh

The monitor can accept a new integrity-verified Stage-7 snapshot.

If:

```text
Wallet A ACTIVE
        ↓ historical re-evaluation
Wallet A UNQUALIFIED
```

then future Wallet-A transactions are ignored after registry refresh.

Previously accepted historical live events remain auditable.

## 15. Operational Health

Stage 8 exposes:

- active wallet count
- active wallet list
- registry snapshot id/fingerprint
- ingest attempts
- seen wallet-signature count
- stored event count
- stored trade-event count
- duplicate count
- normalization-error count
- latest observed block time

## 16. Event Pruning

Old in-process event payloads can be pruned by block-time cutoff.

The idempotency set remains intact, so pruning does not allow an old webhook replay to be re-ingested.

Durable production storage should retain its unique idempotency key independently of rolling analytics retention.

## 17. Implemented Files

- `research/wallet_s8_live_monitor.py`
- `tests/test_wallet_s8_live_monitor.py`

Stage 7 was minimally extended with:

- `verify_registry_snapshot`

so Stage 8 can validate the complete registry artifact before subscribing.

## 18. Deterministic Test Coverage

Stage 8 tests cover:

1. ACTIVE-only subscription batching
2. tampered snapshot rejection
3. account-key wallet touch detection
4. token-owner wallet touch detection
5. normalized/enriched active-wallet BUY
6. one transaction touching two ACTIVE wallets
7. duplicate delivery idempotency
8. missing-signature handling
9. inactive/non-registry wallet exclusion
10. normalization-error retry safety
11. batch delivery counters
12. rolling-window boundary
13. event count vs distinct-wallet count
14. directional BUY/SELL flow
15. SOL/unpriced trade safety
16. overlapping segment membership
17. out-of-order block-time aggregation
18. registry refresh / deactivation
19. storage-neutral persistence row
20. pruning without losing replay protection
21. monitor operational counters

Result:

```text
Stage 8 = 21 / 21 PASS
```

Cumulative deterministic regression:

```text
Stage 1 =  5
Stage 2 =  9
Stage 3 = 11
Stage 4 = 13
Stage 5 = 12
Stage 6 = 15
Stage 7 = 19
Stage 8 = 21
----------------
TOTAL   = 105 tests
```

GitHub Actions:

```text
Ran 105 tests
OK
```

## 19. External Runtime Activation

The deterministic Stage-8 core is complete.

Not yet executed in this repository session:

- creation of a real Helius webhook
- deployment of a public authenticated receiver endpoint
- persistent production database
- real-wallet end-to-end webhook delivery probe

Those require deployment credentials / endpoint configuration and are intentionally not faked in unit tests.

The live core and persistence contract are ready for that activation.

## 20. Stage 8 Decision

```text
WALLET_STAGE8_LIVE_WALLET_MONITOR = PASS
runtime_activation = PENDING_DEPLOYMENT
```

Next:

```text
Stage 8.5 — Vercel Dashboard / UI
```
