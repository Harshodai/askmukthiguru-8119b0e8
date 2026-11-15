"""Unit tests for OKF in-memory concept expansion (memory/okf/compiled.json)."""

from unittest.mock import patch

import numpy as np

from services.first_person_okf_expansion import expand_concepts_via_okf


def test_expand_concepts_empty_vector_returns_empty():
    assert expand_concepts_via_okf([]) == []
    assert expand_concepts_via_okf([0.1] * 512) == []  # Not 1024d


def test_expand_concepts_mock_matrix(tmp_path):
    # Create mock compiled entries
    dummy_entries = [
        {
            "title": "The Nature of Beautiful State",
            "teacher": "sri-preethaji",
            "tags": ["beautiful state", "calm", "inner peace"],
            "embedding": [1.0] + [0.0] * 1023,
        },
        {
            "title": "Dissolving the Suffering State",
            "teacher": "sri-krishnaji",
            "tags": ["suffering state", "ego", "truth of suffering"],
            "embedding": [0.0, 1.0] + [0.0] * 1022,
        },
    ]

    matrix = np.array([e["embedding"] for e in dummy_entries], dtype=np.float32)

    with patch(
        "services.first_person_okf_expansion._load_compiled_matrix",
        return_value=(dummy_entries, matrix),
    ):
        # Query aligned with first entry
        q_vec = [1.0] + [0.0] * 1023
        concepts = expand_concepts_via_okf(q_vec, max_concepts=5)

        assert "beautiful state" in concepts
        assert "calm" in concepts
        assert "inner peace" in concepts
        assert "The Nature of Beautiful State" in concepts or len(concepts) == 5

        # Query filtered by teacher
        concepts_krishna = expand_concepts_via_okf(
            [0.0, 1.0] + [0.0] * 1022,
            teacher_id="sri-krishnaji",
            max_concepts=5,
        )
        assert "suffering state" in concepts_krishna
