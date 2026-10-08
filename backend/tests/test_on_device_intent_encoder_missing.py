"""L-INTENT-ENCODER-1: with the MiniLM encoder missing, a bare keyword must not decide DISTRESS."""
import pytest

from rag.nodes import on_device_intent as odi


@pytest.fixture
def no_encoder(monkeypatch):
    monkeypatch.setattr(odi, "_ENCODER", False)


def test_doctrine_question_with_keyword_defers_to_llm(no_encoder):
    assert odi.classify_with_embeddings("What does the teaching say about the death of the ego?") is None


def test_first_person_distress_still_routes_distress(no_encoder):
    assert odi.classify_with_embeddings("I feel so sad and lonely") == "DISTRESS"


def test_acute_phrase_still_routes_distress(no_encoder):
    assert odi.classify_with_embeddings("I want to die") == "DISTRESS"
