"""Maximal Marginal Relevance selection helpers."""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)


class QdrantMMR:
    """Static MMR selection for diverse retrieval results."""

    @staticmethod
    def mmr_select(
        query_embedding: list[float],
        documents: list[dict],
        doc_embeddings: list[list[float]],
        top_k: int = 5,
        lambda_param: float = 0.7,
    ) -> list[dict]:
        """
        Maximal Marginal Relevance (MMR) selection for diversity.

        Iteratively selects documents that are relevant to the query
        but dissimilar to already-selected documents.

        Args:
            query_embedding: Dense embedding of the query
            documents: List of document dicts
            doc_embeddings: Dense embeddings of each document
            top_k: Number of documents to select
            lambda_param: Balance relevance (1.0) vs diversity (0.0)

        Returns:
            List of selected document dicts (diverse and relevant)
        """
        if len(documents) <= top_k:
            return documents

        query_vec = np.array(query_embedding)
        doc_vecs = np.array(doc_embeddings)

        # Normalize for cosine similarity
        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
        doc_norms = doc_vecs / (np.linalg.norm(doc_vecs, axis=1, keepdims=True) + 1e-10)

        # Query-document similarity
        query_sim = doc_norms @ query_norm

        selected_indices = []
        remaining = list(range(len(documents)))

        for _ in range(min(top_k, len(documents))):
            if not remaining:
                break

            if not selected_indices:
                # First pick: most relevant to query
                best_idx = remaining[np.argmax([query_sim[i] for i in remaining])]
            else:
                # Subsequent picks: MMR score
                best_score = -float("inf")
                best_idx = remaining[0]

                selected_vecs = doc_norms[selected_indices]
                for idx in remaining:
                    relevance = query_sim[idx]
                    # Max similarity to any already-selected document
                    redundancy = np.max(doc_norms[idx] @ selected_vecs.T)
                    mmr_score = lambda_param * relevance - (1 - lambda_param) * redundancy

                    if mmr_score > best_score:
                        best_score = mmr_score
                        best_idx = idx

            selected_indices.append(best_idx)
            remaining.remove(best_idx)

        return [documents[i] for i in selected_indices]
