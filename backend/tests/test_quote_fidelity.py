"""A rendered teacher quote must be the stored words, speaker, title and time.

Regression for the 2026-10-04 expanded benchmark, which reported 8/8 PASS while
video 0z-IZ2ar4eA (stored as a Sri Preethaji interview) was rendered under three
invented titles, once as Sri Krishnaji, with quote text absent from the source.
The rendered markdown below is copied from that report.
"""

import json

from benchmarks.quote_fidelity_check import main as check_main
from services.quote_fidelity import (
    AttributedQuote,
    ChunkRecord,
    SourceRecord,
    cross_case_conflicts,
    parse_attributed_quotes,
    parse_timestamp,
    verify_quote,
)

CASE_3 = """Sri Krishnaji speaks directly to this inner inquiry:

**Sri Krishnaji** · [The Living Reality of Oneness Beyond Philosophy](https://www.youtube.com/watch?v=0z-IZ2ar4eA&t=320s)

Oneness is not a philosophy to be debated; it is a living shift in neurobiology and consciousness. Traditional paths often demand severe renunciation, intellectual contemplation, or years of ascetic struggle.

───

[▶️ Listen in Sri Krishnaji's Voice (05:20 – 07:50)] · The Living Reality of Oneness Beyond Philosophy
"""

CASE_4_HEADER = "**Sri Preethaji** · [Four Sacred Secrets](https://www.youtube.com/watch?v=0z-IZ2ar4eA&t=200s)\n\nSome words here that are long enough to count."

STORED_0Z = SourceRecord(
    video_id="0z-IZ2ar4eA",
    title=(
        "IEC 2023 | Mukti Guru Sri Preethaji Co-Creator Of Ekam Speaks On "
        "Consciousness Superpower| Times now"
    ),
    teacher_id="preethaji",
    duration_seconds=900,
    chunks=[
        ChunkRecord(
            text="[t=5m10s] When you are in a beautiful state, you are connected to everything around you.",
        )
    ],
)


def test_parses_speaker_title_video_and_timestamp_from_rendered_answer():
    [q] = parse_attributed_quotes(CASE_3, case="3")
    assert q.speaker == "Sri Krishnaji"
    assert q.title == "The Living Reality of Oneness Beyond Philosophy"
    assert q.video_id == "0z-IZ2ar4eA"
    assert q.start_seconds == 320
    assert q.text.startswith("Oneness is not a philosophy")
    assert "Listen in" not in q.text


def test_case_3_fails_on_text_speaker_and_title():
    [q] = parse_attributed_quotes(CASE_3, case="3")
    v = verify_quote(q, STORED_0Z)
    assert not v.ok
    assert {"text_not_verbatim", "speaker_mismatch", "title_mismatch"} <= set(v.failures)
    assert len(v.missing_sentences) == 2


def test_verbatim_quote_with_matching_metadata_passes():
    q = AttributedQuote(
        text="When you are in a beautiful state you are connected to everything around you!",
        speaker="Sri Preethaji",
        title=STORED_0Z.title,
        video_id="0z-IZ2ar4eA",
        start_seconds=315,
    )
    assert verify_quote(q, STORED_0Z).ok


def test_timestamp_outside_the_matched_chunk_fails():
    q = AttributedQuote(
        text="When you are in a beautiful state, you are connected to everything around you.",
        speaker="Sri Preethaji",
        title=STORED_0Z.title,
        video_id="0z-IZ2ar4eA",
        start_seconds=40,
    )
    assert verify_quote(q, STORED_0Z).failures == ["timestamp_mismatch"]


def test_timestamp_past_end_of_video_fails():
    src = SourceRecord(
        video_id="M_BYTcsLQuY",
        title="Feel the Power of the chant",
        teacher_id="preethaji",
        duration_seconds=225,
        chunks=[ChunkRecord(text="In the Soul Sync meditation we chant the word Aham.")],
    )
    q = AttributedQuote(
        text="In the Soul Sync meditation we chant the word Aham.",
        speaker="Sri Preethaji",
        title="Feel the Power of the chant",
        video_id="M_BYTcsLQuY",
        start_seconds=600,
    )
    assert "timestamp_past_end_of_video" in verify_quote(q, src).failures


def test_unknown_speaker_and_id_only_title_fail_closed():
    src = SourceRecord(
        video_id="4eV8OvVEm6A",
        title="4eV8OvVEm6A",  # what ingestion_state.json stores for many videos
        teacher_id="ekam",
        chunks=[ChunkRecord(text="Intelligence is not limited to the brain alone.")],
    )
    q = AttributedQuote(
        text="Intelligence is not limited to the brain alone.",
        speaker="Sri Preethaji",
        title="Universal Intelligence & The Neurobiology of Consciousness",
        video_id="4eV8OvVEm6A",
        start_seconds=280,
    )
    failures = set(verify_quote(q, src).failures)
    assert {"speaker_unverifiable", "title_unverifiable", "timestamp_unverifiable"} <= failures


def test_per_chunk_speaker_overrides_video_level_teacher_id():
    src = SourceRecord(
        video_id="UlOt31lBhLY",
        title="Marie Forleo interview",
        teacher_id="preethaji_krishnaji",
        chunks=[
            ChunkRecord(
                text="Suffering is an obsessive preoccupation with oneself.",
                speaker="Sri Krishnaji",
            )
        ],
    )
    q = AttributedQuote(
        text="Suffering is an obsessive preoccupation with oneself.",
        speaker="Sri Preethaji",
        title="Marie Forleo interview",
        video_id="UlOt31lBhLY",
    )
    assert verify_quote(q, src).failures == ["speaker_mismatch"]


def test_missing_video_fails():
    q = AttributedQuote(text="Anything at all that is long enough.", video_id="zzzzzzzzzzz")
    assert verify_quote(q, None).failures == ["video_not_in_corpus"]


def test_one_video_under_several_titles_and_speakers_is_flagged():
    quotes = parse_attributed_quotes(CASE_3, "3") + parse_attributed_quotes(CASE_4_HEADER, "4")
    problems = cross_case_conflicts(quotes)
    assert any("different titles" in p for p in problems)
    assert any("different speakers" in p for p in problems)


def test_parse_timestamp_forms():
    assert parse_timestamp("280s") == 280
    assert parse_timestamp("4m40s") == 280
    assert parse_timestamp("04:40") == 280
    assert parse_timestamp("1:02:03") == 3723
    assert parse_timestamp("") is None


def test_cli_exits_nonzero_for_the_reported_case(tmp_path):
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps([{"case": "3", "answer": CASE_3}]))
    sources = tmp_path / "sources.json"
    sources.write_text(
        json.dumps(
            {
                "0z-IZ2ar4eA": [
                    {
                        "text": STORED_0Z.chunks[0].text,
                        "title": STORED_0Z.title,
                        "teacher_id": "preethaji",
                        "duration": 900,
                    }
                ]
            }
        )
    )
    out = tmp_path / "report.json"
    assert (
        check_main(
            ["--answers", str(answers), "--sources-json", str(sources), "--json-out", str(out)]
        )
        == 1
    )
    report = json.loads(out.read_text())
    assert report["quotes"][0]["verdict"] == "FAIL"
