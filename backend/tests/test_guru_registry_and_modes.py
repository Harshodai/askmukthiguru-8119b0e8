"""L-FP-SPEAKER-REQUEST-1 / L-GURU-REGISTRY-1: named guru is a hard scope; none/both is multi-guru."""

import hashlib
from unittest.mock import MagicMock

import pytest

from services import guru_registry
from services.first_person_pipeline import FirstPersonPipeline, requested_teacher


def test_registry_is_config_driven_and_generic(monkeypatch, tmp_path):
    cfg = tmp_path / "g.yaml"
    cfg.write_text(
        "gurus:\n  - {id: amma, label: Sri Amma Bhagwan, aliases: ['amma\\s+bhagwan']}\n"
        "  - {id: preethaji, label: Sri Preethaji, aliases: ['preethaji']}\n"
    )
    monkeypatch.setattr(guru_registry, "_CONFIG", cfg)
    guru_registry.get_gurus.cache_clear()
    try:
        assert guru_registry.requested_gurus("what does Amma Bhagwan say") == ["amma"]
        assert "Sri Amma Bhagwan" in guru_registry.allowed_speaker_labels()
    finally:
        monkeypatch.undo()
        guru_registry.get_gurus.cache_clear()


def test_default_registry_has_both_current_gurus():
    assert guru_registry.allowed_speaker_labels() == {"Sri Preethaji", "Sri Krishnaji"}


@pytest.mark.parametrize(
    "q,exp",
    [
        ("What does Sri Preethaji say about fear?", "preethaji"),
        ("What does Sri Krishnaji say about fear?", "krishnaji"),
        ("What do Sri Preethaji and Sri Krishnaji say about fear?", None),
        ("both gurus on love, Preethaji", None),
        ("What is fear?", None),
    ],
)
def test_mode_detection(q, exp):
    assert requested_teacher(q) == exp


def _clip(teacher, label, text, cos_vec):
    return {
        "verbatim_text": text,
        "transcript_hash": hashlib.sha256(text.encode()).hexdigest(),
        "speaker": label,
        "teacher_id": teacher,
        "passage_dense": cos_vec,
        "video_id": f"v-{teacher}",
        "point_id": f"p-{teacher}-{len(text)}",
        "start_ms": 0,
        "end_ms": 20000,
    }


def _pipeline(clips):
    store = MagicMock()
    store.collection = "t"
    store.search_hybrid.return_value = clips
    store.points_servable.return_value = True
    redis = MagicMock()
    redis.get.return_value = None
    return FirstPersonPipeline(store=store, redis_client=redis, calibration_profile=None), store


TXT_P = (
    "When you accept this moment fully, the mind stops resisting and a deep calm arises on its own. "
    "You do not have to force peace into being, because peace is what remains when the struggle with life ends. "
    "Sit with that for a moment and notice how the body softens when you stop arguing with what is."
)
TXT_K = (
    "The suffering state ends the moment you observe the thought without becoming the thought itself. "
    "Most of us believe every story the mind tells, and that belief is the whole problem we are trying to solve. "
    "Watch the story rise and fall like a wave, and you will see that you were never inside it."
)


def test_named_guru_never_gets_other_gurus_clip():
    # store filter bypassed on purpose: the pipeline itself must refuse to substitute
    pipe, store = _pipeline([_clip("krishnaji", "Sri Krishnaji", TXT_K, [1.0, 0.0])])
    res = pipe.execute(
        query="What does Sri Preethaji say about suffering?", query_dense_vector=[1.0, 0.0]
    )
    assert store.search_hybrid.call_args.kwargs["teacher_id"] == "preethaji"
    assert res.citations == []
    assert res.status == "abstained"


def test_named_guru_keeps_only_that_gurus_clips():
    pipe, _ = _pipeline(
        [
            _clip("krishnaji", "Sri Krishnaji", TXT_K, [1.0, 0.0]),
            _clip("preethaji", "Sri Preethaji", TXT_P, [0.9, 0.1]),
        ]
    )
    res = pipe.execute(
        query="What does Sri Preethaji say about peace?", query_dense_vector=[1.0, 0.0], max_clips=3
    )
    assert res.citations
    assert {c["speaker"] for c in res.citations} == {"Sri Preethaji"}


@pytest.mark.parametrize(
    "top,label",
    [("preethaji", "Sri Preethaji"), ("krishnaji", "Sri Krishnaji")],
)
def test_unnamed_query_searches_all_gurus_and_labels_by_own_speaker(top, label):
    # No guru named: retrieval is unscoped, and whichever guru's clip ranks first is
    # served under that clip's own verified speaker label (never a fixed one).
    # Several clips per answer from both gurus need a calibration profile (CLAUDE.md
    # invariant 3), so the no-profile route shows the single closest clip.
    clips = {
        "preethaji": _clip("preethaji", "Sri Preethaji", TXT_P, [1.0, 0.0]),
        "krishnaji": _clip("krishnaji", "Sri Krishnaji", TXT_K, [1.0, 0.0]),
    }
    other = "krishnaji" if top == "preethaji" else "preethaji"
    clips[other]["passage_dense"] = [0.5, 0.5]
    pipe, store = _pipeline([clips[top], clips[other]])
    res = pipe.execute(query="How do I stop suffering?", query_dense_vector=[1.0, 0.0], max_clips=3)
    assert store.search_hybrid.call_args.kwargs["teacher_id"] in (None, "both")
    assert [c["speaker"] for c in res.citations] == [label]
