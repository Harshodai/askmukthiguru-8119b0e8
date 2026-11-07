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
        ("Explain the steps of Sudarshan Kriya as taught by Art of Living.", "Sudarshan Kriya"),
        ("What did Jiddu Krishnamurti say about truth being a pathless land?", "Jiddu Krishnamurti"),
    ],
)
def test_external_teacher_patterns_recognized(query: str, expected_teacher: str):
    detected = requested_unregistered_teacher_or_tradition(query)
    assert detected is not None
    assert expected_teacher.lower() in detected.lower()
    # Ensure registered gurus are not falsely detected for external inquiries
    assert requested_gurus(query) == []


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
