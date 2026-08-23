"""Production runtime-artifact verification.

The serving image can be healthy while silently missing optional curated assets.
Keep the check deterministic, side-effect free, and free of file contents: health
telemetry should expose only artifact presence/size so operators can detect image
packaging drift without leaking corpus data.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeArtifact:
    name: str
    path: Path
    required: bool = False


ARTIFACTS: tuple[RuntimeArtifact, ...] = (
    RuntimeArtifact("okf_compiled", Path("/app/memory/okf/compiled.json")),
    RuntimeArtifact("doctrine_lexicon", Path("/app/data/doctrine_lexicon.json")),
    RuntimeArtifact("cpu_reranker_cache", Path("/app/model_cache/sentence_transformers")),
)


def inspect_runtime_artifacts(
    artifacts: tuple[RuntimeArtifact, ...] = ARTIFACTS,
) -> dict[str, object]:
    """Return safe, deterministic artifact metadata for health/diagnostics."""
    items: dict[str, dict[str, object]] = {}
    present = 0
    missing: list[str] = []

    for artifact in artifacts:
        exists = artifact.path.exists()
        size = 0
        if exists and artifact.path.is_file():
            try:
                size = artifact.path.stat().st_size
            except OSError:
                exists = False
        elif exists and artifact.path.is_dir():
            try:
                size = sum(p.stat().st_size for p in artifact.path.rglob("*") if p.is_file())
            except OSError:
                size = 0

        if exists:
            present += 1
        else:
            missing.append(artifact.name)

        items[artifact.name] = {
            "present": exists,
            "size_bytes": size,
            "required": artifact.required,
        }

    return {
        "ok": not missing,
        "present": present,
        "total": len(artifacts),
        "missing": missing,
        "artifacts": items,
    }
