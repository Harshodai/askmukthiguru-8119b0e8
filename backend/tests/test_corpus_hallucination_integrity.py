"""Ruthless Corpus & Hallucination Auditor Test Suite.

Asserts 100% cryptographic and semantic integrity across all 745 corpus packages in
scripts/ingestion/corpus/:
  1. Zero YouTube outro boilerplate (subscribe, like/share, subtitles by, etc.).
  2. Zero unwanted HTML/XML entities, zero-width characters, and non-standard control chars.
  3. Zero uncorrected doctrine variants from DEFAULT_DOCTRINE_TERMS.
  4. 100% Artifact manifest SHA-256 integrity and field agreement across canonical segments,
     transcripts, quality reports, correction ledgers, and manifests.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any
import pytest

from services.doctrine_terms import DEFAULT_DOCTRINE_TERMS, load_doctrine_terms

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = REPO_ROOT / "scripts" / "ingestion" / "corpus"

REQUIRED_FILES = [
    "canonical_segments.json",
    "transcript.md",
    "quality_report.json",
    "correction_ledger.json",
    "artifact_manifest.json",
]

HTML_ENTITY_RE = re.compile(r"&(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\ufeff\u2060\u00ad]")

BOILERPLATE_PATTERNS = [
    re.compile(r"\b(subscribe\s+to\s+(?:our|the|my)\s+channel)\b", re.I),
    re.compile(r"\b(thank\s+you\s+for\s+watching)\b", re.I),
    re.compile(r"\b(thanks\s+for\s+watching)\b", re.I),
    re.compile(r"\b(subtitles?\s+by)\b", re.I),
    re.compile(r"\b(translated\s+by)\b", re.I),
    re.compile(r"\b(captions?\s+by)\b", re.I),
    re.compile(r"\b(like,?\s+share\s+and\s+subscribe)\b", re.I),
    re.compile(r"\b(don'?t\s+forget\s+to\s+subscribe)\b", re.I),
    re.compile(r"\b(hit\s+the\s+bell\s+icon)\b", re.I),
    re.compile(r"\b(amara\.org)\b", re.I),
    re.compile(r"\b(opensubtitles)\b", re.I),
]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@pytest.fixture(scope="module")
def all_packages() -> list[Path]:
    assert CORPUS_ROOT.is_dir(), f"Corpus root {CORPUS_ROOT} does not exist"
    pkgs = sorted(p for p in CORPUS_ROOT.iterdir() if p.is_dir())
    assert len(pkgs) >= 745, f"Expected at least 745 packages, found {len(pkgs)}"
    return pkgs


def test_package_count_and_required_files(all_packages: list[Path]):
    missing_map = {}
    for p in all_packages:
        missing = [f for f in REQUIRED_FILES if not (p / f).is_file()]
        if missing:
            missing_map[p.name] = missing
    assert not missing_map, f"Packages missing required files: {missing_map}"


def test_no_html_entities_or_control_chars_or_zero_width(all_packages: list[Path]):
    violations = []
    for p in all_packages:
        for fname in ["canonical_segments.json", "transcript.md"]:
            fpath = p / fname
            if not fpath.is_file():
                continue
            text = fpath.read_text(encoding="utf-8", errors="replace")
            if HTML_ENTITY_RE.search(text):
                violations.append((p.name, fname, "html_entity"))
            if CONTROL_CHAR_RE.search(text):
                violations.append((p.name, fname, "control_char"))
            if ZERO_WIDTH_RE.search(text):
                violations.append((p.name, fname, "zero_width"))
    assert not violations, f"Found entity/control/zero-width violations: {violations[:10]}"


def test_no_youtube_outro_boilerplate(all_packages: list[Path]):
    boilerplate_hits = []
    for p in all_packages:
        t_file = p / "transcript.md"
        if not t_file.is_file():
            continue
        text = t_file.read_text(encoding="utf-8")
        body = text.split("## Transcript", 1)[1] if "## Transcript" in text else text
        for bp in BOILERPLATE_PATTERNS:
            m = bp.search(body)
            if m:
                boilerplate_hits.append((p.name, m.group(0)))
    assert not boilerplate_hits, f"Found YouTube outro boilerplate in packages: {boilerplate_hits}"


def test_no_uncorrected_doctrine_variants(all_packages: list[Path]):
    all_terms = load_doctrine_terms()
    uncorrected_hits = []
    for p in all_packages:
        seg_file = p / "canonical_segments.json"
        if not seg_file.is_file():
            continue
        s_data = json.loads(seg_file.read_text(encoding="utf-8"))
        segs = s_data.get("segments", []) if isinstance(s_data, dict) else s_data
        for s in segs:
            stext = s.get("text", "")
            for canon, variants in all_terms.items():
                for v in variants:
                    if not v or v.lower() == "akam":
                        continue
                    for match in re.finditer(rf"\b{re.escape(v)}\b", stext):
                        start, end = match.start(), match.end()
                        is_part_of_canon = False
                        if canon in stext:
                            for c_m in re.finditer(rf"\b{re.escape(canon)}\b", stext):
                                if c_m.start() <= start and end <= c_m.end():
                                    is_part_of_canon = True
                                    break
                        if not is_part_of_canon:
                            for other_canon in all_terms:
                                if other_canon in stext:
                                    for oc_m in re.finditer(rf"\b{re.escape(other_canon)}\b", stext):
                                        if oc_m.start() <= start and end <= oc_m.end():
                                            is_part_of_canon = True
                                            break
                        if not is_part_of_canon:
                            uncorrected_hits.append((p.name, s.get("segment_id"), v, canon, stext))

    assert not uncorrected_hits, f"Found {len(uncorrected_hits)} uncorrected doctrine terms: {uncorrected_hits[:10]}"


def test_artifact_manifest_hash_integrity_and_field_agreement(all_packages: list[Path]):
    discrepancies = []
    for p in all_packages:
        vid = p.name
        seg_file = p / "canonical_segments.json"
        t_file = p / "transcript.md"
        q_file = p / "quality_report.json"
        ledg_file = p / "correction_ledger.json"
        man_file = p / "artifact_manifest.json"

        try:
            q_data = json.loads(q_file.read_text(encoding="utf-8"))
            man_data = json.loads(man_file.read_text(encoding="utf-8"))
            ledg_data = json.loads(ledg_file.read_text(encoding="utf-8"))
        except Exception as e:
            discrepancies.append((vid, f"json_parse_error: {e}"))
            continue

        # Score and State parity
        q_score = q_data.get("quality_score")
        q_state = q_data.get("quality_state")
        m_score = man_data.get("quality_score")
        m_state = man_data.get("final_quality_state")

        if q_score != m_score:
            discrepancies.append((vid, f"score_mismatch: q={q_score}, m={m_score}"))
        if q_state != m_state:
            discrepancies.append((vid, f"state_mismatch: q={q_state}, m={m_state}"))

        # Terminology corrections count vs ledger entries
        q_term_count = q_data.get("terminology_corrections_count")
        ledger_entries = ledg_data if isinstance(ledg_data, list) else ledg_data.get("corrections", [])
        if q_term_count is not None and q_term_count != len(ledger_entries):
            discrepancies.append((vid, f"corr_count_mismatch: q={q_term_count}, ledg={len(ledger_entries)}"))

        # Artifact SHA-256 integrity
        artifacts = man_data.get("artifacts", {})
        for art_name, fpath in [
            ("canonical_segments.json", seg_file),
            ("transcript.md", t_file),
            ("quality_report.json", q_file),
            ("correction_ledger.json", ledg_file),
        ]:
            entry = artifacts.get(art_name)
            if not entry or not entry.get("sha256"):
                discrepancies.append((vid, f"missing_manifest_entry_{art_name}"))
            else:
                actual_sha = sha256_file(fpath)
                if entry["sha256"] != actual_sha:
                    discrepancies.append((vid, f"hash_mismatch_{art_name}"))

    assert not discrepancies, f"Found {len(discrepancies)} package discrepancies: {discrepancies[:10]}"
