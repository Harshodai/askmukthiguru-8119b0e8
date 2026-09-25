"""Unit tests for Retrieval Integrity Guard (Invariant A2)."""

import pytest
from services.retrieval_integrity import (
    compute_sha256,
    verify_document_integrity,
    filter_documents_by_integrity,
)


def test_compute_sha256_deterministic():
    text = "In a beautiful state, you are powerful enough to help yourself."
    h1 = compute_sha256(text)
    h2 = compute_sha256(text)
    assert h1 == h2
    assert len(h1) == 64


def test_verify_document_integrity_clean_doc():
    doc = {
        "text": "Living in connection transforms your relationships and conscious presence.",
        "source_url": "https://youtube.com/watch?v=good123",
        "metadata": {"speaker": "Sri Preethaji"},
    }
    is_valid, reason = verify_document_integrity(doc)
    assert is_valid is True
    assert reason is None


def test_verify_document_integrity_empty_text():
    doc = {"text": "   ", "source_url": "https://youtube.com/watch?v=empty"}
    is_valid, reason = verify_document_integrity(doc)
    assert is_valid is False
    assert reason == "empty_document_text"


def test_verify_document_integrity_corrupted_artifact():
    doc = {
        "text": "1. **Deconstruct the User's Request:** Analyze the query.",
        "source_url": "https://youtube.com/watch?v=poison",
    }
    is_valid, reason = verify_document_integrity(doc)
    assert is_valid is False
    assert "corrupted_artifact_detected" in reason


def test_verify_document_integrity_chunk_hash_match():
    text = "True meditation begins with witnessing without division."
    doc = {
        "text": text,
        "chunk_hash": compute_sha256(text),
        "source_url": "https://youtube.com/watch?v=hash",
    }
    is_valid, reason = verify_document_integrity(doc)
    assert is_valid is True
    assert reason is None


def test_verify_document_integrity_chunk_hash_mismatch():
    doc = {
        "text": "Tampered text that does not match the stored cryptographic hash.",
        "chunk_hash": "deadbeef" * 8,
        "source_url": "https://youtube.com/watch?v=tampered",
    }
    is_valid, reason = verify_document_integrity(doc)
    assert is_valid is False
    assert "chunk_hash_mismatch" in reason


def test_filter_documents_by_integrity():
    clean_text = "Every day lived in a beautiful state is life truly lived."
    docs = [
        {"doc_id": "doc1", "text": clean_text},
        {"doc_id": "doc2", "text": "2. **Interpret the Input:** reasoning leak"},
        {"doc_id": "doc3", "text": "Genuine teaching", "chunk_hash": "wronghash"},
    ]
    trusted, quarantined = filter_documents_by_integrity(docs)
    assert len(trusted) == 1
    assert trusted[0]["doc_id"] == "doc1"
    assert len(quarantined) == 2
    assert quarantined[0]["doc_id"] == "doc2"
    assert quarantined[1]["doc_id"] == "doc3"
