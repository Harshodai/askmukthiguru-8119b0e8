"""Pins for the citation-ledger provenance defaults (2026-11-14).

`20261107000000_create_message_citations.sql` created the ledger with
`rights_status DEFAULT 'licensed'` and `speaker_verified DEFAULT true`, so a row
inserted without those columns asserted a cleared licence and a verified voice.
That is the same defect the 2026-11-13 client fix removed from
`src/lib/chatStorage.ts::citationLedgerFlags` (X40: never default missing rights
to licensed). `20261114000000_message_citations_provenance_defaults.sql` drops
both defaults.

These are SOURCE-LEVEL pins: they read the migration and the committed schema
snapshot, not a live database. The live proof (omission rejected, explicit
accepted, invented status rejected, owner-scoped RLS allow + deny) was run
against the local stack and is recorded in
`docs/analysis/ENGINEERING_READINESS_AUDIT_2026-11-13.md` §8.2.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20261114000000_message_citations_provenance_defaults.sql"
)
ORIGINAL = REPO_ROOT / "supabase" / "migrations" / "20261107000000_create_message_citations.sql"
SNAPSHOT = REPO_ROOT / "supabase" / "schema_snapshot.sql"


def _sql(path: Path) -> str:
    """SQL with single-line comments stripped, so a commented-out statement cannot satisfy a pin."""
    text = path.read_text(encoding="utf-8")
    return re.sub(r"--.*$", "", text, flags=re.MULTILINE)


def test_the_unsafe_defaults_were_real() -> None:
    """The defect this migration fixes must be visible in the original migration."""
    sql = _sql(ORIGINAL)
    assert re.search(r"rights_status\s+TEXT\s+NOT\s+NULL\s+DEFAULT\s+'licensed'", sql, re.I)
    assert re.search(r"speaker_verified\s+BOOLEAN\s+NOT\s+NULL\s+DEFAULT\s+true", sql, re.I)


def test_migration_drops_both_provenance_defaults() -> None:
    sql = _sql(MIGRATION)
    assert re.search(r"ALTER\s+COLUMN\s+rights_status\s+DROP\s+DEFAULT", sql, re.I)
    assert re.search(r"ALTER\s+COLUMN\s+speaker_verified\s+DROP\s+DEFAULT", sql, re.I)


def test_migration_constrains_the_rights_vocabulary() -> None:
    sql = _sql(MIGRATION)
    assert re.search(r"CHECK\s*\(\s*rights_status\s+IN\s*\(", sql, re.I)
    for status in ("cleared", "unverified", "licensed", "revoked"):
        assert f"'{status}'" in sql


def test_snapshot_has_no_provenance_defaults() -> None:
    """The committed snapshot is what CI diffs a clean dump against."""
    snapshot = SNAPSHOT.read_text(encoding="utf-8")
    table = snapshot.split('CREATE TABLE IF NOT EXISTS "public"."message_citations"', 1)
    assert len(table) == 2, "message_citations missing from the schema snapshot"
    body = table[1].split(");", 1)[0]
    rights_line = next(line for line in body.splitlines() if '"rights_status"' in line)
    speaker_line = next(line for line in body.splitlines() if '"speaker_verified"' in line)
    assert "DEFAULT" not in rights_line.upper(), rights_line
    assert "DEFAULT" not in speaker_line.upper(), speaker_line
    assert '"rights_status" "text" NOT NULL' in rights_line
    assert '"speaker_verified" boolean NOT NULL' in speaker_line
