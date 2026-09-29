alter table public.wallet_universe_snapshots
  add column if not exists refinement_version text,
  add column if not exists refinement_fingerprint text,
  add column if not exists trader_candidate_wallet_count integer,
  add column if not exists non_trader_activity_wallet_count integer,
  add column if not exists meme_buy_candidate_wallet_count integer,
  add column if not exists refinement_payload jsonb;

alter table public.wallet_universe_candidates
  add column if not exists refinement_version text,
  add column if not exists refinement_record_fingerprint text,
  add column if not exists candidate_status text,
  add column if not exists trader_candidate boolean,
  add column if not exists meme_buy_candidate boolean,
  add column if not exists historical_backfill_eligible boolean,
  add column if not exists trader_event_count integer,
  add column if not exists buy_event_count integer,
  add column if not exists sell_event_count integer,
  add column if not exists meme_buy_event_count integer,
  add column if not exists observed_base_assets text[],
  add column if not exists refinement_payload jsonb;

alter table public.wallet_universe_evidence
  add column if not exists refinement_version text,
  add column if not exists refinement_event_fingerprint text,
  add column if not exists stage2_version text,
  add column if not exists event_type text,
  add column if not exists side text,
  add column if not exists base_asset text,
  add column if not exists quote_asset text,
  add column if not exists confidence text,
  add column if not exists trader_candidate_event boolean,
  add column if not exists meme_buy_candidate_event boolean,
  add column if not exists refinement_reason text,
  add column if not exists stage2_normalized_payload jsonb;

alter table public.wallet_universe_candidates
  drop constraint if exists wallet_universe_candidates_refinement_status_check;
alter table public.wallet_universe_candidates
  add constraint wallet_universe_candidates_refinement_status_check
  check (
    candidate_status is null
    or candidate_status in ('TRADER_CANDIDATE', 'NON_TRADER_ACTIVITY')
  );

alter table public.wallet_universe_candidates
  drop constraint if exists wallet_universe_candidates_meme_implies_trader_check;
alter table public.wallet_universe_candidates
  add constraint wallet_universe_candidates_meme_implies_trader_check
  check (
    coalesce(meme_buy_candidate, false) = false
    or trader_candidate is true
  );

alter table public.wallet_universe_evidence
  drop constraint if exists wallet_universe_evidence_meme_implies_trader_check;
alter table public.wallet_universe_evidence
  add constraint wallet_universe_evidence_meme_implies_trader_check
  check (
    coalesce(meme_buy_candidate_event, false) = false
    or trader_candidate_event is true
  );

create index if not exists wallet_universe_candidates_trader_idx
  on public.wallet_universe_candidates
  (trader_candidate, historical_backfill_eligible);

create index if not exists wallet_universe_candidates_meme_idx
  on public.wallet_universe_candidates
  (meme_buy_candidate);

comment on column public.wallet_universe_candidates.trader_candidate is
  'Stage 10A-1A factual prefilter: at least one Stage-2 SWAP with BUY/SELL side.';
comment on column public.wallet_universe_candidates.meme_buy_candidate is
  'Stage 10A-1A causal meme-track seed: at least one Stage-2 BUY event; not a Meme Hunter label.';
