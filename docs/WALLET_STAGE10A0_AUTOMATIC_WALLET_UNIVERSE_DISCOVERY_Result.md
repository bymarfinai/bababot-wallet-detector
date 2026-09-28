# BabaBot Wallet Detector — Stage 10A-0 Automatic Wallet Universe Discovery

**Date:** 2026-09-28  
**Status:** PASS

## Result

\`\`\`text
WALLET_STAGE10A0_AUTOMATIC_WALLET_UNIVERSE_DISCOVERY = PASS
provider_neutral_solana_json_rpc = PASS
manual_wallet_list_required = false
real_mainnet_smoke = PASS
supabase_persistence = PASS
stage10a1_handoff = PASS
\`\`\`

## What was implemented

Stage 10A-0 now derives candidate wallet addresses automatically from real Solana blocks.

Production discovery no longer requires a hand-maintained wallet list.

\`\`\`text
Solana finalized blocks
        ↓
successful transactions
        ↓
signer addresses
        ↓
token-balance ownership + actual balance change
        ↓
candidate wallet universe
        ↓
deterministic fingerprint + provenance
        ↓
Supabase
        ↓
Stage 10A-1 causal historical backfill
\`\`\`

Discovery remains separate from qualification.

A candidate wallet is **not** called smart money merely because it was discovered.

## Candidate rule V1

A wallet becomes a discovery candidate only when all of these are true in the observed transaction:

1. transaction succeeded;
2. address is a transaction signer;
3. the same address is the owner of a token balance entry;
4. that token balance actually changed.

Frozen V1 discovery reason:

\`\`\`text
SIGNER_WITH_TOKEN_BALANCE_CHANGE
\`\`\`

This intentionally rejects non-signer vault/token-account owners and transactions with no economic token-balance change.

## Provider boundary

The discovery implementation uses standard Solana JSON-RPC:

\`\`\`text
getSlot
getBlocks
getBlock
\`\`\`

Default endpoint:

\`\`\`text
https://api.mainnet-beta.solana.com/
\`\`\`

No Helius key or wallet list is required for Stage 10A-0.

Any standards-compatible Solana RPC endpoint may be supplied using:

\`\`\`text
SOLANA_RPC_URL
SOLANA_RPC_SOURCE_LABEL
\`\`\`

Helius may still be used as an optional RPC/indexing provider, but it is not the source of wallet identity and is not embedded in discovery semantics.

RPC URLs are sanitized before entering provenance so query-string credentials cannot be written into universe artifacts.

## Transaction-version support

Real mainnet validation exposed version-1 Solana transactions.

The discovery client now explicitly supports:

\`\`\`text
maxSupportedTransactionVersion = 1
\`\`\`

and exposes that value as a configurable client/CLI parameter.

## Deterministic universe contract

Every universe contains:

\`\`\`text
version
chain
source kind / label / sanitized origin
requested start/end slot
optional cutoff timestamp
scanned slots
transaction counts
candidate wallet count
candidate records
universe fingerprint
\`\`\`

Each candidate record preserves:

\`\`\`text
wallet
discovered_at
first_observed_at
last_observed_at
first_observed_slot
last_observed_slot
activity_count
changed mints
evidence signatures
discovery source
discovery reason
record fingerprint
\`\`\`

## Causality

An optional historical cutoff excludes blocks whose block time is later than the cutoff.

Universe construction therefore supports:

\`\`\`text
information observable by T
        ↓
candidate universe as-of T
\`\`\`

No future profitability or current smart-wallet status is used to create the candidate universe.

## Supabase persistence

New tables:

\`\`\`text
wallet_universe_snapshots
wallet_universe_candidates
wallet_universe_evidence
\`\`\`

The evidence table preserves one provenance row per:

\`\`\`text
universe + wallet + transaction signature
\`\`\`

All three tables have RLS enabled.

The schema is version-controlled in:

\`\`\`text
supabase/migrations/
20260928223000_wallet_detector_stage10a0_universe_discovery.sql
\`\`\`

## Stage 10A-1 handoff

The existing causal historical backfill now accepts:

\`\`\`text
--universe-file
\`\`\`

Therefore the intended production path is:

\`\`\`text
Stage 10A-0 discovery artifact
        ↓
--universe-file
        ↓
Stage 10A-1 historical backfill
\`\`\`

Manual \`--wallet\` / \`--wallets-file\` inputs remain available only for controlled bootstrap, debugging, and tests.

## Real Solana mainnet validation

Dedicated workflow:

\`\`\`text
.github/workflows/discovery-mainnet-smoke.yml
\`\`\`

Latest successful real-mainnet smoke:

\`\`\`text
GitHub Actions run: 36445042420
source: https://api.mainnet-beta.solana.com/
scanned finalized blocks: 2
transactions observed: 2,229
candidate wallets discovered automatically: 205
universe fingerprint:
5314fc86218d800ab32a4fab140656275e7a9b8138482d7b6a03086710d9a934
\`\`\`

No candidate wallet addresses were supplied to that smoke run.

The mainnet smoke is scoped to discovery-related source/workflow changes so ordinary README/UI commits do not repeatedly hit public Solana RPC.

## Verification

Stage 10A-0 tests cover:

- signer + changed token owner acceptance;
- non-signer rejection;
- unchanged-balance rejection;
- failed-transaction rejection;
- parsed and raw account-key signer formats;
- causal cutoff;
- duplicate signature idempotency;
- deterministic universe fingerprint;
- credential-safe RPC provenance;
- standard JSON-RPC scan flow;
- null/missing block fail-closed behavior;
- Supabase universe/evidence mapping;
- parent-before-child persistence;
- direct Stage 10A-1 artifact handoff;
- fingerprint tamper detection;
- Solana transaction-version 1 support.

Latest Python regression at implementation checkpoint:

\`\`\`text
211 / 211 PASS
\`\`\`

## Important limitation

A 2-block smoke proves the automatic discovery mechanism against real Solana data; it is **not** the final production sampling window and the 205 addresses are not claimed to be smart wallets.

The next step is to define/populate a sufficiently broad causal discovery window and feed those candidates through Stage 10A-1 qualification.

## Next

\`\`\`text
Stage 10A-0 = PASS
        ↓
Stage 10A-1 real causal population
        ↓
Stage 10B real OHLC ingestion
        ↓
Stage 10C empirical replay
        ↓
Stage 11 validation / optimization
\`\`\`
