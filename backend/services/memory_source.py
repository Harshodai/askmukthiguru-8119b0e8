"""Per-memory provenance ("where did this come from?") for the memory API.

A memory only gets a source when the stored row proves one. Today that is the
chat conversation a fact was extracted from (``guru_memories.source_conversation_id``)
and, for the personal Wisdom Map, a saved study-notebook item. Every other memory
(older rows, explicit entries, anything with a malformed id) returns ``None`` so
the UI can say "source unavailable". Nothing here fabricates a source or a URL:
the API returns only ``kind`` + ``id``, and the frontend maps a known kind to one
of its own routes.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# Same shape the extraction edge functions accept before storing the value.
SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")

SOURCE_KIND_CONVERSATION = "conversation"
SOURCE_KIND_NOTEBOOK = "notebook"


def _clean_id(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    return candidate if SOURCE_ID_RE.match(candidate) else None


def memory_source_ref(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Return ``{"kind": "conversation", "id": ...}`` or None when unproven."""
    conversation_id = _clean_id(row.get("source_conversation_id"))
    if conversation_id is None:
        return None
    return {"kind": SOURCE_KIND_CONVERSATION, "id": conversation_id}


def notebook_source_ref(item_id: Any) -> Optional[dict[str, Any]]:
    """Source reference for a study-notebook item node, or None for a bad id."""
    clean = _clean_id(str(item_id) if item_id is not None else None)
    if clean is None:
        return None
    return {"kind": SOURCE_KIND_NOTEBOOK, "id": clean}


def is_missing_column_error(exc: BaseException) -> bool:
    """True when PostgREST/Postgres rejected a select because a column is absent."""
    text = str(exc)
    return any(
        marker in text for marker in ("42703", "PGRST204", "does not exist", "Could not find")
    )
