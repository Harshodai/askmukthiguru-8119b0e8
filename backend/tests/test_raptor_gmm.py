"""
Unit test for RAPTOR GMM clustering (RAGFlow Gap 6).

ONE runnable check: _cluster_gmm clusters synthetic embeddings, returns
labels covering all inputs. KMeans path untouched (default).
"""

import numpy as np
import pytest

from app.config import settings
from ingest.raptor import RaptorIndexer


def _make_indexer():
    # ponytail: bypass real services — only _cluster_gmm is exercised.
    return RaptorIndexer(
        embedding_service=None,
        ollama_service=None,
        qdrant_service=None,
    )


def test_cluster_gmm_labels_cover_all_inputs(monkeypatch):
    monkeypatch.setattr(settings, "raptor_clustering_method", "gmm")
    rng = np.random.RandomState(42)
    embeddings = rng.rand(6, 10).astype(np.float32)

    idx = _make_indexer()
    clusters = idx._cluster_gmm(embeddings, n_clusters=2)

    # Every input index assigned to exactly one cluster
    all_indices = sorted(i for indices in clusters.values() for i in indices)
    assert all_indices == list(range(6))
    assert len(clusters) >= 1


def test_cluster_gmm_degenerate_single_sample():
    idx = _make_indexer()
    embeddings = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
    clusters = idx._cluster_gmm(embeddings, n_clusters=2)
    assert clusters == {0: [0]}