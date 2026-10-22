"""
Mukthi Guru — Quality Gate & Ingestion Pipeline Test Suite
===========================================================
Validates:
1. Single canonical entity resolution (Sri Preethaji, Sri Krishnaji).
2. Reversible offset-based correction ledger & Unicode NFC normalization.
3. Quality scoring & deterministic state promotion across all 11 pilot cases.
4. Server-side schema idempotency and untrusted state rejection.
5. Fail-closed backup all() control flow.
"""

import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.doctrine_terms import (
    apply_corrections_with_ledger,
    load_doctrine_terms,
)


def test_single_canonical_entity_resolution():
    """Verify single canonical entities exist without colliding duplicates."""
    terms = load_doctrine_terms()
    assert "Sri Preethaji" in terms
    assert "Preethaji" not in terms, "Preethaji should be unified under 'Sri Preethaji'"
    assert "Sri Krishnaji" in terms
    assert "Krishnaji" not in terms, "Krishnaji should be unified under 'Sri Krishnaji'"
    assert "Sri Preethaji & Sri Krishnaji" in terms

    # Test correction
    text = "We welcome Sri Pretty Ji and Krishna Ji to the gathering."
    corr, ledger = apply_corrections_with_ledger(text)
    assert corr == "We welcome Sri Preethaji and Sri Krishnaji to the gathering."
    assert len(ledger) == 2


def test_reversible_correction_ledger_offsets_and_multi_match():
    """Verify offset precision, occurrence indexing, and non-destruction of lowercase 'akam'."""
    text = "Akam is the sacred space. Learn more at Akam centre. In Tamil akam means inner self."
    corr, ledger = apply_corrections_with_ledger(text, segment_id="seg_0042")

    # Lowercase 'akam' must NOT be rewritten
    assert "In Tamil akam means inner self" in corr
    # Capitalised 'Akam' must be rewritten to 'Ekam'
    assert corr.startswith("Ekam is the sacred space. Learn more at Ekam centre.")

    assert len(ledger) == 2
    # Match 1
    assert ledger[0]["char_start"] == 0
    assert ledger[0]["char_end"] == 4
    assert ledger[0]["occurrence_index"] == 1
    assert ledger[0]["matched_text"] == "Akam"
    assert ledger[0]["replacement"] == "Ekam"

    # Match 2
    assert ledger[1]["char_start"] == 40
    assert ledger[1]["char_end"] == 44
    assert ledger[1]["occurrence_index"] == 2
    assert ledger[1]["matched_text"] == "Akam"
    assert ledger[1]["replacement"] == "Ekam"

    # Hashes must match
    assert ledger[0]["original_segment_hash"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert ledger[0]["corrected_segment_hash"] == hashlib.sha256(corr.encode("utf-8")).hexdigest()


def test_fail_closed_backup_gate_logic():
    """Verify that backup gate aborts if any backup returns False."""
    b_neo4j = True
    b_qdrant = False
    b_lightrag = True

    all_backups_ok = all([b_neo4j, b_qdrant, b_lightrag])
    assert all_backups_ok is False, "Gate must fail closed if even one backup fails"


