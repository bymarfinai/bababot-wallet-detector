# BabaBot Wallet Detector — Stage 10A-0 Automatic Wallet Universe Discovery

**Date:** 2026-09-28  
**Status:** PREREGISTERED / NEXT

## Purpose

Wallet Detector must discover candidate wallets automatically from public Solana activity.

The final product must **not** depend on a manually maintained list of known successful wallets.

Target flow:

\`\`\`text
SOLANA BLOCKCHAIN
        ↓
AUTOMATIC WALLET UNIVERSE DISCOVERY
        ↓
candidate wallets
        ↓
causal historical reconstruction
        ↓
S1 / S2 / S3 qualification
+ Stage-6 specialty evidence when causally available
        ↓
qualified wallet registry
        ↓
monitoring
        ↓
Stage-9 smart-money signals
        ↓
Stage-10 paper trading
\`\`\`

## Architectural principle

Solana is the canonical data source.

Provider/indexer services are access layers only:

\`\`\`text
Solana blockchain
      ↓
native RPC / Helius / other verified provider
      ↓
Wallet Detector
\`\`\`

A Helius API key may be used for efficient indexed access, but Helius is **not** the source of wallet identity and is **not** an architectural requirement.

The discovery layer must remain provider-neutral where practical.

## Stage placement

This work remains inside Stage 10 activation:

\`\`\`text
Stage 1–9   = deterministic core already implemented
Stage 10    = paper-trading engine already implemented

Stage 10A-0 = automatic wallet universe discovery       ← NEXT
Stage 10A-1 = causal historical backfill + Supabase
Stage 10B   = real token OHLC ingestion
Stage 10C   = real empirical A/B/C/D/E replay
Stage 11    = validation / optimization
\`\`\`

Stage 10A-0 does not replace or renumber Stages 1–9.

## Discovery responsibility

Stage 10A-0 answers:

> Which wallet addresses should enter the historical qualification pipeline?

It does **not** decide whether a wallet is smart money.

Discovery should collect candidate wallets from factual blockchain activity. Quality classification remains the responsibility of Stages 3–7.

Therefore:

\`\`\`text
Discovery ≠ Qualification
Discovery ≠ Performance ranking
Discovery ≠ Meme Hunter label
\`\`\`

## Candidate discovery policy

Initial candidate discovery should be based on observable activity such as:

- participation in successful Solana transactions;
- token balance-changing activity;
- swap/trading activity;
- wallet ownership / account participation that can be attributed safely;
- transaction signatures and timestamps that provide reproducible provenance.

The discovery layer must not invent a performance score.

A wallet should enter the candidate universe because it was **observed trading**, not because future information says it later became profitable.

## Causality / anti-bias requirement

Wallet-universe construction must be reproducible as-of a historical cutoff.

Do not build a historical universe only from wallets known today to be successful and then replay their earlier activity as if they had been selected then.

Required principle:

\`\`\`text
information available by cutoff T
        ↓
wallets discoverable by T
        ↓
history available by T
        ↓
qualification as-of T
        ↓
signals after qualification
\`\`\`

This protects Stage 10 from survivor-selection and lookahead leakage.

## Manual wallet lists

Manual wallet lists remain supported only for:

- unit tests;
- small integration tests;
- provider probes;
- debugging;
- controlled bootstrap comparisons.

They are **not** the intended production discovery mechanism.

The existing Stage-10A historical runner may continue accepting \`--wallet\` / \`--wallets-file\` as an explicit test/bootstrap boundary, but real product activation should feed it from Stage 10A-0 discovery output.

## Required output contract

Stage 10A-0 should emit a deterministic candidate-universe artifact containing at minimum:

\`\`\`text
wallet
chain
discovered_at / cutoff
first_observed_at
last_observed_at
discovery_source
discovery_reason
evidence transaction/signature references
activity counts
universe/version provenance
deterministic fingerprint
\`\`\`

The output must preserve mint/wallet identities exactly and avoid symbol-based identity.

## Persistence

Candidate-universe evidence should be stored before qualification so the system can later answer:

- why was this wallet included?
- when was it first discoverable?
- from which transaction evidence?
- which provider/RPC path supplied the evidence?
- was it eligible to exist in a historical universe at cutoff T?

Supabase remains the primary hot/queryable store.

## Provider strategy

Preferred order:

1. use a provider-neutral interface;
2. use Helius when indexed historical access materially reduces complexity/cost;
3. retain native Solana RPC as audit/fallback where feasible;
4. never couple qualification logic to provider-specific response semantics.

If Helius is used, \`HELIUS_API_KEY\` is a server-side data-access credential only. It is not a wallet private key and does not authorize trading or movement of funds.

## Non-goals

Stage 10A-0 does not:

- select A/B/C/D/E winner;
- optimize trading thresholds;
- score wallet quality;
- classify S1–S5;
- classify Meme Hunter;
- ingest OHLC;
- execute live trades;
- depend on MCD / Market Radar.

## Acceptance criteria

Stage 10A-0 can be marked PASS only when:

1. candidate wallets are discovered automatically from real Solana activity;
2. discovery output is deterministic and deduplicated;
3. every candidate has reproducible provenance;
4. historical cutoff behavior is causal;
5. no current-success/future-profit filter is used to form past universes;
6. output feeds Stage 10A-1 without manual wallet editing;
7. provider-specific transport is separated from discovery semantics;
8. unit/integration tests cover duplicate, cutoff, pagination/provider failure, and provenance behavior.

## Current checkpoint

\`\`\`text
WALLET_STAGE10A0_AUTOMATIC_WALLET_UNIVERSE_DISCOVERY = NEXT
WALLET_STAGE10A1_CAUSAL_HISTORICAL_BACKFILL_ENGINE = PASS
WALLET_STAGE10A1_REAL_POPULATION = BLOCKED_BY_DISCOVERY_ACTIVATION
WALLET_STAGE10B_REAL_OHLC = PENDING
WALLET_STAGE10C_REAL_REPLAY = PENDING
WALLET_STAGE11 = BLOCKED
\`\`\`

## Next implementation

Implement a provider-neutral Solana wallet-universe discovery layer, then feed its deterministic output directly into the existing causal Stage-10A historical backfill.
