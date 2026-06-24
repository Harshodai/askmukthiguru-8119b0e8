"""Mukthi Guru Qdrant vector database subpackage.

Decomposes the monolithic QdrantService into focused concerns:
- client: connection and collection management
- indexer: chunk upsert, delete, backup, counts
- searcher: hybrid/dense retrieval with metadata filtering
- neighbor: context-window neighbour lookup
- raptor: hierarchical summary node retrieval
- filters: reusable Qdrant filter builders
- mmr: maximal marginal relevance selection
- utils: point IDs, poison detection, sparse-vector conversion
"""

from services.qdrant.client import QdrantClientManager
from services.qdrant.filters import QdrantFilterBuilder
from services.qdrant.indexer import QdrantIndexer
from services.qdrant.mmr import QdrantMMR
from services.qdrant.neighbor import QdrantNeighborLookup
from services.qdrant.raptor import QdrantRaptorStore
from services.qdrant.searcher import QdrantSearcher
from services.qdrant.utils import QdrantUtils

__all__ = [
    "QdrantClientManager",
    "QdrantFilterBuilder",
    "QdrantIndexer",
    "QdrantMMR",
    "QdrantNeighborLookup",
    "QdrantRaptorStore",
    "QdrantSearcher",
    "QdrantUtils",
]
