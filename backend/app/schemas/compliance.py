"""Backward-compatible compliance schemas module.

Re-exports unified schemas from app.schemas.compliance_provenance.
"""

from app.schemas.compliance_provenance import (
    AIProvenanceManifest,
    ArtifactModality,
    ComplianceStandard,
    ContentCategory,
    EUComplianceRiskTier,
    GroundingSourceReference,
    OriginType,
    SoftwareAgentDescriptor,
    WatermarkType,
)

__all__ = [
    "AIProvenanceManifest",
    "ArtifactModality",
    "ComplianceStandard",
    "ContentCategory",
    "EUComplianceRiskTier",
    "GroundingSourceReference",
    "OriginType",
    "SoftwareAgentDescriptor",
    "WatermarkType",
]
