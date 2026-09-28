# Stage 10 Empirical Replay Bundle Contract

**Version:** `wallet-s10-replay-v1`

A real replay bundle is one directory containing exactly the three logical inputs below.

```text
<bundle>/
├── manifest.json
├── signals.jsonl
└── prices.jsonl
```

## manifest.json

Required fields:

```json
{
  "version": "wallet-s10-replay-v1",
  "source_kind": "REAL",
  "dataset_id": "<stable dataset id>",
  "signal_source": "<where Stage-9 snapshots came from>",
  "price_source": "<where OHLC came from>",
  "venue": "<execution/price venue>",
  "fee_bps_per_side": "<explicit assumption>",
  "slippage_bps_per_side": "<explicit assumption>",
  "max_holding_seconds": 86400,
  "max_entry_delay_seconds": null,
  "notes": ""
}
```

`source_kind` must be `REAL`. DEMO / SYNTHETIC / TEST bundles are rejected by the empirical replay runner.

## signals.jsonl

One complete Stage-9 `wallet-s9-v1` signal snapshot per JSON line.

Each snapshot must keep its original:

- `as_of`
- token signal objects
- signal fingerprints
- registry provenance
- Stage-6 evidence
- wallet breadth / tier features
- validated USD-flow evidence

Duplicate snapshot timestamps are rejected.

## prices.jsonl

One OHLC row per token/timestamp:

```json
{
  "base_asset": "<canonical token mint>",
  "timestamp": 0,
  "open": "0",
  "high": "0",
  "low": "0",
  "close": "0",
  "source": "<named real source>",
  "venue": "<venue>"
}
```

The token mint remains the identity key.

Every directional-signal token must have at least one OHLC bar strictly after the signal timestamp.

## Preflight

Run:

```bash
python research/wallet_s10_replay_activation.py \
  --bundle data/stage10/<dataset_id> \
  --out outputs/stage10/<dataset_id>-preflight.json \
  --preflight-only
```

The preflight checks:

- manifest is explicitly REAL
- Stage-9 schema compatibility
- duplicate snapshot timestamps
- duplicate token/timestamp price rows
- price source provenance
- directional token coverage
- strictly post-signal entry-price availability

Do not run empirical comparison until:

```text
ready_for_replay = true
```

## Replay

Run all preregistered rules:

```bash
python research/wallet_s10_replay_activation.py \
  --bundle data/stage10/<dataset_id> \
  --out outputs/stage10/<dataset_id>-result.json
```

Or a subset:

```bash
python research/wallet_s10_replay_activation.py \
  --bundle data/stage10/<dataset_id> \
  --rules A,C,E \
  --out outputs/stage10/<dataset_id>-result.json
```

The result preserves:

- normalized manifest + fingerprint
- preflight report + fingerprint
- full Stage-10 paper-trading output
- per-rule trades and summaries
- deterministic empirical-result fingerprint
- explicit `production_rule_selected = false`
- explicit `edge_validated = false`

Stage 11 must perform chronological validation before either flag can change conceptually.

## Current activation status

```text
paper-trading engine       PASS
real-data bundle contract  PASS
preflight validator        PASS
CLI replay runner          PASS
real dataset populated     PENDING
real A-E replay            PENDING
edge claim                 NONE
```
