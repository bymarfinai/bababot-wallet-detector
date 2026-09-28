# BabaBot Wallet Detector

Standalone **smart-money wallet intelligence** for BabaBot.

## Core responsibility

```text
Wallet Detector   = WHO + WHAT are smart wallets buying/selling?
Market Radar      = WHEN is the market starting to move?
Reaction Detector = WHERE is the high-quality reaction/entry area?
```

These systems are intentionally developed as **independent repositories**.

Wallet Detector does **not** require Market Radar to operate, qualify wallets, generate smart-money signals, or run paper-trading validation.

Future MCD/Market Radar use is optional and should consume Wallet Detector through a clean external output contract rather than sharing internal logic or runtime dependencies.

## Architecture

```text
Historical Wallet Discovery
        ↓
Transaction Normalization
        ↓
Trade / Position Reconstruction
        ↓
Wallet Performance Engine
        ↓
S1 / S2 / S3 + Specialty Evidence
        ↓
Qualified Wallet Registry
        ↓
Live Wallet Monitoring
        ↓
5m / 15m / 1H Smart-Money Aggregation
        ↓
Smart-Money Signal Layer
        ↓
Wallet-Only Paper Trading
        ↓
Validation / Optimization
        ↓
Optional ML Ranker
        ↓
External Handoff / Consumer
```

Possible future consumers include:

- Wallet Detector dashboard
- alerting
- manual trading workflow
- Market Radar / MCD
- a future fusion layer

No consumer is required for Wallet Detector itself to work.

## Development stages

| Stage | Status | Responsibility |
|---|---|---|
| 1 | PASS | Solana-first data foundation |
| 2 | PASS | Transaction normalization |
| 3 | PASS | Position / trade reconstruction |
| 4 | PASS | Historical wallet performance engine |
| 5 | PASS | S1 / S2 / S3 classification |
| 6 | PASS | Meme / explosion hunter discovery |
| 7 | PASS | Qualified wallet registry |
| 8 | PASS CORE | Live wallet monitor core |
| 8.5 | PASS | Vercel dashboard / UI |
| 9 | NEXT | Smart-money signal output layer |
| 10 | PLANNED | Wallet-only paper trading |
| 11 | PLANNED | Validation + rule optimization |
| 12 | PLANNED | Optional ML ranker / probability layer |

MCD integration is **not** a required development stage.

## Stage 1 frozen principles

- First chain: **Solana mainnet**
- Wallet-centric ingestion; no hardcoded coin list
- Any wallet-touched token mint can be discovered
- Mint address is the canonical token identity
- Primary historical provider: Helius `getTransactionsForAddress`
- Native Solana RPC is the independent fallback/audit path
- Raw evidence is preserved before BUY/SELL interpretation
- Provider-specific logic stays behind an adapter boundary
- No API key or trading credential is committed

## Frozen V1 wallet classification

### S1 — Consistent

```text
clean closed trades >= 50
net median ROI >= +1% per trade
net win rate >= 60%
net total realized PnL > 0
```

### S2 — Momentum

```text
clean closed trades >= 50
net median ROI >= +5% per trade
net total realized PnL > 0
```

### S3 — High Velocity

```text
clean closed trades >= 50
net median ROI >= +10% per trade
net total realized PnL > 0
```

Median net realized ROI is intentionally preferred over arithmetic mean so a small number of jackpot trades cannot dominate qualification.

Holding time, profit factor, drawdown, activity consistency, and sample size remain recorded as validation features.

## Specialty labels

### Meme / Explosion Hunter

Stage 6 is an orthogonal specialty detector.

Current historical evidence includes:

```text
2x / 5x / 10x
within
6H / 24H / 72H
```

and explosion-event lead-time analysis.

The specialty label must remain conceptually independent from S1 / S2 / S3.

Current Stage-7 V1 still inherits live eligibility strictly from Stage-5 qualification. This is a known design limitation, not a final statement that a validated Meme Hunter specialist must also pass S1/S2/S3.

A standalone Meme Hunter live-eligibility rule should only be frozen after empirical population calibration.

### Whale

Whale remains a separate capital-size label and is deferred until reliable comparable capital / trade-size data exists.

Whale must not be treated as a quality tier.

## Stage 9 — Smart-Money Signal Output

Stage 9 should convert factual Stage-8 wallet activity into an external signal contract.

Inputs may include:

```text
unique qualified BUY wallets
unique qualified SELL wallets
S1 / S2 / S3 participation
Meme Hunter participation
net base flow
validated USD net flow when available
freshness
5m / 15m / 1H persistence
```

Initial descriptive states:

```text
ACCUMULATION
DISTRIBUTION
BALANCED / NEUTRAL
```

Do not invent an arbitrary 0–100 strength score before paper-trading evidence exists.

The output should be consumable independently through API / JSON / another small handoff boundary.

## Stage 10 — Wallet-Only Paper Trading

Wallet Detector should be tested **independently** before any optional combination with MCD.

Primary baseline objective:

```text
TP = +1.0%
SL = -1.0%
RR = 1:1
fees + estimated slippage included
```

For SHORT, the direction is mirrored.

Baseline execution rules:

- signal confirmed from Wallet Detector only
- entry at the first causal tradable price after the signal
- one active position per symbol
- no overlapping re-entry on the same symbol until the current paper position closes
- record multiple evaluation horizons even if the trading timeout is shorter

Evaluation horizons should include at least:

```text
30m
1H
4H
12H
24H
```

Every paper trade should preserve:

```text
symbol
side
signal time
entry time
entry price
qualified-wallet count
S1 / S2 / S3 counts
Meme Hunter participation
BUY / SELL wallet counts
net flow
TP / SL
MFE
MAE
time to TP
time to SL
net PnL after fees/slippage
```

The key metric is not simply direction accuracy.

The main benchmark is:

```text
P(+1% before -1%)
```

Candidate rule variants should be compared empirically, for example:

```text
A  >= 2 qualified wallets
B  >= 3 qualified wallets
C  >= 3 wallets + at least one S2/S3
D  >= 3 wallets + Meme Hunter participation
E  stronger independent accumulation + positive validated net flow
```

The winning V1 rule must come from data rather than discretionary weighting.

## Stage 11 — Validation / Optimization

Validation should answer:

- which wallet conditions materially improve +1% hit probability?
- how does performance change by holding horizon?
- how much edge remains after fees and slippage?
- how stable are rules across different market periods?
- which conditions raise win rate without collapsing trade frequency?
- when does wallet activity provide lead rather than late confirmation?

This stage should freeze the simplest robust rule set before ML is allowed to influence signals.

## Stage 12 — AI / ML role

AI/ML is **planned but not currently implemented as a live decision layer**.

The intended architecture is:

```text
deterministic wallet ingestion
        ↓
rule-based qualification
        ↓
rule-based smart-money candidate
        ↓
paper-trading dataset
        ↓
validated features
        ↓
ML ranker / probability model
        ↓
TAKE / SKIP ranking evidence
```

AI/ML must **not** replace the deterministic wallet pipeline.

The preferred first models are tabular models such as:

- LightGBM
- XGBoost
- CatBoost

A general-purpose LLM is not the preferred core model for numerical trade-outcome prediction.

Primary ML target:

```text
P(+1% before -1%)
```

Possible secondary targets:

```text
P(+5% within 6H)
P(+10% within 24H)
P(+20%)
P(+50%)
P(2x)
```

ML features may include:

```text
wallet historical median net ROI
wallet win rate
holding-time profile
sample size
profit factor
drawdown reference
wallet segment
Meme Hunter evidence
independent-wallet count
net flow
signal freshness
5m / 15m / 1H persistence
```

ML deployment policy:

1. Train only after a sufficiently large causal paper/historical dataset exists.
2. Evaluate on chronological out-of-sample data.
3. Run in **shadow mode** first.
4. Compare rule-only vs ML-filtered results.
5. Only promote ML if it improves out-of-sample expectancy / hit rate without unacceptable trade-frequency loss.
6. If ML does not add stable edge, keep the rule-based system.

## Live-runtime status

Stage 8 core implementation is complete, including:

- qualified-wallet subscription planning
- wallet-touch detection
- Stage-2 normalization reuse
- idempotency key `wallet + signature`
- 5m / 15m / 1H rolling aggregation
- accumulation / distribution state
- segment participation
- duplicate-delivery protection

The following live-production activation items remain separate from the deterministic core:

- authenticated public webhook receiver
- real Helius webhook provisioning
- durable event persistence
- end-to-end Solana mainnet delivery probe

The dashboard build is implemented and the latest repository commit reports a successful Vercel deployment status.

## Current files

```text
.github/
└── workflows/
    └── tests.yml

app/
├── api/
│   └── dashboard/
│       └── route.ts
├── globals.css
├── layout.tsx
└── page.tsx

components/
└── dashboard.tsx

lib/
├── dashboard-data.ts
└── dashboard-types.ts

docs/
├── WALLET_STAGE1_DATA_FOUNDATION_Preregistration.md
├── WALLET_STAGE1_DATA_FOUNDATION_Result.md
├── WALLET_STAGE1_DATA_FOUNDATION_Status.txt
├── WALLET_STAGE2_TRANSACTION_NORMALIZATION_Preregistration.md
├── WALLET_STAGE2_TRANSACTION_NORMALIZATION_Result.md
├── WALLET_STAGE2_TRANSACTION_NORMALIZATION_Status.txt
├── WALLET_STAGE3_POSITION_TRADE_RECONSTRUCTION_Preregistration.md
├── WALLET_STAGE3_POSITION_TRADE_RECONSTRUCTION_Result.md
├── WALLET_STAGE3_POSITION_TRADE_RECONSTRUCTION_Status.txt
├── WALLET_STAGE4_HISTORICAL_PERFORMANCE_Preregistration.md
├── WALLET_STAGE4_HISTORICAL_PERFORMANCE_Result.md
├── WALLET_STAGE4_HISTORICAL_PERFORMANCE_Status.txt
├── WALLET_STAGE5_CLASSIFICATION_Preregistration.md
├── WALLET_STAGE5_CLASSIFICATION_Result.md
├── WALLET_STAGE5_CLASSIFICATION_Status.txt
├── WALLET_STAGE6_MEME_EXPLOSION_HUNTER_Preregistration.md
├── WALLET_STAGE6_MEME_EXPLOSION_HUNTER_Result.md
├── WALLET_STAGE6_MEME_EXPLOSION_HUNTER_Status.txt
├── WALLET_STAGE7_QUALIFIED_WALLET_REGISTRY_Preregistration.md
├── WALLET_STAGE7_QUALIFIED_WALLET_REGISTRY_Result.md
├── WALLET_STAGE7_QUALIFIED_WALLET_REGISTRY_Status.txt
├── WALLET_STAGE8_LIVE_WALLET_MONITOR_Preregistration.md
├── WALLET_STAGE8_LIVE_WALLET_MONITOR_Result.md
├── WALLET_STAGE8_LIVE_WALLET_MONITOR_Status.txt
├── WALLET_STAGE8_5_VERCEL_DASHBOARD_UI_Preregistration.md
├── WALLET_STAGE8_5_VERCEL_DASHBOARD_UI_Result.md
└── WALLET_STAGE8_5_VERCEL_DASHBOARD_UI_Status.txt

research/
├── __init__.py
├── wallet_s1_data_foundation.py
├── wallet_s1_helius_probe.py
├── wallet_s2_transaction_normalizer.py
├── wallet_s3_position_reconstruction.py
├── wallet_s4_historical_performance.py
├── wallet_s5_classification.py
├── wallet_s6_meme_explosion_hunter.py
├── wallet_s7_qualified_registry.py
├── wallet_s8_live_monitor.py
└── wallet_s8_5_dashboard_contract.py

tests/
├── __init__.py
├── test_wallet_s1_data_foundation.py
├── test_wallet_s2_transaction_normalizer.py
├── test_wallet_s3_position_reconstruction.py
├── test_wallet_s4_historical_performance.py
├── test_wallet_s5_classification.py
├── test_wallet_s6_meme_explosion_hunter.py
├── test_wallet_s7_qualified_registry.py
├── test_wallet_s8_live_monitor.py
└── test_wallet_s8_5_dashboard_contract.py

package.json
tsconfig.json
next.config.ts
next-env.d.ts
.env.example
```

## Run deterministic Stage 1–8.5 tests

```bash
python -m unittest discover -s tests -v
```

## Run dashboard locally

```bash
npm install
npm run dev
```

Without `WALLET_DETECTOR_DASHBOARD_URL`, the dashboard clearly runs in **DEMO** mode.

For a live backend, copy the environment template and configure the server-only values documented in `.env.example`.

## Optional real Helius probe

Set the API key only in the environment:

```powershell
$env:HELIUS_API_KEY="YOUR_KEY"
python research/wallet_s1_helius_probe.py --wallet <SOLANA_WALLET> --limit 10 --out wallet_probe.json
```

## Current checkpoint

```text
WALLET_STAGE1_DATA_FOUNDATION = PASS
WALLET_STAGE2_TRANSACTION_NORMALIZATION = PASS
WALLET_STAGE3_POSITION_TRADE_RECONSTRUCTION = PASS
WALLET_STAGE4_HISTORICAL_PERFORMANCE_ENGINE = PASS
WALLET_STAGE5_CLASSIFICATION_V1 = PASS
WALLET_STAGE6_MEME_EXPLOSION_HUNTER = PASS
WALLET_STAGE7_QUALIFIED_WALLET_REGISTRY = PASS
WALLET_STAGE8_LIVE_WALLET_MONITOR_CORE = PASS
WALLET_STAGE8_5_VERCEL_DASHBOARD_UI = PASS

NEXT = WALLET_STAGE9_SMART_MONEY_SIGNAL_OUTPUT

FUTURE:
WALLET_STAGE10_WALLET_ONLY_PAPER_TRADING
WALLET_STAGE11_VALIDATION_OPTIMIZATION
WALLET_STAGE12_OPTIONAL_ML_RANKER
```
