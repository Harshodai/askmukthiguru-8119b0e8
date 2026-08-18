"""EU AI Act Compliance & Provenance Framework Schemas.

Implements W3C PROV-O semantic ontology, Dublin Core metadata, and EU AI Act
Article 50 (Transparency Obligations for AI Systems) data models.
"""

from __future__ import annotations

import datetime as _dt
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field, field_validator, model_validator


class OriginType(str, Enum):
    """Classification of content origin."""
    HUMAN_GENERATED = "human_generated"
    AI_ASSISTED = "ai_assisted"
    AI_GENERATED = "ai_generated"
    AI_SYNTHESIZED = "ai_synthesized"
    HYBRID = "hybrid"
    USER_AUTHORED = "user_authored"


class ArtifactModality(str, Enum):
    """Data modality of the generated or processed artifact."""
    TEXT_CHAT = "text_chat"
    SYNTHETIC_AUDIO = "synthetic_audio"
    USER_MEMORY = "user_memory"
    KNOWLEDGE_GRAPH_NODE = "knowledge_graph_node"
    VECTOR_EMBEDDING = "vector_embedding"
    DOCUMENT_EXPORT = "document_export"


class EUComplianceRiskTier(str, Enum):
    """Risk categorization under the EU AI Act (Regulation (EU) 2024/1689)."""
    MINIMAL_RISK = "minimal_risk"
    TRANSPARENCY_ART50 = "transparency_art50"
    SPECIFIC_CAUTION = "specific_caution"


class ComplianceStandard(str, Enum):
    """Applicable compliance and provenance standards."""
    EU_AI_ACT_ARTICLE_50 = "eu_ai_act_article_50"
    W3C_PROV = "w3c_prov"
    C2PA = "c2pa"


class WatermarkType(str, Enum):
    """Techniques used for content verification and watermarking."""
    ZERO_WIDTH_TEXT = "zero_width_text"
    AUDIO_TAG = "audio_tag"
    HTTP_HEADER = "http_header"
    METADATA_PAYLOAD = "metadata_payload"


class ContentCategory(str, Enum):
    """Taxonomy of spiritual and system content."""
    DISCOURSE = "discourse"
    TRANSCRIPT = "transcript"
    BOOK = "book"
    SUMMARY = "summary"
    MEDITATION = "meditation"
    TEACHING = "teaching"
    RESPONSE = "response"


class GroundingSourceReference(BaseModel):
    """Reference to a grounding source / knowledge chunk used in generation (prov:used)."""
    source_id: str = Field(..., description="Unique identifier for the knowledge source or chunk")
    source_type: str = Field(default="spiritual_wisdom", description="Corpus or collection identifier")
    title: Optional[str] = Field(default=None, description="Title of discourse, book, or transcript")
    url: Optional[str] = Field(default=None, description="Canonical source URL if available")
    snippet_hash: Optional[str] = Field(default=None, description="SHA-256 hash of the cited snippet")
    score: Optional[float] = Field(default=None, description="Relevance or retrieval score")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional provenance metadata")


class SoftwareAgentDescriptor(BaseModel):
    """Descriptor of the AI agent / model responsible for generation (prov:SoftwareAgent)."""
    agent_id: str = Field(default="askmukthiguru-core", description="Identifier for the software agent")
    name: str = Field(default="AskMukthiGuru AI Assistant", description="Human-readable agent name")
    version: Optional[str] = Field(default="1.0.0", description="System/software version")
    model_name: Optional[str] = Field(
        default=None,
        description="Model identifier (e.g., meta-llama/llama-3.1-8b-instruct, bulbul:v3)",
    )
    provider: Optional[str] = Field(
        default=None,
        description="Inference provider (e.g., sarvam, openrouter, nim, ollama)",
    )
    role: Optional[str] = Field(default="Spiritual AI Guide", description="Functional role of the agent")
    system_prompt_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 fingerprint of the system prompt for audit",
    )


class AIProvenanceManifest(BaseModel):
    """Standard AI Provenance Manifest matching W3C PROV-O, Schema.org,

    and EU AI Act Article 50 transparency requirements.
    """
    artifact_id: str = Field(
        default_factory=lambda: f"urn:uuid:{uuid.uuid4()}",
        description="Globally unique identifier for the generated artifact",
    )
    manifest_id: Optional[str] = Field(
        default=None,
        description="Unique identifier for the provenance manifest",
    )
    content_id: Optional[str] = Field(
        default=None,
        description="Target content / message / chunk identifier",
    )
    parent_artifact_id: Optional[str] = Field(
        default=None,
        description="Parent artifact ID if derived from another artifact (e.g., TTS from text)",
    )
    modality: ArtifactModality = Field(
        default=ArtifactModality.TEXT_CHAT,
        description="Modality of the generated artifact",
    )
    origin_type: OriginType = Field(
        default=OriginType.AI_GENERATED,
        description="Origin classification (human_generated, ai_assisted, ai_generated, ai_synthesized)",
    )
    risk_tier: EUComplianceRiskTier = Field(
        default=EUComplianceRiskTier.TRANSPARENCY_ART50,
        description="EU AI Act risk tier classification",
    )
    compliance_standard: ComplianceStandard = Field(
        default=ComplianceStandard.EU_AI_ACT_ARTICLE_50,
        description="Primary regulatory compliance standard referenced",
    )
    schema_version: str = Field(
        default="1.0",
        description="Provenance schema version",
    )
    generated_at: _dt.datetime = Field(
        default_factory=lambda: _dt.datetime.now(_dt.timezone.utc),
        description="UTC timestamp of artifact generation",
    )
    agent: SoftwareAgentDescriptor = Field(
        default_factory=SoftwareAgentDescriptor,
        description="Software agent and model metadata",
    )
    model_name: Optional[str] = Field(
        default=None,
        description="Convenience accessor for model name",
    )
    model_provider: Optional[str] = Field(
        default=None,
        description="Convenience accessor for model provider",
    )
    sources: List[GroundingSourceReference] = Field(
        default_factory=list,
        description="Grounding sources used to produce this artifact (prov:used)",
    )
    source_urls: List[str] = Field(
        default_factory=list,
        description="Grounding source URLs",
    )
    confidence_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence / verification score [0.0, 1.0]",
    )
    content_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 hash of the artifact content",
    )
    watermark_signature: Optional[str] = Field(
        default=None,
        description="Cryptographic or zero-width watermark signature if applied",
    )
    disclosure_statement: str = Field(
        default="This content was generated by AskMukthiGuru AI assistant in compliance with EU AI Act Article 50 transparency obligations.",
        description="Article 50 transparency disclosure statement",
    )
    disclaimer: Optional[str] = Field(
        default=None,
        description="Human-readable transparency disclosure / disclaimer",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Request/session identifier",
    )
    user_id_hash: Optional[str] = Field(
        default=None,
        description="GDPR-safe salted hash of the user ID",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary additional provenance metadata",
    )

    @field_validator("content_id")
    @classmethod
    def _validate_content_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not isinstance(v, str) or not v.strip():
                raise ValueError("content_id must be a non-empty string")
            return v.strip()
        return v

    @field_validator("confidence_score")
    @classmethod
    def _validate_confidence_score(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            if isinstance(v, bool):
                raise ValueError("confidence_score cannot be a boolean")
            if not (0.0 <= float(v) <= 1.0):
                raise ValueError(f"confidence_score must be between 0.0 and 1.0, got {v}")
        return v

    @field_validator("origin_type", mode="before")
    @classmethod
    def _normalize_origin_type(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_lower = v.strip().lower()
            for member in OriginType:
                if member.value == v_lower or member.name.lower() == v_lower:
                    return member
        return v

    @field_validator("modality", mode="before")
    @classmethod
    def _normalize_modality(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_lower = v.strip().lower()
            for member in ArtifactModality:
                if member.value == v_lower or member.name.lower() == v_lower:
                    return member
        return v

    @field_validator("risk_tier", mode="before")
    @classmethod
    def _normalize_risk_tier(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_lower = v.strip().lower()
            for member in EUComplianceRiskTier:
                if member.value == v_lower or member.name.lower() == v_lower:
                    return member
        return v

    @model_validator(mode="after")
    def _sync_fields(self) -> AIProvenanceManifest:
        if not self.manifest_id:
            self.manifest_id = f"prov-{uuid.uuid4().hex[:12]}"

        if not self.content_id:
            self.content_id = self.artifact_id

        # Sync model_name / provider
        if self.model_name and not self.agent.model_name:
            self.agent.model_name = self.model_name
        elif self.agent.model_name and not self.model_name:
            self.model_name = self.agent.model_name

        if self.model_provider and not self.agent.provider:
            self.agent.provider = self.model_provider
        elif self.agent.provider and not self.model_provider:
            self.model_provider = self.agent.provider

        # Sync source_urls / sources
        if self.source_urls and not self.sources:
            self.sources = [
                GroundingSourceReference(source_id=u, url=u) for u in self.source_urls
            ]
        elif self.sources and not self.source_urls:
            self.source_urls = [s.url or s.source_id for s in self.sources if s.url or s.source_id]

        # Sync disclaimer / disclosure
        if not self.disclaimer:
            if self.origin_type in (OriginType.AI_GENERATED, OriginType.AI_SYNTHESIZED, OriginType.AI_ASSISTED):
                self.disclaimer = (
                    "This content was generated with AI assistance in accordance with "
                    "EU AI Act Article 50 transparency requirements."
                )
            else:
                self.disclaimer = "Authentic primary source spiritual wisdom teachings."

        return self

    def to_json_ld(self) -> Dict[str, Any]:
        """Serialize manifest into combined W3C PROV-O, Schema.org, and EU AI Act JSON-LD format."""
        iso_time = (
            self.generated_at.isoformat()
            if isinstance(self.generated_at, _dt.datetime)
            else str(self.generated_at)
        )
        is_ai = self.origin_type in (
            OriginType.AI_GENERATED,
            OriginType.AI_SYNTHESIZED,
            OriginType.AI_ASSISTED,
        )

        agent_urn = f"urn:agent:{self.agent.agent_id}"
        activity_urn = f"urn:activity:{self.artifact_id.replace('urn:uuid:', '')}"

        prov_used: List[Dict[str, Any]] = []
        for src in self.sources:
            item: Dict[str, Any] = {
                "@id": src.url or f"urn:source:{src.source_id}",
                "@type": "prov:Entity",
                "source_type": src.source_type,
            }
            if src.title:
                item["dc:title"] = src.title
            if src.score is not None:
                item["schema:score"] = src.score
            if src.snippet_hash:
                item["snippet_hash"] = src.snippet_hash
            prov_used.append(item)

        producer_name = (
            self.model_name
            or self.agent.name
            or ("AskMukthiGuru AI" if is_ai else "Sri Preethaji & Sri Krishnaji")
        )
        producer_provider = (
            self.model_provider
            or self.agent.provider
            or ("AskMukthiGuru" if is_ai else "Ekam / O&O Academy")
        )
        standard_str = (
            self.compliance_standard.value
            if hasattr(self.compliance_standard, "value")
            else str(self.compliance_standard)
        )

        doc: Dict[str, Any] = {
            "@context": {
                "prov": "http://www.w3.org/ns/prov#",
                "dc": "http://purl.org/dc/terms/",
                "schema": "https://schema.org/",
                "euaiact": "https://eur-lex.europa.eu/eli/reg/2024/1689/oj#",
                "xsd": "http://www.w3.org/2001/XMLSchema#",
            },
            "@id": self.artifact_id,
            "@type": ["prov:Entity", "schema:CreativeWork", "DigitalDocument"],
            "identifier": self.content_id or self.artifact_id,
            "additionalType": "https://w3id.org/prov#Entity",
            "creativeWorkStatus": "AI-Generated" if is_ai else "Human-Authored",
            "originType": self.origin_type.value,
            "dc:format": self.modality.value,
            "dc:created": {
                "@type": "xsd:dateTime",
                "@value": iso_time,
            },
            "dc:rights": "AskMukthiGuru AI Provenance & EU AI Act Art. 50 Disclosure",
            "producer": {
                "@type": "SoftwareApplication" if is_ai else "Person",
                "name": producer_name,
                "provider": producer_provider,
            },
            "dateCreated": iso_time,
            "citation": self.source_urls,
            "version": self.schema_version,
            "euaiact:riskTier": self.risk_tier.value,
            "euaiact:originType": self.origin_type.value,
            "euaiact:disclosure": self.disclosure_statement,
            "compliance": {
                "standard": standard_str,
                "watermark": self.watermark_signature,
                "confidence": self.confidence_score,
                "disclaimer": self.disclaimer,
                "manifestId": self.manifest_id,
            },
            "prov:wasAttributedTo": {
                "@id": agent_urn,
                "@type": ["prov:Agent", "prov:SoftwareAgent"],
                "schema:name": self.agent.name,
                "schema:version": self.agent.version,
                "schema:role": self.agent.role,
                "schema:model": self.model_name or self.agent.model_name,
                "schema:provider": self.model_provider or self.agent.provider,
                "system_prompt_hash": self.agent.system_prompt_hash,
            },
            "prov:wasGeneratedBy": {
                "@id": activity_urn,
                "@type": "prov:Activity",
                "prov:startedAtTime": {
                    "@type": "xsd:dateTime",
                    "@value": iso_time,
                },
                "prov:wasAssociatedWith": agent_urn,
                "prov:used": prov_used,
            },
        }

        if self.parent_artifact_id:
            doc["prov:wasDerivedFrom"] = self.parent_artifact_id
        elif prov_used:
            doc["prov:wasDerivedFrom"] = [u["@id"] for u in prov_used]

        meta: Dict[str, Any] = {}
        if self.content_hash:
            meta["content_hash"] = self.content_hash
        if self.watermark_signature:
            meta["watermark_signature"] = self.watermark_signature
        if self.session_id:
            meta["session_id"] = self.session_id
        if self.user_id_hash:
            meta["user_id_hash"] = self.user_id_hash
        if self.metadata:
            meta.update(self.metadata)
        if meta:
            doc["schema:metadata"] = meta

        return doc
