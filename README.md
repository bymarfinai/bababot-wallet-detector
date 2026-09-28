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
Automatic Wallet Universe Discovery
        ↓
Historical Wallet Discovery / Backfill
        ↓
Transaction Normalization
        ↓
Trade / Position Reconstruction
        ↓
Wallet Performance Engine
        ↓
Performance Tier + Specialty + Capital Labels
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
| 5 | PASS V1 | S1 / S2 / S3 classification currently implemented |
| 6 | PASS V1 | Meme / explosion hunter evidence |
| 7 | PASS | Qualified wallet registry |
| 8 | PASS CORE | Live wallet monitor core |
| 8.5 | PASS | Vercel dashboard / UI |
| 9 | PASS | Smart-money signal output layer |
| 10A-0 | NEXT | Automatic wallet universe discovery from real Solana activity |
| 10A-1 | PASS ENGINE | Supabase causal historical backfill; real population waits on automatic discovery activation |
| 10B | PENDING | Real token OHLC ingestion |
| 10C | PENDING | Real empirical A/B/C/D/E replay |
| 11 | PLANNED | Validation + rule optimization + S4/S5 calibration |
| 12 | PLANNED | Optional ML ranker / probability layer |

MCD integration is **not** a required development stage.

Stage 10 is not considered empirically complete until real Stage-9 signal snapshots and causal token-price data have been replayed through the frozen engine.

## Product discovery principle

Wallet Detector is intended to **find smart wallets automatically**, not require the operator to maintain a hand-picked wallet list.

The target product loop is:

```text
Solana blockchain
        ↓
automatic candidate-wallet discovery
        ↓
causal historical reconstruction
        ↓
S1 / S2 / S3 qualification
+ orthogonal specialty evidence
        ↓
qualified wallet registry
        ↓
live monitoring
        ↓
smart-money signal
        ↓
paper-trading validation
```

Wallet discovery and wallet qualification are separate concerns:

```text
DISCOVERY
= which wallets were observably active and therefore eligible to be evaluated?

QUALIFICATION
= which discovered wallets actually satisfy the Stage-5 performance rules?
```

A manually supplied wallet list remains acceptable for unit tests, debugging, provider probes, and controlled bootstrap comparisons, but it is **not the final production discovery mechanism**.

The canonical source is the public Solana blockchain. Helius, native RPC, or another verified provider may be used as an access/indexing layer. An API provider is not the source of wallet identity and must not be embedded into qualification semantics.

Historical wallet-universe construction must be causal. A wallet may only enter a historical universe when it was discoverable from information available by that cutoff. Current-success/future-profit information must not be used to construct past universes.

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

## Wallet taxonomy

A wallet is described using **three independent dimensions**:

```text
1. PERFORMANCE TIER
   S1 / S2 / S3 / S4 / S5

2. SPECIALTY
   Meme Hunter / None

3. CAPITAL
   Normal / Large / Whale
```

These dimensions must not be collapsed into one score.

A high-capital wallet is not automatically smart money, and a Meme Hunter does not automatically need to be a high performance-tier wallet.

## Performance tiers

Performance tiers describe **consistent net realized return per reconstructed trade episode**.

Target taxonomy:

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

### S4 — Elite Return

```text
clean closed trades >= 50
net median ROI >= +20% per trade
net total realized PnL > 0
```

### S5 — Extreme Return

```text
clean closed trades >= 50
net median ROI >= +50% per trade
net total realized PnL > 0
```

S1 keeps the frozen V1 win-rate gate of >=60%.

No extra S2/S3/S4/S5 win-rate threshold should be invented before empirical validation.

Tier membership is cumulative by threshold:

```text
median net ROI = +24%

S1 PASS
S2 PASS
S3 PASS
S4 PASS
S5 FAIL

primary performance tier = S4
```

Median net realized ROI is intentionally preferred over arithmetic mean so a small number of jackpot trades cannot dominate qualification.

Holding time, profit factor, drawdown, activity consistency, and sample size remain recorded as validation features.

### Current implementation status

Stage 5 code currently implements **S1 / S2 / S3 only**.

S4 / S5 are now part of the target taxonomy, but should be added to production classification only with tests and downstream registry/dashboard updates. The documentation must not claim S4/S5 are already live before that code change is completed.

## Specialty labels

### Meme / Explosion Hunter

Meme Hunter is an **orthogonal specialty detector**, not an extension of S1-S5.

Its purpose is specifically to identify wallets that repeatedly enter before potential **SHIB / PEPE / BONK-style monster runners**.

The minimum meaningful explosion is:

```text
>= 2x from the wallet-relevant entry reference
```

**2x is the minimum qualifying explosion, not the final target.**

Explosion capability buckets:

```text
E1  >= 2x
E2  >= 5x
E3  >= 10x
E4  >= 20x
E5  >= 50x
E6  >= 100x
```

These are event/run capability buckets, **not wallet median-return tiers**.

Example:

```text
Wallet A

Performance Tier      S2
Median net ROI        +6.3%

Meme Hunter           YES
>=2x captured         21 events
>=5x captured          9 events
>=10x captured         4 events
>=20x captured         2 events
>=50x captured         1 event

Highest Explosion     E5
Best Runner           73.4x
```

A wallet can therefore be:

```text
S2 + Meme Hunter + Large
S4 + None + Whale
S1 + Meme Hunter + Normal
```

without mixing the meanings of performance, specialty, and capital.

### Continuous runner measurement

Do not store only discrete buckets.

For every eligible wallet BUY / explosion event, preserve the actual observed maximum multiple where data coverage permits.

Example:

```text
entry price      0.000001
future peak      0.000083
max_multiple     83x

>=2x    YES
>=5x    YES
>=10x   YES
>=20x   YES
>=50x   YES
>=100x  NO
```

This retains information needed for later validation and ML instead of reducing an 83x runner to a generic 50x bucket.

### Meme Hunter evaluation horizons

Short-horizon explosion evidence remains useful:

```text
6H
24H
72H
```

For monster-runner discovery, also evaluate longer horizons:

```text
7D
30D
```

This allows separation between:

```text
FAST EXPLOSION
>=2x within 6H–72H

MEGA RUNNER
large multi-x expansion developing over 7D–30D
```

### Meme Hunter quality metrics

A future calibrated Meme Hunter label should consider:

```text
>=2x hit rate
>=5x / >=10x / >=20x / >=50x / >=100x capture rate
actual max multiple distribution
distinct explosive tokens captured
repeatability across independent events
median entry lead time
false-positive rate
eligible buy count
data-coverage completeness
```

Repeated buys of the same token must not artificially inflate distinct-token success.

The specialty label must remain conceptually independent from S1-S5.

Current Stage-7 V1 still inherits live eligibility strictly from Stage-5 qualification. This is a known design limitation, not a final statement that a validated Meme Hunter specialist must also pass a normal performance tier.

A standalone Meme Hunter live-eligibility rule should only be frozen after empirical population calibration.

### Whale

Whale remains a separate capital-size label and is deferred until reliable comparable capital / trade-size data exists.

Whale must not be treated as a quality tier.

## Stage 9 — Smart-Money Signal Output

Stage 9 converts factual Stage-8 wallet activity into an external signal contract.

Inputs may include:

```text
unique qualified BUY wallets
unique qualified SELL wallets
S1 / S2 / S3 / S4 / S5 participation
Meme Hunter participation
Meme Hunter explosion evidence
net base flow
validated USD net flow when available
freshness
5m / 15m / 1H persistence
```

Implemented descriptive states:

```text
ACCUMULATION
DISTRIBUTION
NEUTRAL
```

Current V1 output includes:

```text
freshest active basis window
qualified BUY / SELL wallet breadth
overlapping performance-tier participation
validated USD flow with COMPLETE / PARTIAL / UNAVAILABLE coverage
exact freshness age + 5m / 15m / 1H bucket
rolling-window state agreement
non-overlapping 0–5m / 5–15m / 15–60m persistence bands
Stage-6 Meme Hunter evidence
event-time Stage-7 registry provenance
deterministic signal + snapshot fingerprints
JSON handoff
```

Rolling-window agreement is intentionally separated from true temporal persistence. A single recent event can appear in all nested rolling windows, so Stage 9 only claims 15m / 1H directional persistence when matching activity exists in the corresponding non-overlapping historical time bands.

Frozen V1 policy:

```text
strength_score = null
entry_rule = null
```

Do not invent an arbitrary 0–100 strength score before paper-trading evidence exists.

The output is consumable independently through JSON / a small external handoff boundary. Market Radar / MCD remains an optional future consumer rather than a dependency.

## Stage 10 — Wallet-Only Paper Trading

Wallet Detector is tested **independently** before any optional combination with MCD.

Implemented baseline:

```text
TP = +1.0%
SL = -1.0%
RR = 1:1
fees + estimated slippage included as explicit inputs
```

For SHORT, direction is mirrored.

Frozen execution rules:

- Wallet Detector / Stage-9 signal only
- ACCUMULATION → LONG
- DISTRIBUTION → SHORT
- NEUTRAL → no trade
- entry at the first OHLC bar open strictly after the signal timestamp
- one active position per symbol per candidate rule
- no overlapping same-symbol re-entry until the current paper position closes
- same-bar TP + SL ambiguity resolves conservatively to SL-first
- incomplete price history remains INCOMPLETE_DATA rather than being forced into an outcome
- fee and slippage assumptions are explicit caller inputs rather than hardcoded market claims

Evaluation horizons:

```text
30m
1H
4H
12H
24H
```

Every paper trade preserves:

```text
symbol / mint
side
signal time
signal fingerprint
entry time
entry delay
raw + slippage-adjusted entry
TP / SL trigger prices
exit time / exit reason
raw + slippage-adjusted exit
qualified-wallet count
S1 / S2 / S3 / future S4 / S5 counts
Stage-6 Meme Hunter evidence
BUY / SELL wallet counts
wallet-net breadth
validated USD flow
freshness / persistence
MFE / MAE
time to TP / SL
30m / 1H / 4H / 12H / 24H path metrics
gross return
net return after fees/slippage
```

Primary benchmark:

```text
P(+1% before -1%)
```

Candidate variants are now implemented as experiments:

```text
A  >= 2 directional qualified wallets

B  >= 3 directional qualified wallets

C  >= 3 directional qualified wallets
   + same-side higher-tier participation

D  >= 3 directional qualified wallets
   + same-side Stage-6 Meme Hunter evidence

E  >= 3 directional qualified wallets
   + same-side wallet breadth advantage >= 2
   + validated USD flow aligned with signal direction
```

Stage 10 intentionally does **not** select a winner.

```text
winner_selected = false
selection_policy = STAGE11_VALIDATION_REQUIRED
```

### Current Stage-10 status

Deterministic engine and methodology:

```text
PASS
31 / 31 Stage-10 engine tests
```

Empirical replay activation pipeline:

```text
PASS
12 / 12 replay-activation tests
REAL-only manifest validation
Stage-9 JSONL ingestion
OHLC JSONL ingestion
causal coverage preflight
A–E replay CLI
deterministic replay fingerprints
```

Full Python regression:

```text
196 / 196 PASS
```

### Stage 10A-0 — Automatic wallet universe discovery

**NEXT.**

The existing historical backfill engine currently accepts explicit wallet inputs for testing/bootstrap, but the final activation path must discover candidate wallets automatically from real Solana activity.

Stage 10A-0 must:

- discover candidate wallet addresses automatically;
- preserve transaction/signature provenance;
- deduplicate deterministically;
- support historical as-of cutoffs;
- avoid current-success / future-profit selection bias;
- feed Stage 10A-1 without manual wallet editing;
- keep provider transport separate from discovery semantics.

Helius may be used as an indexed access layer, but it is not an architectural dependency. Native Solana RPC remains a valid audit/fallback path.

See:

```text
docs/WALLET_STAGE10A0_AUTOMATIC_WALLET_UNIVERSE_DISCOVERY_Preregistration.md
```

### Stage 10A-1 — Supabase causal historical backfill

Implemented:

```text
Supabase project + versioned schema
raw Helius history persistence
Stage-2 normalized history persistence
causal Stage-3 → Stage-7 qualification reconstruction
Stage-8 eligible event reconstruction
Stage-9 historical signal generation
batched PostgREST upserts
```

Historical qualification is **not** copied backward from today's registry. A status change triggered at timestamp T becomes effective only after T, so the transaction that creates qualification is never retroactively counted as a smart-money event.

Stage-6 Meme evidence is disabled in historical Stage-10A replay until an as-of-safe reconstruction exists. Therefore historical A/B/C/E can be prepared causally, while historical Rule D remains pending.

The Supabase project and causal backfill engine are live. The current runner can still accept manual wallet inputs for tests/bootstrap, but **real product activation is now intentionally blocked on Stage 10A-0 automatic discovery**.

If Helius is chosen as the indexed provider, `HELIUS_API_KEY` is required by that transport. It is not required by the Wallet Detector architecture itself.

No trading edge is claimed from Stage 10A implementation tests.

Real trading-edge evidence:

```text
PENDING
```

A real replay bundle uses:

```text
<bundle>/
├── manifest.json
├── signals.jsonl
└── prices.jsonl
```

The bundle contract requires `source_kind = REAL` and rejects DEMO / SYNTHETIC / TEST data for empirical replay.

The repository still does not contain a populated real dataset combining:

```text
historical Stage-9 signal snapshots
+
causal token OHLC
+
explicit real execution-cost assumptions
```

Therefore Stage 10 currently proves **backtest + replay-pipeline correctness**, not profitability.

The next work item remains inside Stage 10: populate a real replay bundle and run candidates A–E. Stage 11 must not optimize rules from synthetic unit-test outcomes.

## Stage 11 — Validation / Optimization

Validation should answer:

- which wallet conditions materially improve +1% hit probability?
- how does performance change by holding horizon?
- how much edge remains after fees and slippage?
- how stable are rules across different market periods?
- which conditions raise win rate without collapsing trade frequency?
- when does wallet activity provide lead rather than late confirmation?
- do S4/S5 add useful separation beyond S1/S2/S3?
- which Meme Hunter evidence predicts ordinary +1% trades versus true mega-runners?

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
paper-trading + explosion dataset
        ↓
validated features
        ↓
ML ranker / probability model
        ↓
TAKE / SKIP or runner-probability evidence
```

AI/ML must **not** replace the deterministic wallet pipeline.

The preferred first models are tabular models such as:

- LightGBM
- XGBoost
- CatBoost

A general-purpose LLM is not the preferred core model for numerical trade-outcome prediction.

Primary short-horizon ML target:

```text
P(+1% before -1%)
```

Secondary momentum targets:

```text
P(+5%)
P(+10%)
P(+20%)
P(+50%)
```

Meme Hunter / monster-runner targets:

```text
P(>=2x)
P(>=5x)
P(>=10x)
P(>=20x)
P(>=50x)
P(>=100x)
expected / predicted max_multiple
```

The model should therefore distinguish two different problems:

```text
TRADE QUALITY
→ can this signal reach +1% before -1%?

MONSTER-RUNNER DISCOVERY
→ can this token become >=2x, and how far might the expansion continue?
```

ML features may include:

```text
wallet historical median net ROI
wallet win rate
holding-time profile
sample size
profit factor
drawdown reference
performance tier
Meme Hunter evidence
historical max-multiple distribution
explosion hit rates
entry lead-time profile
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
6. Monster-runner models must be evaluated separately from +1% trade models.
7. If ML does not add stable edge, keep the rule-based system.

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
├── WALLET_STAGE8_5_VERCEL_DASHBOARD_UI_Status.txt
├── WALLET_STAGE9_SMART_MONEY_SIGNAL_OUTPUT_Preregistration.md
├── WALLET_STAGE9_SMART_MONEY_SIGNAL_OUTPUT_Result.md
├── WALLET_STAGE9_SMART_MONEY_SIGNAL_OUTPUT_Status.txt
├── WALLET_STAGE10_PAPER_TRADING_Preregistration.md
├── WALLET_STAGE10_PAPER_TRADING_Result.md
├── WALLET_STAGE10_PAPER_TRADING_Status.txt
├── WALLET_STAGE10_EMPIRICAL_REPLAY_BUNDLE_CONTRACT.md
├── WALLET_STAGE10_EMPIRICAL_REPLAY_ACTIVATION_Result.md
├── WALLET_STAGE10A0_AUTOMATIC_WALLET_UNIVERSE_DISCOVERY_Preregistration.md
├── WALLET_STAGE10A_SUPABASE_CAUSAL_BACKFILL_Result.md
└── WALLET_STAGE10A_SUPABASE_CAUSAL_BACKFILL_Status.txt

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
├── wallet_s8_5_dashboard_contract.py
├── wallet_s9_smart_money_signal.py
├── wallet_s10_paper_trading.py
├── wallet_s10_replay_activation.py
├── wallet_s10a_historical_backfill.py
└── wallet_supabase_adapter.py

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
├── test_wallet_s8_5_dashboard_contract.py
├── test_wallet_s9_smart_money_signal.py
├── test_wallet_s10_paper_trading.py
├── test_wallet_s10_replay_activation.py
└── test_wallet_s10a_historical_backfill.py

supabase/
└── migrations/
    ├── 20260928071800_wallet_detector_stage10_core.sql
    └── 20260928074000_wallet_detector_stage10a_history_evidence.sql

package.json
tsconfig.json
next.config.ts
next-env.d.ts
.env.example
```

## Run deterministic Stage 1–10 tests

```bash
python -m unittest discover -s tests -v
```


## Run Stage 10A-1 causal historical backfill

Server-side environment:

```text
WALLET_SUPABASE_URL=https://yuqkodwdqaggsexbqiqa.supabase.co
WALLET_SUPABASE_SECRET_KEY=<server secret>
HELIUS_API_KEY=<helius key>
```

Example:

```bash
python research/wallet_s10a_historical_backfill.py \
  --wallets-file wallets.json \
  --signal-from-unix <timestamp> \
  --signal-to-unix <timestamp> \
  --out outputs/stage10a/backfill-report.json
```

Use `--dry-run` to build the causal replay without writing Supabase.

## Run Stage 10 real-data replay

Bundle contract:

```text
data/stage10/<dataset_id>/
├── manifest.json
├── signals.jsonl
└── prices.jsonl
```

Preflight only:

```bash
python research/wallet_s10_replay_activation.py \
  --bundle data/stage10/<dataset_id> \
  --out outputs/stage10/<dataset_id>-preflight.json \
  --preflight-only
```

Run A–E:

```bash
python research/wallet_s10_replay_activation.py \
  --bundle data/stage10/<dataset_id> \
  --out outputs/stage10/<dataset_id>-result.json
```

The empirical runner accepts `source_kind=REAL` only.


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
WALLET_STAGE5_CLASSIFICATION_V1_S1_TO_S3 = PASS
TARGET_TAXONOMY_S4_S5 = DOCUMENTED_NOT_YET_IMPLEMENTED
WALLET_STAGE6_MEME_EXPLOSION_HUNTER_V1 = PASS
WALLET_STAGE7_QUALIFIED_WALLET_REGISTRY = PASS
WALLET_STAGE8_LIVE_WALLET_MONITOR_CORE = PASS
WALLET_STAGE8_5_VERCEL_DASHBOARD_UI = PASS
WALLET_STAGE9_SMART_MONEY_SIGNAL_OUTPUT = PASS
WALLET_STAGE10_PAPER_TRADING_ENGINE = PASS
WALLET_STAGE10_EMPIRICAL_REPLAY_PIPELINE = PASS
WALLET_STAGE10A0_AUTOMATIC_WALLET_UNIVERSE_DISCOVERY = NEXT
WALLET_STAGE10A1_SUPABASE_ADAPTER = PASS
WALLET_STAGE10A1_CAUSAL_HISTORICAL_BACKFILL = PASS
WALLET_STAGE10A1_REAL_POPULATION = BLOCKED_BY_DISCOVERY_ACTIVATION
WALLET_STAGE10B_REAL_OHLC = PENDING
WALLET_STAGE10C_EMPIRICAL_REPLAY = PENDING_REAL_DATA
WALLET_STAGE10_EMPIRICAL_REPLAY_DATASET = PENDING_REAL_DATA
WALLET_STAGE10_REAL_A_B_C_E_COMPARISON = PENDING
WALLET_STAGE10_HISTORICAL_RULE_D = PENDING_CAUSAL_STAGE6

NEXT = STAGE10A0_AUTOMATIC_WALLET_UNIVERSE_DISCOVERY

FUTURE AFTER REAL STAGE10 RESULTS:
WALLET_STAGE11_VALIDATION_OPTIMIZATION_AND_S4_S5
WALLET_STAGE12_OPTIONAL_ML_RANKER
```
