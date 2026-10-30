"""Corpus Governance & OKF Manifest Gating.

Implements explicit, versioned, fail-closed source governance across compiled OKF
and retrieval paths per SPEC-corpus-governance.md.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Valid explicit statuses
STATUS_CLEARED = "cleared"
STATUS_PENDING = "pending"
STATUS_QUARANTINED = "quarantined"
STATUS_REJECTED = "rejected"

VALID_STATUSES = frozenset(
    {
        STATUS_CLEARED,
        STATUS_PENDING,
        STATUS_QUARANTINED,
        STATUS_REJECTED,
    }
)

# Markers that can NEVER imply clearance by themselves
IMPLIED_CLEARANCE_MARKERS = frozenset(
    {
        "stable",
        "licensed",
        "true",
        "1",
        "yes",
        "rights_cleared",
        "domain_rights_status",
        "licensed_default",
        "unconfirmed",
        "cleared_payload",
    }
)


class CorpusGovernanceError(ValueError):
    """Raised when corpus governance validation or invariants fail."""

    pass


def assert_not_implied_clearance(label: str) -> None:
    """Verify that 'stable' or 'licensed' alone is NOT treated as clearance.

    Raises:
        CorpusGovernanceError: If label is an informal marker (e.g. 'stable', 'licensed',
            'true', 'rights_cleared') attempting to represent clearance.
    """
    normalised = str(label).strip().lower()
    if normalised in IMPLIED_CLEARANCE_MARKERS:
        raise CorpusGovernanceError(
            f"Marker {label!r} cannot imply clearance; explicit manifest clearance required."
        )


@dataclass(frozen=True)
class SourceAssetManifestRow:
    """A single governed source asset record in the manifest."""

    source_id: str
    corpus_version: str
    content_hash: str
    serving_tier: str = "general"
    status: str = STATUS_PENDING
    evidence_reference: str = ""
    reviewer_id: str = ""
    decision_date: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SourceAssetManifestRow:
        return cls(
            source_id=str(data.get("source_id", "")).strip(),
            corpus_version=str(data.get("corpus_version", "")).strip(),
            content_hash=str(data.get("content_hash", "")).strip(),
            serving_tier=str(data.get("serving_tier", "general")).strip(),
            status=str(data.get("status", STATUS_PENDING)).strip(),
            evidence_reference=str(data.get("evidence_reference", "")).strip(),
            reviewer_id=str(data.get("reviewer_id", "")).strip(),
            decision_date=str(data.get("decision_date", "")).strip(),
        )


class SourceAssetManifest:
    """Governed source asset manifest providing strict, fail-closed eligibility checks."""

    def __init__(
        self,
        rows: Optional[Sequence[SourceAssetManifestRow | Mapping[str, Any]]] = None,
        expected_digest: Optional[str] = None,
        stale: bool = False,
    ) -> None:
        self._raw_rows: list[SourceAssetManifestRow] = []
        self._rows: dict[tuple[str, str], SourceAssetManifestRow] = {}
        self._duplicate_keys: set[tuple[str, str]] = set()
        self._malformed_errors: list[str] = []
        self.is_stale: bool = bool(stale)
        self.expected_digest: Optional[str] = expected_digest

        if rows:
            for item in rows:
                if isinstance(item, SourceAssetManifestRow):
                    row = item
                elif isinstance(item, Mapping):
                    # Check for malformed record without minimum required keys
                    if not item.get("source_id") or not item.get("corpus_version"):
                        self._malformed_errors.append(
                            f"Row missing source_id or corpus_version: {item}"
                        )
                    row = SourceAssetManifestRow.from_dict(item)
                else:
                    self._malformed_errors.append(f"Invalid row type: {type(item)}")
                    continue

                if not row.source_id or not row.corpus_version:
                    self._malformed_errors.append(f"Row missing source_id or corpus_version: {row}")

                key = (row.source_id, row.corpus_version)
                if key in self._rows or key in self._duplicate_keys:
                    self._duplicate_keys.add(key)
                else:
                    self._rows[key] = row
                self._raw_rows.append(row)

        if self.expected_digest and self.expected_digest != self.manifest_digest:
            self.is_stale = True

    @property
    def manifest_digest(self) -> str:
        """Compute canonical SHA-256 digest of sorted manifest rows."""
        canonical_rows = [
            {
                "source_id": r.source_id,
                "corpus_version": r.corpus_version,
                "content_hash": r.content_hash,
                "serving_tier": r.serving_tier,
                "status": r.status,
                "evidence_reference": r.evidence_reference,
                "reviewer_id": r.reviewer_id,
                "decision_date": r.decision_date,
            }
            for r in sorted(
                self._raw_rows,
                key=lambda x: (x.source_id, x.corpus_version, x.serving_tier),
            )
        ]
        serialised = json.dumps(canonical_rows, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        return hashlib.sha256(serialised).hexdigest()

    @property
    def digest(self) -> str:
        return self.manifest_digest

    def __len__(self) -> int:
        return len(self._raw_rows)

    @property
    def rows(self) -> list[SourceAssetManifestRow]:
        return list(self._raw_rows)

    def get_row(self, source_id: str, corpus_version: str) -> Optional[SourceAssetManifestRow]:
        return self._rows.get((str(source_id).strip(), str(corpus_version).strip()))

    def validate(self) -> None:
        """Validate all rows and manifest invariants, raising CorpusGovernanceError on failure."""
        if self.is_stale:
            raise CorpusGovernanceError("Manifest is marked as stale or expired")
        if self._malformed_errors:
            raise CorpusGovernanceError(f"Malformed manifest: {'; '.join(self._malformed_errors)}")
        if self._duplicate_keys:
            duplicates = [f"{k[0]}@{k[1]}" for k in sorted(self._duplicate_keys)]
            raise CorpusGovernanceError(
                f"Duplicate manifest keys detected: {', '.join(duplicates)}"
            )
        if self.expected_digest and self.expected_digest != self.manifest_digest:
            raise CorpusGovernanceError(
                f"Manifest digest mismatch: expected {self.expected_digest}, computed {self.manifest_digest}"
            )
        for row in self._raw_rows:
            if not row.source_id or not row.corpus_version:
                raise CorpusGovernanceError(
                    f"Row missing required source_id or corpus_version: {row}"
                )
            if not row.content_hash:
                raise CorpusGovernanceError(f"Row missing content_hash: {row.source_id}")
            if not row.reviewer_id or not row.decision_date or not row.evidence_reference:
                raise CorpusGovernanceError(
                    f"Row {row.source_id} has incomplete provenance (reviewer_id, decision_date, or evidence_reference missing)"
                )
            if row.status not in VALID_STATUSES:
                raise CorpusGovernanceError(
                    f"Row {row.source_id} has invalid status {row.status!r}; expected one of {sorted(VALID_STATUSES)}"
                )

    def is_entry_eligible(
        self,
        source_id: str,
        corpus_version: str,
        content_hash: Optional[str] = None,
        tier: str = "general",
        require_content_hash: bool = True,
    ) -> tuple[bool, str]:
        """Check whether a source asset is eligible for serving in the specified tier.

        Returns:
            Tuple of (is_eligible, reason_code).
        """
        if self.is_stale:
            return False, "stale_manifest"
        if self._malformed_errors:
            return False, "malformed_manifest"

        key = (str(source_id).strip(), str(corpus_version).strip())
        if key in self._duplicate_keys:
            return False, "duplicate_manifest_key"
        if key not in self._rows:
            return False, "unmanifested_source"

        row = self._rows[key]

        if row.status != STATUS_CLEARED:
            return False, f"ineligible_status_{row.status}"

        # Fail closed on missing evidence: a caller that cannot present the content
        # hash cannot prove the bytes it serves are the bytes that were cleared.
        # ``require_content_hash=False`` is for callers that hold a *derived* artifact
        # (an OKF summary) and so cannot present the source asset's bytes; clearance
        # then rests on the asset's status and tier only. A hash that IS supplied is
        # always compared.
        have_hash = content_hash is not None and bool(str(content_hash).strip())
        if not have_hash and require_content_hash:
            return False, "content_hash_missing"
        if have_hash and str(content_hash).strip() != row.content_hash.strip():
            return False, "content_hash_mismatch"

        # No wildcard tier: serving must name the tier the row was cleared for.
        if row.serving_tier != tier:
            return False, f"tier_mismatch_{row.serving_tier}"

        if (
            not row.reviewer_id.strip()
            or not row.decision_date.strip()
            or not row.evidence_reference.strip()
        ):
            return False, "incomplete_provenance"

        return True, "cleared"

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any] | Sequence[Any],
        expected_digest: Optional[str] = None,
        stale: bool = False,
    ) -> SourceAssetManifest:
        if isinstance(data, Sequence):
            raw_rows = list(data)
            exp_digest = expected_digest
        elif isinstance(data, Mapping):
            raw_rows = list(data.get("rows") or data.get("entries") or [])
            exp_digest = expected_digest or data.get("manifest_digest") or data.get("digest")
        else:
            raise CorpusGovernanceError(f"Unsupported manifest data format: {type(data)}")

        return cls(rows=raw_rows, expected_digest=exp_digest, stale=stale)

    @classmethod
    def from_json(
        cls,
        json_str: str,
        expected_digest: Optional[str] = None,
        stale: bool = False,
    ) -> SourceAssetManifest:
        try:
            parsed = json.loads(json_str)
        except Exception as exc:
            raise CorpusGovernanceError(f"Malformed manifest JSON: {exc}") from exc
        return cls.from_dict(parsed, expected_digest=expected_digest, stale=stale)

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        expected_digest: Optional[str] = None,
        stale: bool = False,
    ) -> SourceAssetManifest:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Source asset manifest not found: {p}")
        text = p.read_text(encoding="utf-8")
        return cls.from_json(text, expected_digest=expected_digest, stale=stale)

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_version": "v1",
            "manifest_digest": self.manifest_digest,
            "rows": [r.to_dict() for r in self._raw_rows],
        }

    def to_file(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, sort_keys=True)
