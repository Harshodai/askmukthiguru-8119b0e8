"""Guru Brain package.

Keep the ontology/governance submodules importable without loading the full
Qdrant-backed persona service. The historical public package exports remain
available through module-level lazy attribute resolution.
"""

from __future__ import annotations

from typing import Any

from .tone_extractor import SpeakerRole, ToneExtractor

__all__ = ["GuruBrainService", "get_guru_brain_service", "ToneExtractor", "SpeakerRole"]


def __getattr__(name: str) -> Any:
    if name in {"GuruBrainService", "get_guru_brain_service"}:
        from .guru_brain_service import GuruBrainService, get_guru_brain_service

        exported = {
            "GuruBrainService": GuruBrainService,
            "get_guru_brain_service": get_guru_brain_service,
        }
        return exported[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
