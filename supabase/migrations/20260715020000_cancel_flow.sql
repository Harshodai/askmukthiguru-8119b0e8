-- Cancel flow (Task B3a): exit surveys, save offers, cancellations.
-- Implements the 5-stage churn-prevention flow with real persistence + win-back emails.

-- Exit surveys (Stage 2): reason + optional details collected before save offer.
create table if not exists exit_surveys (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  reason varchar(50) not null,
  details text,
  responded_to boolean default false,
  response_type varchar(20),  -- 'saved', 'cancelled', 'paused'
  created_at timestamptz default now()
);

-- Save offers (Stage 3): which offer was presented and whether accepted.
create table if not exists save_offers (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  offer_type varchar(50) not null,
  accepted boolean not null,
  applied_at timestamptz default now(),
  expires_at timestamptz
);

-- Cancellations (Stage 4/5): scheduling + win-back email tracking.
create table if not exists cancellations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  status varchar(20) not null,  -- 'scheduled', 'completed', 'reactivated'
  reason varchar(50),
  data_retention varchar(20),  -- 'keep_30_days', 'keep_90_days', 'delete_immediately'
  scheduled_deletion timestamptz,
  completed_deletion timestamptz,
  reactivated_at timestamptz,
  win_back_emails_sent jsonb default '[]'::jsonb,  -- ["day0","day3","day14","day30"]
  created_at timestamptz default now()
);

-- Indexes
create index if not exists idx_exit_surveys_user on exit_surveys(user_id);
create index if not exists idx_exit_surveys_reason on exit_surveys(reason);
create index if not exists idx_save_offers_user on save_offers(user_id);
create index if not exists idx_cancellations_status on cancellations(status);
create index if not exists idx_cancellations_scheduled on cancellations(scheduled_deletion);
create index if not exists idx_cancellations_user on cancellations(user_id);

-- Row Level Security: users can only touch their own rows; service role bypasses.
alter table exit_surveys enable row level security;
alter table save_offers enable row level security;
alter table cancellations enable row level security;

create policy users_select_own on exit_surveys for select
  using (auth.uid() = user_id);
create policy users_insert_own on exit_surveys for insert
  with check (auth.uid() = user_id);
create policy users_update_own on exit_surveys for update
  using (auth.uid() = user_id);

create policy users_select_own on save_offers for select
  using (auth.uid() = user_id);
create policy users_insert_own on save_offers for insert
  with check (auth.uid() = user_id);
create policy users_update_own on save_offers for update
  using (auth.uid() = user_id);

create policy users_select_own on cancellations for select
  using (auth.uid() = user_id);
create policy users_insert_own on cancellations for insert
  with check (auth.uid() = user_id);
create policy users_update_own on cancellations for update
  using (auth.uid() = user_id);

-- Notify PostgREST to reload schema cache (PGRST204 fix pattern).
notify pgrst, 'reload schema';