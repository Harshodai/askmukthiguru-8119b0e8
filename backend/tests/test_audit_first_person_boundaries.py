"""Boundary audit summary (plan rev 2, card B5)."""

from scripts.ops.audit_first_person_boundaries import summarize


def _clip(text, duration_s=20.0):
    return {
        "video_id": "v",
        "speaker": "preethaji",
        "verbatim_text": text,
        "duration_s": duration_s,
    }


def test_summarize_counts_clean_head_and_tail_defects():
    s = summarize(
        [
            _clip("Suffering is not a fact."),
            _clip("and then you let go of", 9.0),
            _clip("So approach your yoga gently.", 50.0),
        ]
    )
    assert (s["clips"], s["clean"], s["clean_pct"]) == (3, 2, 66.67)
    assert (s["head_defect_clips"], s["tail_defect_clips"]) == (1, 1)
    assert s["duration_buckets"] == {"18-25s": 1, "<18s": 1, ">45s": 1}
    assert [e["head"] for e in s["defective_examples"]] == ["and then you let go of"]


def test_summarize_empty_source():
    assert summarize([])["clean_pct"] == 0.0
