"""Section C — OKF + citation integrity gap tests (first-person E2E audit 2026-09-29).

Written by the Section C audit. Two shapes live here:

* PASSING tests  — integrity gates verified working today (first-person sha256 /
  speaker / provenance gate, `_build_citation` OKF refusal, quote-weaver
  assertion gate rejections, TEDx OKF provenance).
* XFAIL tests    — documented gaps. Each asserts the DESIRED behaviour, carries
  the exact defect inventory in its `reason`, and flips to XPASS the moment the
  follow-up lands (then delete the marker).

Status 2026-09-30 (Phase 3 of ``abstention_gate_and_index_hygiene_plan.md``):
GAP-C1/C2/C3 were patched in ``services/quote_weaver.py`` and their markers
removed; GAP-O1/O2/O3 were repaired in the ``memory/okf/*.md`` sources (never
compiled.json) and their markers removed once the recompile landed. GAP-O4
(corpus-wide verbatim backlog) remains open on purpose. The once-frozen fix
owners (``services/quote_weaver.py`` etc.) are editable again for this phase.
Full matrix + evidence: ``.claude/tasks/audit_2026-09-29/C.md``.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re

import pytest

from services.first_person_pipeline import (
    _ALLOWED_SPEAKERS,
    _passes_integrity_gate,
)
from services.memory.okf_store import OKF_DIR
from services.quote_weaver import QuoteWeaverAssertionGate
from services.text_quality_filter import find_artifact

# ─────────────────────────────────────────────────────────────────────────────
# A. First-person citation integrity gate (sha256 / speaker / provenance)
# ─────────────────────────────────────────────────────────────────────────────


def _clean_clip(**overrides):
    text = "Suffering is resistance to what is."
    clip = {
        "verbatim_text": text,
        "transcript_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "speaker": "Sri Preethaji",
        "video_id": "abc123",
        "provenance_kind": "speech_turn_clip",
    }
    clip.update(overrides)
    return clip


@pytest.mark.unit
def test_gate_accepts_sha256_valid_allowlisted_clip():
    assert _passes_integrity_gate(_clean_clip()) is True


@pytest.mark.unit
def test_gate_rejects_tampered_verbatim_text():
    """(b) citations only from clips whose sha256 still matches their stored hash."""
    tampered = _clean_clip(verbatim_text="Suffering is resistance to whatever I like.")
    assert _passes_integrity_gate(tampered) is False


@pytest.mark.unit
def test_gate_rejects_curated_okf_provenance():
    """(a) an OKF (LLM-summary) entry can never ride the first-person clip path."""
    assert _passes_integrity_gate(_clean_clip(provenance_kind="curated_okf")) is False


@pytest.mark.unit
def test_gate_rejects_non_allowlisted_speaker():
    assert _ALLOWED_SPEAKERS == {"Sri Preethaji", "Sri Krishnaji"}
    assert _passes_integrity_gate(_clean_clip(speaker="Unknown Channel")) is False


@pytest.mark.unit
def test_gate_rejects_provider_degradation_string():
    """AGENTS.md contamination vector #2 — canned degradation text is not doctrine."""
    text = "I'm currently experiencing a temporary connection issue with the provider."
    clip = _clean_clip(
        verbatim_text=text,
        transcript_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
    assert _passes_integrity_gate(clip) is False


@pytest.mark.unit
def test_gate_rejects_non_verbatim_flags():
    assert _passes_integrity_gate(_clean_clip(is_verbatim=False)) is False


@pytest.mark.unit
def test_build_citation_refuses_okf_and_cached_citations_are_rechecked():
    """(a) `_build_citation` raises on curated_okf, and the Redis cache path
    re-runs the same refusal before serving a cached answer.

    `_build_citation` is a closure inside `FirstPersonPipeline`, so this is a
    source fence on the two guards (the behavioural half is covered by
    `test_gate_rejects_curated_okf_provenance` above).
    """
    import services.first_person_pipeline as fp

    src = inspect.getsource(fp)
    assert 'if provenance_kind == "curated_okf"' in src
    assert 'raise ValueError("OKF entries cannot become first-person citations")' in src
    # Cached citations are re-checked before serve (check_exact_cache).
    assert 'cit.get("provenance_kind") == "curated_okf"' in src
    # Citations are only ever built from clips that already cleared the gate.
    assert (
        "_passes_integrity_gate(clip, boundary_guard_enabled=self._boundary_guard_enabled)" in src
    )


# ─────────────────────────────────────────────────────────────────────────────
# B. Chat-corpus citation speaker gate (tests/test_citation_contract.py owns
#    this file — read-only here; this pins the gate behaviourally too).
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_chat_corpus_speaker_gate_still_refuses_channel_handles():
    from rag.nodes.citation_extractor import extract_citations

    state = {
        "answer": "The beautiful state is a state of connection and joy.",
        "relevant_docs": [
            {
                "text": "The beautiful state is connection, joy, love.",
                "source_url": "https://youtu.be/abc123",
                "speaker": "pkconsciousness",
                "teacher_id": "ekam",
            }
        ],
    }
    citation = extract_citations(state)["citations"][0]
    assert citation["speaker"] is None
    assert citation["text_snippet"] is None


# ─────────────────────────────────────────────────────────────────────────────
# C. QuoteWeaverAssertionGate — verified rejections
# ─────────────────────────────────────────────────────────────────────────────

_CLIP_TEXT = "Suffering is resistance to what is."
_CLIPS = [
    {
        "verbatim_text": _CLIP_TEXT,
        "video_id": "abc123",
        "speaker": "Sri Preethaji",
    }
]


def _answer(body: str) -> str:
    return (
        "A serene opening sentence for the seeker.\n\n"
        "**Sri Preethaji** · [A Talk](https://www.youtube.com/watch?v=abc123&t=99s)\n\n"
        f"{body}\n\n"
        "---\n\n"
        "*What is the mind resisting right now?*\n\n"
        "*Where does this resistance live in the body?*"
    )


@pytest.mark.unit
def test_quote_gate_rejects_fabricated_quoted_teaching():
    ok, reason = QuoteWeaverAssertionGate.validate(
        _answer('"Enlightenment arrives on Tuesdays for those who blink."'),
        _CLIPS,
        [],
    )
    assert ok is False
    assert "Fabricated or non-verbatim quote" in reason


@pytest.mark.unit
def test_quote_gate_requires_a_timestamped_video_link():
    text = _answer(_CLIP_TEXT).replace(
        "https://www.youtube.com/watch?v=abc123&t=99s", "https://example.com/notes"
    )
    ok, reason = QuoteWeaverAssertionGate.validate(text, _CLIPS, [])
    assert ok is False
    assert reason == "Missing video timestamp link"


@pytest.mark.unit
def test_quote_gate_rejects_machine_artifacts_and_affirmations():
    ok, reason = QuoteWeaverAssertionGate.validate(
        _answer(_CLIP_TEXT) + "\n\nNow place your hands upon your heart and repeat.",
        _CLIPS,
        [],
    )
    assert ok is False
    assert "affirmation" in reason or "artifact" in reason.lower()


@pytest.mark.unit
def test_quote_gate_keeps_served_clip_text_intact():
    altered = _answer(_CLIP_TEXT.replace("what is", "whatever I like"))
    ok, reason = QuoteWeaverAssertionGate.validate(altered, _CLIPS, [])
    assert ok is False
    assert "missing or altered" in reason


# ─────────────────────────────────────────────────────────────────────────────
# D. QuoteWeaverAssertionGate — documented gaps (desired behaviour asserted)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_gap_fabricated_timestamp_is_rejected():
    """GAP-C1 (fixed 2026-09-30): the t= value is validated against the cited
    clip's time window — or the 12h upload ceiling when the clip has no window."""
    text = _answer(_CLIP_TEXT).replace("t=99s", "t=99999s")
    ok, _ = QuoteWeaverAssertionGate.validate(text, _CLIPS, [])
    assert ok is False


@pytest.mark.unit
def test_gap_unquoted_fabricated_claim_is_rejected():
    """GAP-C2 (fixed 2026-09-30): an unquoted teacher-attributed claim in the
    LLM opening/connective must be verbatim in a clip/OKF source."""
    text = _answer(_CLIP_TEXT).replace(
        "A serene opening sentence for the seeker.",
        "Sri Preethaji teaches that blinking grants enlightenment instantly.",
    )
    ok, _ = QuoteWeaverAssertionGate.validate(text, _CLIPS, [])
    assert ok is False


@pytest.mark.unit
def test_gap_third_clip_text_is_also_verified():
    """GAP-C3 (fixed 2026-09-30): the verbatim-DB check iterates ALL clips —
    a third (or later) clip whose text was dropped or altered fails the gate."""
    # 3 clips: clips[0] and clips[1] verbatim text IS served, clips[2] is not.
    served = [
        {"verbatim_text": _CLIP_TEXT, "video_id": "abc123", "speaker": "Sri Preethaji"},
        {"verbatim_text": _CLIP_TEXT, "video_id": "def456", "speaker": "Sri Preethaji"},
    ]
    unserved = {
        "verbatim_text": "THIS CLIP TEXT IS NOT IN THE ANSWER",
        "video_id": "ghi789",
        "speaker": "Sri Preethaji",
    }
    ok, _ = QuoteWeaverAssertionGate.validate(_answer(_CLIP_TEXT), served + [unserved], [])
    assert ok is False


# ─────────────────────────────────────────────────────────────────────────────
# E. compiled.json known-defect quarantine (pre-existing, NOT the 715→717 pair)
# ─────────────────────────────────────────────────────────────────────────────


def _compiled_entries():
    path = OKF_DIR / "compiled.json"
    if not path.exists():
        pytest.skip("compiled.json not found")
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("entries", [])


@pytest.mark.unit
def test_gap_no_markdown_bold_leaks_in_key_teachings():
    # GAP-O1 fixed 2026-09-30: 13 leaks repaired in memory/okf/*.md sources
    # + recompiled (backup ../.claude/tasks/audit_2026-09-29/backup_compiled_2026-09-30.json
    # had 13 KT-with-`**`, fresh compiled has 0). Marker removed post-recompile.
    offenders = [
        (e["title"], t)
        for e in _compiled_entries()
        for t in e.get("key_teachings", [])
        if "**" in t
    ]
    assert not offenders, f"markdown leaks: {offenders[:3]}"


@pytest.mark.unit
def test_gap_no_mojibake_or_mixed_script_teachings():
    # GAP-O2 fixed 2026-09-30: 14 mojibake-only teachings repaired in
    # memory/okf/*.md sources + recompiled (fresh compiled: U+FFFD=0,
    # devanagari-mixed=0). Marker removed post-recompile.
    def bad(t: str) -> bool:
        if "\ufffd" in t:
            return True
        devanagari = sum(1 for c in t if "\u0900" <= c <= "\u097f")
        latin = sum(1 for c in t if c.isascii() and c.isalpha())
        return devanagari > 0 and latin > 0

    offenders = [
        (e["title"], t) for e in _compiled_entries() for t in e.get("key_teachings", []) if bad(t)
    ]
    assert not offenders, f"garbage teachings: {[o[0] for o in offenders][:5]}"


@pytest.mark.unit
def test_gap_every_key_teaching_clears_find_artifact():
    # GAP-O3 fixed 2026-09-30: truncated repetition-loop KTs repaired in
    # the_transformative_power_of_consciousness.md + transforming_suffering_
    # into_positive_outcomes.md sources + recompiled (fresh compiled:
    # find_artifact failures = 0/2090). Marker removed post-recompile.
    offenders = [
        (e["title"], find_artifact(t))
        for e in _compiled_entries()
        for t in e.get("key_teachings", [])
        if find_artifact(t) is not None
    ]
    assert not offenders, f"artifact-flagged teachings: {offenders[:3]}"


@pytest.mark.unit
@pytest.mark.xfail(
    strict=False,
    reason="GAP-O4: 126 of 2090 key_teachings (43 entries, mostly memory/okf/shared/ "
    "plus 2 teacher-subdir entries) are NOT verbatim anywhere in the transcript of "
    "their own declared source video — they are paraphrases presented as verbatim "
    'teachings. Reproduce: python3 -c "from evals.grounding.verify_quote import '
    'verify_verbatim_quote ...". Only runnable where repo-root transcripts/ exists '
    "(gitignored, not mounted in the container).",
)
def test_gap_key_teachings_are_verbatim_in_their_source_transcript():
    verify_quote = pytest.importorskip(
        "evals.grounding.verify_quote",
        reason="repo-root evals/ not importable from this environment",
    )
    transcripts = OKF_DIR.parent.parent / "transcripts"
    if not transcripts.is_dir():
        pytest.skip("repo-root transcripts/ not available in this environment")
    vid_re = re.compile(r"(?:v=|youtu\.be/|shorts/)([\w-]{6,})")
    offenders = []
    for e in _compiled_entries():
        m = vid_re.search(e.get("source") or e.get("resource") or "")
        if not m:
            continue
        missing = [
            t
            for t in e.get("key_teachings", [])
            if not verify_quote.verify_verbatim_quote(t, m.group(1), transcripts).matched
        ]
        if missing:
            offenders.append((e["path"].rsplit("/", 1)[-1], len(missing)))
    assert not offenders, f"{len(offenders)} entries: {offenders[:5]}"


# ─────────────────────────────────────────────────────────────────────────────
# F. TEDx KC provenance — the 715 → 717 entries (deterministic single-video
#    ingest of owner-rights-confirmed video TqxxCYnAxo8)
# ─────────────────────────────────────────────────────────────────────────────

_TEDX = (
    "how_to_live_in_a_beautiful_state_tedxkc_talk.md",
    "how_to_live_in_a_beautiful_state_tedxkc_talk_practice.md",
)


def _tedx_entries():
    return [e for e in _compiled_entries() if (e.get("path") or "").rsplit("/", 1)[-1] in _TEDX]


@pytest.mark.unit
def test_tedx_entries_exist_and_cite_the_confirmed_video():
    # The talk and practice entries are 97% identical text from the same video;
    # the deterministic compile dedups them to one on purpose (2026-10-05).
    entries = _tedx_entries()
    assert len(entries) == 1, f"expected one deduped TEDx entry, found {len(entries)}"
    for e in entries:
        assert e["source"] == "https://www.youtube.com/watch?v=TqxxCYnAxo8"
        assert e["status"] == "stable"
        assert e["key_teachings"], f"{e['title']}: no key teachings"


@pytest.mark.unit
def test_tedx_entries_attributed_to_preethaji():
    """Attribution repair (audit C): YouTube oEmbed for TqxxCYnAxo8 reads
    'How to end stress, unhappiness and anxiety to live in a beautiful state |
    Preetha ji | TEDxKC', and CONTENT-RIGHTS.md:25 records the owner-confirmed
    source as 'Sri Preethaji at TEDxKC'. The ingest heuristic
    (scripts/ingest_single_video_okf.py:65-70) mis-detected the speaker
    because Preethaji's transcript only *mentions* Krishnaji
    ('Krishnaji, my husband')."""
    entries = _tedx_entries()
    assert entries, "TEDx entries missing from compiled.json"
    for e in entries:
        assert e["teacher"] == "sri-preethaji", (
            f"{e['title']}: TEDxKC talk is Preethaji's, not Krishnaji's"
        )


@pytest.mark.unit
def test_tedx_key_teachings_are_verbatim_in_the_source_doc():
    """The compiled teachings must literally occur in the on-disk OKF source
    document (which itself is a verbatim extract of transcripts/TqxxCYnAxo8.md —
    verified host-side by the audit: all 7 teachings are exact substrings)."""
    for e in _tedx_entries():
        md_path = OKF_DIR / (e["path"].rsplit("/", 1)[-1])
        assert md_path.exists(), f"source doc missing: {md_path}"
        body = md_path.read_text(encoding="utf-8")
        for t in e["key_teachings"]:
            assert t in body, f"{e['title']}: teaching not verbatim in source doc: {t!r}"


if __name__ == "__main__":  # ponytail: runnable self-check
    raise SystemExit(pytest.main([__file__, "-q"]))
