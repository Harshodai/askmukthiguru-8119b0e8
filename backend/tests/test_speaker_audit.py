"""P6: the seeded audit sampler and the gate that reads the listeners' answers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND.parent
for _entry in (str(_REPO_ROOT), str(_BACKEND)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from domain import speaker_audit as audit  # noqa: E402


def _payload(n, method="ecapa_voxceleb_span_slice_v2", guru="krishnaji", **over):
    base = {
        "record_type": "retrieval_child",
        "source_span_id": f"span-{n:04d}",
        "video_id": f"vid{n % 7}",
        "guru_id": guru,
        "speaker_verified": True,
        "voice_verification_method": method,
    }
    base.update(over)
    return base


def _pool(n_auto=200, n_human=0):
    pool = [_payload(i) for i in range(n_auto)]
    pool += [_payload(10_000 + i, method="human_listen_v1") for i in range(n_human)]
    return pool


def _ids(sample):
    return [row["source_span_id"] for row in sample["spans"]]


# ---- size rule ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "pool,expected",
    [(0, 0), (10, 10), (30, 30), (200, 30), (600, 30), (601, 31), (2000, 100), (4000, 200)],
)
def test_size_is_30_or_5_percent_whichever_is_larger_capped_at_the_pool(pool, expected):
    assert audit.audit_sample_size(pool) == expected


# ---- reproducibility ------------------------------------------------------------------------
def test_the_same_seed_batch_and_pool_draw_the_same_spans():
    first = audit.draw_audit_sample(_pool(), batch_id="b1", seed="s")
    second = audit.draw_audit_sample(list(reversed(_pool())), batch_id="b1", seed="s")
    assert _ids(first) == _ids(second)
    assert first["sample_sha256"] == second["sample_sha256"]


def test_a_different_seed_or_batch_draws_different_spans():
    base = _ids(audit.draw_audit_sample(_pool(), batch_id="b1", seed="s"))
    assert base != _ids(audit.draw_audit_sample(_pool(), batch_id="b1", seed="other"))
    assert base != _ids(audit.draw_audit_sample(_pool(), batch_id="b2", seed="s"))


def test_the_sample_is_a_subset_of_the_pool_with_no_duplicates():
    sample = audit.draw_audit_sample(_pool(), batch_id="b1", seed="s")
    ids = _ids(sample)
    assert len(ids) == len(set(ids)) == 30
    assert set(ids) <= {p["source_span_id"] for p in _pool()}


def test_the_sample_is_not_just_the_first_spans():
    ids = _ids(audit.draw_audit_sample(_pool(1000), batch_id="b1", seed="s"))
    assert max(ids) > "span-0500"  # drawn from across the pool


def test_an_empty_seed_or_batch_is_refused():
    with pytest.raises(ValueError):
        audit.draw_audit_sample(_pool(), batch_id="", seed="s")
    with pytest.raises(ValueError):
        audit.draw_audit_sample(_pool(), batch_id="b", seed=" ")


# ---- pool and strata ------------------------------------------------------------------------
def test_only_verified_children_with_a_recognised_method_are_eligible():
    payloads = [
        _payload(1),
        _payload(2, speaker_verified=False),
        _payload(3, voice_verification_method=None),
        _payload(4, voice_verification_method="trust_me"),
        {"record_type": "parent_unit", "speaker_verified": True},
    ]
    sample = audit.draw_audit_sample(payloads, batch_id="b", seed="s")
    assert _ids(sample) == ["span-0001"]


def test_human_verified_spans_are_audited_as_their_own_stratum():
    sample = audit.draw_audit_sample(_pool(n_auto=200, n_human=100), batch_id="b", seed="s")
    assert sample["strata"]["automated"] == {"pool": 200, "sampled": 30}
    assert sample["strata"]["human"] == {"pool": 100, "sampled": 30}
    assert {row["stratum"] for row in sample["spans"]} == {"automated", "human"}


# ---- review classification and the gate -----------------------------------------------------
@pytest.mark.parametrize(
    "guru,choice,expected",
    [
        ("krishnaji", "sri_krishnaji", "confirmed"),
        ("preethaji", "sri_preethaji", "confirmed"),
        ("krishnaji", "sri_preethaji", "not_teacher"),
        ("krishnaji", "host_or_interviewer", "not_teacher"),
        ("krishnaji", "other", "not_teacher"),
        ("krishnaji", "unclear", "unresolved"),
        ("krishnaji", None, "unresolved"),
        ("krishnaji", "krishnaji", "unresolved"),
        ("unknown_guru", "sri_krishnaji", "not_teacher"),
    ],
)
def test_review_classification(guru, choice, expected):
    assert audit.classify_review(guru, choice) == expected


def _sample():
    return audit.draw_audit_sample(_pool(60), batch_id="b1", seed="s", minimum=5, fraction=0.05)


def _reviews(sample, choice="sri_krishnaji", **overrides):
    out = {row["source_span_id"]: {"review_choice": choice} for row in sample["spans"]}
    out.update(overrides)
    return out


def test_all_confirmed_passes():
    sample = _sample()
    result = audit.audit_gate(sample, _reviews(sample))
    assert result["decision"] == audit.DECISION_PASS and result["ok"] is True
    assert result["confirmed"] == result["sampled"] == 5


def test_one_not_the_teacher_stops_the_batch():
    sample = _sample()
    victim = _ids(sample)[0]
    result = audit.audit_gate(
        sample, _reviews(sample, **{victim: {"review_choice": "host_or_interviewer"}})
    )
    assert result["decision"] == audit.DECISION_BLOCKED_NOT_TEACHER
    assert result["ok"] is False
    assert result["not_teacher_span_ids"] == [victim]
    assert "recalibrate" in result["action"]


def test_a_rejection_outranks_missing_answers():
    sample = _sample()
    ids = _ids(sample)
    reviews = {ids[0]: {"review_choice": "other"}}  # the rest unanswered
    assert audit.audit_gate(sample, reviews)["decision"] == audit.DECISION_BLOCKED_NOT_TEACHER


def test_a_sampled_span_nobody_answered_blocks_as_incomplete():
    sample = _sample()
    reviews = _reviews(sample)
    missing = _ids(sample)[-1]
    reviews.pop(missing)
    result = audit.audit_gate(sample, reviews)
    assert result["decision"] == audit.DECISION_BLOCKED_INCOMPLETE
    assert result["unresolved_span_ids"] == [missing]


def test_an_unclear_answer_blocks_as_incomplete():
    sample = _sample()
    first = _ids(sample)[0]
    result = audit.audit_gate(sample, _reviews(sample, **{first: {"review_choice": "unclear"}}))
    assert result["decision"] == audit.DECISION_BLOCKED_INCOMPLETE


def test_an_empty_sample_never_passes():
    empty = audit.draw_audit_sample([], batch_id="b", seed="s")
    assert audit.audit_gate(empty, {})["ok"] is False


def test_reviews_of_spans_outside_the_sample_are_reported_not_counted():
    sample = _sample()
    reviews = _reviews(sample, **{"span-9999": {"review_choice": "sri_krishnaji"}})
    result = audit.audit_gate(sample, reviews)
    assert result["ok"] is True
    assert result["reviews_for_spans_outside_the_sample"] == ["span-9999"]


# ---- CLI ------------------------------------------------------------------------------------
def test_cli_sample_then_gate_round_trip(tmp_path, monkeypatch, capsys):
    from scripts.ops import speaker_audit as cli

    monkeypatch.setattr(cli, "_scroll", lambda *_a, **_k: iter(_pool(60)))
    out = tmp_path / "sample.json"
    code = cli.main(
        [
            "sample",
            "--collection",
            "c",
            "--batch-id",
            "b1",
            "--seed",
            "s",
            "--min-spans",
            "5",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    sample = json.loads(out.read_text())
    assert sample["collection"] == "c" and len(sample["spans"]) == 5

    reviews = tmp_path / "reviews.jsonl"
    reviews.write_text(
        "".join(
            json.dumps({"source_span_id": r["source_span_id"], "review_choice": "sri_krishnaji"})
            + "\n"
            for r in sample["spans"]
        )
    )
    assert cli.main(["gate", "--sample", str(out), "--reviews", str(reviews)]) == 0

    reviews.write_text(
        json.dumps(
            {"source_span_id": sample["spans"][0]["source_span_id"], "review_choice": "other"}
        )
        + "\n"
    )
    assert cli.main(["gate", "--sample", str(out), "--reviews", str(reviews)]) == 1


def test_cli_gate_rejects_a_malformed_reviews_file(tmp_path, capsys):
    from scripts.ops import speaker_audit as cli

    sample = tmp_path / "s.json"
    sample.write_text(json.dumps(audit.draw_audit_sample(_pool(40), batch_id="b", seed="s")))
    bad = tmp_path / "r.jsonl"
    bad.write_text("{not json\n")
    assert cli.main(["gate", "--sample", str(sample), "--reviews", str(bad)]) == 2
    assert "invalid_input" in capsys.readouterr().err


def test_cli_later_review_lines_win(tmp_path):
    from scripts.ops import speaker_audit as cli

    path = tmp_path / "r.jsonl"
    path.write_text(
        json.dumps({"source_span_id": "x", "review_choice": "other"})
        + "\n"
        + json.dumps({"source_span_id": "x", "review_choice": "sri_krishnaji"})
        + "\n"
    )
    assert cli.load_reviews(path)["x"]["review_choice"] == "sri_krishnaji"
