# BabaBot Wallet Detector — Stage 2 Transaction Normalization

**Status:** IMPLEMENTED / NORMALIZATION CONTRACT FROZEN  
**Date:** 2026-09-28  
**Repository:** `bymarfinai/bababot-wallet-detector`

## 1. Objective

Convert Stage-1 raw Solana transaction evidence into deterministic wallet-level economic events without inventing trades.

```text
raw Solana transaction
        ↓
wallet token/native deltas
        ↓
remove explicit network fee from wallet SOL delta
        ↓
SWAP / TRANSFER / WRAP / OTHER / AMBIGUOUS
        ↓
BUY / SELL when quote identity is trustworthy
        ↓
base / quote / execution price
```

## 2. Core Invariants

1. Use wallet-level net balance changes as the economic source of truth.
2. Network fee is not a trade leg and must not create a false SOL sell.
3. Stablecoin identity is based on verified mint address, never ticker text.
4. Native SOL and WSOL are valid quote assets.
5. SOL ↔ WSOL wrap/unwrap is not a market trade.
6. If a transaction has more economic legs than can be safely resolved, emit `AMBIGUOUS`.
7. Never fabricate BUY/SELL from an untrusted token-token quote relationship.
8. Failed transactions do not enter trade reconstruction.
9. Raw asset deltas remain attached to every normalized event.

## 3. Trusted Quote Assets

Mainnet quote identities currently frozen:

- USDC: `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`
- USDT: `Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB`
- Native SOL: `SOL_NATIVE`
- WSOL: `So11111111111111111111111111111111111111112`

Stablecoin mint validation follows the Solana production-readiness principle that token identity must be checked by mint address, not name/symbol.

## 4. Event Types

### SWAP

Exactly one negative economic asset delta and one positive economic asset delta.

Examples:

```text
USDC -10
TOKEN +100
→ BUY TOKEN @ 0.1 USDC
```

```text
TOKEN -50
USDC +10
→ SELL TOKEN @ 0.2 USDC
```

### TRANSFER_IN / TRANSFER_OUT

Exactly one economic asset delta after network-fee removal.

### WRAP / UNWRAP

Native SOL and WSOL move in opposite directions at approximately the same amount.

These events are explicitly excluded from trading episodes.

### OTHER

No wallet-level economic asset delta remains after fee removal.

### FAILED

`meta.err != null`.

### AMBIGUOUS

Multiple economic legs remain and Stage 2 cannot safely infer one trade.

No BUY/SELL is emitted.

## 5. BUY / SELL Semantics

BUY/SELL is emitted only when Stage 2 has a trusted quote hierarchy.

Priority:

```text
USD stablecoin
    ↓
SOL / WSOL
    ↓
unquoted token-to-token
```

Rules:

- quote decreases + base increases → BUY
- base decreases + quote increases → SELL
- no trusted quote → side = SWAP

This prevents arbitrary token-token swaps from poisoning later wallet win-rate statistics.

## 6. Execution Price

Execution price uses actual wallet input/output amounts:

```text
execution_price_quote = abs(quote_delta) / abs(base_delta)
```

For verified USD stablecoin quote:

```text
usd_notional = abs(stablecoin_delta)
pricing_quality = DIRECT_USD_EXECUTION
```

For WSOL quote:

```text
pricing_quality = DIRECT_WSOL_EXECUTION
```

For native SOL quote:

```text
raw wallet SOL delta
+ explicit network fee when wallet is fee payer
= economic SOL delta
```

Native SOL execution is marked `MEDIUM` confidence because account rent/refund effects may coexist in the same transaction. No fake historical SOL/USD conversion is inserted in Stage 2.

## 7. Aggregator / Multi-Hop Handling

Jupiter/Raydium/direct DEX-specific parsing is intentionally not required for the common case.

If a complex route leaves only two wallet-level net endpoints:

```text
TOKEN A -
TOKEN B +
```

Stage 2 can normalize it protocol-agnostically.

If more than two wallet-level economic deltas survive, the event is `AMBIGUOUS` and retained for later protocol-aware resolution rather than guessed.

## 8. Stage-1 Regression Fix Found During Stage 2

Stage-1 token delta extraction previously assumed a mint present in `preTokenBalances` also existed in `postTokenBalances`.

That fails when a token account disappears/closes after the transaction.

The parser is now symmetric:

- missing pre balance → zero
- missing post balance → zero

This is covered by a permanent regression test.

## 9. Implemented Files

- `research/wallet_s2_transaction_normalizer.py`
- `tests/test_wallet_s2_transaction_normalizer.py`
- patched `research/wallet_s1_data_foundation.py`
- patched `tests/test_wallet_s1_data_foundation.py`

## 10. Acceptance Tests

Stage 2 tests cover:

- USDC → token = BUY
- token → USDC = SELL
- native SOL → token with network-fee removal
- inbound token transfer
- outbound token transfer
- SOL → WSOL wrap exclusion
- unquoted token → token swap
- multi-leg ambiguous transaction
- failed transaction exclusion

Full Stage-1 + Stage-2 deterministic regression suite:

```text
tests = 14
pass  = 14
fail  = 0
```

## 11. Stage 2 Decision

```text
WALLET_STAGE2_TRANSACTION_NORMALIZATION = PASS
```

Next:

```text
Stage 3 — Position / Trade Reconstruction
normalized BUY / SELL / SWAP events
        ↓
weighted entries
partial exits
position lifecycle
        ↓
closed trading episodes
        ↓
realized ROI / holding time
```
