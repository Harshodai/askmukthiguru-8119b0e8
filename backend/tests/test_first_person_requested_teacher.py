"""L-FP-SPEAKER-REQUEST-1: naming one teacher scopes retrieval to that teacher."""

import pytest

from services.first_person_pipeline import requested_teacher


@pytest.mark.parametrize(
    "q,expected",
    [
        ("What does Sri Preethaji say about forgiveness?", "preethaji"),
        ("what does preethaji say about fear", "preethaji"),
        ("How does Sri Krishnaji explain the Beautiful State?", "krishnaji"),
        ("What do Sri Preethaji and Sri Krishnaji say about love?", None),
        ("Krishnaji and Preethaji on anger", None),
        ("What is the Beautiful State?", None),
        ("", None),
    ],
)
def test_requested_teacher(q, expected):
    assert requested_teacher(q) == expected
