-- ==============================================================================
-- Schema: Frontier AI Product Harness & Corpus Governance
-- Application: AskMukthiGuru
-- Target: PostgreSQL 16+ (Supabase / Neon / AWS RDS)
-- ==============================================================================

-- Enable UUID extension
create extension if not exists "pgcrypto";

-- ------------------------------------------------------------------------------
-- 1. Source Releases & Lineage Catalog
-- Tracks every ingested media broadcast, discourse, or text document.
-- ------------------------------------------------------------------------------
create table if not exists public.source_releases (
    id uuid primary key default gen_random_uuid(),
    source_url text not null unique,
    canonical_id text not null,
    title text not null,
    speaker_id text not null,
    media_type text not null check (media_type in ('youtube_video', 'audio_broadcast', 'transcribed_discourse', 'scanned_book', 'qa_archive')),
    published_at timestamptz not null,
    release_version integer not null default 1,
    content_checksum char(64) not null, -- SHA-256 hash of entire verbatim source text
    audio_file_duration_ms integer,
    audio_archive_path text,
    rights_clearance_id text not null,
    domain_rights_status text not null default 'unverified' check (domain_rights_status in ('licensed', 'unverified', 'revoked', 'quarantined')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_source_releases_speaker on public.source_releases (speaker_id);
create index if not exists idx_source_releases_rights on public.source_releases (domain_rights_status);
create index if not exists idx_source_releases_checksum on public.source_releases (content_checksum);

-- ------------------------------------------------------------------------------
-- 2. Content Rights Register
-- Independent legal authority register governing content distribution.
-- Invariant X40: Rights status originates solely from this register.
-- ------------------------------------------------------------------------------
create table if not exists public.content_rights_register (
    id uuid primary key default gen_random_uuid(),
    clearance_id text not null unique,
    source_prefix text not null,
    licensor_name text not null,
    status text not null check (status in ('active_licensed', 'pending_verification', 'revoked', 'expired')),
    permitted_territories text[] not null default '{"GLOBAL"}',
    attribution_requirements text not null,
    effective_from timestamptz not null,
    expires_at timestamptz,
    register_hash char(64) not null, -- SHA-256 hash of legal document / manifest
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_rights_register_status on public.content_rights_register (status);
create index if not exists idx_rights_register_clearance on public.content_rights_register (clearance_id);

-- ------------------------------------------------------------------------------
-- 3. Corpus Gate Rejections
-- Invariant X40: Every item rejected by quality gates MUST be recorded here.
-- Never silently discard ingestion failures.
-- ------------------------------------------------------------------------------
create table if not exists public.corpus_gate_rejections (
    id uuid primary key default gen_random_uuid(),
    source_url text not null,
    source_release_version integer not null,
    chunk_index integer,
    tier text not null check (tier in ('rights_gate', 'asr_verification', 'speaker_diarization', 'quality_filter', 'content_integrity')),
    rejection_code text not null, -- e.g., 'unlicensed_rights', 'voice_mismatch', 'zero_byte_wav'
    rejection_message text not null,
    raw_payload jsonb not null default '{}'::jsonb,
    source_coordinates jsonb not null default '{}'::jsonb, -- e.g., { start_ms, end_ms, span_index }
    quarantined_at timestamptz not null default now()
);

create index if not exists idx_gate_rejections_source on public.corpus_gate_rejections (source_url);
create index if not exists idx_gate_rejections_tier on public.corpus_gate_rejections (tier);
create index if not exists idx_gate_rejections_code on public.corpus_gate_rejections (rejection_code);

-- ------------------------------------------------------------------------------
-- 4. Serving Cache Fingerprints (Cryptographic Exact Cache)
-- Invariant X13: Binds 6 cryptographic dimensions to prevent cache poisoning.
-- ------------------------------------------------------------------------------
create table if not exists public.serving_cache_fingerprints (
    cache_key char(64) primary key, -- SHA-256 of composite request factors
    query_normalized text not null,
    prompt_template_hash char(64) not null,
    model_revision text not null,
    collection_version text not null,
    rights_register_hash char(64) not null,
    policy_fingerprint text not null,
    response_payload jsonb not null,
    hit_count integer not null default 1,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null
);

create index if not exists idx_cache_expires_at on public.serving_cache_fingerprints (expires_at);

-- ------------------------------------------------------------------------------
-- 5. Human Review Packets (Speaker Conflicts & Governance)
-- Invariant X41: Human gates are packets, not prose.
-- Unsigned rows remain unreviewed; automated agents are barred from signing off.
-- ------------------------------------------------------------------------------
create table if not exists public.human_review_packets (
    id uuid primary key default gen_random_uuid(),
    packet_type text not null check (packet_type in ('speaker_conflict', 'rights_ambiguity', 'high_loss_content')),
    source_url text not null,
    video_id text not null,
    audio_start_ms integer not null,
    audio_end_ms integer not null,
    wav_sha256 char(64) not null,
    ecapa_score numeric(6, 4) not null,
    expected_guru text not null,
    detected_guru text,
    provenance_hash char(64) not null, -- Hash of input columns; editing inputs invalidates hash
    decision text check (decision in ('approved_guru', 'reclassified_channel', 'quarantined_discard')),
    decision_notes text,
    reviewer_identity text,
    reviewed_at timestamptz,
    created_at timestamptz not null default now()
);

create index if not exists idx_review_packets_status on public.human_review_packets (decision) where decision is null;
create index if not exists idx_review_packets_video on public.human_review_packets (video_id);

-- ------------------------------------------------------------------------------
-- 6. Evaluation Manifests & Run Ledgers
-- Invariant X41: Graded evidence requires collection fingerprint.
-- ------------------------------------------------------------------------------
create table if not exists public.eval_runs (
    id uuid primary key default gen_random_uuid(),
    run_name text not null,
    evaluator_version text not null,
    collection_fingerprint char(64) not null, -- Read-only fingerprint from collection_fingerprint.py
    total_cases integer not null,
    passed_cases integer not null default 0,
    failed_cases integer not null default 0,
    avg_faithfulness numeric(4, 3) not null default 0.0,
    avg_relevance numeric(4, 3) not null default 0.0,
    citation_accuracy numeric(4, 3) not null default 0.0,
    manifest_payload jsonb not null default '{}'::jsonb,
    executed_by text not null,
    started_at timestamptz not null default now(),
    completed_at timestamptz
);

create table if not exists public.eval_case_results (
    id uuid primary key default gen_random_uuid(),
    eval_run_id uuid not null references public.eval_runs(id) on delete cascade,
    case_identifier text not null,
    query_text text not null,
    expected_teaching text not null,
    actual_teaching text,
    status text not null check (status in ('pass', 'fail', 'abstained', 'draft_needs_owner_review')),
    faithfulness_score numeric(4, 3),
    relevance_score numeric(4, 3),
    citations_verified boolean not null default false,
    latency_ms integer not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_eval_results_run on public.eval_case_results (eval_run_id);
create index if not exists idx_eval_results_status on public.eval_case_results (status);

-- ------------------------------------------------------------------------------
-- 7. Row Level Security (RLS) Policies
-- ------------------------------------------------------------------------------

alter table public.source_releases enable row level security;
alter table public.content_rights_register enable row level security;
alter table public.corpus_gate_rejections enable row level security;
alter table public.serving_cache_fingerprints enable row level security;
alter table public.human_review_packets enable row level security;
alter table public.eval_runs enable row level security;
alter table public.eval_case_results enable row level security;

-- Public read access restricted exclusively to licensed releases
create policy "Public can view active licensed source releases"
    on public.source_releases for select
    using (domain_rights_status = 'licensed');

-- Internal service role access (backend API full control)
create policy "Service role has full access to source releases"
    on public.source_releases for all
    using (auth.role() = 'service_role');

create policy "Service role has full access to rights register"
    on public.content_rights_register for all
    using (auth.role() = 'service_role');

create policy "Service role has full access to gate rejections"
    on public.corpus_gate_rejections for all
    using (auth.role() = 'service_role');

create policy "Service role has full access to cache fingerprints"
    on public.serving_cache_fingerprints for all
    using (auth.role() = 'service_role');

create policy "Service role has full access to human review packets"
    on public.human_review_packets for all
    using (auth.role() = 'service_role');

create policy "Service role has full access to eval runs"
    on public.eval_runs for all
    using (auth.role() = 'service_role');

create policy "Service role has full access to eval case results"
    on public.eval_case_results for all
    using (auth.role() = 'service_role');
