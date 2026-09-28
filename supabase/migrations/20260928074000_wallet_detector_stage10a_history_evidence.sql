create table if not exists public.historical_wallet_transactions (
  wallet text not null,
  signature text not null,
  chain text not null default 'solana',
  source text not null default 'helius_gtfa',
  slot bigint,
  block_time_unix bigint,
  raw_payload jsonb not null,
  fetched_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  primary key (wallet, signature)
);

create index if not exists historical_wallet_transactions_time_idx
  on public.historical_wallet_transactions (wallet, block_time_unix);
create index if not exists historical_wallet_transactions_signature_idx
  on public.historical_wallet_transactions (signature);

create table if not exists public.normalized_wallet_history (
  wallet text not null,
  signature text not null,
  stage2_version text not null default 'wallet-s2-v1',
  chain text not null default 'solana',
  slot bigint,
  block_time_unix bigint not null,
  event_type text not null,
  side text not null,
  base_asset text,
  quote_asset text,
  base_amount numeric,
  quote_amount numeric,
  usd_notional numeric,
  execution_price numeric,
  network_fee_lamports bigint,
  normalized_payload jsonb not null,
  created_at timestamptz not null default now(),
  primary key (wallet, signature),
  constraint normalized_wallet_history_raw_fkey
    foreign key (wallet, signature)
    references public.historical_wallet_transactions(wallet, signature)
    on delete cascade,
  constraint normalized_wallet_history_side_check
    check (side in ('BUY','SELL','SWAP','NONE')),
  constraint normalized_wallet_history_event_type_check
    check (
      event_type in (
        'SWAP','TRANSFER_IN','TRANSFER_OUT','WRAP','UNWRAP',
        'OTHER','FAILED','AMBIGUOUS'
      )
    )
);

create index if not exists normalized_wallet_history_wallet_time_idx
  on public.normalized_wallet_history (wallet, block_time_unix);
create index if not exists normalized_wallet_history_base_time_idx
  on public.normalized_wallet_history (base_asset, block_time_unix)
  where base_asset is not null;
create index if not exists normalized_wallet_history_trade_idx
  on public.normalized_wallet_history (wallet, event_type, side, block_time_unix);

alter table public.historical_wallet_transactions enable row level security;
alter table public.normalized_wallet_history enable row level security;

comment on table public.historical_wallet_transactions is
  'Immutable Helius historical evidence keyed by wallet + transaction signature.';
comment on table public.normalized_wallet_history is
  'Stage-2 normalized historical wallet events, including pre-qualification evidence used for causal Stage-3-to-7 reconstruction.';
