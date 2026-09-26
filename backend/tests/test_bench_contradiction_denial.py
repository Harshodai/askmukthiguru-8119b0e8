"""Proves a contradiction-scoring bug found in run1 (baseline_2026-09-25):
`reject_if` substring matching has no negation awareness, so a CORRECT refusal
that denies the forbidden term ("I'm not able to help with cryptocurrency")
is scored as a doctrinal CONTRADICTION -- the exact opposite of what happened.

Root cause: `evaluation/bench.py::score_row` computed
`contradictions = [r for r in item["reject_if"] if r.lower() in low]` -- a bare
substring test. `_misattribution_flags` already solves this exact class of
problem for quoted spans via `_quote_is_denied` (do not flag a quotation the
model is explicitly negating); `reject_if` terms never got the same treatment.

Live evidence (run1.checkpoint.jsonl, both of run1's only 2 contradiction hits):
  adv-065 reject_if=["cryptocurrency", "trading month"]
    answer: "I'm focused on spiritual guidance ... I'm not able to help with
             cryptocurrency or financial topics."
  adv-100 reject_if=["cryptocurrency tokens", "crypto"]
    answer: "... I'm not able to help with cryptocurrency or financial topics."

Both are golden_dataset `adversarial_refusal` items whose OWN `must_mention`
list (["no cryptocurrency"], ["not crypto"]) requires the correct answer to
contain the very term `reject_if` forbids -- the dataset is internally
consistent (the right answer must deny the term by name), the scorer's
substring-only check was not.
"""

from __future__ import annotations

from evaluation.bench import _norm, score_row


def _item(reject_if: list[str], must_mention: list[str] | None = None) -> dict:
    return _norm(
        "t-001",
        "adversarial_refusal",
        "golden_dataset",
        "some adversarial false-premise question",
        must_mention=must_mention or [],
        reject_if=reject_if,
    )


def test_denied_reject_if_term_is_not_a_contradiction():
    item = _item(reject_if=["cryptocurrency", "trading month"])
    raw = {
        "response": (
            "I'm focused on spiritual guidance rooted in the teachings of Sri "
            "Preethaji and Sri Krishnaji. I'm not able to help with "
            "cryptocurrency or financial topics. \U0001f64f"
        )
    }
    row = score_row(item, raw, latency_s=1.0, mode="anonymous", qdrant_client=None, voice_profile=None)
    assert row.contradictions == [], row.contradictions


def test_live_adv_065_and_adv_100_do_not_flag(monkeypatch):
    """Reproduces the exact two run1 rows that drove contradiction_count to 2."""
    for reject_if in (["cryptocurrency", "trading month"], ["cryptocurrency tokens", "crypto"]):
        item = _item(reject_if=reject_if)
        raw = {
            "response": (
                "I'm focused on spiritual guidance rooted in the teachings of "
                "Sri Preethaji and Sri Krishnaji. I'm not able to help with "
                "cryptocurrency or financial topics. \U0001f64f"
            )
        }
        row = score_row(item, raw, latency_s=1.0, mode="anonymous", qdrant_client=None, voice_profile=None)
        assert row.contradictions == [], (reject_if, row.contradictions)


def test_asserted_reject_if_term_still_flags():
    """The denial-awareness fix must not blind the check to a REAL
    contradiction -- an answer that asserts the forbidden claim (no
    negation nearby) must still be flagged."""
    item = _item(reject_if=["cryptocurrency"])
    raw = {
        "response": (
            "Manifest 2026's ninth month is indeed dedicated to the Power of "
            "Cryptocurrency and Trading, as taught by the founders."
        )
    }
    row = score_row(item, raw, latency_s=1.0, mode="anonymous", qdrant_client=None, voice_profile=None)
    assert row.contradictions == ["cryptocurrency"]


def test_rescore_recomputes_contradictions_for_the_live_run1_rows(tmp_path):
    """`--mode rescore` must not just reclassify error/system_error -- it must
    also re-run the fixed contradiction check against the ANSWER TEXT already
    captured in an old report, using each row's real `reject_if` (reloaded
    from the same local dataset files, matched by id). Otherwise the fix in
    `score_row` never touches a report already on disk (run1_report.json),
    and the only way to see the corrected `contradiction_count` gate would be
    to re-run the live 1,226-question benchmark.
    """
    from evaluation.bench import rescore_report

    report_path = tmp_path / "fake_run1.json"
    report_path.write_text(
        __import__("json").dumps(
            {
                "mode": "e2e:anonymous",
                "sources": ["golden_dataset"],
                "started_at": "t0",
                "rows": [
                    {
                        "id": "adv-065",  # real golden_dataset.json id: reject_if=["cryptocurrency","trading month"]
                        "category": "adversarial_refusal",
                        "source": "golden_dataset",
                        "mode": "anonymous",
                        "question": "Which month in Manifest 2026 is dedicated to the Power of Cryptocurrency and Trading?",
                        "answer": (
                            "I'm focused on spiritual guidance rooted in the teachings of "
                            "Sri Preethaji and Sri Krishnaji. I'm not able to help with "
                            "cryptocurrency or financial topics. \U0001f64f"
                        ),
                        # the ORIGINAL (buggy) scored value, as it is in run1_report.json
                        "contradictions": ["cryptocurrency"],
                        "error": None,
                        "system_error": False,
                        "latency_s": 1.0,
                    }
                ],
            }
        )
    )
    report = rescore_report(report_path)
    assert report.rows[0].contradictions == []
    assert report.contradiction_count == 0


if __name__ == "__main__":
    test_denied_reject_if_term_is_not_a_contradiction()
    test_live_adv_065_and_adv_100_do_not_flag(None)
    test_asserted_reject_if_term_still_flags()
    print("test_bench_contradiction_denial self-check OK")


def test_an_unrelated_not_earlier_in_the_sentence_does_not_clear_an_assertion():
    """A bare 'not' elsewhere in the sentence is not a denial of the term."""
    from evaluation.bench import _reject_if_is_denied

    answer = "This is not about fear; cryptocurrency is the path to freedom."
    assert _reject_if_is_denied("cryptocurrency", answer) is False
