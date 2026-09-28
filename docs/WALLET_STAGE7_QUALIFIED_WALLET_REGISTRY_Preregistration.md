# BabaBot Wallet Detector — Stage 7 Qualified Wallet Registry

**Status:** IMPLEMENTED / REGISTRY CONTRACT FROZEN  
**Date:** 2026-09-28  
**Repository:** `bymarfinai/bababot-wallet-detector`

## 1. Objective

Stage 7 converts Stage 4/5/6 outputs into one durable operational wallet registry.

The registry is the boundary between historical qualification and Stage 8 live monitoring.

Stage 7 does **not** introduce a new scoring model.

## 2. Eligibility Rule

Live-monitor eligibility is inherited strictly from Stage 5.

```text
Stage 5 QUALIFIED
    ↓
registry_status = ACTIVE
live_monitor_eligible = true
```

```text
Stage 5 UNQUALIFIED
    ↓
registry_status = UNQUALIFIED
live_monitor_eligible = false
```

```text
Stage 5 NOT_READY
    ↓
registry_status = NOT_READY
live_monitor_eligible = false
```

Stage 6 Meme / Explosion Hunter evidence is metadata only in V1.

It cannot promote an unqualified wallet into ACTIVE.

## 3. Required Provenance

An ACTIVE wallet must have an available Stage-4 performance source.

Registry creation rejects a QUALIFIED Stage-5 record without corresponding Stage-4 provenance.

This prevents manually fabricated classification payloads from silently entering Stage 8.

## 4. Wallet Identity Integrity

All supplied sources must point to the same wallet:

- Stage 4 performance
- Stage 5 classification
- Stage 6 Meme Hunter profile
- Stage 6 explosion match profile

A mismatch raises an error.

Wallet syntax is validated using the frozen Solana address validator.

## 5. Source Version Compatibility

Frozen V1 compatibility:

```text
Stage 4 = wallet-s4-v1
Stage 5 = wallet-s5-v1
Stage 6 = wallet-s6-v1
Stage 7 = wallet-s7-v1
```

Unexpected source schema versions are rejected instead of being silently interpreted.

## 6. Registry Record

Each wallet record contains:

- chain
- wallet address
- registry status
- live-monitor eligibility
- eligibility reason
- primary S1/S2/S3 segment
- all qualifying segments
- Stage-5 classification snapshot
- compact Stage-4 performance summary
- compact Stage-6 Meme Hunter evidence
- special-label state
- source versions
- deterministic record fingerprint

## 7. Meme Hunter Evidence

The registry preserves Stage-6 evidence including:

- evaluated BUY count
- distinct tokens
- eligible/hit/miss/incomplete counts
- buy hit rates
- token hit rates
- lead-time summaries
- matched explosion event count
- matched distinct explosion tokens

Current special-label state remains:

```text
EVIDENCE_PROFILE_ONLY
```

until population calibration freezes a final Meme Hunter threshold.

## 8. Fingerprint Integrity

Every record has:

```text
record_fingerprint = SHA256(canonical registry record)
```

Snapshot building and upsert operations recompute the fingerprint.

Therefore:

```text
payload changed
+ old fingerprint retained
→ rejected
```

This gives Stage 8 a deterministic tamper/integrity check.

## 9. Registry Snapshot

`build_registry_snapshot` creates an immutable logical snapshot containing:

- snapshot id
- record count
- active wallet count
- sorted active wallet list
- status counts
- segment counts
- sorted registry records
- deterministic snapshot fingerprint

Input order does not change the snapshot fingerprint.

Duplicate wallet identities are rejected.

## 10. Stage-8 Consumption Contract

Stage 8 should subscribe only to:

```text
snapshot.active_wallets
```

and use the matching ACTIVE registry records for metadata.

No UNQUALIFIED or NOT_READY wallet should enter the live subscription set.

## 11. Upsert Behavior

Registry identity is the wallet address.

`upsert_registry_records`:

- replaces an existing wallet record with the newest supplied record
- never creates duplicate wallet identities
- validates record version
- verifies record fingerprint
- returns deterministic wallet ordering

Example:

```text
Wallet A ACTIVE
        ↓ re-evaluation
Wallet A UNQUALIFIED
        ↓
one Wallet A record remains
status = UNQUALIFIED
```

## 12. No New Ranking Layer

Stage 7 intentionally does not add:

- wallet score
- priority score
- AI rank
- manual promotion rule
- Meme Hunter auto-promotion
- Whale auto-promotion

Those require separate evidence and belong to later validation/optimization.

## 13. Deterministic Test Coverage

Stage 7 tests cover:

1. QUALIFIED → ACTIVE
2. UNQUALIFIED exclusion
3. NOT_READY reason preservation
4. Stage-6 evidence cannot promote wallet
5. compact Meme Hunter evidence
6. Stage-4 identity mismatch
7. Stage-6 identity mismatch
8. invalid segment structure
9. unsupported classification status
10. deterministic record fingerprint
11. fingerprint changes with classification
12. active-wallet snapshot filtering
13. deterministic snapshot ordering
14. duplicate-wallet snapshot rejection
15. wallet upsert replacement
16. source-version preservation
17. ACTIVE requires Stage-4 provenance
18. tampered record rejection
19. source-version mismatch rejection

Final result:

```text
Stage 7 = 19 / 19 PASS
```

Cumulative regression inventory:

```text
Stage 1 =  5
Stage 2 =  9
Stage 3 = 11
Stage 4 = 13
Stage 5 = 12
Stage 6 = 15
Stage 7 = 19
----------------
TOTAL   = 84 tests
```

GitHub Actions passed the final Stage-7 integrity suite.

## 14. Stage 7 Decision

```text
WALLET_STAGE7_QUALIFIED_WALLET_REGISTRY = PASS
```

Next:

```text
Stage 8 — Live Wallet Monitor
```
