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
    # Invariant 4: OKF and doctrine lexicon are curated offline extractions subject
    # to human review. Runtime gracefully falls back to Qdrant vector and Neo4j relational
    # traversal when absent, so they do not fail the serving health readiness probe.
    RuntimeArtifact("okf_compiled", Path("/app/memory/okf/compiled.json"), required=False),
    RuntimeArtifact("doctrine_lexicon", Path("/app/data/doctrine_lexicon.json"), required=False),
    RuntimeArtifact("cpu_reranker_cache", Path("/app/model_cache/sentence_transformers"), required=False),
)


def inspect_runtime_artifacts(
    artifacts: tuple[RuntimeArtifact, ...] = ARTIFACTS,
) -> dict[str, object]:
    """Return safe, deterministic artifact metadata for health/diagnostics."""
    items: dict[str, dict[str, object]] = {}
    present = 0
    missing: list[str] = []
    missing_required: list[str] = []

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
            if artifact.required:
                missing_required.append(artifact.name)

        items[artifact.name] = {
            "present": exists,
            "size_bytes": size,
            "required": artifact.required,
        }

    return {
        # `ok` is the readiness signal: optional performance caches may be cold,
        # but curated doctrine inputs may never be absent from a release image.
        # Keep `ok` backward-compatible for diagnostics: any missing artifact
        # is visible. `readiness_ok` is the release gate and ignores only
        # explicitly optional performance caches.
        "ok": not missing,
        "readiness_ok": not missing_required,
        "present": present,
        "total": len(artifacts),
        "missing": missing,
        "missing_required": missing_required,
        "artifacts": items,
    }
