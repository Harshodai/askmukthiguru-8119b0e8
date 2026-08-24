"""Provenance-first evidence bands for vector/graph context.

Accepts both ``ContextItem`` objects from GraphRAGFusion and plain retrieval
dicts from the finalization boundary. Returns a bounded, serializable evidence
contract for generation, telemetry, and the frontend provenance drawer.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

BAND_DIRECT = "direct_source"
BAND_GRAPH = "graph_one_hop"
BAND_CORROBORATED = "corroborated"
BAND_COMMUNITY = "community_summary"
BANDS = (BAND_DIRECT, BAND_GRAPH, BAND_CORROBORATED, BAND_COMMUNITY)


@dataclass
class ProvenanceEvidence:
    text: str
    band: str
    score: float
    source_url: Optional[str] = None
    source_segment_id: Optional[str] = None
    entity_ids: list[str] = field(default_factory=list)
    relation: Optional[str] = None
    hop: int = 0
    confidence: float = 0.0
    ontology_version: Optional[str] = None
    rights_status: Optional[str] = None
    channel: str = "vector"
    corroborated: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["text"] = self.text[:4000]
        payload["entity_ids"] = list(dict.fromkeys(self.entity_ids))[:32]
        return payload


@dataclass
class ProvenanceContext:
    bands: dict[str, list[ProvenanceEvidence]]
    total_tokens: int
    evidence_count: int
    entities_touched: list[str] = field(default_factory=list)

    def to_manifest(self) -> dict[str, Any]:
        return {
            "bands": {
                band: [item.to_public_dict() for item in self.bands.get(band, [])]
                for band in BANDS
            },
            "total_tokens": self.total_tokens,
            "evidence_count": self.evidence_count,
            "entities_touched": list(dict.fromkeys(self.entities_touched)),
        }

    def to_prompt_block(self) -> str:
        lines: list[str] = []
        index = 1
        for band in BANDS:
            for item in self.bands.get(band, []):
                source = item.source_url or "unattributed"
                relation = f" relation={item.relation}" if item.relation else ""
                hop = f" hop={item.hop}" if item.hop else ""
                lines.append(
                    f"[{index}] band={band} source={source}{relation}{hop} {item.text}"
                )
                index += 1
        return "\n".join(lines)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    return [str(item) for item in values if item not in (None, "")]


def _prov_from_item(item: Any) -> dict[str, Any]:
    """Normalize provenance from a ContextItem or a plain retrieval dict."""
    if isinstance(item, dict):
        # Plain retrieval dict from finalization boundary
        prov = dict(item.get("provenance") or {})
        prov.setdefault("source_url", item.get("source_url") or item.get("source_url"))
        prov.setdefault("source", item.get("source_url") or item.get("source"))
        prov.setdefault("chunk_id", item.get("chunk_id") or item.get("id"))
        prov.setdefault("entity_ids", item.get("entity_ids", []))
        prov.setdefault("relation", item.get("graph_relation"))
        prov.setdefault("hop", item.get("graph_hop", 0))
        prov.setdefault("ontology_version", item.get("ontology_version"))
        prov.setdefault("rights_status", item.get("domain_rights_status") or item.get("rights_status"))
        prov.setdefault("entity_resolution_confidence", item.get("entity_resolution_confidence"))
        prov.setdefault("source_segment_id", (item.get("source_segment_ids") or [None])[0])
        return prov
    # ContextItem or any object with .provenance
    value = getattr(item, "provenance", None)
    return dict(value) if isinstance(value, dict) else {}


def _text_from(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("text") or "").strip()
    return str(getattr(item, "text", "") or "").strip()


def _score_from(item: Any) -> float:
    if isinstance(item, dict):
        return float(item.get("score") or 0.0)
    return float(getattr(item, "score", 0.0) or 0.0)


def _channel_from(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("channel") or "vector")
    return str(getattr(item, "channel", "vector") or "vector")


def _band_for(item: Any, provenance: dict[str, Any]) -> str:
    content_type = (
        item.get("content_type") if isinstance(item, dict) else None
    )
    if content_type in {"community_summary", "graph_summary", "lightrag_relationship_summary"}:
        return BAND_COMMUNITY
    if provenance.get("community_summary"):
        return BAND_COMMUNITY
    channel = _channel_from(item)
    if channel == "graph" or provenance.get("graph"):
        if provenance.get("graph") and provenance.get("source"):
            return BAND_CORROBORATED
        return BAND_GRAPH
    return BAND_DIRECT


def _confidence(score: float, provenance: dict[str, Any], band: str) -> float:
    explicit = provenance.get("entity_resolution_confidence") or provenance.get("confidence")
    if isinstance(explicit, (int, float)):
        return max(0.0, min(1.0, float(explicit)))
    base = max(0.0, min(1.0, float(score)))
    if band == BAND_CORROBORATED:
        return max(base, min(1.0, base + 0.15))
    if band == BAND_GRAPH:
        return max(base, 0.65)
    return base


def build_provenance_context(
    items: Iterable[Any],
    *,
    entities_touched: Optional[Iterable[str]] = None,
    max_tokens: int = 4000,
    max_items_per_band: int = 24,
) -> ProvenanceContext:
    """Build bounded four-band evidence from ContextItems or retrieval dicts."""
    bands: dict[str, list[ProvenanceEvidence]] = {band: [] for band in BANDS}
    used = 0
    sorted_items = sorted(
        list(items),
        key=lambda value: _score_from(value),
        reverse=True,
    )
    for item in sorted_items:
        text = _text_from(item)
        if not text:
            continue
        provenance = _prov_from_item(item)
        band = _band_for(item, provenance)
        if len(bands[band]) >= max_items_per_band:
            continue
        token_estimate = max(1, len(text) // 4)
        if used + token_estimate > max(1, int(max_tokens)):
            continue
        score = _score_from(item)
        entity_ids = _as_list(provenance.get("entity_ids"))
        entity_id = provenance.get("entity_id")
        if entity_id:
            entity_ids.extend(_as_list(entity_id))
        segment = (
            provenance.get("source_segment_id")
            or provenance.get("chunk_id")
            or provenance.get("id")
        )
        evidence = ProvenanceEvidence(
            text=text,
            band=band,
            score=score,
            source_url=(
                provenance.get("source_url")
                or provenance.get("source")
                or provenance.get("graph_source")
            ),
            source_segment_id=str(segment) if segment else None,
            entity_ids=list(dict.fromkeys(entity_ids)),
            relation=provenance.get("relation"),
            hop=int(provenance.get("hop") or 0),
            confidence=_confidence(score, provenance, band),
            ontology_version=provenance.get("ontology_version"),
            rights_status=provenance.get("rights_status") or provenance.get("domain_rights_status"),
            channel=_channel_from(item),
            corroborated=bool(provenance.get("graph")),
        )
        bands[band].append(evidence)
        used += token_estimate
    return ProvenanceContext(
        bands=bands,
        total_tokens=used,
        evidence_count=sum(len(values) for values in bands.values()),
        entities_touched=list(
            dict.fromkeys(str(value) for value in (entities_touched or []) if value)
        ),
    )


def attach_provenance_to_state(
    state: dict[str, Any],
    docs: Iterable[Any],
    *,
    entities_touched: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    """Return a state update; never mutates or persists private memory text."""
    context = build_provenance_context(
        docs,
        entities_touched=entities_touched or [],
        max_tokens=4000,
    )
    manifest = context.to_manifest()
    return {
        "provenance_context": manifest,
        "provenance_evidence_count": context.evidence_count,
        "provenance_entities_touched": context.entities_touched,
    }
