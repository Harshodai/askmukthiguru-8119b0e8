"""A generic reference to the in-domain teachings is not an external teacher.

Live 2026-11-19: "What is suffering according to the teachings?" abstained as an
"external teacher/tradition inquiry (teachings)" while "What is suffering?"
served a clip. The "according to X" pattern captured "the teachings" and, since
"teachings" is not a registered guru id, treated it as an outside authority.
"""

from __future__ import annotations

import pytest

from services.guru_registry import requested_unregistered_teacher_or_tradition

IN_DOMAIN = [
    "What is suffering according to the teachings?",
    "According to the gurus, what is love?",
    "What is fear according to your teachings?",
    "What is love according to Sri Krishnaji?",
]

EXTERNAL = {
    # A pronoun may refer back to an external teacher named in a prior turn.
    "according to him what is ego?": "him",
    "according to the Ascended Masters what is light?": "Ascended Masters",
    "What is karma according to Osho?": "Osho",
    "According to the Bible what is sin?": "Bible",
    "What does Sadhguru say about fear?": "Sadhguru",
    "What is love according to Thich Nhat Hanh?": "Thich Nhat Hanh",
}


@pytest.mark.parametrize("query", IN_DOMAIN)
def test_generic_in_domain_reference_is_not_external(query: str) -> None:
    assert requested_unregistered_teacher_or_tradition(query, allow_comparative=True) is None


@pytest.mark.parametrize("query,target", EXTERNAL.items())
def test_named_external_teacher_still_detected(query: str, target: str) -> None:
    assert requested_unregistered_teacher_or_tradition(query, allow_comparative=True) == target
