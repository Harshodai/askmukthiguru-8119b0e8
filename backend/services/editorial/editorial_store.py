"""Persistence port for editorial projects (in-memory default, Supabase adapter behind a flag)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from services.editorial.editorial_service import EditorialProject


class EditorialStoreError(RuntimeError):
    """Raised when the persistent store is unavailable or rejects a write. Never swallowed."""


class EditorialStore(Protocol):
    def save(self, project: EditorialProject) -> None: ...

    def get(self, project_id: str) -> EditorialProject | None: ...

    def list(self) -> list[EditorialProject]: ...

    def append_audit(self, project_id: str, entry: dict[str, Any]) -> None: ...


class InMemoryEditorialStore:
    """Process-local store: the audit trail lives inside ``project.audit_log`` only."""

    def __init__(self) -> None:
        self._projects: dict[str, EditorialProject] = {}

    def save(self, project: EditorialProject) -> None:
        self._projects[project.project_id] = project

    def get(self, project_id: str) -> EditorialProject | None:
        return self._projects.get(project_id)

    def list(self) -> list[EditorialProject]:
        return list(self._projects.values())

    def append_audit(self, project_id: str, entry: dict[str, Any]) -> None:
        return None  # ponytail: audit already rides in project.audit_log


class SupabaseEditorialStore:
    """Persists to ``editorial_projects`` (full snapshot) and append-only ``editorial_audit_log``.

    Needs the columns added by 20261126120000_editorial_persistence.sql. Every client
    failure propagates; there is no fallback to memory.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    def _require(self) -> Any:
        if self._client is None:
            raise EditorialStoreError("Supabase client unavailable for editorial persistence.")
        return self._client

    def save(self, project: EditorialProject) -> None:
        row = {
            "id": project.project_id,
            "title": project.title,
            "topic": project.topic,
            "objective": project.objective,
            "target_format": project.target_format,
            "status": project.status,
            "assigned_editor_id": project.author_id,
            "approved_by": project.approved_by,
            "approved_at": project.approved_at.isoformat() if project.approved_at else None,
            "updated_at": project.updated_at.isoformat(),
            "snapshot": project.model_dump(mode="json"),
        }
        self._require().table("editorial_projects").upsert(row).execute()

    def get(self, project_id: str) -> EditorialProject | None:
        from services.editorial.editorial_service import EditorialProject

        resp = (
            self._require()
            .table("editorial_projects")
            .select("snapshot")
            .eq("id", project_id)
            .limit(1)
            .execute()
        )
        rows = list(getattr(resp, "data", None) or [])
        return EditorialProject.model_validate(rows[0]["snapshot"]) if rows else None

    def list(self) -> list[EditorialProject]:
        from services.editorial.editorial_service import EditorialProject

        resp = self._require().table("editorial_projects").select("snapshot").execute()
        return [EditorialProject.model_validate(r["snapshot"]) for r in (resp.data or [])]

    def append_audit(self, project_id: str, entry: dict[str, Any]) -> None:
        row = {
            "project_id": project_id,
            "actor_id": entry.get("actor_id"),
            "event": entry["event"],
            "from_state": entry.get("from_state"),
            "to_state": entry.get("to_state"),
            "detail": entry,
            "created_at": entry["at"],
        }
        self._require().table("editorial_audit_log").insert(row).execute()
