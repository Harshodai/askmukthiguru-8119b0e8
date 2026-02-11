"""
Mukthi Guru — RAPTOR Hierarchical Indexing

Design Patterns:
  - Builder Pattern: Builds a 2-level tree from flat chunks
  - Composite Pattern: Tree of leaf nodes (chunks) and summary nodes
  - Strategy Pattern: Clustering strategy (K-Means with UMAP reduction)

RAPTOR = Recursive Abstractive Processing for Tree-Organized Retrieval.

How it works:
1. Embed all leaf chunks
2. Reduce dimensions with UMAP (384 → 10)
3. Cluster with K-Means (groups of ~8 chunks)
4. Summarize each cluster with LLM
5. Index summaries as "level-1" nodes in Qdrant

This creates a 2-level hierarchy:
  - Level 0 (leaves): Specific, granular chunks for detailed questions
  - Level 1 (summaries): Thematic overviews for broad questions

The retrieval pipeline searches BOTH levels simultaneously.
"""

import logging
import asyncio
from typing import Optional

import numpy as np
from sklearn.cluster import KMeans

from app.config import settings
from services.embedding_service import EmbeddingService
from services.ollama_service import OllamaService
from services.qdrant_service import QdrantService

logger = logging.getLogger(__name__)


class RaptorIndexer:
    """
    Builds hierarchical summary tree from leaf chunks.
    
    Builder Pattern: Construct the tree step by step:
    1. collect() — gather all leaf chunks
    2. cluster() — group semantically similar chunks
    3. summarize() — LLM-generate summary for each cluster
    4. index() — upsert summaries as level-1 nodes
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        ollama_service: OllamaService,
        qdrant_service: QdrantService,
    ) -> None:
        self._embedder = embedding_service
        self._llm = ollama_service
        self._qdrant = qdrant_service
        self._cluster_size = settings.raptor_cluster_size

    async def build_tree(self, chunks: list[dict]) -> int:
        """
        Build the RAPTOR summary tree from leaf chunks.
        
        Args:
            chunks: List of dicts with 'text' and metadata keys
            
        Returns:
            Number of summary nodes created
        """
        # Validate: filter out empty/whitespace-only chunks
        chunks = [c for c in chunks if c.get("text", "").strip()]

        if len(chunks) < self._cluster_size:
            logger.info(f"RAPTOR: too few chunks ({len(chunks)}), skipping tree build")
            return 0

        # Step 1: Embed all chunks
        texts = [c["text"] for c in chunks]
        embeddings = self._embedder.encode(texts)
        embeddings_array = np.array(embeddings)

        # Step 2: Dimensionality reduction
        reduced = self._reduce_dimensions(embeddings_array)

        # Step 3: Cluster
        n_clusters = max(2, len(texts) // self._cluster_size)
        # Guard: n_clusters cannot exceed sample count
        n_clusters = min(n_clusters, len(texts))
        clusters = self._cluster_texts(reduced, n_clusters)

        # Step 4: Summarize each cluster
        summaries = await self._summarize_clusters(texts, clusters)

        # Step 5: Index summaries as level-1 nodes
        summary_texts = [s["text"] for s in summaries]
        summary_vectors = self._embedder.encode(summary_texts)
        summary_metas = [
            {
                "content_type": "summary",
                "raptor_level": 1,
                "cluster_id": s["cluster_id"],
                "source_chunks": s["source_count"],
            }
            for s in summaries
        ]

        count = self._qdrant.upsert_chunks(summary_texts, summary_vectors, summary_metas)
        logger.info(f"RAPTOR: created {count} level-1 summary nodes from {len(texts)} chunks")
        return count

    def _reduce_dimensions(self, embeddings: np.ndarray, n_components: int = 10) -> np.ndarray:
        """
        Reduce embedding dimensions for better clustering.
        
        Uses UMAP to reduce 384-dim vectors to 10-dim while preserving
        semantic neighborhoods. Falls back to truncation if UMAP fails.
        """
        try:
            import umap
            n_samples = embeddings.shape[0]
            # UMAP requires n_components < n_samples - 1 and n_neighbors < n_samples
            safe_components = min(n_components, max(1, n_samples - 2))
            safe_neighbors = min(15, max(2, n_samples - 1))
            
            if safe_components < 2 or n_samples < 4:
                logger.warning(f"UMAP: too few samples ({n_samples}), falling back to truncation")
                return embeddings[:, :min(n_components, embeddings.shape[1])]
            
            reducer = umap.UMAP(
                n_components=safe_components,
                n_neighbors=safe_neighbors,
                min_dist=0.1,
                metric='cosine',
                random_state=42,
            )
            return reducer.fit_transform(embeddings)
        except Exception as e:
            logger.warning(f"UMAP failed, falling back to truncation: {e}")
            return embeddings[:, :min(n_components, embeddings.shape[1])]

    def _cluster_texts(self, embeddings: np.ndarray, n_clusters: int) -> dict:
        """
        Cluster reduced embeddings using K-Means.
        
        Returns: Dict mapping cluster_id → list of text indices
        """
        n_clusters = min(n_clusters, embeddings.shape[0])
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(embeddings)

        clusters = {}
        for idx, label in enumerate(labels):
            clusters.setdefault(int(label), []).append(idx)

        logger.info(f"RAPTOR: {n_clusters} clusters, sizes: {[len(v) for v in clusters.values()]}")
        return clusters

    async def _summarize_clusters(self, texts: list[str], clusters: dict) -> list[dict]:
        """
        Generate LLM summaries for each cluster.
        
        Each summary captures the thematic essence of its cluster members.
        """
        summaries = []
        for cluster_id, indices in clusters.items():
            cluster_texts = [texts[i] for i in indices]
            
            try:
                summary_text = await self._llm.summarize(cluster_texts)
                summaries.append({
                    "text": summary_text,
                    "cluster_id": cluster_id,
                    "source_count": len(cluster_texts),
                })
            except Exception as e:
                logger.error(f"RAPTOR: Failed to summarize cluster {cluster_id}: {e}")
                # Fallback: concatenate first and last chunk
                fallback = f"{cluster_texts[0][:200]} ... {cluster_texts[-1][:200]}"
                summaries.append({
                    "text": fallback,
                    "cluster_id": cluster_id,
                    "source_count": len(cluster_texts),
                })

        return summaries
