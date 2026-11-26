"""Ingest speaker labels come from the guru registry (T8-02), byte-identical to the old literal map."""

import pytest

from services.first_person_ingest_service import _speaker_label_for


@pytest.mark.parametrize(
    "teacher_id, expected",
    [
        ("preethaji", "Sri Preethaji"),
        ("KRISHNAJI", "Sri Krishnaji"),
        ("both", "Sri Preethaji & Sri Krishnaji"),
        ("unknown", "Sri Preethaji & Sri Krishnaji"),
    ],
)
def test_speaker_label_matches_previous_literal_map(teacher_id, expected):
    assert _speaker_label_for(teacher_id) == expected
