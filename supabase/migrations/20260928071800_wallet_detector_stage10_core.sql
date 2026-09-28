create table if not exists public.registry_snapshots (
  snapshot_id text primary key,
  snapshot_fingerprint text not null unique,
  stage7_version text not null default 'wallet-s7-v1',
  active_wallet_count integer not null default 0 check (active_wallet_count >= 0),
  total_record_count integer not null default 0 check (total_record_count >= 0),
  source_payload jsonb not null,
  observed_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create table if not exists public.wallet_registry (
  snapshot_id text not null references public.registry_snapshots(snapshot_id) on delete cascade,
  wallet text not null,
  chain text not null default 'solana',
  record_fingerprint text not null,
  registry_status text not null,
  live_monitor_eligible boolean not null default false,
  primary_segment text,
  qualifying_segments text[] not null default '{}',
  classification jsonb not null default '{}'::jsonb,
  performance_summary jsonb,
  meme_hunter_evidence jsonb,
  special_labels jsonb not null default '{}'::jsonb,
  source_versions jsonb not null default '{}'::jsonb,
  source_payload jsonb not null,
  created_at timestamptz not null default now(),
  primary key (snapshot_id, wallet),
  unique (snapshot_id, record_fingerprint)
);

create index if not exists wallet_registry_wallet_idx
  on public.wallet_registry (wallet);
create index if not exists wallet_registry_live_idx
  on public.wallet_registry (live_monitor_eligible, registry_status);
create index if not exists wallet_registry_segments_gin_idx
  on public.wallet_registry using gin (qualifying_segments);

create table if not exists public.wallet_events (
  id bigint generated always as identity primary key,
  live_event_id text not null,
  idempotency_key text not null,
  wallet text not null,
  signature text not null,
  chain text not null default 'solana',
  event_type text not null,
  side text not null,
  base_asset text,
  quote_asset text,
  base_amount numeric,
  quote_amount numeric,
  usd_notional numeric,
  execution_price numeric,
  block_time_unix bigint not null,
  slot bigint,
  primary_segment text,
  qualifying_segments text[] not null default '{}',
  meme_hunter_evidence jsonb,
  special_labels jsonb not null default '{}'::jsonb,
  registry_snapshot_id text,
  registry_snapshot_fingerprint text,
  registry_record_fingerprint text,
  normalized_payload jsonb not null,
  received_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  constraint wallet_events_wallet_signature_uniq unique (wallet, signature),
  constraint wallet_events_live_event_id_uniq unique (live_event_id),
  constraint wallet_events_idempotency_uniq unique (idempotency_key),
  constraint wallet_events_side_check check (side in ('BUY','SELL','SWAP','NONE')),
  constraint wallet_events_event_type_check check (
    event_type in ('SWAP','TRANSFER_IN','TRANSFER_OUT','WRAP','UNWRAP','OTHER','FAILED','AMBIGUOUS')
  )
);

create index if not exists wallet_events_base_time_idx
  on public.wallet_events (base_asset, block_time_unix desc);
create index if not exists wallet_events_wallet_time_idx
  on public.wallet_events (wallet, block_time_unix desc);
create index if not exists wallet_events_trade_time_idx
  on public.wallet_events (event_type, side, block_time_unix desc);
create index if not exists wallet_events_segments_gin_idx
  on public.wallet_events using gin (qualifying_segments);

create table if not exists public.smart_money_signal_snapshots (
  snapshot_fingerprint text primary key,
  stage9_version text not null default 'wallet-s9-v1',
  chain text not null default 'solana',
  as_of_unix bigint not null unique,
  signal_count integer not null check (signal_count >= 0),
  source_payload jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists public.smart_money_signals (
  signal_fingerprint text primary key,
  snapshot_fingerprint text not null
    references public.smart_money_signal_snapshots(snapshot_fingerprint)
    on delete cascade,
  stage9_version text not null default 'wallet-s9-v1',
  chain text not null default 'solana',
  base_asset text not null,
  as_of_unix bigint not null,
  state text not null check (state in ('ACCUMULATION','DISTRIBUTION','NEUTRAL')),
  state_basis_window text not null check (state_basis_window in ('5m','15m','1h')),
  unique_wallet_count integer not null default 0 check (unique_wallet_count >= 0),
  buy_wallet_count integer not null default 0 check (buy_wallet_count >= 0),
  sell_wallet_count integer not null default 0 check (sell_wallet_count >= 0),
  wallet_net_count integer not null default 0,
  net_base_amount numeric,
  usd_coverage text not null check (usd_coverage in ('COMPLETE','PARTIAL','UNAVAILABLE')),
  validated_usd_net_notional numeric,
  usd_direction text not null check (usd_direction in ('POSITIVE','NEGATIVE','FLAT','UNAVAILABLE')),
  spans_15m_directionally boolean not null default false,
  spans_1h_directionally boolean not null default false,
  meme_evidence_wallet_count integer not null default 0 check (meme_evidence_wallet_count >= 0),
  source_payload jsonb not null,
  created_at timestamptz not null default now(),
  constraint smart_money_signals_snapshot_token_uniq unique (snapshot_fingerprint, base_asset),
  constraint smart_money_signals_time_token_uniq unique (as_of_unix, base_asset)
);

create index if not exists smart_money_signals_token_time_idx
  on public.smart_money_signals (base_asset, as_of_unix desc);
create index if not exists smart_money_signals_state_time_idx
  on public.smart_money_signals (state, as_of_unix desc);

create table if not exists public.token_price_bars (
  base_asset text not null,
  venue text not null,
  source text not null,
  source_kind text not null default 'REAL'
    check (source_kind in ('REAL','DEMO','TEST')),
  quote_asset text,
  interval_seconds integer not null check (interval_seconds > 0),
  timestamp_unix bigint not null,
  open numeric not null check (open > 0),
  high numeric not null check (high > 0),
  low numeric not null check (low > 0),
  close numeric not null check (close > 0),
  volume numeric,
  created_at timestamptz not null default now(),
  primary key (base_asset, venue, interval_seconds, timestamp_unix),
  constraint token_price_bars_ohlc_check check (
    high >= greatest(open, close, low)
    and low <= least(open, close, high)
  )
);

create index if not exists token_price_bars_lookup_idx
  on public.token_price_bars (base_asset, timestamp_unix);
create index if not exists token_price_bars_real_lookup_idx
  on public.token_price_bars (source_kind, base_asset, timestamp_unix);

create table if not exists public.replay_runs (
  id bigint generated always as identity primary key,
  dataset_id text not null,
  source_kind text not null check (source_kind = 'REAL'),
  status text not null default 'PENDING'
    check (status in ('PENDING','PREFLIGHT_PASS','PREFLIGHT_FAIL','RUNNING','COMPLETED','FAILED')),
  manifest_fingerprint text not null,
  preflight_fingerprint text,
  result_fingerprint text,
  venue text not null,
  fee_bps_per_side numeric not null check (fee_bps_per_side >= 0),
  slippage_bps_per_side numeric not null check (slippage_bps_per_side >= 0),
  max_holding_seconds integer not null check (max_holding_seconds > 0),
  max_entry_delay_seconds integer check (max_entry_delay_seconds is null or max_entry_delay_seconds >= 0),
  manifest_payload jsonb not null,
  preflight_payload jsonb,
  result_summary jsonb,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  unique (dataset_id, manifest_fingerprint)
);

create index if not exists replay_runs_dataset_idx
  on public.replay_runs (dataset_id, created_at desc);
create index if not exists replay_runs_status_idx
  on public.replay_runs (status, created_at desc);

create table if not exists public.paper_trades (
  trade_fingerprint text primary key,
  replay_run_id bigint not null references public.replay_runs(id) on delete cascade,
  rule_id text not null check (rule_id in ('A','B','C','D','E')),
  base_asset text not null,
  side text not null check (side in ('LONG','SHORT')),
  signal_time_unix bigint not null,
  entry_time_unix bigint not null,
  exit_time_unix bigint,
  exit_reason text not null,
  entry_fill_price numeric not null check (entry_fill_price > 0),
  exit_fill_price numeric check (exit_fill_price is null or exit_fill_price > 0),
  gross_return_pct numeric,
  net_return_pct numeric,
  mfe_pct numeric,
  mae_pct numeric,
  feature_snapshot jsonb not null default '{}'::jsonb,
  evaluation_horizons jsonb not null default '{}'::jsonb,
  source_payload jsonb not null,
  created_at timestamptz not null default now(),
  unique (replay_run_id, rule_id, base_asset, signal_time_unix)
);

create index if not exists paper_trades_run_rule_idx
  on public.paper_trades (replay_run_id, rule_id);
create index if not exists paper_trades_token_time_idx
  on public.paper_trades (base_asset, signal_time_unix desc);

alter table public.registry_snapshots enable row level security;
alter table public.wallet_registry enable row level security;
alter table public.wallet_events enable row level security;
alter table public.smart_money_signal_snapshots enable row level security;
alter table public.smart_money_signals enable row level security;
alter table public.token_price_bars enable row level security;
alter table public.replay_runs enable row level security;
alter table public.paper_trades enable row level security;

comment on table public.wallet_events is
  'Stage-8 normalized wallet events. UNIQUE(wallet, signature) is the canonical idempotency contract.';
comment on table public.smart_money_signals is
  'Stage-9 descriptive smart-money signals. No production strength score or entry rule is stored here.';
comment on table public.token_price_bars is
  'Causal OHLC archive for Stage-10 replay. Empirical replay consumes source_kind=REAL only.';
comment on table public.paper_trades is
  'Stage-10 paper trades. Candidate A-E results are experimental until Stage-11 validation.';
