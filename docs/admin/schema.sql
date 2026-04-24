-- AskMukthiGuru Admin Observability — full schema.
-- Run this once when Lovable Cloud is enabled.
-- Designed for graceful degradation: pgvector and pg_cron are optional upgrades.

-- ============================================================================
-- ROLES
-- ============================================================================
create type public.app_role as enum ('admin', 'user');

create table public.user_roles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade not null,
  role app_role not null,
  unique (user_id, role)
);

alter table public.user_roles enable row level security;

create or replace function public.has_role(_user_id uuid, _role app_role)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.user_roles
    where user_id = _user_id and role = _role
  )
$$;

create policy "Admins can read user_roles" on public.user_roles
  for select to authenticated using (public.has_role(auth.uid(), 'admin'));

-- ============================================================================
-- CORE TELEMETRY
-- ============================================================================
create table public.chat_sessions (
  id uuid primary key default gen_random_uuid(),
  anon_user_id text, channel text,
  started_at timestamptz default now()
);

create table public.prompt_versions (
  id uuid primary key default gen_random_uuid(),
  name text not null, version int not null,
  content text not null, active boolean default false,
  created_at timestamptz default now(), created_by uuid,
  unique (name, version)
);

create table public.chat_queries (
  id uuid primary key default gen_random_uuid(),
  session_id uuid references chat_sessions(id) on delete cascade,
  anon_user_id text,
  query_text text not null,
  prompt_version_id uuid references prompt_versions(id),
  model text, prompt_tokens int, completion_tokens int,
  cost_estimate numeric, latency_ms int, status text,
  created_at timestamptz default now()
);

create table public.retrieval_events (
  id uuid primary key default gen_random_uuid(),
  query_id uuid references chat_queries(id) on delete cascade,
  chunk_ids text[], source_docs text[], scores numeric[],
  top_k int, retrieval_hit boolean
);

create table public.chat_responses (
  id uuid primary key default gen_random_uuid(),
  query_id uuid references chat_queries(id) on delete cascade,
  response_text text, citations jsonb,
  faithfulness numeric, answer_relevancy numeric,
  context_precision numeric, context_recall numeric,
  hallucination_flag boolean, judge_reasoning text, confidence numeric,
  created_at timestamptz default now()
);

create table public.trigger_events (
  id uuid primary key default gen_random_uuid(),
  query_id uuid references chat_queries(id) on delete cascade,
  trigger_name text not null,
  metadata jsonb, created_at timestamptz default now()
);

create table public.user_feedback (
  id uuid primary key default gen_random_uuid(),
  response_id uuid references chat_responses(id) on delete cascade,
  rating smallint, accuracy smallint, comment text,
  created_at timestamptz default now()
);

create table public.trace_spans (
  id uuid primary key default gen_random_uuid(),
  query_id uuid references chat_queries(id) on delete cascade,
  parent_span_id uuid references trace_spans(id),
  name text not null, start_ms bigint, duration_ms int,
  attributes jsonb, created_at timestamptz default now()
);

create table public.safety_events (
  id uuid primary key default gen_random_uuid(),
  query_id uuid references chat_queries(id) on delete cascade,
  type text, severity text, excerpt text,
  created_at timestamptz default now()
);

create table public.golden_questions (
  id uuid primary key default gen_random_uuid(),
  question text, expected_answer text,
  expected_sources text[], tags text[], active boolean default true
);

create table public.eval_runs (
  id uuid primary key default gen_random_uuid(),
  triggered_by text,
  prompt_version_id uuid references prompt_versions(id),
  started_at timestamptz default now(), finished_at timestamptz,
  summary jsonb
);

create table public.eval_results (
  id uuid primary key default gen_random_uuid(),
  eval_run_id uuid references eval_runs(id) on delete cascade,
  golden_id uuid references golden_questions(id),
  faithfulness numeric, answer_relevancy numeric,
  context_precision numeric, context_recall numeric,
  passed boolean, response_text text
);

create table public.ingestion_runs (
  id uuid primary key default gen_random_uuid(),
  source text, chunks_added int, embedding_model text,
  duration_ms int, status text, error_log text,
  created_at timestamptz default now()
);

create table public.app_logs (
  id bigserial primary key,
  level text, message text, context jsonb,
  request_id text, created_at timestamptz default now()
);

create table public.model_pricing (
  model text primary key,
  input_per_1k numeric, output_per_1k numeric, currency text default 'USD'
);

create table public.query_clusters (
  query_id uuid primary key references chat_queries(id) on delete cascade,
  cluster_id int, cluster_label text,
  embedding jsonb  -- swap to vector(N) if pgvector is enabled
);

create table public.alert_rules (
  id uuid primary key default gen_random_uuid(),
  name text, metric text, comparator text, threshold numeric,
  window_minutes int, channel text, target text, active boolean default true
);

create table public.alert_events (
  id uuid primary key default gen_random_uuid(),
  rule_id uuid references alert_rules(id), value numeric,
  fired_at timestamptz default now(), resolved_at timestamptz
);

create table public.annotations (
  id uuid primary key default gen_random_uuid(),
  response_id uuid references chat_responses(id),
  reviewer_id uuid, label text, notes text,
  promoted_to_golden boolean default false,
  created_at timestamptz default now()
);

-- ============================================================================
-- RLS — admin-only SELECT on every telemetry table
-- ============================================================================
do $$
declare t text;
begin
  for t in select unnest(array[
    'chat_sessions','prompt_versions','chat_queries','retrieval_events',
    'chat_responses','trigger_events','user_feedback','trace_spans',
    'safety_events','golden_questions','eval_runs','eval_results',
    'ingestion_runs','app_logs','model_pricing','query_clusters',
    'alert_rules','alert_events','annotations'
  ]) loop
    execute format('alter table public.%I enable row level security', t);
    execute format(
      $f$create policy "Admins can read %1$s" on public.%1$I
         for select to authenticated using (public.has_role(auth.uid(), 'admin'))$f$, t);
  end loop;
end $$;

-- ============================================================================
-- INDEXES
-- ============================================================================
create index on chat_queries (created_at desc);
create index on chat_responses (hallucination_flag, created_at desc);
create index on trigger_events (trigger_name, created_at desc);
create index on trace_spans (query_id);
create index on safety_events (type, created_at desc);
create index on app_logs (created_at desc);

-- ============================================================================
-- OPTIONAL UPGRADES (no-op if extension unavailable)
-- ============================================================================
do $$ begin
  begin
    create extension if not exists vector;
    -- if it succeeds, follow up with: alter table query_clusters
    --   alter column embedding type vector(384) using embedding::text::vector;
  exception when others then null;
  end;
end $$;

do $$ begin
  begin
    alter publication supabase_realtime add table chat_queries;
  exception when others then null;
  end;
end $$;

-- ============================================================================
-- SEED FIRST ADMIN — replace UUID
-- ============================================================================
-- insert into user_roles (user_id, role)
-- values ('<your-auth.users-uuid>', 'admin');
