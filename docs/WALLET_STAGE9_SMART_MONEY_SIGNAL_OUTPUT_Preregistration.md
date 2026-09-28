# BabaBot Wallet Detector — Stage 9 Smart-Money Signal Output

**Status:** IMPLEMENTED / SIGNAL CONTRACT FROZEN  
**Date:** 2026-09-28  
**Repository:** bymarfinai/bababot-wallet-detector

## 1. Objective

Stage 9 converts factual Stage-8 qualified-wallet activity into a clean external smart-money signal contract.

It answers:

```text
What token is qualified smart money accumulating or distributing?
How many independent qualified wallets participate?
Which performance tiers participate?
Is validated USD flow available and does it agree?
How fresh is the activity?
Is activity actually persistent over time?
What Stage-6 Meme Hunter evidence accompanies the contributors?
```

Stage 9 remains descriptive.

It does not decide whether to enter a trade.

## 2. Input Boundary

Stage 9 consumes Stage-8 normalized live events.

Only events satisfying:

```text
event_type = SWAP
side = BUY or SELL
wallet present
base asset present
block time present
```

are eligible.

Only the trailing 1H universe is used in one signal snapshot.

Future events and events older than the 1H boundary are excluded.

## 3. Signal State

The external state is:

```text
ACCUMULATION
DISTRIBUTION
NEUTRAL
```

Stage-8 BALANCED maps to Stage-9 NEUTRAL.

The state is derived from net base-token flow in the freshest active rolling window:

```text
5m if available
else 15m
else 1h
```

The exact basis window is always included as state_basis_window.

No validated USD value overrides the base-flow state.

If base flow and validated USD flow disagree, both facts remain visible for Stage-10/11 testing.

## 4. Qualified-Wallet Breadth

Every signal exposes, on its state-basis window:

- unique qualified wallet count
- unique BUY wallet count
- unique SELL wallet count
- BUY minus SELL wallet count
- performance-tier membership counts

Performance-tier membership remains overlapping.

A wallet belonging to S1 + S2 contributes to both membership counters.

The contract is generic and can carry future S4/S5 membership when Stage-11 classification support is implemented.

Stage 9 does not claim that S4/S5 are currently live.

## 5. USD Flow Safety

Validated USD output includes:

```text
COMPLETE
PARTIAL
UNAVAILABLE
```

### COMPLETE

Every event in the basis window has a validated Stage-8 USD notional.

### PARTIAL

At least one event is directly USD-priced and at least one remains unpriced.

### UNAVAILABLE

No event has a validated USD notional.

Stage 9 never invents USD conversion for SOL or another unpriced quote.

The contract exposes:

- validated USD BUY notional
- validated USD SELL notional
- validated USD net notional
- priced event count
- unpriced event count
- POSITIVE / NEGATIVE / FLAT / UNAVAILABLE direction

## 6. Freshness

Freshness is anchored to the real last on-chain block time.

Output:

- last activity time
- exact age in seconds
- freshness bucket

Buckets are tied to the existing Stage-8 windows:

```text
age < 5m   → WITHIN_5M
age < 15m  → WITHIN_15M
age < 1h   → WITHIN_1H
```

This avoids adding an arbitrary freshness score.

## 7. Rolling-Window Agreement vs True Temporal Persistence

Stage 9 explicitly separates two concepts.

### Rolling-window agreement

The 5m / 15m / 1h windows are nested.

A single event two minutes ago appears in all three windows.

Therefore identical 5m / 15m / 1h states do not prove one hour of persistence.

Stage 9 reports rolling-window states and directional agreement, but does not call that temporal persistence by itself.

### Exact non-overlapping time bands

Stage 9 also evaluates:

```text
0–5m
5–15m
15–60m
```

These bands do not overlap.

Directional persistence fields are only true when matching directional activity exists in separate historical bands:

```text
spans_15m_directionally
spans_1h_directionally
```

For example:

```text
one BUY 2 minutes ago
→ 5m / 15m / 1h rolling states may all say ACCUMULATION
→ spans_15m_directionally = false
→ spans_1h_directionally = false
```

This prevents nested windows from creating false persistence evidence.

## 8. Contributors

Every signal preserves distinct contributing wallets over the trailing 1H.

Per contributor:

- wallet address
- BUY / SELL side(s)
- event count
- latest activity time
- observed primary tier(s)
- all qualifying tier memberships
- Stage-6 Meme Hunter label-status evidence
- historical matched explosion events
- historical matched explosion token count
- registry snapshot provenance

Repeated events from one wallet do not create duplicate contributor identities.

A wallet may correctly appear with both BUY and SELL sides if it traded both directions in the period.

## 9. Meme Hunter Evidence

Stage 6 is currently evidence-only, not a calibrated standalone specialty qualification.

Therefore Stage 9 deliberately exposes:

```text
meme evidence wallet count
Stage-6 label-status counts
historical explosion-event matches
historical explosion-token matches
calibration_status = EVIDENCE_ONLY_STAGE6_V1
```

Stage 9 does not manufacture a final meme_hunter_wallet_count.

This prevents EVIDENCE_PROFILE_ONLY from being misrepresented as a calibrated Meme Hunter label.

## 10. Registry Provenance

Stage-8 events preserve the Stage-7 registry snapshot that qualified the wallet at event time.

Stage 9 exposes:

- contributing registry snapshot IDs
- contributing registry snapshot fingerprints
- whether multiple snapshot IDs are present
- whether multiple snapshot fingerprints are present

Policy:

```text
EVENT_TIME_QUALIFICATION_PROVENANCE
```

A registry refresh does not silently rewrite the historical qualification provenance of an already accepted live event.

## 11. No Strength Score

Frozen Stage-9 policy:

```text
strength_score = null
entry_rule = null
descriptive_only = true
```

No arbitrary 0–100 score, weighted tier score, or TAKE/SKIP rule exists yet.

Stage 10 paper trading and Stage 11 validation must determine which factual conditions create edge.

## 12. Independent Handoff

Stage 9 produces:

```text
SMART_MONEY_SIGNAL_SNAPSHOT
```

with:

- schema version
- chain
- as-of timestamp
- per-token signals
- deterministic signal fingerprint
- deterministic snapshot fingerprint

The snapshot is JSON serializable through:

```text
serialize_signal_snapshot(...)
```

This is the clean external boundary for:

- Stage-10 wallet-only paper trading
- dashboard / alerts
- manual workflows
- optional future Market Radar / MCD consumer
- future fusion layer

No consumer is required for Stage 9 itself to work.

## 13. Stage-8 Specialty Handoff Hardening

Stage 8 was minimally extended so accepted live events now preserve:

- meme_hunter_evidence
- special_labels

The persistence-row contract preserves the same fields.

No Stage-8 BUY/SELL definition or aggregation rule was changed.

## 14. Deterministic Test Coverage

Stage 9 adds 24 tests covering:

1. accumulation state
2. distribution state
3. balanced → neutral mapping
4. exact 5m freshness boundary
5. >1H exclusion
6. future-event exclusion
7. nested-window false-persistence prevention
8. true 15m directional persistence
9. true 1H directional persistence
10. partial USD coverage
11. unavailable USD coverage
12. base-flow / USD-flow disagreement preservation
13. overlapping S1/S2 membership
14. generic future S4/S5 pass-through
15. repeated-event contributor deduplication
16. one contributor trading both sides
17. distinct-wallet Meme evidence aggregation
18. evidence-only specialty policy
19. mixed registry snapshot provenance
20. deterministic signal/snapshot fingerprints
21. absence of strength score / entry rule
22. JSON handoff round trip
23. independent multi-token signals
24. neutral signals cannot claim directional persistence

Stage 8 also adds one regression proving specialty evidence survives live-event and persistence-row construction.

Current Python regression:

```text
Ran 139 tests
OK
```

Breakdown of new coverage:

```text
Stage 8 specialty handoff hardening = 1 test
Stage 9 signal output              = 24 tests
```

GitHub Actions also passed the existing Next.js typecheck, production build, and smoke test.

## 15. Stage 9 Decision

```text
WALLET_STAGE9_SMART_MONEY_SIGNAL_OUTPUT = PASS
```

Next:

```text
Stage 10 — Wallet-Only Paper Trading
```
