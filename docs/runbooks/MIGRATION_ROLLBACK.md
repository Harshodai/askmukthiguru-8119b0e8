# Migration Rollback Runbook

## Purpose

Document how to revert Supabase migrations safely. Every schema-altering migration in `supabase/migrations/` must contain a commented-out `-- REVERT:` block that explains and contains the undo SQL. These blocks are human-reviewed, executable SQL comments; they are never run automatically.

## Policy

1. **Never auto-revert in production.** A revert is a manual operation performed by an engineer during an incident or a controlled drill.
2. **Read the `-- REVERT:` block first.** It contains the exact inverse operation and any preconditions (data cleanup, column renames, dependent-object drops, etc.).
3. **Prefer forward fix over rollback when data is at risk.** Rollbacks that drop columns, tables, or constraints destroy data; use them only when the migration itself is unsafe to keep in place.
4. **Run revert SQL inside a transaction when possible.** Test on a local or staging database first.
5. **Update this runbook when the revert strategy changes.** If a migration is amended, add a note in the Index below.

## Determining the Revert Strategy

| Migration type | Typical revert |
| --- | --- |
| CREATE TABLE / TYPE / FUNCTION | `DROP TABLE/TYPE/FUNCTION IF EXISTS ...` |
| ALTER TABLE ADD COLUMN | `ALTER TABLE ... DROP COLUMN IF EXISTS ...` |
| ALTER TABLE ADD CONSTRAINT | `ALTER TABLE ... DROP CONSTRAINT IF EXISTS ...` |
| CREATE INDEX | `DROP INDEX IF EXISTS ...` |
| GRANT/REVOKE | Inverse GRANT/REVOKE statement |
| RLS policy change | `DROP POLICY IF EXISTS ...` then recreate previous policy |
| Data seed / backfill | Manual data correction; often not reversible with a single command |
| Extension or publication change | Do not drop shared infra unless explicitly required |

## Index of Migrations and Revert Strategy

> Generated from `-- REVERT:` blocks in `supabase/migrations/*.sql`. Keep in sync when new migrations land.

| File | High-level change | Revert summary |
| --- | --- | --- |
| `20240430000000_schema.sql` | Base observability schema | Destructive: drop all created tables, `has_role`, and `app_role`. Only for fresh/dev reset. |
| `20260506061859_969175ae-50fb-4d23-a45d-262c10029c65.sql` | Satsang tables and triggers | Drop created tables/functions/triggers in dependency order. |
| `20260506061924_89930c43-e214-4471-b173-1cd05b2f866a.sql` | Daily teachings structure | Drop tables/types/indexes created by this migration. |
| `20260506061946_ef6edab1-60a5-4fe6-809b-7d93ba4b39ff.sql` | Satsang RLS policies | Drop policies and recreate prior state if needed. |
| `20260506064449_d698be63-b027-463b-ba24-a90cec443811.sql` | Chat session/message tables | Drop tables/indexes/functions; clean up dependent objects first. |
| `20260506064513_18ea0bdd-e54c-49c1-a175-4b15e21214cd.sql` | User profiles & auth hook | Drop table/function/trigger; restore default auth behavior. |
| `20260508043115_0eb9a75d-8aa0-4988-a3f6-0b4b012e5621.sql` | Knowledge base schema | Drop tables/types/functions created in this migration. |
| `20260509115452_6b12135e-bd5a-4f68-8a9f-ab1c00f93838.sql` | KB RLS policies | Drop policies added; note data loss implications. |
| `20260509180000_secure_realtime.sql` | Realtime publication/security | Revert publication changes and role grants carefully. |
| `20260511_create_daily_teachings_bucket.sql` | Storage bucket for daily teachings | Drop bucket and policies if empty; manual asset migration otherwise. |
| `20260515122052_4624ba2e-1e4f-4b2a-968d-c676bb9beecb.sql` | Prompts / prompt versions | Drop tables and restore any previous prompt storage. |
| `20260516182217_515238b1-b493-4e4e-88dc-75a5db2cb880.sql` | Model pricing / eval tables | Drop created tables; no row-level cleanup needed. |
| `20260516182245_44f5bf76-8079-446d-b0b3-74236330e7ff.sql` | App logs / telemetry tables | Drop tables/indexes; note log data loss. |
| `20260516190000_user_memory.sql` | User memory tables | Drop memory-related tables/functions; data loss. |
| `20260516191000_fix_telemetry_and_seed.sql` | Telemetry fixes and seed data | Revert column/index changes and seed inserts as documented. |
| `20260526050952_a6a2b7ca-beb1-4d07-a4c6-335de99b8dd2.sql` | Notebook / study tables | Drop tables and dependent objects. |
| `20260527060500_57f4da6f-be73-46d8-a87a-24534aeb92cd.sql` | Backend improvements batch | Multiple objects; follow the dependency-ordered drop block. |
| `20260530141027_7381bcc3-40f2-436d-9b37-5c182a838cb5.sql` | Router / decision tables | Drop tables/functions/policies in order. |
| `20260601050554_d184ca2a-1755-4713-9b5a-6572499cdf09.sql` | Ingest jobs / checkpoints | Drop created tables/types/functions. |
| `20260601090000_admin_telemetry_reliability_fields.sql` | Reliability columns | Drop added columns/indexes; data in those columns is lost. |
| `20260604000001_fix_trace_spans_span_name_compat.sql` | Trace spans compat fix | Revert the column/type/compat change per block. |
| `20260605023720_602a5230-c7aa-47c2-9b22-195342ada89b.sql` | Eval / safety event tables | Drop tables and indexes. |
| `20260606024228_4a5cf016-573e-47af-bef7-a9959217cfbc.sql` | Query clusters / feedback | Drop created tables/functions. |
| `20260607180000_memory_layer.sql` | Memory layer refactor | Drop new memory tables/functions; restore old layer if required. |
| `20260610055007_1750df65-b2d6-45db-ab95-8b2bba92d12b.sql` | Alert rules / events | Drop tables and related trigger functions. |
| `20260613043512_a3c17109-f08f-4b9c-9944-d265d1daa192.sql` | Trigger events / user feedback | Drop tables/functions/indexes. |
| `20260613120000_fix_memory_embedding_dims.sql` | Memory embedding dimension fix | Revert dimension-related column/type changes. |
| `20260613180000_fix_memory_to_1024_dim.sql` | Memory embedding to 1024 | Revert 1024-dim changes per block. |
| `20260615044110_ccb90a86-ce4b-42dd-b1d4-7cc0124d4933.sql` | Golden questions / eval runs | Drop tables/indexes. |
| `20260615120000_backend_improvements.sql` | Backend improvements batch | Follow multi-object drop block in dependency order. |
| `20260616050645_effd7cd1-c5a9-403c-abc7-053a5f5f932c.sql` | Annotations / retrieval events | Drop tables/indexes. |
| `20260616050717_7b7722a8-f581-4d55-bcae-7c4c45b30ab4.sql` | Chat response metadata | Drop added columns/indexes. |
| `20260617000000_add_dashboard_indexes.sql` | Dashboard indexes | `DROP INDEX IF EXISTS ...` for each index. |
| `20260618044620_58e0642d-38c0-469d-9bd5-b6e91fc32297.sql` | Tenant RLS step 1 | Drop policies/grants added; recreate previous state. |
| `20260618045331_cdb918bb-9241-493b-ab1a-5174b83c5710.sql` | Tenant RLS step 2 | Drop/recreate policies as documented. |
| `20260618100000_telemetry_hardening_indexes.sql` | Telemetry indexes | `DROP INDEX IF EXISTS ...` for each index. |
| `20260618110000_db_consolidation.sql` | Consolidation changes | Revert the specific consolidation per block. |
| `20260621033728_d14bd1cf-bb63-485e-871d-455aa729d6b2.sql` | User personas scene blocks | Drop tables/indexes. |
| `20260623000000_add_chat_queries_assistant_slug.sql` | Assistant slug column | `ALTER TABLE ... DROP COLUMN IF EXISTS assistant_slug`. |
| `20260626062100_create_router_decisions.sql` | Router decisions table | Drop table/indexes/policies. |
| `20260627120000_create_ingest_jobs.sql` | Ingest jobs table | Drop table/indexes/triggers. |
| `20260627130000_tenant_rls.sql` | Tenant RLS policies | Drop and recreate policies per block. |
| `20260627140000_user_episodes.sql` | User episodes table | Drop table/indexes/policies. |
| `20260630140000_study_notebooks.sql` | Study notebooks table | Drop table/indexes/policies. |
| `20260701140000_app_settings.sql` | App settings table | Drop table/indexes/policies. |
| `20260702150000_staging_quality_queue.sql` | Staging quality queue | Drop table/indexes/triggers. |
| `20260703160000_okf_review_queue.sql` | OKF review queue | Drop table/indexes/policies. |
| `20260703170000_gurus_and_configurations.sql` | Gurus/configurations | Drop tables/indexes/policies. |
| `20260704180000_create_ingestion_checkpoints.sql` | Ingestion checkpoints | Drop table/indexes. |
| `20260705000000_fix_memory_service_auth.sql` | Memory service auth fix | Revert grants/policies/functions per block. |
| `20260706035450_554143f3-5acc-4f23-a091-c6428071ff71.sql` | User course progress | Drop table/indexes/policies. |
| `20260708021442_7a1a7776-3fef-4f0b-b511-d50ecdd20d7d.sql` | User streaks / retention | Drop tables/indexes. |
| `20260710000000_add_guru_memories_missing_columns.sql` | Missing columns to guru_memories | `ALTER TABLE ... DROP COLUMN IF EXISTS ...` for each column. |
| `20260711000000_enable_rls_on_all_tables.sql` | Enable RLS on all tables | Disable RLS or restore previous policy state per table. |
| `20260712000000_add_retention_and_summary.sql` | Retention and summary columns | Drop added columns/indexes. |
| `20260713000000_create_push_devices.sql` | Push devices table | Drop table/indexes/policies. |
| `20260713000001_user_retention_cards.sql` | User retention cards | Drop table/indexes/policies. |
| `20260714000000_harden_rls_and_security_invoker.sql` | RLS hardening | Revert policy/security invoker changes per block. |
| `20260714051557_c3977534-69e8-43c4-9427-699ea9b00d06.sql` | Daily teachings policies | Drop/recreate policies per block. |
| `20260714064138_12207701-9e67-4374-97a5-774bc440fe73.sql` | OKF queue policies | Drop/recreate policies per block. |
| `20260714071022_6c0e906c-9864-443b-bb1b-928c3c846aca.sql` | Chat messages RLS | Drop/recreate policies per block. |
| `20260714080216_b87a05f0-8df7-4370-82ad-1833dd26e6aa.sql` | Router decisions RLS | Drop/recreate policies per block. |
| `20260715000000_harden_linter_warnings.sql` | Linter warning fixes | Revert lint-driven renames/grants per block. |
| `20260715010000_fix_prompt_versions_and_app_settings.sql` | Prompt versions / app settings fix | Revert column/constraint changes per block. |
| `20260715020000_cancel_flow.sql` | Cancel flow support | Drop columns/constraints/functions per block. |
| `20260715050512_8ab790ce-1979-4afc-8d5f-5db683c9e421.sql` | User streaks step 1 | Drop/recreate objects per block. |
| `20260715051301_bb0ec1c6-ee99-44ff-bc91-2d7ff2fdc403.sql` | User streaks step 2 | Drop/recreate objects per block. |
| `20260715052416_cbbec360-6db7-44c7-be78-87c9f9cc91ff.sql` | User streaks step 3 | Drop/recreate objects per block. |
| `20260717191006_second_brain_vault.sql` | Second brain vault table | Drop table/indexes/policies/functions. |
| `20260718000000_user_streaks.sql` | User streaks table | Drop table/indexes/policies. |
| `20260718120000_add_unique_session_summary.sql` | Unique session summary | Drop constraint/index/column per block. |
| `20260718120001_second_brain_keys_table.sql` | Second brain keys table | Drop table/indexes/policies. |
| `20260722000000_add_citation_verification_columns.sql` | Citation verification columns | Drop added columns/indexes. |
| `20260722090000_drop_match_kb_chunks_768.sql` | Drop dead match function | Recreate the dropped function if still required. |
| `20260724000000_allow_assistant_role_chat_messages.sql` | Allow assistant role in chat_messages | Restore two-role CHECK constraint; clean assistant rows first. |
| `20260724054031_41ce0885-a2cf-4301-9911-516ba2b8d26a.sql` | Scene blocks / skills policies | Drop/recreate policies per block. |
| `20260724080000_harden_security_and_rls_lints.sql` | Security/RLS lint fixes | Revert policy/grant changes per block. |
| `20260724090000_drop_permissive_daily_teachings_policies.sql` | Drop permissive policies | Recreate previous policies if needed. |
| `20260728000000_create_user_personas.sql` | User personas table | Drop table/indexes/policies. |
| `20260728103548_85070891-f7bf-4835-94db-4246463b3813.sql` | User scene blocks & skills | Drop tables/indexes/policies. |
| `20260729000000_create_user_scene_blocks_and_skills.sql` | Scene blocks/skills creation | Drop tables/indexes/policies. |
| `20260730000000_verify_rls_with_check.sql` | WITH CHECK migration | Drop/recreate policies with correct USING/WITH CHECK. |
| `20260730044540_f2e71129-2f79-4b21-823c-2e888e6c82e9.sql` | Healing courses table | Drop table/indexes/policies. |
| `20260801000000_user_course_progress_one_active.sql` | One active course constraint | Drop trigger/constraint; restore previous allow-many behavior. |
| `20260804000001_add_with_check_to_tenant_rls.sql` | Add WITH CHECK to tenant RLS | Drop/recreate policies per block. |
| `20260804000002_revoke_router_decisions_anon_grant.sql` | Revoke anon grant | Re-grant anon permission only if intentionally required. |
| `20260804000003_drop_kb_chunks_dead_column.sql` | Drop dead column | `ALTER TABLE ... ADD COLUMN ...` to recreate if needed. |
| `20260804000004_add_chat_messages_composite_index.sql` | Composite index | `DROP INDEX IF EXISTS ...`. |
| `20260804000006_add_push_devices_user_id_index.sql` | Push devices index | `DROP INDEX IF EXISTS ...`. |

## How to Perform a Rollback

1. Identify the migration to revert and read its `-- REVERT:` block in full.
2. Open a transaction in the target database (local/staging first, then production).
3. Run the undo SQL from the block line by line. Pay attention to `NOTE:` warnings about data cleanup.
4. Verify the expected state: `\d` table descriptions, `\dp` policies, `
SELECT count(*)` sanity checks.
5. If production, record the rollback in the incident log and notify the team.
6. Optionally mark the migration as not-applied in local state only if you are using a local migration tracker; Supabase migrations themselves are immutable.

## CI Enforcement

The workflow `.github/workflows/migration-revert-check.yml` fails a PR if any new or changed migration in `supabase/migrations/` does not contain `-- REVERT:`.
