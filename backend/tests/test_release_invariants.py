"""NEW-ANS-8: release invariants (AC-ANS-01 to 09). Every case must pass on every release.

One file that fails on any of:
  I-1 a generated or edited teacher quote (served text not exact, hash mismatch);
  I-2 a misattribution served as fact (bare teacher name on an unverified clip);
  I-3 cross-user memory in an answer (personalised turns bypass shared caches);
  I-4 a success-shaped response after a failed step (fault injection);
  I-5 a served clip that fails the hash gate (refused at assembly);
  I-7 a crisis turn reaching the bridge (safety stages run first);
  I-8 a translated quote (quotes are language independent);
  plus static checks: no production call site for a helper that re-hashes
  joined clip text (it would certify a quote that no stored span holds).

Fakes only: no LLM, no Qdrant, no network. Most cases reuse the bridge suite's
fixtures so they exercise the real ``FirstPersonBridgeStage``.
"""

from __future__ import annotations

import ast
import hashlib
import random
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import tests.test_first_person_bridge as _bridge_tests
from app.answer_contract import served_clip_integrity_failures
from app.answer_outcome import build_answer_outcome
from app.grounding import grounding_state_for
from app.pipeline.stages import build_default_pipeline
from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
from tests.test_first_person_bridge import _CLIP_TEXT, _clip_citation, _container, _ctx, _fp_result

_bridge_gates = _bridge_tests._bridge_gates
fp_pipeline = _bridge_tests.fp_pipeline

_BACKEND = Path(__file__).resolve().parents[1]

# Mixed scripts the corpus can hold: Latin, Devanagari, Telugu, Tamil, combining
# marks, curly quotes, zero-width joiner. sha256 is over UTF-8 bytes.
_ALPHABET = (
    "abcdefghijklmnopqrstuvwxyz ,.?'"
    "अआइईउऊएऐओऔकखगघचछजझटठडढणतथदधनपफबभमयरलवशषसहािीुूेैोौं्"
    "అఆఇఈఉఊఎఏఐఒఓఔకఖగఘచఛజఝటఠడఢణతథదధనపఫబభమయరలవశషసహాిీుూెేైొోౌ్"
    "அஆஇஈஉஊஎஏஐஒஓஔகஙசஞடணதநபமயரலவழளறன"
    "‘’“”‍́"
)


def _span_text(rng: random.Random) -> str:
    return "".join(rng.choice(_ALPHABET) for _ in range(rng.randint(15, 240))).strip() or "x"


def _hashed(text: str, **extra) -> dict:
    return _clip_citation(
        verbatim_text=text,
        text_snippet=text,
        transcript_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        **extra,
    )


# ---------------------------------------------------------------- I-1 ----------


def test_every_served_quote_is_exact_and_hashed():
    rng = random.Random(20261106)
    for _ in range(200):
        text = _span_text(rng)
        citation = _hashed(text)
        answer = f"{text}"
        assert served_clip_integrity_failures([citation], answer) == []
        # One code point changed (a paraphrase, a "fixed" word): hash and substring fail.
        pos = rng.randrange(len(text))
        edited = text[:pos] + ("ा" if text[pos] != "ा" else "a") + text[pos + 1 :]
        tampered = dict(citation, verbatim_text=edited)
        assert "hash" in served_clip_integrity_failures([tampered], edited)
        assert served_clip_integrity_failures([citation], edited) == ["substring"]


def test_unicode_normalisation_is_not_silently_equal():
    """NFC and NFD of the same word are different stored bytes; no silent folding.

    (Devanagari nukta letters such as U+0958 are composition exclusions, so
    NFC and NFD agree there; a Latin accent shows the difference.)"""
    import unicodedata

    nfc = unicodedata.normalize("NFC", "a quiet mind, café")
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    assert served_clip_integrity_failures([_hashed(nfc)], nfd) == ["substring"]


# ---------------------------------------------------------------- I-2 ----------


@pytest.mark.parametrize("verified", [False, None])
def test_unverified_clip_never_carries_a_bare_teacher_name(verified):
    from app.orchestrator import _coerce_citations

    citation = _clip_citation(speaker="Sri Krishnaji")
    citation["speaker_verified"] = verified
    out = _coerce_citations([citation])
    assert out, "the clip itself still reaches the wire"
    assert out[0].get("speaker") not in ("Sri Krishnaji", "Sri Preethaji")


def test_verified_clip_keeps_its_teacher_name():
    from app.orchestrator import _coerce_citations

    citation = _clip_citation(speaker="Sri Preethaji")
    citation["speaker_verified"] = True
    assert _coerce_citations([citation])[0].get("speaker") == "Sri Preethaji"


# ---------------------------------------------------------------- I-3 ----------


def test_personalised_turn_bypasses_the_shared_caches():
    from app.pipeline.stages.cache_stage import _is_personalization_eligible

    ctx = MagicMock()
    ctx.personalization_eligible = False
    ctx.request = MagicMock(attachment_context=None, guru_tone=None)
    ctx.state = {"memory_context": "seeker A's private facts"}
    assert _is_personalization_eligible(ctx) is True


# ---------------------------------------------------------------- I-4 ----------


def _faults():
    def _raises(p, c):
        p.execute.side_effect = RuntimeError("qdrant down")

    def _status_error(p, c):
        p.execute.return_value = _fp_result(citations=[], status="error", is_direct=False)

    def _scorer_indeterminate(p, c):
        r = _fp_result(citations=[], status="abstained", is_direct=False)
        r.abstain_reason, r.answerability = "relevance_indeterminate", "relevance_indeterminate"
        p.execute.return_value = r

    def _gate_indeterminate(p, c):
        r = _fp_result(citations=[], status="abstained", is_direct=False)
        r.abstain_reason, r.answerability = "answerability_withheld", "indeterminate"
        p.execute.return_value = r

    def _contract_violation(p, c):
        r = _fp_result(citations=[], status="abstained", is_direct=False)
        r.abstain_reason = "serving_contract_violation"
        p.execute.return_value = r

    def _no_output_rail(p, c):
        c.guardrails = None

    def _encoder_down(p, c):
        c.embedding.encode_single_full_async.side_effect = RuntimeError("encoder down")

    def _tampered_clip(p, c):
        p.execute.return_value = _fp_result(citations=[_clip_citation(transcript_hash="0" * 64)])

    return {
        "store_exception": _raises,
        "store_error_status": _status_error,
        "scorer_timeout": _scorer_indeterminate,
        "answerability_timeout": _gate_indeterminate,
        "contract_violation": _contract_violation,
        "output_rail_missing": _no_output_rail,
        "encoder_down": _encoder_down,
        "hash_gate_bypassed": _tampered_clip,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", sorted(_faults()))
async def test_fault_injection_never_success_shaped(fault, fp_pipeline):
    container = _container()
    _faults()[fault](fp_pipeline, container)

    result = await FirstPersonBridgeStage().run(_ctx(container))

    assert result is not None, "first-person-only: a fault is a static abstain"
    assert result.route_decision == "first_person_abstain"
    assert result.citations == []
    assert _CLIP_TEXT not in result.final_answer
    assert result.model_used is None
    assert result.verification["passed"] is False
    assert result.verification["abstain_cause"] == "system_unavailable"
    record = build_answer_outcome(
        request_id="t",
        route_decision=result.route_decision,
        route_reason=None,
        grounding_state=grounding_state_for(result),
        citations=result.citations,
        verification=result.verification,
        cache_hit=False,
        latency_ms=1,
        model_used=None,
    )
    assert record["outcome"] == "error"


# ---------------------------------------------------------------- I-5 ----------
# Covered by the "hash_gate_bypassed" fault above: the bridge refuses the clip.


# ---------------------------------------------------------------- I-7 ----------


def test_safety_stages_run_before_the_graph_that_hosts_the_bridge():
    names = [getattr(s, "name", type(s).__name__) for s in build_default_pipeline()]
    graph = names.index("langgraph")
    for safety in ("input_guardrails", "distress_detection"):
        assert names.index(safety) < graph, names
    for short_circuit in ("casual_short_circuit", "off_topic_short_circuit"):
        assert names.index("distress_detection") < names.index(short_circuit), names


# ---------------------------------------------------------------- I-8 ----------


@pytest.mark.asyncio
async def test_quote_text_is_language_independent(fp_pipeline):
    async def _translate(*, text: str, **_kw):
        return f"TRANSLATED({text})"

    en = await FirstPersonBridgeStage().run(_ctx(_container()))
    container = _container()
    container.translation = MagicMock()
    container.translation.translate_text = _translate
    hi = await FirstPersonBridgeStage().run(_ctx(container, lang="hi", is_indic=True))

    assert _CLIP_TEXT in en.final_answer and _CLIP_TEXT in hi.final_answer
    assert f"TRANSLATED({_CLIP_TEXT})" not in hi.final_answer
    assert [c["verbatim_text"] for c in en.citations] == [c["verbatim_text"] for c in hi.citations]


# ---------------------------------------------------------- static checks -------


def _call_sites(name: str) -> list[str]:
    hits = []
    for root in ("app", "services", "rag", "ingest", "domain"):
        for path in (_BACKEND / root).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = node.func
                    called = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                    if called == name:
                        hits.append(f"{path.relative_to(_BACKEND)}:{node.lineno}")
    return hits


def test_joined_clip_rehash_helper_is_not_on_the_serve_path():
    """``_club_consecutive_citations`` joins two spans up to 45 s apart and
    re-hashes the joined text, so the result passes every hash gate while
    quoting words no stored span holds (the gap is dropped). It has no
    production caller today; wiring it in would break invariant 1."""
    assert _call_sites("_club_consecutive_citations") == []
