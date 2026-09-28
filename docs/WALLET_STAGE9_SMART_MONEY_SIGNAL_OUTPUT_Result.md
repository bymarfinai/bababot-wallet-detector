# BabaBot Wallet Detector — Stage 9 Smart-Money Signal Output — Result

**Date:** 2026-09-28  
**Repository:** bymarfinai/bababot-wallet-detector

## Result

```text
WALLET_STAGE9_SMART_MONEY_SIGNAL_OUTPUT = PASS
```

Wallet Detector now has an independent factual smart-money signal contract.

## Output Example

Conceptually, a token signal now looks like:

```text
base_asset              <mint>
state                   ACCUMULATION
state_basis_window      5m

qualified wallets
  unique                7
  BUY                   6
  SELL                  1

validated USD flow
  coverage              PARTIAL
  net                    +...
  direction              POSITIVE

freshness
  age_seconds            ...
  bucket                 WITHIN_5M

rolling windows
  5m                     ACCUMULATION
  15m                    ACCUMULATION
  1h                     ACCUMULATION

true temporal bands
  0-5m                   ACCUMULATION
  5-15m                  ACCUMULATION
  15-60m                 NEUTRAL

spans 15m               true
spans 1h                false
```

The key distinction is that rolling-window agreement and actual temporal persistence are not conflated.

## No Entry Rule Yet

Stage 9 intentionally outputs:

```text
strength_score = null
entry_rule = null
```

A token is not declared a trade merely because qualified wallets are accumulating it.

Stage 10 will test candidate wallet-only entry rules with TP +1% / SL -1%.

## Meme Hunter Handling

Stage-6 evidence is carried into the signal by distinct contributing wallet.

Current Stage-6 state remains:

```text
EVIDENCE_PROFILE_ONLY
```

Stage 9 does not turn this into a calibrated Meme Hunter qualification.

## Provenance

Signals preserve event-time registry snapshot provenance.

If contributing events came from multiple Stage-7 registry snapshots, that fact is exposed instead of hidden.

## External Boundary

Every signal and signal snapshot receives a deterministic fingerprint.

The complete snapshot can be emitted as JSON without a dependency on Market Radar / MCD.

## Verification

Latest Python regression:

```text
Ran 139 tests
OK
```

Stage 9 additions:

```text
24 / 24 PASS
```

Stage-8 specialty handoff regression:

```text
1 / 1 PASS
```

Existing dashboard CI also remains green:

```text
TypeScript = PASS
Next.js build = PASS
Production smoke = PASS
```

## Next Stage

```text
Stage 10 — Wallet-Only Paper Trading
```

Stage 10 will measure whether these factual wallet signals create independent tradable edge before any optional external fusion.
