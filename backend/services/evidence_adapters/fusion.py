"""Reciprocal Rank Fusion (RRF) & canonical evidence deduplication across retrieval systems."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from domain.evidence_contract import EvidenceCandidate


@dataclass(frozen=True)
class RRFConfig:
    """Configurable parameters for cross-system Reciprocal Rank Fusion."""

    k0: int = 60
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "qdrant": 1.0,
            "memgraph": 0.75,
            "okf": 0.50,
            "canonical_registry": 1.0,
        }
    )


class EvidenceFusionEngine:
    """Fuses ranked lists from independent retrieval adapters via RRF with canonical ID deduplication.

    Invariant: an evidence unit returned by all three systems (Qdrant, Memgraph, OKF)
    is merged into a single EvidenceCandidate with ``corroborating_sources`` populated,
    never counted as three independent sources.
    """

    def __init__(self, config: RRFConfig | None = None) -> None:
        self._config = config or RRFConfig()

    def fuse(
        self,
        ranked_lists: dict[str, Iterable[EvidenceCandidate]],
        *,
        limit: int = 20,
    ) -> list[EvidenceCandidate]:
        k0 = max(1, int(self._config.k0))
        weights = self._config.weights

        merged: dict[str, EvidenceCandidate] = {}
        rrf_scores: dict[str, float] = {}
        sources_map: dict[str, list[str]] = {}

        for system_name, candidates in ranked_lists.items():
            weight = float(weights.get(system_name, 0.5))
            seen_in_system: set[str] = set()
            for rank_idx, cand in enumerate(candidates, start=1):
                key = cand.dedup_key
                if key in seen_in_system:
                    continue
                seen_in_system.add(key)
                rrf_scores[key] = rrf_scores.get(key, 0.0) + (weight / float(k0 + rank_idx))
                sources_map.setdefault(key, [])
                if system_name not in sources_map[key]:
                    sources_map[key].append(system_name)

                if key not in merged:
                    merged[key] = cand
                else:
                    merged[key] = self._merge_pair(merged[key], cand)

        ordered_keys = sorted(merged.keys(), key=lambda k: rrf_scores[k], reverse=True)[:limit]
        results: list[EvidenceCandidate] = []
        for k in ordered_keys:
            cand = merged[k]
            results.append(
                cand.model_copy(
                    update={
                        "rrf_score": round(rrf_scores[k], 6),
                        "corroborating_sources": list(sources_map[k]),
                    }
                )
            )
        return results

    @staticmethod
    def _merge_pair(primary: EvidenceCandidate, incoming: EvidenceCandidate) -> EvidenceCandidate:
        """Preserve the highest-authority verification/provenance fields across corroborating systems."""
        prefer_incoming = (not primary.speaker_verified and incoming.speaker_verified) or (
            primary.retrieval_source != "qdrant" and incoming.retrieval_source == "qdrant"
        )
        base = incoming if prefer_incoming else primary
        other = primary if prefer_incoming else incoming

        merged_concepts = list(dict.fromkeys([*base.concepts, *other.concepts]))
        merged_paths = list(dict.fromkeys([*base.graph_paths, *other.graph_paths]))
        surrounding = base.surrounding_context or other.surrounding_context
        return base.model_copy(
            update={
                "concepts": merged_concepts,
                "graph_paths": merged_paths,
                "surrounding_context": surrounding,
                "speaker_verified": base.speaker_verified or other.speaker_verified,
                "start_time": base.start_time if base.start_time is not None else other.start_time,
                "end_time": base.end_time if base.end_time is not None else other.end_time,
                "page_number": base.page_number
                if base.page_number is not None
                else other.page_number,
                "chapter": base.chapter or other.chapter,
            }
        )
