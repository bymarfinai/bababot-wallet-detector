# BabaBot Wallet Detector — Stage 8.5 Vercel Dashboard / UI

**Status:** IMPLEMENTED / UI CONTRACT FROZEN  
**Date:** 2026-09-28  
**Repository:** bymarfinai/bababot-wallet-detector

## 1. Objective

Stage 8.5 provides the operational command center between the Stage-8 live monitor and Stage-9 Market Radar integration.

The UI answers:

```text
Which qualified wallets are active?
What are they buying / selling?
Which token mints are accumulating or distributing?
What is happening over 5m / 15m / 1h?
Is the live monitor healthy?
```

The dashboard does not invent a new trading signal.

## 2. Architecture

```text
Stage 7 Qualified Registry
        +
Stage 8 Live Monitor
        ↓
Stage 8.5 dashboard contract adapter
        ↓
runtime dashboard endpoint
        ↓
Next.js server-side adapter
        ↓
Vercel Dashboard / UI
```

The Python adapter is research/wallet_s8_5_dashboard_contract.py.

The Next.js dashboard is provider/backend agnostic and reads a single JSON contract.

## 3. Dashboard Runtime Modes

The dashboard explicitly exposes one of:

```text
LIVE
DEMO
OFFLINE
```

LIVE means a valid runtime endpoint is configured and returned a compatible payload.

DEMO means no runtime endpoint is configured. The dashboard intentionally shows contract-safe sample data and visibly labels it as DEMO.

OFFLINE means a runtime endpoint is configured but cannot be reached or returns an incompatible payload. The UI falls back to contract-safe sample data and visibly labels the backend failure.

The dashboard never presents demo data as live.

## 4. Environment Contract

Optional server-side variables:

```text
WALLET_DETECTOR_DASHBOARD_URL
WALLET_DETECTOR_DASHBOARD_TOKEN
```

The token is server-only and must not use a NEXT_PUBLIC_ prefix.

A committed .env.example documents the contract without exposing credentials.

## 5. UI Information Architecture

Header:
- Wallet Detector identity
- runtime mode
- explicit refresh action
- registry snapshot identifier

KPI row:
- qualified wallet count
- current-window trade event count
- accumulation / distribution state count
- monitor health

Smart Money Flow:
- token symbol / mint
- flow state
- unique wallet count
- BUY wallet count
- SELL wallet count
- BUY event count
- SELL event count
- directly priced USD net flow
- unpriced event count

Registry panel:
- ACTIVE wallet count
- S1 membership
- S2 membership
- S3 membership
- stored trade events
- duplicate deliveries rejected
- normalization errors
- latest chain activity

Live tape:
- BUY / SELL
- wallet
- primary segment
- all qualifying segments
- token
- USD notional when available
- relative activity time

## 6. User Interaction

Frozen V1 interaction:
- 5m / 15m / 1h timeframe selection
- symbol / mint search
- manual refresh
- automatic 15-second refresh
- responsive desktop / tablet / mobile layout

No trading execution control is included.

## 7. Data Contract

The TypeScript UI contract lives in lib/dashboard-types.ts.

The Python Stage-8 adapter produces the same logical contract through build_dashboard_payload(...).

Required windows:

```text
5m
15m
1h
```

The adapter rejects:
- tampered Stage-7 snapshots
- monitor/snapshot provenance mismatch
- missing required rolling windows
- unsupported runtime modes

## 8. Token Identity

Mint address remains the canonical identity.

Optional symbol metadata is display-only.

If no symbol resolver is available:

```text
symbol = short mint prefix
```

The display symbol never replaces the mint identity in the contract.

## 9. Currency Safety

The dashboard displays USD notional only when Stage 8 already produced a valid usd_notional.

Unpriced events remain visible.

The UI does not convert SOL or other quote currencies into USD on its own.

## 10. Security

Stage 8.5 security requirements:
- live backend token stays server-side
- external runtime URL is controlled by server environment, not user input
- no wallet private keys
- no trading credentials
- no browser-exposed provider secret
- dashboard endpoint is fetched with cache: no-store
- response route uses no-store semantics

Next.js was upgraded during Stage 8.5 from 16.0.1 after CI surfaced a security warning.

Frozen version:

```text
Next.js 16.3.6
```

The secure build reported:

```text
found 0 vulnerabilities
```

## 11. Build / Runtime Verification

GitHub Actions now contains two independent jobs.

Python regression:

```text
python -m unittest discover -s tests -v
Ran 114 tests
OK
```

UI build gate:
- install dependencies
- TypeScript typecheck
- production Next.js build
- start production server
- GET /
- verify rendered Wallet Detector content
- GET /api/dashboard
- verify runtime mode
- verify registry payload
- verify rolling-window payload

Current result:

```text
Typecheck = PASS
Next build = PASS
Production smoke = PASS
```

## 12. Stage 8.5 Python Contract Tests

Nine deterministic tests cover:
1. registry + monitor health export
2. all required rolling windows
3. mint→symbol resolver
4. unknown symbol fallback
5. recent-event ordering
6. recent-event limit
7. monitor/snapshot provenance mismatch
8. missing rolling-window rejection
9. invalid runtime mode rejection

Stage 8.5 deterministic additions:

```text
9 / 9 PASS
```

Cumulative Python regression:

```text
Stage 1–8 = 105 tests
Stage 8.5 = 9 tests
--------------------
TOTAL = 114 / 114 PASS
```

## 13. Vercel Deployment State

The connected Vercel account currently exposes:

```text
team = bymarfinai's projects
projects = 0
```

Therefore no existing Vercel project is available to receive a deployment in this session.

Stage 8.5 is:

```text
implementation = PASS
production build = PASS
production smoke = PASS
Vercel project link = PENDING
Vercel deployment = PENDING
```

The repository is ready to be linked as a Next.js project without changing the dashboard architecture.

## 14. Stage 8.5 Decision

```text
WALLET_STAGE8_5_VERCEL_DASHBOARD_UI = PASS
deployment_activation = PENDING_VERCEL_PROJECT_LINK
```

Next:

```text
Stage 9 — Smart-Money Signal + MCD Integration
```
