# BabaBot Wallet Detector

Standalone **smart-money wallet intelligence** for BabaBot.

## Core responsibility

```text
Wallet Detector = WHO + WHAT are smart wallets buying/selling?
Market Radar    = WHEN is the market starting to move?
Reaction Detector = WHERE is the high-quality reaction/entry area?
```

Wallet Detector is intentionally independent from `bababot-discovery` and `bababot-market-radar`.

## Architecture

```text
Historical Wallet Discovery
        ↓
Trade / Position Reconstruction
        ↓
Wallet Performance Scoring
        ↓
S1 / S2 / S3 + Special Labels
        ↓
Qualified Wallet Registry
        ↓
Live Wallet Monitoring
        ↓
5m / 15m / 1H Smart-Money Aggregation
        ↓
Priority Watch / Confirmation
        ↓
BabaBot Market Radar
```

## Development stages

| Stage | Status | Responsibility |
|---|---|---|
| 1 | PASS | Solana-first data foundation |
| 2 | PASS | Transaction normalization |
| 3 | PASS | Position / trade reconstruction |
| 4 | PASS | Historical wallet performance engine |
| 5 | PASS | S1 / S2 / S3 classification |
| 6 | NEXT | Meme / explosion hunter discovery |
| 7 | PLANNED | Qualified wallet registry |
| 8 | PLANNED | Live wallet monitor |
| 8.5 | PLANNED | Vercel dashboard / UI |
| 9 | PLANNED | Smart-money signal + MCD integration |
| 10 | PLANNED | Validation + ML optimization |

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

## Current files

```text
.github/
└── workflows/
    └── tests.yml

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
└── WALLET_STAGE5_CLASSIFICATION_Status.txt

research/
├── __init__.py
├── wallet_s1_data_foundation.py
├── wallet_s1_helius_probe.py
├── wallet_s2_transaction_normalizer.py
├── wallet_s3_position_reconstruction.py
├── wallet_s4_historical_performance.py
└── wallet_s5_classification.py

tests/
├── __init__.py
├── test_wallet_s1_data_foundation.py
├── test_wallet_s2_transaction_normalizer.py
├── test_wallet_s3_position_reconstruction.py
├── test_wallet_s4_historical_performance.py
└── test_wallet_s5_classification.py
```

## Run deterministic Stage 1–5 tests

```bash
python -m unittest discover -s tests -v
```

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
NEXT = WALLET_STAGE6_MEME_EXPLOSION_HUNTER
```
