# BabaBot Wallet Detector — Stage 7 Qualified Wallet Registry — Result

**Date:** 2026-09-28  
**Repository:** `bymarfinai/bababot-wallet-detector`

## Result

```text
WALLET_STAGE7_QUALIFIED_WALLET_REGISTRY = PASS
```

Wallet Detector now has a deterministic registry boundary between historical research and live monitoring.

## Operational Rule

```text
Stage 5 QUALIFIED
→ ACTIVE
→ Stage 8 may monitor

Stage 5 UNQUALIFIED
→ excluded

Stage 5 NOT_READY
→ excluded
```

Stage-6 Meme Hunter evidence is attached but cannot override Stage-5 eligibility.

## Registry Record

Each wallet now carries:

```text
wallet
chain
registry_status
live_monitor_eligible
eligibility_reason

primary_segment
qualifying_segments

classification snapshot
performance summary
Meme Hunter evidence

source versions
record fingerprint
```

## Integrity Hardening

Two production-grade gates were added before PASS:

### Provenance gate

An ACTIVE wallet must include an available Stage-4 performance source.

### Fingerprint verification

Snapshot and upsert operations recalculate the deterministic record fingerprint.

Tampered records are rejected.

## Snapshot

Stage 7 can produce:

```text
snapshot_id
record_count
active_wallet_count
active_wallets
status_counts
segment_counts
records
snapshot_fingerprint
```

The same logical records generate the same fingerprint regardless of input ordering.

## Upsert

Wallet address is the canonical registry identity.

A new record replaces the old record for that wallet rather than creating duplicates.

This supports periodic historical re-evaluation before live subscription refresh.

## CI Finding During Development

GitHub Actions correctly caught an invalid Solana test fixture address during the first full Stage-7 suite.

The fixture was corrected; no production registry rule was weakened.

A second hardening pass then added:

- Stage-4 provenance requirement
- source-version validation
- fingerprint recomputation

Final full regression:

```text
Stage 1 =  5 /  5
Stage 2 =  9 /  9
Stage 3 = 11 / 11
Stage 4 = 13 / 13
Stage 5 = 12 / 12
Stage 6 = 15 / 15
Stage 7 = 19 / 19
-------------------
TOTAL   = 84 / 84 PASS
```

## Stage-8 Handoff

Stage 8 now has a clean subscription contract:

```text
Qualified Registry Snapshot
        ↓
active_wallets
        ↓
Live Solana Wallet Monitor
```

No classification logic needs to be duplicated inside the live monitor.

## Next Stage

```text
Stage 8 — Live Wallet Monitor
```
