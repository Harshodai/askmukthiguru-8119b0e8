"""Server-side assistant persona allowlist (audit item M3).

The client may send an ``assistant`` block on ``ChatRequest`` carrying a
``slug`` and a ``system_prompt``. The input rail screens ``system_prompt`` and
``GraphStage`` honours it only for authenticated users, but until M3 there was
no server-side registry of which slugs are real personas — anyone could ship a
custom slug with their prompt and have it act as the system instruction.

This module owns the allowlist. ``validate_assistant_slug`` is the single
gate: it returns the slug when it is in the allowlist, ``None`` otherwise. The
guardrail stage calls it and clears ``assistant.system_prompt`` when the slug
is rejected, so the honesty guard in ``rag/nodes/generation`` stays ON and no
attacker persona replaces the guru.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _allowed_slugs() -> frozenset[str]:
    """Return the frozen set of allowlisted assistant slugs from settings.

    ``settings.allowed_assistant_slugs`` is a comma-separated string. Whitespace
    around each slug is stripped; empty entries are dropped. Cached because it
    is read on every chat turn and the setting is process-static.
    """
    raw = getattr(settings, "allowed_assistant_slugs", "") or ""
    parsed = {s.strip() for s in raw.split(",") if s.strip()}
    return frozenset(parsed)


def validate_assistant_slug(slug: Optional[str]) -> Optional[str]:
    """Return ``slug`` if it is in the server-side allowlist, else ``None``.

    ``None``/empty input returns ``None`` (no assistant persona to validate).
    A non-allowlisted slug is logged at INFO (the slug itself is not PII — it
    is a short identifier the client chose, not user content) and rejected.
    Callers must clear ``assistant.system_prompt`` on a ``None`` return so the
    honesty guard in generation stays ON.
    """
    if not slug or not isinstance(slug, str):
        return None
    if slug in _allowed_slugs():
        return slug
    logger.info("Rejecting non-allowlisted assistant slug %r (M3).", slug)
    return None


def _self_check() -> None:
    """Runnable self-check: print the parsed allowlist and a few probes."""
    print(f"allowed_assistant_slugs={sorted(_allowed_slugs())}")
    for probe in ("guru", "evil_injected_slug", None, ""):
        print(f"validate({probe!r}) -> {validate_assistant_slug(probe)!r}")


if __name__ == "__main__":
    _self_check()