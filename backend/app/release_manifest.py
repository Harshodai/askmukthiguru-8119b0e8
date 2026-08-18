"""Release Provenance & Manifest Specification (Phase 3).

Defines the immutable ReleaseManifest dataclass, singleton accessor,
and startup readiness validation. Never includes secrets, credentials, or tokens.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Any

from app.config import settings


class ReleaseManifestError(ValueError):
    """Raised when a ReleaseManifest fails validation or contains unsafe content."""


# Secret and token patterns that MUST NEVER appear in a release manifest
_SECRET_PATTERNS = [
    re.compile(r"(?i)\bsk-[a-zA-Z0-9_\-]{16,}"),
    re.compile(r"(?i)\bghp_[a-zA-Z0-9]{20,}"),
    re.compile(r"(?i)\beyJ[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}"),
    re.compile(r"(?i)\bBearer\s+[a-zA-Z0-9_\-\.]{10,}"),
    re.compile(r"(?i)-----BEGIN[A-Z\s]+PRIVATE KEY-----"),
    re.compile(r"(?i)(password|api_key|secret_key|auth_token)\s*[:=]\s*['\"][^'\"]+['\"]"),
]


@dataclass(frozen=True)
class ReleaseManifest:
    """Immutable release and policy provenance manifest."""

    release_id: str
    git_sha: str
    build_timestamp: str
    corpus_version: str
    embedding_model: str
    embedding_dim: int
    reranker_model: str
    policy_version: str
    schema_version: str

    def to_dict(self) -> dict[str, Any]:
        """Convert manifest to a JSON-serializable dictionary."""
        return asdict(self)

    def validate(self) -> None:
        """Validate manifest invariants and readiness at startup.

        Raises ReleaseManifestError if any required field is missing, invalid,
        or contains potential credentials/secrets.
        """
        # 1. Type and value validations
        str_fields = {
            "release_id": self.release_id,
            "git_sha": self.git_sha,
            "build_timestamp": self.build_timestamp,
            "corpus_version": self.corpus_version,
            "embedding_model": self.embedding_model,
            "reranker_model": self.reranker_model,
            "policy_version": self.policy_version,
            "schema_version": self.schema_version,
        }

        for field_name, value in str_fields.items():
            if not isinstance(value, str) or not value.strip():
                raise ReleaseManifestError(
                    f"ReleaseManifest field '{field_name}' must be a non-empty string, got {value!r}"
                )

        # 2. Embedding dimension validation (strictly positive int, reject bool)
        if isinstance(self.embedding_dim, bool) or not isinstance(self.embedding_dim, int) or self.embedding_dim <= 0:
            raise ReleaseManifestError(
                f"ReleaseManifest field 'embedding_dim' must be a positive integer, got {self.embedding_dim!r}"
            )

        # 3. Secret and token scanner across all fields
        manifest_dict = self.to_dict()
        for field_name, value in manifest_dict.items():
            str_val = str(value)
            for pattern in _SECRET_PATTERNS:
                if pattern.search(str_val):
                    raise ReleaseManifestError(
                        f"ReleaseManifest field '{field_name}' contains potential secret or credential token"
                    )


_GLOBAL_MANIFEST: ReleaseManifest | None = None


def build_release_manifest(
    *,
    release_id: str | None = None,
    git_sha: str | None = None,
    build_timestamp: str | None = None,
    corpus_version: str | int | None = None,
    embedding_model: str | None = None,
    embedding_dim: int | None = None,
    reranker_model: str | None = None,
    policy_version: str | None = None,
    schema_version: str | None = None,
) -> ReleaseManifest:
    """Build a ReleaseManifest instance from settings and environment variables."""
    resolved_git_sha = (
        git_sha
        or os.getenv("GIT_SHA")
        or os.getenv("RAILWAY_GIT_COMMIT_SHA")
        or getattr(settings, "git_sha", "unknown-sha")
        or ""
    ).strip() or "unknown-sha"

    resolved_build_ts = (
        build_timestamp
        or os.getenv("BUILD_TIMESTAMP")
        or "2026-08-17T00:00:00Z"
    ).strip() or "2026-08-17T00:00:00Z"

    raw_corpus_v = (
        corpus_version
        if corpus_version is not None
        else os.getenv("CORPUS_VERSION")
        or getattr(settings, "corpus_release_fallback_version", "1")
    )
    resolved_corpus_version = str(raw_corpus_v).strip() or "1"

    resolved_embed_model = (
        embedding_model
        or getattr(settings, "embedding_model", "BAAI/bge-m3")
        or ""
    ).strip() or "BAAI/bge-m3"

    resolved_embed_dim = (
        embedding_dim
        if embedding_dim is not None
        else int(getattr(settings, "embedding_dimension", 1024))
    )

    resolved_reranker = (
        reranker_model
        or getattr(settings, "reranker_model", "BAAI/bge-reranker-v2-m3")
        or ""
    ).strip() or "BAAI/bge-reranker-v2-m3"

    resolved_policy_version = (
        policy_version
        or getattr(settings, "openrouter_policy_id", "gemini-flash-budget-v1")
        or ""
    ).strip() or "gemini-flash-budget-v1"

    resolved_schema_version = (
        schema_version
        or os.getenv("SCHEMA_VERSION")
        or getattr(settings, "schema_version", "1.0.0")
        or ""
    ).strip() or "1.0.0"

    resolved_release_id = (
        (release_id or os.getenv("RELEASE_ID") or "").strip()
        or f"rel-{resolved_git_sha[:8] if resolved_git_sha != 'unknown-sha' else 'dev'}-c{resolved_corpus_version}-p{resolved_policy_version}"
    )

    manifest = ReleaseManifest(
        release_id=resolved_release_id,
        git_sha=resolved_git_sha,
        build_timestamp=resolved_build_ts,
        corpus_version=resolved_corpus_version,
        embedding_model=resolved_embed_model,
        embedding_dim=resolved_embed_dim,
        reranker_model=resolved_reranker,
        policy_version=resolved_policy_version,
        schema_version=resolved_schema_version,
    )
    return manifest


def get_release_manifest() -> ReleaseManifest:
    """Return the active singleton ReleaseManifest.

    Validates readiness on creation.
    """
    global _GLOBAL_MANIFEST
    if _GLOBAL_MANIFEST is None:
        manifest = build_release_manifest()
        manifest.validate()
        _GLOBAL_MANIFEST = manifest
    return _GLOBAL_MANIFEST


def set_release_manifest(manifest: ReleaseManifest | None) -> None:
    """Set or reset the global ReleaseManifest singleton (used for tests/reloads)."""
    global _GLOBAL_MANIFEST
    if manifest is not None:
        manifest.validate()
    _GLOBAL_MANIFEST = manifest


def validate_release_manifest(manifest: ReleaseManifest | None = None) -> None:
    """Startup readiness validation entrypoint.

    Validates the provided manifest or the active singleton.
    """
    target = manifest or get_release_manifest()
    target.validate()
