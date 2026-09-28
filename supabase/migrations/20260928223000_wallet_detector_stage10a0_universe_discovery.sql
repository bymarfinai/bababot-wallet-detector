create table if not exists public.wallet_universe_snapshots (
  universe_fingerprint text primary key,
  version text not null,
  chain text not null default 'solana',
  source_kind text not null,
  source_label text not null,
  source_origin text not null,
  requested_start_slot bigint not null,
  requested_end_slot bigint not null,
  cutoff_unix bigint,
  scanned_block_count integer not null check (scanned_block_count >= 0),
  transaction_count integer not null check (transaction_count >= 0),
  eligible_transaction_count integer not null check (eligible_transaction_count >= 0),
  candidate_wallet_count integer not null check (candidate_wallet_count >= 0),
  source_payload jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists public.wallet_universe_candidates (
  universe_fingerprint text not null
    references public.wallet_universe_snapshots(universe_fingerprint)
    on delete cascade,
  wallet text not null,
  record_fingerprint text not null,
  chain text not null default 'solana',
  discovered_at_unix bigint not null,
  first_observed_at_unix bigint not null,
  last_observed_at_unix bigint not null,
  first_observed_slot bigint not null,
  last_observed_slot bigint not null,
  activity_count integer not null check (activity_count > 0),
  distinct_changed_mint_count integer not null check (distinct_changed_mint_count >= 0),
  evidence_signature_count integer not null check (evidence_signature_count > 0),
  discovery_source text not null,
  discovery_reason text not null,
  changed_mints text[] not null default '{}',
  evidence_signatures text[] not null default '{}',
  source_payload jsonb not null,
  created_at timestamptz not null default now(),
  primary key (universe_fingerprint, wallet),
  unique (universe_fingerprint, record_fingerprint)
);

create index if not exists wallet_universe_candidates_wallet_idx
  on public.wallet_universe_candidates (wallet);
create index if not exists wallet_universe_candidates_discovered_idx
  on public.wallet_universe_candidates (discovered_at_unix);
create index if not exists wallet_universe_candidates_mints_gin_idx
  on public.wallet_universe_candidates using gin (changed_mints);

create table if not exists public.wallet_universe_evidence (
  universe_fingerprint text not null,
  wallet text not null,
  signature text not null,
  slot bigint not null,
  block_time_unix bigint not null,
  discovery_source text not null,
  discovery_reason text not null,
  changed_mints text[] not null default '{}',
  evidence_payload jsonb not null,
  created_at timestamptz not null default now(),
  primary key (universe_fingerprint, wallet, signature),
  foreign key (universe_fingerprint, wallet)
    references public.wallet_universe_candidates(universe_fingerprint, wallet)
    on delete cascade
);

create index if not exists wallet_universe_evidence_time_idx
  on public.wallet_universe_evidence (wallet, block_time_unix);
create index if not exists wallet_universe_evidence_signature_idx
  on public.wallet_universe_evidence (signature);

alter table public.wallet_universe_snapshots enable row level security;
alter table public.wallet_universe_candidates enable row level security;
alter table public.wallet_universe_evidence enable row level security;

comment on table public.wallet_universe_snapshots is
  'Stage 10A-0 deterministic candidate-wallet universes discovered from real Solana activity.';
comment on table public.wallet_universe_candidates is
  'Stage 10A-0 candidate wallets. Discovery is factual and does not imply smart-money qualification.';
comment on table public.wallet_universe_evidence is
  'Per-signature provenance explaining why a wallet entered a Stage 10A-0 candidate universe.';
