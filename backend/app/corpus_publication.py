"""Atomic application-facing corpus publication manifests.

Ingestion may touch several stores over time.  The serving application must
never treat a partially populated collection as a release merely because one
store is reachable.  A single manifest is written *after* every declared
store has passed validation; startup can then expose only that manifest.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from app.index_fingerprint import IndexFingerprint, IndexFingerprintError

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CorpusPublicationError(RuntimeError):
    """Raised when an active corpus publication is unsafe to serve."""


@dataclass(frozen=True)
class CorpusPublicationManifest:
    """Browser-safe publication metadata; no source text or credentials."""

    manifest_version: str
    collection: str
    corpus_version: str
    source_manifest_sha256: str
    index_fingerprint: str
    qdrant_points: int
    qdrant_sources: int
    graph_required: bool
    graph_nodes: int | None
    graph_edges: int | None

    def payload(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def digest(self) -> str:
        serialised = repr(sorted(self.payload().items())).encode("utf-8")
        return hashlib.sha256(serialised).hexdigest()

    def validate(self) -> None:
        if self.manifest_version != "v1":
            raise CorpusPublicationError("unsupported corpus publication manifest version")
        if not self.collection or not self.corpus_version:
            raise CorpusPublicationError("collection and corpus_version are required")
        if not _SHA256.fullmatch(self.source_manifest_sha256):
            raise CorpusPublicationError(
                "source_manifest_sha256 must be a lowercase SHA-256 digest"
            )
        if not _SHA256.fullmatch(self.index_fingerprint):
            raise CorpusPublicationError("index_fingerprint must be a lowercase SHA-256 digest")
        if self.qdrant_points <= 0 or self.qdrant_sources <= 0:
            raise CorpusPublicationError("published vector corpus must contain points and sources")
        if self.graph_required and (
            self.graph_nodes is None
            or self.graph_edges is None
            or self.graph_nodes <= 0
            or self.graph_edges <= 0
        ):
            raise CorpusPublicationError(
                "required graph publication must contain nodes and edges"
            )
        if not self.graph_required and (
            self.graph_nodes is not None or self.graph_edges is not None
        ):
            raise CorpusPublicationError("optional graph publication must not report graph counts")

    def assert_compatible(self, contract: IndexFingerprint) -> None:
        self.validate()
        if self.collection != contract.collection:
            raise CorpusPublicationError("publication collection does not match the active collection")
        if self.corpus_version != contract.corpus_version:
            raise CorpusPublicationError("publication corpus version does not match active configuration")
        if self.index_fingerprint != contract.digest:
            raise CorpusPublicationError("publication index fingerprint does not match active configuration")

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> CorpusPublicationManifest:
        try:
            manifest = cls(
                manifest_version=str(payload["manifest_version"]),
                collection=str(payload["collection"]),
                corpus_version=str(payload["corpus_version"]),
                source_manifest_sha256=str(payload["source_manifest_sha256"]),
                index_fingerprint=str(payload["index_fingerprint"]),
                qdrant_points=int(payload["qdrant_points"]),
                qdrant_sources=int(payload["qdrant_sources"]),
                graph_required=bool(payload["graph_required"]),
                graph_nodes=(
                    int(payload["graph_nodes"])
                    if payload.get("graph_nodes") is not None
                    else None
                ),
                graph_edges=(
                    int(payload["graph_edges"])
                    if payload.get("graph_edges") is not None
                    else None
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CorpusPublicationError("published corpus manifest is malformed") from exc
        manifest.validate()
        return manifest


def build_publication_record(
    contract: IndexFingerprint, publication: CorpusPublicationManifest
) -> dict[str, Any]:
    """Construct the single Redis value that becomes visible atomically."""
    publication.assert_compatible(contract)
    return {
        "index_contract": contract.published_payload(),
        "publication": publication.payload(),
        "publication_fingerprint": publication.digest,
    }


def validate_publication_record(record: Mapping[str, Any], contract: IndexFingerprint) -> None:
    """Fail closed unless both the index and corpus publication agree."""
    index_contract = record.get("index_contract")
    publication_payload = record.get("publication")
    if not isinstance(index_contract, Mapping) or not isinstance(publication_payload, Mapping):
        raise CorpusPublicationError(
            "published release lacks index contract or corpus manifest"
        )
    try:
        contract.assert_matches(index_contract)
    except IndexFingerprintError as exc:
        raise CorpusPublicationError(str(exc)) from exc
    publication = CorpusPublicationManifest.from_payload(publication_payload)
    publication.assert_compatible(contract)
    fingerprint = record.get("publication_fingerprint")
    if fingerprint != publication.digest:
        raise CorpusPublicationError("published corpus manifest fingerprint is corrupt")
