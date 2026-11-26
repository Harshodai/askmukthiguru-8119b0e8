"""Independent retrieval adapters for Qdrant, Memgraph, OKF, RRF fusion, and claim verification."""

from services.evidence_adapters.claim_verifier import ClaimVerificationService
from services.evidence_adapters.fusion import EvidenceFusionEngine, RRFConfig
from services.evidence_adapters.memgraph_adapter import MemgraphEvidenceAdapter
from services.evidence_adapters.okf_adapter import OKFEvidenceAdapter
from services.evidence_adapters.qdrant_adapter import QdrantEvidenceAdapter

__all__ = [
    "ClaimVerificationService",
    "EvidenceFusionEngine",
    "MemgraphEvidenceAdapter",
    "OKFEvidenceAdapter",
    "QdrantEvidenceAdapter",
    "RRFConfig",
]
