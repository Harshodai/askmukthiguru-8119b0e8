"""Validator for Keyword Research payloads and Excel deliverables."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path

from services.keyword_research.models import KeywordResearchPayload

_HEX_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class KeywordValidationError(ValueError):
    """Raised when keyword research deliverable violates the locked-in contract."""

    pass


def validate_keyword_research_payload(
    payload: KeywordResearchPayload,
    *,
    require_external_certification: bool = False,
) -> list[str]:
    """Validate that payload strictly meets all cardinalities, schema invariants, and provenance rules.

    - Uncertified baseline payloads must declare production_certified=False and is_simulated=True.
    - Production-certified payloads (either requested via require_external_certification=True or
      declared via payload.production_certified=True or provenance.production_certified=True)
      must provide tamper-evident cryptographic provenance with valid SHA-256 request/response hashes,
      ISO-8601 timestamp, non-empty provider, valid source URL, matching keyword count, and
      is_simulated=False.
    - Contradictory payloads (e.g. production_certified=True with is_simulated=True or missing hashes)
      are strictly rejected.
    """
    errors: list[str] = []

    # 1. Exactly 300 keywords
    if len(payload.keywords) != 300:
        errors.append(f"Expected exactly 300 keywords, found {len(payload.keywords)}.")

    # 2. Exactly 5 topic clusters
    clusters = {k.topic_cluster for k in payload.keywords}
    if len(clusters) != 5:
        errors.append(
            f"Expected exactly 5 topic clusters, found {len(clusters)}: {sorted(clusters)}."
        )

    # 3. Top 20 competitors
    if len(payload.competitors) != 20:
        errors.append(f"Expected exactly 20 competitors, found {len(payload.competitors)}.")

    # 4. Exactly 20 keyword gaps
    if len(payload.gaps) != 20:
        errors.append(f"Expected exactly 20 keyword gaps, found {len(payload.gaps)}.")

    # 5. Exactly 5 findings and 5 recommendations
    if len(payload.findings) != 5:
        errors.append(f"Expected exactly 5 findings, found {len(payload.findings)}.")
    if len(payload.recommendations) != 5:
        errors.append(f"Expected exactly 5 recommendations, found {len(payload.recommendations)}.")

    # 6. Scoped volume label
    if not payload.volume_scope_label:
        errors.append("volume_scope_label cannot be empty.")

    # 7. Metric range validation
    for kw in payload.keywords:
        if kw.monthly_volume < 0:
            errors.append(
                f"Keyword '{kw.keyword}' has negative monthly volume: {kw.monthly_volume}."
            )
        if kw.global_volume < 0:
            errors.append(f"Keyword '{kw.keyword}' has negative global volume: {kw.global_volume}.")
        if not (0 <= kw.kd <= 100):
            errors.append(f"Keyword '{kw.keyword}' has KD out of [0, 100] range: {kw.kd}.")
        if kw.cpc < 0.0:
            errors.append(f"Keyword '{kw.keyword}' has negative CPC: {kw.cpc}.")

    # 8. Provenance and Production Certification Validation
    prov = payload.provenance if isinstance(payload.provenance, dict) else {}
    prov_certified = bool(prov.get("production_certified", False))
    payload_certified = bool(getattr(payload, "production_certified", False))
    claims_certification = payload_certified or prov_certified

    prov_simulated = bool(prov.get("is_simulated", False))
    payload_simulated = bool(getattr(payload, "is_simulated", False))
    is_simulated = payload_simulated or prov_simulated

    if require_external_certification and not claims_certification:
        errors.append(
            "Payload failed external certification check: require_external_certification is True but payload is uncertified."
        )

    if claims_certification:
        # Check contradictory certification claim
        if is_simulated:
            errors.append(
                "Contradictory certification marker: payload cannot claim production_certified=True while is_simulated=True."
            )

        if not payload.provenance:
            errors.append("Externally certified payload missing required provenance object.")
        else:
            provider = prov.get("provider")
            if (
                not provider
                or not isinstance(provider, str)
                or provider.strip() in ("", "public_data_baseline", "simulated")
            ):
                errors.append(
                    f"Certified payload requires verified external provider name, got: {provider!r}."
                )

            source_url = prov.get("source_url")
            if (
                not source_url
                or not isinstance(source_url, str)
                or not (source_url.startswith("http://") or source_url.startswith("https://"))
            ):
                errors.append(
                    f"Certified payload requires valid external source_url (http/https), got: {source_url!r}."
                )

            retrieved_at = prov.get("retrieved_at")
            if not retrieved_at or not isinstance(retrieved_at, str):
                errors.append("Certified payload requires ISO-8601 retrieved_at timestamp.")
            else:
                try:
                    datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
                except ValueError:
                    errors.append(
                        f"Certified payload has malformed retrieved_at timestamp: {retrieved_at!r}."
                    )

            req_sha = prov.get("request_sha256")
            if (
                not req_sha
                or not isinstance(req_sha, str)
                or not _HEX_SHA256_PATTERN.match(req_sha.lower())
            ):
                errors.append(
                    f"Certified payload requires valid 64-character hex request_sha256 hash, got: {req_sha!r}."
                )

            resp_sha = prov.get("response_sha256")
            if (
                not resp_sha
                or not isinstance(resp_sha, str)
                or not _HEX_SHA256_PATTERN.match(resp_sha.lower())
            ):
                errors.append(
                    f"Certified payload requires valid 64-character hex response_sha256 hash, got: {resp_sha!r}."
                )

            req_kw_count = prov.get("requested_keyword_count")
            if req_kw_count != len(payload.keywords):
                errors.append(
                    f"Certified payload requested_keyword_count mismatch: provenance declared {req_kw_count}, payload contains {len(payload.keywords)}."
                )

    if errors:
        raise KeywordValidationError("Payload contract violation:\n  " + "\n  ".join(errors))

    return errors


def inspect_xlsx_sheet_names(xlsx_path: Path) -> list[str]:
    """Inspect sheet names of an .xlsx file using standard library zipfile/XML."""
    xlsx_path = Path(xlsx_path)
    if not xlsx_path.exists():
        raise FileNotFoundError(f"Workbook not found: {xlsx_path}")

    sheet_names = []
    with zipfile.ZipFile(xlsx_path, "r") as z:
        wb_xml = z.read("xl/workbook.xml")
        root = ET.fromstring(wb_xml)
        for elem in root.iter():
            if elem.tag.endswith("sheet") and "name" in elem.attrib:
                sheet_names.append(elem.attrib["name"])
    return sheet_names
