"""Unit tests for QdrantIndexer named-vector mapping and dynamic schema resolution."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from services.qdrant.indexer import QdrantIndexer


class TestQdrantIndexerVectorNames(unittest.TestCase):
    def test_default_collection_vector_names(self):
        """Standard collections default to ('dense', 'sparse')."""
        client = MagicMock()
        client.get_collection.side_effect = Exception("Not connected")
        indexer = QdrantIndexer(client=client, collection="spiritual_wisdom_contextual")
        dense_name, sparse_name = indexer._get_vector_names()
        self.assertEqual(dense_name, "dense")
        self.assertEqual(sparse_name, "sparse")

    def test_first_person_collection_fallback(self):
        """First-person collections fallback to ('passage_dense', 'passage_sparse') on mock/error."""
        client = MagicMock()
        client.get_collection.side_effect = Exception("Not connected")
        indexer = QdrantIndexer(client=client, collection="first_person_v13_shadow")
        dense_name, sparse_name = indexer._get_vector_names()
        self.assertEqual(dense_name, "passage_dense")
        self.assertEqual(sparse_name, "passage_sparse")

    def test_dynamic_resolution_from_collection_config(self):
        """Dynamic resolution inspects params.vectors from get_collection."""
        client = MagicMock()
        col_info = MagicMock()
        col_info.config.params.vectors = {"passage_dense": MagicMock()}
        col_info.config.params.sparse_vectors = {"passage_sparse": MagicMock()}
        client.get_collection.return_value = col_info

        indexer = QdrantIndexer(client=client, collection="custom_shadow_coll")
        dense_name, sparse_name = indexer._get_vector_names()
        self.assertEqual(dense_name, "passage_dense")
        self.assertEqual(sparse_name, "passage_sparse")

    def test_explicit_vector_names_override(self):
        """Explicit vector names passed to constructor override auto-detection."""
        client = MagicMock()
        indexer = QdrantIndexer(
            client=client,
            collection="first_person_v13_shadow",
            dense_vector_name="custom_dense",
            sparse_vector_name="custom_sparse",
        )
        dense_name, sparse_name = indexer._get_vector_names()
        self.assertEqual(dense_name, "custom_dense")
        self.assertEqual(sparse_name, "custom_sparse")
        # client.get_collection should not even be called
        client.get_collection.assert_not_called()

    def test_upsert_chunks_uses_passage_dense_for_first_person(self):
        """upsert_chunks builds PointStruct with passage_dense and passage_sparse for first_person."""
        client = MagicMock()
        client.get_collection.side_effect = Exception("Mock client")
        indexer = QdrantIndexer(client=client, collection="first_person_v13_shadow")

        texts = ["Wisdom begins with self-observation."]
        vectors = [[0.1] * 1024]
        metadatas = [{"video_id": "test_vid", "chunk_index": 0}]
        sparse_vectors = [{"indices": [1, 5], "values": [0.2, 0.8]}]

        written = indexer.upsert_chunks(
            texts=texts,
            vectors=vectors,
            metadatas=metadatas,
            sparse_vectors=sparse_vectors,
        )
        self.assertEqual(written, 1)
        client.upsert.assert_called_once()
        points = client.upsert.call_args.kwargs["points"]
        self.assertEqual(len(points), 1)
        point = points[0]
        self.assertIn("passage_dense", point.vector)
        self.assertEqual(point.vector["passage_dense"], vectors[0])
        self.assertIn("passage_sparse", point.vector)
        self.assertNotIn("dense", point.vector)


if __name__ == "__main__":
    unittest.main()
