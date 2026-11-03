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


# ------------------------------------------------------------ P4: promotion gate


def _v2(span_id, video="v1", **over):
    row = {
        "record_type": "retrieval_child",
        "source_span_id": span_id,
        "video_id": video,
        "speaker_verified": True,
        "voice_verification_method": "ecapa_voxceleb_span_slice_v2",
        "voice_model_revision": "rev-1",
        "voice_score": 0.7,
        "voice_margin": 0.4,
        "voice_threshold_applied": {"cosine_floor": 0.28, "margin_threshold": 0.05},
        "voice_calibration_id": "cal-1",
        "speaker_verification_status": "verified",
    }
    row.update(over)
    return row


def _unverified(span_id, video="v1"):
    return {
        "record_type": "retrieval_child",
        "source_span_id": span_id,
        "video_id": video,
        "speaker_verified": False,
    }


def test_promotion_gate_passes_a_clean_collection():
    from domain.speaker_audit import promotion_speaker_gate

    report = promotion_speaker_gate(
        [_v2("a"), _v2("b"), _unverified("c"), {"record_type": "parent_unit"}]
    )
    assert report["ok"] is True and report["decision"] == "pass"
    assert report["children"] == 3 and report["verified"] == 2
    assert report["violators"]["count"] == 0


def test_promotion_gate_one_bare_flag_span_blocks():
    from domain.speaker_audit import promotion_speaker_gate

    bare = _v2("bad", voice_verification_method=None)
    report = promotion_speaker_gate([_v2("a"), bare])
    assert report["ok"] is False
    assert report["decision"] == "blocked_violators"
    assert report["violators"]["count"] == 1
    assert report["violators"]["span_ids_first_20"] == ["bad"]
    assert report["violators"]["by_code"] == {"speaker_verified_without_method": 1}


def test_promotion_gate_blocks_a_method_with_no_calibration_id():
    from domain.speaker_audit import promotion_speaker_gate

    report = promotion_speaker_gate([_v2("a", voice_calibration_id=None)])
    assert report["decision"] == "blocked_violators"
    assert report["violators"]["by_code"] == {"ecapa_missing": 1}


def test_promotion_gate_counts_legacy_centroid_without_blocking():
    from domain.speaker_audit import promotion_speaker_gate

    legacy = {
        "record_type": "retrieval_child",
        "source_span_id": "old",
        "video_id": "v1",
        "speaker_verified": True,
        "voice_verification_method": "ecapa_voxceleb_centroid_v1",
    }
    report = promotion_speaker_gate([_v2("a"), legacy])
    assert report["ok"] is True
    assert report["legacy_centroid_verified"] == 1


def test_promotion_gate_empty_collection_never_passes():
    from domain.speaker_audit import promotion_speaker_gate

    assert promotion_speaker_gate([])["decision"] == "blocked_empty"
    assert promotion_speaker_gate([{"record_type": "parent_unit"}])["ok"] is False


def test_promotion_gate_reads_the_audit_result():
    from domain.speaker_audit import promotion_speaker_gate

    spans = [_v2("a")]
    blocked = promotion_speaker_gate(
        spans, audit_gate={"ok": False, "decision": "blocked_not_teacher"}
    )
    assert blocked["decision"] == "blocked_audit" and blocked["ok"] is False
    # A result that says ok but names another decision is not trusted.
    odd = promotion_speaker_gate(spans, audit_gate={"ok": True, "decision": "blocked_incomplete"})
    assert odd["ok"] is False
    passed = promotion_speaker_gate(spans, audit_gate={"ok": True, "decision": "pass"})
    assert passed["ok"] is True and passed["audit_gate_checked"] is True


def test_promotion_gate_require_audit_gate_blocks_when_missing():
    from domain.speaker_audit import promotion_speaker_gate

    report = promotion_speaker_gate([_v2("a")], require_audit_gate=True)
    assert report["decision"] == "blocked_audit_missing"
    assert promotion_speaker_gate([_v2("a")])["audit_gate_checked"] is False


def test_all_teacher_video_is_flagged_but_never_blocks():
    from domain.speaker_audit import promotion_speaker_gate

    spans = [_v2(f"s{i}", video="qa") for i in range(10)]
    spans += [_v2("x", video="short")] + [_v2(f"m{i}", video="mixed") for i in range(9)]
    spans.append(_unverified("host", video="mixed"))
    report = promotion_speaker_gate(spans)
    flags = report["all_teacher_video_flags"]
    assert report["ok"] is True and flags["blocking"] is False
    assert flags["videos"] == [{"video_id": "qa", "spans": 10}]
