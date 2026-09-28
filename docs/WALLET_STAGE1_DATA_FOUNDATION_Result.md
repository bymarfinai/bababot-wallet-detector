# BabaBot Wallet Detector — Stage 1 Data Foundation — Result

**Date:** 2026-09-28  
**Repository:** `bymarfinai/bababot-wallet-detector`

## Result

```text
WALLET_STAGE1_DATA_FOUNDATION = PASS
```

Stage 1 successfully freezes the Solana-first data boundary required before BUY/SELL normalization and trade reconstruction.

## Frozen Decisions

- First chain: **Solana mainnet**
- Discovery model: **wallet-centric**
- Coin universe: **dynamic / no hardcoded coin list**
- Token identity: **mint address**
- Historical primary: **Helius getTransactionsForAddress**
- Historical filter: **tokenAccounts=balanceChanged**
- Historical order: **ascending**
- Transaction detail: **full**
- Successful transactions only
- Provider boundary isolated from wallet intelligence
- Raw transaction evidence retained for later deterministic replay

## Implemented

- `research/wallet_s1_data_foundation.py`
- `research/wallet_s1_helius_probe.py`
- `tests/test_wallet_s1_data_foundation.py`
- `docs/WALLET_STAGE1_DATA_FOUNDATION_Preregistration.md`

## Deterministic Test

Synthetic transaction:

```text
wallet:
USDC  -10
TOKEN +100
SOL   -0.000005
```

Observed assertions:

```text
PASS request uses getTransactionsForAddress
PASS tokenAccounts=balanceChanged
PASS no token/symbol filter
PASS quote-token negative delta retained
PASS acquired-token positive delta retained
PASS native lamport delta retained
PASS Stage-2 sufficiency report = true
```

Unit test summary:

```text
tests = 4
pass  = 4
fail  = 0
```

## Important Interpretation

Stage 1 does **not** yet decide:

- BUY vs SELL
- swap vs transfer
- aggregator route vs direct DEX route
- stablecoin/SOL quote valuation
- position boundaries
- wallet profitability

Those belong to Stage 2+.

Stage 1 only guarantees that the ingestion contract preserves the facts required to derive those decisions causally.

## Remaining Provider Probe

A real Helius page can be tested with:

```powershell
$env:HELIUS_API_KEY="YOUR_KEY"
python research/wallet_s1_helius_probe.py --wallet <SOLANA_WALLET> --limit 10 --out wallet_probe.json
```

No API key is committed or required for the deterministic test suite.

## Next Stage

```text
Stage 2 — Transaction Normalization

raw Solana transaction
        ↓
wallet-level economic deltas
        ↓
SWAP / TRANSFER / OTHER
        ↓
BUY / SELL
        ↓
base mint / quote mint
        ↓
canonical normalized event
```
