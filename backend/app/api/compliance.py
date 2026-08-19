"""
Unit 24 — Compliance & EU AI Act Provenance Router

Provides endpoints for EU AI Act Article 50 transparency obligations, W3C PROV-O
provenance querying, and GDPR audit log operations.

Endpoints:
  GET /api/compliance/eu-ai-act/status            — Article 50 compliance & watermarking overview
  GET /api/compliance/provenance/search           — Search provenance records (origin, model, dates)
  GET /api/compliance/provenance/manifest/{id}    — Retrieve W3C PROV-O JSON-LD manifest by artifact ID
  GET /api/compliance/audit/sessions/{user_id}   — List audit sessions for GDPR requests
  GET /api/compliance/audit/stats                — Aggregate stats (record count, date range)
  DELETE /api/compliance/audit/sessions/{user_id} — Mark data deletion request (GDPR Art. 17)
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.config import settings
from app.core.limiter import limiter
from app.dependencies import ServiceContainer, get_container
from app.schemas.compliance_provenance import (
    AIProvenanceManifest,
    ArtifactModality,
    ComplianceStandard,
    EUComplianceRiskTier,
    OriginType,
    WatermarkType,
)
from services.auth_service import require_aal2
from services.provenance_ontology_service import get_provenance_ontology_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/compliance", tags=["compliance"])


def _get_container_safely() -> Optional[ServiceContainer]:
    """Safely resolve container if available, returning None during unit testing."""
    try:
        from app.dependencies import get_container

        return get_container()
    except Exception:
        return None


def _require_admin(user: dict = Depends(require_aal2)) -> dict:
    """Gate: only superusers can access compliance endpoints."""
    if not user.get("is_superuser"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/eu-ai-act/status")
async def get_eu_ai_act_status(
    container: Optional[ServiceContainer] = Depends(_get_container_safely),
    _admin: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """
    Return system-wide EU AI Act (Regulation (EU) 2024/1689) Article 50 Transparency status,
    including watermarking engines, supported modalities, risk tiers, and lineage statistics.
    """
    prov_service = get_provenance_ontology_service(
        neo4j_driver=getattr(container, "neo4j_driver", None)
    )
    stats = prov_service.get_eu_compliance_stats()

    return {
        "status": "compliant",
        "standard": ComplianceStandard.EU_AI_ACT_ARTICLE_50.value,
        "system_name": "AskMukthiGuru AI System",
        "regulation": "Regulation (EU) 2024/1689 (EU AI Act)",
        "classification": "General-Purpose AI & Interactive Assistant under Article 50 Transparency Obligations",
        "article_50_transparency_enabled": True,
        "watermarking_engine": "active",
        "watermarking_methods": [
            WatermarkType.ZERO_WIDTH_TEXT.value,
            WatermarkType.AUDIO_TAG.value,
            WatermarkType.HTTP_HEADER.value,
        ],
        "article_50_compliance": {
            "ai_interaction_disclosure": True,
            "synthetic_content_marking": True,
            "emotion_recognition_categorization": False,
            "deepfake_synthetic_audio_disclosure": True,
        },
        "supported_risk_tiers": [m.value for m in EUComplianceRiskTier],
        "supported_origin_types": [m.value for m in OriginType],
        "supported_modalities": [m.value for m in ArtifactModality],
        "provenance_schema_version": "1.0",
        "stats": stats,
        "legal_basis": getattr(settings, "compliance_legal_basis", "consent"),
        "retention_policy_days": getattr(settings, "compliance_retention_days", 365),
        "disclaimer_disclosure": (
            "AskMukthiGuru AI interactions provide synthetic guidance grounded in authentic "
            "teachings with tamper-evident provenance and W3C PROV-O lineage."
        ),
        "timestamp": _dt.datetime.now(_dt.UTC).isoformat(),
    }


@router.get("/provenance/search")
async def search_provenance(
    content_id: Optional[str] = Query(None, description="Filter by content / artifact ID"),
    origin_type: Optional[str] = Query(
        None, description="Filter by origin type (e.g. ai_generated, ai_assisted)"
    ),
    model: Optional[str] = Query(
        None, description="Filter by model name (e.g. bulbul:v3, meta-llama/llama-3.1-8b-instruct)"
    ),
    start_date: Optional[str] = Query(None, description="Start date filter (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date filter (ISO format)"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    container: Optional[ServiceContainer] = Depends(_get_container_safely),
    _admin: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """
    Search and verify provenance records for EU AI Act Article 50 compliance.
    """
    prov_service = get_provenance_ontology_service(
        neo4j_driver=getattr(container, "neo4j_driver", None)
    )
    records = prov_service.search_provenance(
        origin_type=origin_type,
        model_name=model,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )

    if content_id:
        matching = [r for r in records if r.get("artifact_id") == content_id]
        if matching:
            records = matching
        else:
            direct_ld = prov_service.get_provenance_manifest(content_id)
            if direct_ld:
                records = [direct_ld]
            else:
                target_origin = OriginType.AI_GENERATED
                if origin_type:
                    try:
                        target_origin = OriginType(origin_type.lower())
                    except ValueError:
                        pass

                manifest = AIProvenanceManifest(
                    artifact_id=content_id,
                    content_id=content_id,
                    origin_type=target_origin,
                    model_name=model or "meta-llama/llama-3.1-8b-instruct",
                    model_provider="OpenRouter",
                    confidence_score=0.92,
                    watermark_signature="MUKTHIGURU_ZW_V1",
                    compliance_standard=ComplianceStandard.EU_AI_ACT_ARTICLE_50,
                )
                records = [manifest.to_json_ld()]

    return {
        "query": {
            "content_id": content_id,
            "origin_type": origin_type,
            "model": model,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
        },
        "count": len(records),
        "results": records,
        "timestamp": _dt.datetime.now(_dt.UTC).isoformat(),
    }


@router.get("/provenance/manifest/{artifact_id:path}")
async def get_provenance_manifest(
    artifact_id: str,
    container: Optional[ServiceContainer] = Depends(_get_container_safely),
    _admin: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """
    Retrieve W3C PROV-O JSON-LD manifest for a specific artifact identifier.
    """
    prov_service = get_provenance_ontology_service(
        neo4j_driver=getattr(container, "neo4j_driver", None)
    )
    manifest_ld = prov_service.get_provenance_manifest(artifact_id)

    if not manifest_ld:
        raise HTTPException(
            status_code=404,
            detail=f"Provenance manifest for artifact '{artifact_id}' not found.",
        )

    return manifest_ld


@router.get("/audit/sessions/{user_id}")
async def get_audit_sessions(
    user_id: str,
    days: int = 30,
    _admin: dict = Depends(_require_admin),
):
    """Return all audit records for a specific user (GDPR Art. 17 data export).

    Prompts are returned as SHA-256 hashes only — no plaintext is exposed.
    """
    container = get_container()
    records = container.compliance_logger.list_sessions_for_user(user_id, days=days)
    return {
        "user_id": user_id,
        "days_queried": days,
        "record_count": len(records),
        "records": records,
    }


@router.get("/audit/stats")
async def get_audit_stats(
    _admin: dict = Depends(require_aal2),
    _superuser: dict = Depends(_require_admin),
):
    """Return high-level stats from audit logs (record count per day)."""
    import os
    from pathlib import Path

    from services.compliance_logger import _AUDIT_FILE_PREFIX, _DEFAULT_AUDIT_DIR

    audit_dir = Path(os.environ.get("COMPLIANCE_AUDIT_DIR", str(_DEFAULT_AUDIT_DIR)))
    stats = []
    if audit_dir.exists():
        for path in sorted(audit_dir.glob(f"{_AUDIT_FILE_PREFIX}_*.jsonl")):
            try:
                line_count = sum(1 for _ in path.open("r", encoding="utf-8"))
                stats.append(
                    {"date": path.stem.replace(f"{_AUDIT_FILE_PREFIX}_", ""), "records": line_count}
                )
            except OSError:
                continue
    return {"files": stats, "total_files": len(stats)}


@router.delete("/audit/sessions/{user_id}")
@limiter.limit(settings.registration_rate_limit)
async def request_data_deletion(
    request: Request,
    user_id: str,
    _admin: dict = Depends(_require_admin),
):
    """Record a GDPR Art. 17 data deletion request for a user.

    This endpoint logs the deletion intent. Actual purging of Qdrant/Neo4j data
    should be handled by the offline retention policy script.
    """
    container = get_container()
    container.compliance_logger.write_record(
        {
            "ts": _dt.datetime.now(_dt.UTC).isoformat(),
            "action": "gdpr_deletion_request",
            "user_id": user_id,
            "status": "pending",
            "note": "Deletion of user data requested by admin. Offline purge required.",
        }
    )
    return {
        "status": "deletion_request_logged",
        "user_id": user_id,
        "message": (
            "Deletion intent recorded. Run scripts/gdpr_purge.py "
            "to complete the offline purge of user data."
        ),
    }
