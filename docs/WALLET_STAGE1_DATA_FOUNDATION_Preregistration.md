# BabaBot Wallet Detector — Stage 1 Data Foundation

**Status:** IMPLEMENTED / FOUNDATION FROZEN  
**Date:** 2026-09-28  
**Repository:** `bymarfinai/bababot-wallet-detector`

## 1. Objective

Stage 1 freezes the data boundary before wallet scoring begins.

The detector is **wallet-centric**, not coin-list-centric:

```text
tracked / candidate wallet
        ↓
all relevant on-chain activity
        ↓
all token mints touched by that wallet
```

There is no hardcoded trading-symbol universe in Stage 1.

## 2. Chain Scope V1

V1 starts with **Solana mainnet**.

Supported ingestion scope:

- native SOL balance changes
- SPL Token activity
- Token-2022 activity when exposed by transaction metadata
- any fungible mint touched by the wallet
- arbitrary/new token mints without needing prior symbol registration

Token identity is always the **mint address**. Symbols and names are metadata only and must never be used as a primary key.

NFTs and non-trading program activity may remain in raw history but are not assumed to be trading episodes.

EVM chains are explicitly deferred until Solana Stage 1–5 are validated. The internal contract must remain chain/provider agnostic enough to add them later.

## 3. Historical Source

### Primary

**Helius `getTransactionsForAddress` (gTFA)**.

Frozen request policy:

```text
transactionDetails = full
sortOrder           = asc
filters.status      = succeeded
filters.tokenAccounts = balanceChanged
limit               = 100
```

Why `tokenAccounts=balanceChanged`:

A Solana wallet owns token accounts; not every token-account transaction necessarily references the owner wallet directly. Stage 1 therefore requires token-account-aware history instead of relying only on transactions whose account keys contain the main wallet.

Pagination is cursor-based using `paginationToken`.

### Baseline / Fallback

Standard Solana RPC remains the independent fallback/audit path:

```text
getSignaturesForAddress
        ↓
getTransaction
        ↓
pre/post SOL balances
pre/post token balances
```

For complete wallet token activity, the fallback implementation must also enumerate wallet-owned token accounts; plain `getSignaturesForAddress(wallet)` alone is not treated as complete wallet history.

## 4. Future Live Source

Live monitoring is NOT implemented in Stage 1, but the data boundary is chosen so Stage 8 can use:

1. Helius parsed/raw webhook or stream for the qualified wallet registry.
2. A lower-level Solana stream if provider independence or latency later requires it.

Historical and live ingestion must converge into the same internal event model before wallet logic sees the data.

## 5. Canonical Raw Facts Required

Stage 1 must preserve enough information for Stage 2 normalization and Stage 3 trade reconstruction:

```text
chain
provider
wallet address
transaction signature
slot
block time
success/failure state
account keys
pre/post native balances
pre/post token balances
token mint
token owner
raw token amount
token decimals
network fee when available
raw transaction payload
```

The transaction signature is the canonical transaction-level idempotency key on Solana.

Raw payloads are immutable evidence. Later normalized BUY/SELL records must be reproducible from stored raw inputs.

## 6. Token Discovery Rule

There is **no coin allowlist required for ingestion**.

```text
wallet touches unknown mint
        ↓
mint is discovered automatically
        ↓
raw balance delta stored
        ↓
Stage 2 decides whether it is a swap/trade/transfer/noise
```

Do not discard a mint merely because:

- it has no known symbol,
- it is not listed on Binance,
- it is new,
- it has tiny market cap,
- metadata is temporarily unavailable.

Spam/dust filtering belongs after raw ingestion so the original evidence remains auditable.

## 7. USD / Price Policy

Stage 1 does not invent historical token prices.

Preferred valuation hierarchy for later stages:

1. Stablecoin leg (USDC/USDT or another explicitly whitelisted USD stable) gives direct USD execution value.
2. SOL/WSOL leg gives token/SOL execution price; historical SOL/USD can be joined at the transaction timestamp.
3. Multi-hop/ambiguous routes remain unvalued until Stage 2 resolves the economic swap legs.
4. No synthetic USD value is filled merely to avoid nulls.

The actual on-chain input/output amounts are the source of truth for execution price.

## 8. Fee / Slippage Policy

Stage 1 stores observable on-chain fees and raw amounts.

- Network/priority fees: record explicitly when available.
- Swap execution slippage is already reflected in actual input/output amounts.
- Do not double-count embedded pool/protocol economics as a second arbitrary slippage penalty.
- Conservative fee/slippage assumptions used for S1/S2/S3 qualification are frozen later in the wallet-performance stage.

## 9. Provider Boundary

Wallet intelligence must not import provider-specific response fields throughout the codebase.

Provider flow:

```text
Helius / Solana RPC
        ↓
provider adapter
        ↓
canonical raw transaction facts
        ↓
Stage 2 normalization
```

If Helius changes or is replaced, wallet classification logic must not need rewriting.

## 10. Security

- API keys only through environment variables.
- Never commit provider keys.
- Never log full secrets.
- Read-only blockchain data access only.
- No private key or trading credential belongs in Wallet Detector data ingestion.

Expected environment variable for the Stage 1 probe:

```text
HELIUS_API_KEY
```

## 11. Implemented Stage-1 Code

### `research/wallet_s1_data_foundation.py`

Implements:

- Solana address validation
- frozen Helius gTFA request builder
- owner-level token balance delta extraction
- wallet native lamport delta extraction
- deterministic data-sufficiency report

### `research/wallet_s1_helius_probe.py`

Implements:

- read-only gTFA API probe
- API key from environment
- one-page historical fetch
- pagination-token reporting
- optional raw JSON save

### `tests/test_wallet_s1_data_foundation.py`

Synthetic deterministic tests prove:

- no token/symbol allowlist enters the historical request
- token-account balance changes are requested
- negative quote delta and positive acquired-token delta survive extraction
- native lamport changes survive extraction
- raw transaction evidence is sufficient to feed Stage 2

## 12. Acceptance Criteria

Stage 1 is considered complete when:

- [x] Solana is frozen as first chain.
- [x] ingestion is wallet-centric, not coin-centric.
- [x] unknown/new token mints are accepted automatically.
- [x] token identity uses mint address.
- [x] historical primary + independent fallback are defined.
- [x] raw facts required for reconstruction are frozen.
- [x] provider-specific logic is isolated.
- [x] no secret is embedded in code.
- [x] deterministic unit tests pass.
- [ ] one real-wallet Helius probe is executed with an API key.
- [ ] raw response is inspected for edge cases before Stage 2 parser is frozen.

The final two items require a runtime `HELIUS_API_KEY`; they do not change the Stage-1 architecture.

## 13. Stage 1 Decision

```text
WALLET_STAGE1_DATA_FOUNDATION = PASS
```

Architecture is frozen for Stage 2:

```text
Solana historical transactions
        ↓
ALL token-account balance changes for wallet
        ↓
raw immutable evidence
        ↓
Stage 2 — Transaction Normalization
```
