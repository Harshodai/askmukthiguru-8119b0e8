"""RAPTOR hierarchical summary-node retrieval."""

from __future__ import annotations

import logging
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    FieldCondition,
    Filter,
    MatchValue,
)

from services.qdrant.utils import QdrantUtils

logger = logging.getLogger(__name__)


class QdrantRaptorStore:
    """Retrieves RAPTOR level-1 summary nodes for tree navigation."""

    def __init__(self, client: QdrantClient, collection: str, utils: Optional[QdrantUtils] = None) -> None:
        self._client = client
        self._collection = collection
        self._utils = utils or QdrantUtils()

    def get_summary_nodes(
        self, query_vector: Optional[list[float]] = None, limit: int = 15
    ) -> list[dict]:
        """
        Retrieve RAPTOR level-1 summary nodes for tree navigation.
        If query_vector is provided, searches by similarity; otherwise scrolls.
        """
        try:
            if query_vector is not None:
                query_res = self._client.query_points(
                    collection_name=self._collection,
                    query=query_vector,
                    using="dense",
                    query_filter=Filter(
                        must=[
                            FieldCondition(
                                key="raptor_level",
                                match=MatchValue(value=1),
                            )
                        ]
                    ),
                    limit=limit,
                    with_payload=True,
                )
                results = query_res.points
            else:
                results, _ = self._client.scroll(
                    collection_name=self._collection,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(
                                key="raptor_level",
                                match=MatchValue(value=1),
                            )
                        ]
                    ),
                    limit=100,  # Unlikely to have more than 100 summary nodes
                    with_payload=True,
                )

            nodes = []
            for point in results:
                payload = point.payload or {}
                text = payload.get("text", "")
                if self._utils.is_poisoned_node(text):
                    continue
                nodes.append(
                    {
                        "cluster_id": payload.get("cluster_id", 0),
                        "text": text,
                        "topic_label": payload.get("topic_label", ""),
                        "titles": payload.get("titles", []),
                        "source_urls": payload.get("source_urls", []),
                    }
                )

            logger.info(f"Tree navigation: retrieved {len(nodes)} summary nodes")
            return nodes

        except Exception as e:
            logger.error(f"Failed to retrieve summary nodes: {e}")
            return []
