"""T2-01: Offline PR Eval Suite Harness.

Runs offline quality tests on every PR without secrets or live infrastructure:
- Deterministic routing prefilters (evals/pr_suite/routing.jsonl)
- Distress benign verification (evals/pr_suite/distress_benign.jsonl)
- Acute distress crisis detection (evals/pr_suite/distress_crisis.jsonl, non-blocking until clinician review)
- Out-of-corpus null queries (evals/pr_suite/abstain_null.jsonl)
- Quote integrity verification (evals/pr_suite/quote_integrity.py)
- Voice governance linter (evals/pr_suite/voice_lint.py)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Ensure repo root is accessible for importing evals.pr_suite
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals.pr_suite.quote_integrity import (
    compute_span_hash,
    verify_citation_record,
    verify_span_integrity,
)
from evals.pr_suite.voice_lint import is_voice_compliant, lint_voice
from rag.meditation import is_meditation_imperative
from services.serene_mind_engine import DistressLevel, SereneMindEngine

PR_SUITE_DIR = REPO_ROOT / "evals/pr_suite"


def _read_jsonl(filename: str) -> list[dict[str, Any]]:
    path = PR_SUITE_DIR / filename
    assert path.exists(), f"Evaluation dataset {path} must exist"
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def test_routing_prefilter_offline():
    """Verify routing dataset items against deterministic offline routing checks."""
    items = _read_jsonl("routing.jsonl")
    assert len(items) >= 10, "routing dataset must contain at least 10 items"

    engine = SereneMindEngine()
    for item in items:
        query = item["query"]
        expected_intent = item["expected_intent"]

        if expected_intent == "MEDITATION":
            assert is_meditation_imperative(query) is True, f"Failed meditation check on: {query}"
        elif expected_intent == "DISTRESS":
            assessment = engine.assess_distress(query)
            assert assessment.level >= DistressLevel.MODERATE, f"Failed distress check on: {query}"


def test_distress_benign_offline():
    """Verify that benign inquiries about anxiety/stress do NOT trigger acute crisis escalation."""
    items = _read_jsonl("distress_benign.jsonl")
    assert len(items) >= 8, "distress benign dataset must have at least 8 items"

    engine = SereneMindEngine()
    for item in items:
        query = item["query"]
        assessment = engine.assess_distress(query)
        # Benign philosophical questions must never be classified as SEVERE / CRISIS
        assert assessment.level < DistressLevel.SEVERE, (
            f"Benign inquiry falsely escalated to SEVERE/CRISIS: '{query}' (level={assessment.level})"
        )


def test_distress_crisis_offline():
    """Verify acute self-harm/crisis detection on crisis set.

    Per audit specification: this set is non-blocking until clinician review is recorded.
    """
    items = _read_jsonl("distress_crisis.jsonl")
    assert len(items) >= 5, "distress crisis dataset must have at least 5 items"

    engine = SereneMindEngine()
    passed = 0
    total = len(items)

    for item in items:
        query = item["query"]
        assessment = engine.assess_distress(query)
        # Acute crisis cues should reach at least MODERATE or SEVERE
        if assessment.level >= DistressLevel.MODERATE:
            passed += 1

    # Record evidence and assert baseline recall
    recall = passed / total
    # Non-blocking assertion if dataset is not clinician reviewed, but ensure reasonable baseline (>60%)
    assert recall >= 0.6, f"Crisis pre-screen recall too low: {passed}/{total} ({recall:.1%})"


def test_abstain_null_offline():
    """Verify out-of-domain queries are not recognized as meditation or spiritual queries."""
    items = _read_jsonl("abstain_null.jsonl")
    assert len(items) >= 6, "abstain null dataset must have at least 6 items"

    for item in items:
        query = item["query"]
        # Out-of-domain queries must not match meditation imperative
        assert is_meditation_imperative(query) is False, (
            f"Null query falsely matched meditation: {query}"
        )


def test_quote_integrity_verifier():
    """Verify that quote_integrity correctly detects clean vs tampered quotes."""
    sample_quote = "Awareness of the inner state is the beginning of transformation."
    sample_hash = compute_span_hash(sample_quote)

    # Clean verification
    assert verify_span_integrity(sample_quote, sample_hash) is True

    # Tampered text fails
    tampered_quote = "Awareness of the outer state is the beginning of transformation."
    assert verify_span_integrity(tampered_quote, sample_hash) is False

    # Citation record verification
    clean_citation = {
        "text": sample_quote,
        "source_text_hash": sample_hash,
    }
    ok, reason = verify_citation_record(clean_citation)
    assert ok is True and reason == "verified"

    # Citation with hash mismatch
    bad_citation = {
        "text": tampered_quote,
        "source_text_hash": sample_hash,
    }
    ok, reason = verify_citation_record(bad_citation)
    assert ok is False and reason == "hash_mismatch"


def test_voice_governance_linter():
    """Verify voice linter flags teacher first-person delivery and permits compliant text."""
    # Impersonation violations
    violations_krishnaji = lint_voice("I am Sri Krishnaji and I bless you on your journey.")
    assert len(violations_krishnaji) >= 1
    assert is_voice_compliant("I am Sri Krishnaji") is False

    violations_preethaji = lint_voice("As Sri Preethaji, I tell you that suffering is an illusion.")
    assert len(violations_preethaji) >= 1
    assert is_voice_compliant("As Sri Preethaji, I speak") is False

    violations_bless = lint_voice("My dear disciple, I grant you peace.")
    assert len(violations_bless) >= 1

    # Clean assistant / third-person text passes
    clean_text = "Sri Krishnaji teaches that observing inner conflict dissolves it."
    assert lint_voice(clean_text) == []
    assert is_voice_compliant(clean_text) is True

    clean_quote_intro = (
        "In our own words, Sri Preethaji explains the nature of the beautiful state."
    )
    assert lint_voice(clean_quote_intro) == []
    assert is_voice_compliant(clean_quote_intro) is True
