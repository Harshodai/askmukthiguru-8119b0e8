"""Immutable retrieval-index compatibility contracts.

Qdrant being reachable only proves that it can answer vector queries.  It does
not prove those vectors were created with the encoder, chunker, sparse schema,
or corpus release the running application expects.  This module makes that
contract explicit and produces a deterministic SHA-256 digest that can be
published alongside a corpus release.

The contract deliberately contains configuration identifiers only.  It never
contains source bodies, queries, credentials, or generated answers.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping


class IndexFingerprintError(RuntimeError):
    """Raised when a published index contract is malformed or incompatible."""


@dataclass(frozen=True)
class IndexFingerprint:
    """All answer-affecting retrieval-index settings for one collection."""

    contract_version: str
    collection: str
    corpus_version: str
    embedding_model: str
    embedding_revision: str
    embedding_backend: str
    dense_dimension: int
    pooling_mode: str
    sparse_encoder: str
    sparse_enabled: bool
    chunking_version: str
    chunk_size: int
    chunk_overlap: int
    adaptive_chunking_enabled: bool
    proposition_chunking: str
    late_chunking_enabled: bool
    metadata_schema_version: str
    raptor_enabled: bool
    raptor_cluster_size: int
    raptor_clustering_method: str
    reranker_model: str
    reranker_backend: str

    def payload(self) -> dict[str, Any]:
        """Return a canonical JSON-safe payload, excluding its own digest."""
        return asdict(self)

    @property
    def digest(self) -> str:
        """Return the stable SHA-256 identity for this exact contract."""
        encoded = json.dumps(
            self.payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def published_payload(self) -> dict[str, Any]:
        """Return the durable record written by an explicit publication step."""
        return {"contract": self.payload(), "fingerprint": self.digest}

    def assert_matches(self, published: Mapping[str, Any]) -> None:
        """Fail closed unless a published record is exactly this contract."""
        if not isinstance(published, Mapping):
            raise IndexFingerprintError("published index contract must be an object")
        contract = published.get("contract")
        fingerprint = published.get("fingerprint")
        if not isinstance(contract, Mapping) or not isinstance(fingerprint, str):
            raise IndexFingerprintError(
                "published index contract must contain an object contract and fingerprint"
            )
        canonical = json.dumps(
            dict(contract), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        actual_digest = hashlib.sha256(canonical).hexdigest()
        if actual_digest != fingerprint:
            raise IndexFingerprintError("published index contract fingerprint is corrupt")
        if fingerprint == self.digest and dict(contract) == self.payload():
            return

        contract_keys = set(contract.keys())
        payload_keys = set(self.payload().keys())
        if contract_keys != payload_keys:
            missing = payload_keys - contract_keys
            extra = contract_keys - payload_keys
            issues = []
            if missing:
                issues.append(f"missing keys: {missing}")
            if extra:
                issues.append(f"extra keys: {extra}")
            raise ValueError(f"Contract key mismatch: {'; '.join(issues)}")

        changed = sorted(
            key
            for key in set(self.payload()) | set(contract)
            if self.payload().get(key) != contract.get(key)
        )
        raise IndexFingerprintError(
            "published index contract is incompatible; changed fields: " + ", ".join(changed)
        )


def _as_str(value: Any, fallback: str) -> str:
    value = str(value if value is not None else fallback).strip()
    return value or fallback


def build_index_fingerprint(
    settings: Any, *, collection: str, corpus_version: str | int | None = None
) -> IndexFingerprint:
    """Build the expected collection contract from the active configuration."""
    resolved_corpus_version = _as_str(
        corpus_version
        if corpus_version is not None
        else getattr(settings, "corpus_release_fallback_version", None),
        "1",
    )
    return IndexFingerprint(
        contract_version=_as_str(getattr(settings, "index_contract_version", None), "v1"),
        collection=_as_str(collection, "unknown"),
        corpus_version=resolved_corpus_version,
        embedding_model=_as_str(getattr(settings, "embedding_model", None), "unknown"),
        embedding_revision=_as_str(
            getattr(settings, "embedding_model_revision", None), "unresolved"
        ),
        embedding_backend=_as_str(getattr(settings, "embedding_backend", None), "unknown"),
        dense_dimension=int(getattr(settings, "embedding_dimension", 0) or 0),
        pooling_mode=_as_str(getattr(settings, "embedding_pooling_mode", None), "mean"),
        sparse_encoder=_as_str(getattr(settings, "sparse_encoder", None), "bge-m3"),
        sparse_enabled=bool(getattr(settings, "bm25_retrieval_enabled", False)),
        chunking_version=_as_str(getattr(settings, "ingestion_chunking_version", None), "v1"),
        chunk_size=int(getattr(settings, "rag_chunk_size", 0) or 0),
        chunk_overlap=int(getattr(settings, "rag_chunk_overlap", 0) or 0),
        adaptive_chunking_enabled=bool(getattr(settings, "use_adaptive_chunking", False)),
        proposition_chunking=_as_str(
            getattr(settings, "use_proposition_chunking", None), "never"
        ),
        late_chunking_enabled=bool(getattr(settings, "reingest_late_chunking", False)),
        metadata_schema_version=_as_str(
            getattr(settings, "retrieval_metadata_schema_version", None), "v1"
        ),
        raptor_enabled=bool(getattr(settings, "raptor_parent_summaries_enabled", False)),
        raptor_cluster_size=int(getattr(settings, "raptor_cluster_size", 0) or 0),
        raptor_clustering_method=_as_str(
            getattr(settings, "raptor_clustering_method", None), "unknown"
        ),
        reranker_model=_as_str(getattr(settings, "reranker_model", None), "unknown"),
        reranker_backend=_as_str(getattr(settings, "reranker_backend", None), "unknown"),
    )
