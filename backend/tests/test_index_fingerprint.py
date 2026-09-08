"""Regression tests for published retrieval-index compatibility contracts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.corpus_publication import (
    CorpusPublicationError,
    CorpusPublicationManifest,
    build_publication_record,
    validate_publication_record,
)
from app.index_fingerprint import IndexFingerprintError, build_index_fingerprint


def _settings(**overrides):
    values = {
        "index_contract_version": "v1",
        "corpus_release_fallback_version": 4,
        "embedding_model": "BAAI/bge-m3",
        "embedding_model_revision": "5617a9f61b028005a4858fdac845db406aefb181",
        "embedding_backend": "flagembedding",
        "embedding_dimension": 1024,
        "embedding_pooling_mode": "mean",
        "sparse_encoder": "bge-m3",
        "bm25_retrieval_enabled": True,
        "ingestion_chunking_version": "contextual-v2",
        "rag_chunk_size": 1500,
        "rag_chunk_overlap": 200,
        "use_adaptive_chunking": True,
        "use_proposition_chunking": "auto",
        "reingest_late_chunking": True,
        "retrieval_metadata_schema_version": "v2",
        "raptor_parent_summaries_enabled": True,
        "raptor_cluster_size": 8,
        "raptor_clustering_method": "kmeans",
        "reranker_model": "BAAI/bge-reranker-v2-m3",
        "reranker_backend": "onnx_int8",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_index_fingerprint_is_stable_for_identical_contracts():
    first = build_index_fingerprint(_settings(), collection="spiritual_wisdom_contextual")
    second = build_index_fingerprint(_settings(), collection="spiritual_wisdom_contextual")

    assert first.digest == second.digest
    first.assert_matches(second.published_payload())


@pytest.mark.parametrize(
    "field,value",
    [
        ("embedding_model_revision", "a" * 40),
        ("embedding_dimension", 768),
        ("use_adaptive_chunking", False),
        ("raptor_clustering_method", "gmm"),
        ("reranker_backend", "flagembedding"),
    ],
)
def test_index_fingerprint_rejects_answer_affecting_drift(field, value):
    expected = build_index_fingerprint(_settings(), collection="spiritual_wisdom_contextual")
    changed = build_index_fingerprint(
        _settings(**{field: value}), collection="spiritual_wisdom_contextual"
    )

    with pytest.raises(IndexFingerprintError, match="incompatible"):
        expected.assert_matches(changed.published_payload())


def test_index_fingerprint_rejects_tampered_published_contract():
    contract = build_index_fingerprint(_settings(), collection="spiritual_wisdom_contextual")
    published = contract.published_payload()
    published["contract"]["dense_dimension"] = 384

    with pytest.raises(IndexFingerprintError, match="corrupt"):
        contract.assert_matches(published)


def _publication(contract, **overrides):
    values = {
        "manifest_version": "v1",
        "collection": contract.collection,
        "corpus_version": contract.corpus_version,
        "source_manifest_sha256": "a" * 64,
        "index_fingerprint": contract.digest,
        "qdrant_points": 10,
        "qdrant_sources": 2,
        "graph_required": True,
        "graph_nodes": 4,
        "graph_edges": 3,
    }
    values.update(overrides)
    return CorpusPublicationManifest(**values)


def test_publication_manifest_requires_vector_and_graph_agreement():
    contract = build_index_fingerprint(_settings(), collection="spiritual_wisdom_contextual")
    record = build_publication_record(contract, _publication(contract))

    validate_publication_record(record, contract)


def test_publication_manifest_rejects_index_or_graph_drift():
    contract = build_index_fingerprint(_settings(), collection="spiritual_wisdom_contextual")
    with pytest.raises(CorpusPublicationError, match="nodes and edges"):
        build_publication_record(
            contract, _publication(contract, graph_nodes=0, graph_edges=0)
        )
    with pytest.raises(CorpusPublicationError, match="index fingerprint"):
        build_publication_record(contract, _publication(contract, index_fingerprint="b" * 64))


def test_publication_script_requires_explicit_mode():
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "ops"
        / "publish_retrieval_index_contract.py"
    )
    result = subprocess.run(
        [sys.executable, str(script), "--source-manifest", "dummy.json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert "one of the arguments --dry-run --apply is required" in result.stderr


def test_publication_script_requires_source_manifest():
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "ops"
        / "publish_retrieval_index_contract.py"
    )
    result = subprocess.run(
        [sys.executable, str(script), "--dry-run"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert "the following arguments are required: --source-manifest" in result.stderr
