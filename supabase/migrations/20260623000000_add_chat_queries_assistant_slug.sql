-- Migration: add assistant_slug to chat_queries telemetry
-- Run this in your Supabase SQL Editor or via supabase migration new
-- The backend already writes this field in backend/app/telemetry_sink.py

-- Step 1: add nullable text column
alter table public.chat_queries
    add column if not exists assistant_slug text;

-- Step 2: optional index for admin dashboards / quality breakdowns by assistant
-- drop index if exists idx_chat_queries_assistant_slug;
create index if not exists idx_chat_queries_assistant_slug
    on public.chat_queries(assistant_slug)
    where assistant_slug is not null;

-- Step 3: optional helper view for assistant-level quality metrics
-- drop view if exists public.v_chat_queries_by_assistant;
create or replace view public.v_chat_queries_by_assistant as
select
    assistant_slug,
    count(*) as query_count,
    avg(latency_ms) as avg_latency_ms,
    avg(prompt_tokens) as avg_prompt_tokens,
    avg(completion_tokens) as avg_completion_tokens,
    max(created_at) as last_query_at
from public.chat_queries
where assistant_slug is not null
group by assistant_slug;

-- Step 4: update RLS policies if you have table-level policies that restrict columns.
-- No RLS change is strictly required because the backend writes via service role key.
-- If you want to expose assistant_slug to authenticated users, ensure the
-- existing select policy for chat_queries includes this column (RLS sees new
-- columns automatically unless a policy explicitly excludes them).
