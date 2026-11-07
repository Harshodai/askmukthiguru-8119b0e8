"""Regression tests for external teacher and non-corpus tradition inquiries (ua46, GURU-011).

Inquiries asking specifically for teachings of external teachers or traditions
(e.g., Thich Nhat Hanh, Sadhguru, Eckhart Tolle, Advaita Vedanta, Buddha, etc.)
must honestly abstain without serving misattributed clips from Sri Preethaji or
Sri Krishnaji.
"""

from __future__ import annotations

import pytest

from services.first_person_pipeline import FirstPersonPipeline
from services.guru_registry import (
    requested_gurus,
    requested_unregistered_teacher_or_tradition,
)


@pytest.mark.parametrize(
    ("query", "expected_teacher"),
    [
        ("What does Thich Nhat Hanh teach about walking meditation?", "Thich Nhat Hanh"),
        ("What does Sadhguru teach about the Isha Kriya practice?", "Sadhguru"),
        ("Explain Shankaracharya's argument for Advaita Vedanta in his own words.", "Shankaracharya"),
        ("What did the Buddha say about the Four Noble Truths in the Pali canon?", "Buddha"),
        ("Recite the Lord's Prayer and explain its meaning.", "Lord's Prayer"),
        ("What does Eckhart Tolle say about the pain-body?", "Eckhart Tolle"),
        ("Explain the ten Sefirot in Kabbalah.", "ten Sefirot"),
        ("What are the main ideas in Marcus Aurelius' Meditations?", "Marcus Aurelius"),
        ("Explain the steps of Sudarshan Kriya as taught by Art of Living.", "Art of Living"),
        ("What did Jiddu Krishnamurti say about truth being a pathless land?", "Jiddu Krishnamurti"),
        ("What does Meister Eckhart teach about detachment?", "Meister Eckhart"),
        ("What does Rupert Spira teach about awareness?", "Rupert Spira"),
        ("What does Tara Brach say about radical acceptance?", "Tara Brach"),
        ("Explain Spinoza's view on nature and God.", "Spinoza"),
        ("How does Lao Tzu describe the Tao in the Tao Te Ching?", "Lao Tzu"),
        ("Alan Watts on ego", "Alan Watts"),
        ("According to Shunryu Suzuki, what is beginner's mind?", "Shunryu Suzuki"),
        ("What is Eckhart Tolle's advice on anxiety?", "Eckhart Tolle"),
    ],
)
def test_external_teacher_patterns_recognized(query: str, expected_teacher: str):
    detected = requested_unregistered_teacher_or_tradition(query)
    assert detected is not None
    assert expected_teacher.lower() in detected.lower()
    # Ensure registered gurus are not falsely detected for external inquiries
    assert requested_gurus(query) == []


@pytest.mark.parametrize(
    ("query", "expected_registered", "expected_guru_id"),
    [
        ("What does Sri Preethaji teach about meditation?", True, "preethaji"),
        ("What does Krishnaji say about anger and fear?", True, "krishnaji"),
        ("What does Krishna ji teach about suffering?", True, "krishnaji"),
        ("How does Sri Preethaji explain the beautiful state?", True, "preethaji"),
        ("Preethaji on relationships", True, "preethaji"),
        ("How do I walk peacefully in daily life?", False, None),
        ("What is the beautiful state?", False, None),
        ("How do I forgive my father?", False, None),
        ("How do I deal with anxiety in my daily life?", False, None),
    ],
)
def test_registered_and_benign_queries_authority_extraction(
    query: str, expected_registered: bool, expected_guru_id: str | None
):
    from services.guru_registry import extract_target_authority

    auth = extract_target_authority(query)
    if not expected_registered:
        # Benign inquiries should not extract an external teacher or tradition
        assert requested_unregistered_teacher_or_tradition(query) is None
    else:
        assert auth is not None
        assert auth["is_registered"] is True
        assert auth["guru_id"] == expected_guru_id
        assert requested_unregistered_teacher_or_tradition(query) is None


@pytest.mark.parametrize(
    "query",
    [
        "What does Sri Preethaji teach about meditation?",
        "What does Krishnaji say about anger and fear?",
        "How do I walk peacefully in daily life?",
        "How can I experience the beautiful state?",
        "How do I forgive my father?",
    ],
)
def test_registered_and_benign_queries_not_flagged_as_external(query: str):
    assert requested_unregistered_teacher_or_tradition(query) is None


def test_first_person_pipeline_abstains_on_external_teacher():
    pipeline = FirstPersonPipeline()
    result = pipeline.execute(
        query="What does Thich Nhat Hanh teach about walking meditation?",
        query_dense_vector=[0.0] * 1024,
    )
    assert result.status == "abstained"
    assert result.abstain_reason == "no_verified_clips"
    assert result.citations == []
    assert result.is_direct_answer is False


def test_first_person_pipeline_abstains_on_zero_shot_external_teacher():
    pipeline = FirstPersonPipeline()
    result = pipeline.execute(
        query="What does Meister Eckhart teach about detachment?",
        query_dense_vector=[0.0] * 1024,
    )
    assert result.status == "abstained"
    assert result.abstain_reason == "no_verified_clips"
    assert result.citations == []
    assert result.is_direct_answer is False
