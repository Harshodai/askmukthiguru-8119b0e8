"""Governed source-release registry for corpus publication.

Only source metadata and state transitions are stored. Source bodies, seeker text,
prompts, and generated answers are deliberately excluded from this control plane.
The Supabase migration provides transaction-safe approval and activation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

_VALID_STATUSES = frozenset({"pending", "approved", "active", "superseded", "rejected"})
_MAX_CORPUS_ID_LENGTH = 160
_MAX_SOURCE_IDENTITY_LENGTH = 1024
_MAX_SOURCE_URL_LENGTH = 4096
_MAX_CHECKSUM_LENGTH = 256
_MAX_NOTES_LENGTH = 1000


class CorpusReleaseRegistryError(RuntimeError):
    """Base release-registry operation error."""


class CorpusReleaseRegistryDisabled(CorpusReleaseRegistryError):
    """Raised when a mutable operation is requested while the feature is off."""


class CorpusReleaseRegistryUnavailable(CorpusReleaseRegistryError):
    """Raised when an enabled registry cannot reach its control store."""


class CorpusReleaseTransitionError(CorpusReleaseRegistryError):
    """Raised when a requested source-release transition is illegal."""


def _normalise_text(field: str, value: Any, max_length: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    result = value.strip()
    if not result:
        raise ValueError(f"{field} must not be empty")
    if len(result) > max_length:
        raise ValueError(f"{field} exceeds {max_length} characters")
    return result


def _normalise_uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("release_id must be a valid UUID") from exc


def _optional_text(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _timestamp(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return value if isinstance(value, str) else None


@dataclass(frozen=True)
class SourceRelease:
    """Immutable, browser-safe source-release projection."""

    id: str
    corpus_id: str
    source_url: str
    source_identity: str
    release_version: int
    status: str
    approved_by: str | None = None
    approved_at: str | None = None
    activated_at: str | None = None
    notes: str | None = None
    created_at: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> SourceRelease:
        status = str(row.get("status") or "")
        if status not in _VALID_STATUSES:
            raise ValueError("source release returned an invalid status")
        try:
            version = int(row.get("release_version"))
        except (TypeError, ValueError) as exc:
            raise ValueError("source release returned an invalid version") from exc
        if version < 1:
            raise ValueError("source release returned a non-positive version")
        return cls(
            id=_normalise_uuid(str(row.get("id") or "")),
            corpus_id=_normalise_text("corpus_id", row.get("corpus_id"), _MAX_CORPUS_ID_LENGTH),
            source_url=_normalise_text("source_url", row.get("source_url"), _MAX_SOURCE_URL_LENGTH),
            source_identity=_normalise_text(
                "source_identity", row.get("source_identity"), _MAX_SOURCE_IDENTITY_LENGTH
            ),
            release_version=version,
            status=status,
            approved_by=_optional_text(row.get("approved_by")),
            approved_at=_timestamp(row.get("approved_at")),
            activated_at=_timestamp(row.get("activated_at")),
            notes=_optional_text(row.get("notes")),
            created_at=_timestamp(row.get("created_at")),
        )

    def admin_dict(self) -> dict[str, Any]:
        """Allowlist browser-safe operational metadata; omit checksum/source body."""
        return {
            "id": self.id,
            "corpus_id": self.corpus_id,
            "source_url": self.source_url,
            "source_identity": self.source_identity,
            "release_version": self.release_version,
            "status": self.status,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "activated_at": self.activated_at,
            "notes": self.notes,
            "created_at": self.created_at,
        }


@dataclass
class CorpusReleaseRegistry:
    """Supabase-backed source-release controller with fail-soft version reads."""

    enabled: bool
    client: Any | None = None
    fallback_version: int = 1

    @classmethod
    def from_settings(
        cls, settings: Any | None = None, *, client: Any | None = None
    ) -> CorpusReleaseRegistry:
        if settings is None:
            from app.config import settings as app_settings

            settings = app_settings
        enabled = bool(getattr(settings, "corpus_release_registry_enabled", False))
        fallback = int(getattr(settings, "corpus_release_fallback_version", 1) or 1)
        fallback = fallback if fallback > 0 else 1
        if not enabled or client is not None:
            return cls(enabled=enabled, client=client, fallback_version=fallback)
        try:
            from app.telemetry_db import _get_client

            return cls(enabled=True, client=_get_client(), fallback_version=fallback)
        except Exception as exc:
            logger.warning("Source-release registry client unavailable: %s", exc)
            return cls(enabled=True, client=None, fallback_version=fallback)

    def register_source(
        self,
        *,
        corpus_id: str,
        source_url: str,
        source_identity: str,
        content_checksum: str,
        notes: str | None = None,
    ) -> SourceRelease:
        self._require_mutable_client()
        return self._rpc_release(
            "register_source_release",
            {
                "p_corpus_id": _normalise_text("corpus_id", corpus_id, _MAX_CORPUS_ID_LENGTH),
                "p_source_url": _normalise_text("source_url", source_url, _MAX_SOURCE_URL_LENGTH),
                "p_source_identity": _normalise_text(
                    "source_identity", source_identity, _MAX_SOURCE_IDENTITY_LENGTH
                ),
                "p_content_checksum": _normalise_text(
                    "content_checksum", content_checksum, _MAX_CHECKSUM_LENGTH
                ),
                "p_notes": self._notes(notes),
            },
        )

    def list_releases(
        self, *, corpus_id: str, source_identity: str | None = None, limit: int = 100
    ) -> list[SourceRelease]:
        if not self.enabled:
            return []
        if self.client is None:
            raise CorpusReleaseRegistryUnavailable("source-release control store is unavailable")
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        try:
            query = (
                self.client.table("source_releases")
                .select(
                    "id,corpus_id,source_url,source_identity,release_version,status,approved_by,approved_at,activated_at,notes,created_at"
                )
                .eq("corpus_id", _normalise_text("corpus_id", corpus_id, _MAX_CORPUS_ID_LENGTH))
            )
            if source_identity:
                query = query.eq(
                    "source_identity",
                    _normalise_text(
                        "source_identity", source_identity, _MAX_SOURCE_IDENTITY_LENGTH
                    ),
                )
            response = query.order("created_at", desc=True).limit(limit).execute()
            return [SourceRelease.from_row(row) for row in (getattr(response, "data", None) or [])]
        except CorpusReleaseRegistryError:
            raise
        except Exception as exc:
            raise CorpusReleaseRegistryUnavailable("could not list source releases") from exc

    def approve_release(self, release_id: str, *, approved_by: str) -> SourceRelease:
        return self._rpc_release(
            "approve_source_release",
            {
                "p_release_id": _normalise_uuid(release_id),
                "p_approved_by": _normalise_text("approved_by", approved_by, 256),
            },
        )

    def reactivate_release(self, release_id: str, *, approved_by: str) -> SourceRelease:
        """Explicitly re-approve a superseded release, then atomically activate it."""
        self.approve_release(release_id, approved_by=approved_by)
        return self.activate_release(release_id)

    def activate_release(self, release_id: str) -> SourceRelease:
        return self._rpc_release(
            "activate_source_release", {"p_release_id": _normalise_uuid(release_id)}
        )

    def reject_release(self, release_id: str) -> SourceRelease:
        return self._rpc_release(
            "reject_source_release", {"p_release_id": _normalise_uuid(release_id)}
        )

    def get_active_release(self, *, corpus_id: str, source_identity: str) -> SourceRelease | None:
        if not self.enabled or self.client is None:
            return None
        try:
            response = (
                self.client.table("source_releases")
                .select(
                    "id,corpus_id,source_url,source_identity,release_version,status,approved_by,approved_at,activated_at,notes,created_at"
                )
                .eq("corpus_id", _normalise_text("corpus_id", corpus_id, _MAX_CORPUS_ID_LENGTH))
                .eq(
                    "source_identity",
                    _normalise_text(
                        "source_identity", source_identity, _MAX_SOURCE_IDENTITY_LENGTH
                    ),
                )
                .eq("status", "active")
                .limit(1)
                .execute()
            )
            rows = getattr(response, "data", None) or []
            return SourceRelease.from_row(rows[0]) if rows else None
        except Exception as exc:
            logger.warning("Source-release active-version lookup failed: %s", exc)
            return None

    def get_active_version(
        self,
        *,
        corpus_id: str,
        source_identity: str,
        fallback_version: int | None = None,
    ) -> int:
        fallback = self.fallback_version
        if isinstance(fallback_version, int) and fallback_version > 0:
            fallback = fallback_version
        active = self.get_active_release(
            corpus_id=corpus_id,
            source_identity=source_identity,
        )
        return active.release_version if active is not None else fallback

    def _rpc_release(self, function_name: str, payload: dict[str, Any]) -> SourceRelease:
        self._require_mutable_client()
        try:
            response = self.client.rpc(function_name, payload).execute()
            data = getattr(response, "data", None)
            row = data[0] if isinstance(data, list) and data else data
            if not isinstance(row, dict):
                raise CorpusReleaseRegistryUnavailable("release control store returned no release")
            return SourceRelease.from_row(row)
        except CorpusReleaseRegistryError:
            raise
        except Exception as exc:
            message = str(exc).lower()
            if (
                "only approved" in message
                or "not pending" in message
                or "may be rejected" in message
            ):
                raise CorpusReleaseTransitionError(str(exc)) from exc
            raise CorpusReleaseRegistryUnavailable(
                f"release control store rejected {function_name}"
            ) from exc

    def _require_mutable_client(self) -> None:
        if not self.enabled:
            raise CorpusReleaseRegistryDisabled("source-release registry is disabled")
        if self.client is None:
            raise CorpusReleaseRegistryUnavailable("source-release control store is unavailable")

    @staticmethod
    def _notes(notes: str | None) -> str | None:
        if notes is None:
            return None
        value = notes.strip()
        if not value:
            return None
        if len(value) > _MAX_NOTES_LENGTH:
            raise ValueError(f"notes exceeds {_MAX_NOTES_LENGTH} characters")
        return value
