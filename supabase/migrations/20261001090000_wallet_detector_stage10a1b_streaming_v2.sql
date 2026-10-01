-- Stage 10A-1B V2: streaming historical scanner.
-- Fresh V2 schema: raw and normalized transaction payloads are never durable
-- evidence. The scanner keeps only compact resume state, closed-trade summaries,
-- and the final Stage-4/5 profile.

create table if not exists public.wallet_history_scan_state (
  universe_fingerprint text not null,
  wallet text not null,
  version text not null default 'wallet-s10a1b-stream-v2',
  provider text not null default 'indexed_gtfa',
  source_label text,
  source_origin text,
  history_as_of_unix bigint not null,
  scan_exhausted boolean not null default false,
  history_complete boolean not null default false,
  next_pagination_token text,
  last_signature text,
  pages_fetched_total integer not null default 0,
  transactions_scanned_total bigint not null default 0,
  normalized_events_total bigint not null default 0,
  normalization_errors_total bigint not null default 0,
  closed_trade_summary_count bigint not null default 0,
  stage3_state jsonb not null default '{}'::jsonb,
  profile_finalized_at timestamptz,
  updated_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  primary key (universe_fingerprint, wallet)
);

create index if not exists wallet_history_scan_state_complete_idx
  on public.wallet_history_scan_state
  (history_complete, history_as_of_unix);

create table if not exists public.wallet_historical_trade_summaries (
  universe_fingerprint text not null,
  wallet text not null,
  episode_id text not null,
  base_asset text not null,
  quote_asset text not null,
  quote_is_usd boolean not null default false,
  opened_at bigint,
  closed_at bigint not null,
  opened_slot bigint,
  close_slot bigint,
  holding_seconds bigint,
  realized_cost_quote numeric not null,
  realized_proceeds_quote numeric not null,
  realized_pnl_quote numeric not null,
  realized_roi_pct numeric not null,
  network_fee_lamports bigint not null default 0,
  buy_count integer not null default 0,
  sell_count integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (universe_fingerprint, wallet, episode_id)
);

create index if not exists wallet_historical_trade_summaries_wallet_time_idx
  on public.wallet_historical_trade_summaries
  (universe_fingerprint, wallet, closed_at, close_slot);

create table if not exists public.wallet_historical_profiles (
  universe_fingerprint text not null,
  wallet text not null,
  history_as_of_unix bigint not null,
  stage4_version text,
  stage5_version text,
  closed_trade_count integer not null default 0,
  performance_payload jsonb not null,
  classification_payload jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (universe_fingerprint, wallet)
);

alter table public.wallet_history_scan_state enable row level security;
alter table public.wallet_historical_trade_summaries enable row level security;
alter table public.wallet_historical_profiles enable row level security;

comment on table public.wallet_history_scan_state is
  'Stage 10A-1B V2 compact checkpoint. Stores only resume cursor and open Stage-3 inventory state; no raw transaction history.';
comment on table public.wallet_historical_trade_summaries is
  'Compact clean closed-trade output emitted by the Stage 10A-1B V2 streaming scanner.';
comment on table public.wallet_historical_profiles is
  'Final Stage-4 performance and Stage-5 classification output for a completed historical streaming scan.';
