-- ============================================================================
-- Migration: 20261114000000_message_citations_provenance_defaults.sql
-- Provenance defaults in the citation ledger (CLAUDE.md / AGENTS.md X40).
--
-- 20261107000000 created two column defaults that assert provenance nobody
-- verified:
--     rights_status    TEXT NOT NULL DEFAULT 'licensed'
--     speaker_verified BOOLEAN NOT NULL DEFAULT true
-- A row inserted without those columns therefore claims a cleared licence and a
-- voice-verified speaker. That is the same defect the 2026-11-13 client fix
-- removed from src/lib/chatStorage.ts (citationLedgerFlags), left in the table.
-- The only writer (chatStorage.ts:483-503) always supplies both columns
-- explicitly, so dropping the defaults changes no working insert path; it makes
-- an omission an error instead of a false assertion.
--
-- The vocabulary constraint stops a typo or a future writer from inventing a
-- status the readers do not know. 'licensed' stays permitted because it is the
-- corpus/rights-register vocabulary that service_role backfills use; it may only
-- be written explicitly.
--
-- REVERT:
-- ALTER TABLE public.message_citations DROP CONSTRAINT IF EXISTS message_citations_rights_status_vocabulary;
-- ALTER TABLE public.message_citations ALTER COLUMN rights_status SET DEFAULT 'licensed';
-- ALTER TABLE public.message_citations ALTER COLUMN speaker_verified SET DEFAULT true;
-- ============================================================================

ALTER TABLE public.message_citations
    ALTER COLUMN rights_status DROP DEFAULT;

ALTER TABLE public.message_citations
    ALTER COLUMN speaker_verified DROP DEFAULT;

ALTER TABLE public.message_citations
    DROP CONSTRAINT IF EXISTS message_citations_rights_status_vocabulary;

ALTER TABLE public.message_citations
    ADD CONSTRAINT message_citations_rights_status_vocabulary
    CHECK (rights_status IN ('cleared', 'unverified', 'licensed', 'revoked'));

COMMENT ON COLUMN public.message_citations.rights_status IS
    'Rights state for this cited span. No column default: an insert must state it. '
    'Client writes use cleared|unverified (citationLedgerFlags); licensed|revoked are for '
    'service_role backfills from the rights register. Never default a missing state to licensed.';

COMMENT ON COLUMN public.message_citations.speaker_verified IS
    'True only when the speaker attribution was verified, never defaulted. '
    'See services/first_person_serving_contract.py and X23.';
