"""Serving-contract separation between the legacy clip store and the fp-context store.

Public-release blocker **B4** (``docs/FIRST_PERSON_PUBLIC_RELEASE_STATUS_2026-10-21.md``):
``FIRST_PERSON_COLLECTION`` and ``FIRST_PERSON_CONTEXT_COLLECTION`` could point
at the same collection, and the legacy clip store filters on
``first_person_eligible`` — a field the fp-context-v1 schema does not carry.
The result was a route that silently served nothing (or, once the harness is
wired, one that reads context records through a legacy path).

This module makes the separation explicit and checkable:

* a **contract file** declares, per collection, its payload schema, its corpus
  version, the payload fields the path requires, and the evidence policy the
  collection is allowed to assert;
* :func:`validate_serving_contract` turns that declaration into a report of
  errors and warnings;
* :func:`assert_startup_safe` decides whether those errors must stop the
  process. In production they always do. Outside production they stop the
  process only when the affected path is actually enabled — otherwise the
  module logs them and the affected route refuses to serve instead of reading
  the wrong schema.

The module is deliberately offline and deterministic: it never contacts
Qdrant, never mutates an alias and never mutates a collection. The optional
live probe (:func:`probe_collection_payload_fields`) is used by the ops
verification script, not by the request path.

Cache fingerprinting
--------------------
The exact-answer cache key must change when *what may be served* changes.
:data:`REQUIRED_FINGERPRINT_COMPONENTS` names the four inputs that must ride
in the serving-policy fingerprint: the collection, its payload schema, its
corpus version and its evidence policy. :func:`fingerprint_components` returns
them so the pipeline and the tests cannot drift apart.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

LEGACY_SCHEMA = "first-person-legacy-clip-v1"
CONTEXT_SCHEMA = "fp-context-v1"

ROLE_LEGACY = "legacy"
ROLE_CONTEXT = "context"

# Fields every legacy clip-store record must carry for the legacy path to be
# schema-compatible at all.
LEGACY_REQUIRED_PAYLOAD_FIELDS: tuple[str, ...] = (
    "first_person_eligible",
    "teacher_id",
    "verbatim_text",
    "video_id",
)

# Fields every fp-context record must carry for the context path to be
# schema-compatible at all.
CONTEXT_REQUIRED_PAYLOAD_FIELDS: tuple[str, ...] = (
    "record_type",
    "source_span_id",
    "parent_unit_id",
    "guru_id",
    "verbatim_text",
    "source_text_hash",
    "transcript_hash",
    "speaker_verified",
    "rights_cleared",
    "corpus_version",
)

# The four serving-policy inputs that must ride in the cache fingerprint.
REQUIRED_FINGERPRINT_COMPONENTS: tuple[str, ...] = (
    "collection",
    "schema",
    "corpus_version",
    "evidence_policy",
)

CONTRACT_SCHEMA = "fp-serving-contract-v1"

DEFAULT_CONTRACT_PATH = "config/first_person_serving_contract.json"


class FirstPersonServingContractError(RuntimeError):
    """Raised when a first-person serving configuration is unsafe."""


@dataclass(frozen=True)
class CollectionContract:
    """The declared contract of one collection."""

    name: str
    schema: str
    role: str
    corpus_version: str
    required_payload_fields: tuple[str, ...]
    evidence_policy: str
    source: str = ""

    @property
    def is_legacy(self) -> bool:
        return self.role == ROLE_LEGACY

    @property
    def is_context(self) -> bool:
        return self.role == ROLE_CONTEXT


@dataclass(frozen=True)
class ContractReport:
    """Outcome of validating a serving configuration against the contract."""

    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    legacy_collection: str = ""
    context_collection: str = ""
    legacy_ok: bool = True
    context_ok: bool = True
    fingerprint_components: Mapping[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def raise_if_unsafe(self) -> None:
        if self.errors:
            raise FirstPersonServingContractError(
                "Unsafe first-person serving contract:\n- " + "\n- ".join(self.errors)
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "legacy_collection": self.legacy_collection,
            "context_collection": self.context_collection,
            "legacy_ok": self.legacy_ok,
            "context_ok": self.context_ok,
            "fingerprint_components": dict(self.fingerprint_components),
        }


# ---------------------------------------------------------------------------
# contract loading
# ---------------------------------------------------------------------------
def default_contract_path() -> Path:
    """Resolve the contract file.

    The default sits next to the backend package (``backend/config/…``) so the
    same relative path works on the host and inside the image
    (``COPY backend/ .`` -> ``/app``). An override is passed in by the caller
    (the route and the pipeline read it from ``settings``) — this module never
    reads the environment directly, because every env value must reach the app
    through ``Settings`` (see ``tests/test_settings_guards.py``).
    """
    return Path(__file__).resolve().parents[1] / "config" / "first_person_serving_contract.json"


@lru_cache(maxsize=4)
def load_contract_cached(path: str | None = None) -> dict[str, CollectionContract]:
    """Cached contract loader. Raises on an unreadable/invalid contract."""
    return load_contract(Path(path) if path else default_contract_path())


# ---------------------------------------------------------------------------
# rights register artifact
# ---------------------------------------------------------------------------
# The corpus rights register is a dated, reviewed artifact: rebuilds must pin the
# same file, so its location is one constant rather than a literal repeated in
# the serving pipeline and the corpus builder (a drifted literal would silently
# pin a different file).
RIGHTS_MANIFEST_RELPATH = "audits/evidence/public_release_phase4_rights_manifest_2026-10-22.json"


def rights_manifest_path() -> Path:
    """Absolute path to the pinned rights register (``RIGHTS_MANIFEST_RELPATH``)."""
    return Path(__file__).resolve().parents[2] / RIGHTS_MANIFEST_RELPATH


def load_contract(path: str | Path) -> dict[str, CollectionContract]:
    """Load and validate the contract file. Fails closed."""
    contract_path = Path(path)
    try:
        raw = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FirstPersonServingContractError(
            f"first-person serving contract is unreadable: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise FirstPersonServingContractError("first-person serving contract must be a JSON object")
    if raw.get("schema") != CONTRACT_SCHEMA:
        raise FirstPersonServingContractError(
            f"first-person serving contract schema must be {CONTRACT_SCHEMA!r}; "
            f"got {raw.get('schema')!r}"
        )
    collections = raw.get("collections")
    if not isinstance(collections, dict) or not collections:
        raise FirstPersonServingContractError(
            "first-person serving contract declares no collections"
        )

    out: dict[str, CollectionContract] = {}
    for name, entry in collections.items():
        if not isinstance(entry, dict):
            raise FirstPersonServingContractError(f"contract entry for {name!r} must be an object")
        schema = str(entry.get("schema") or "")
        role = str(entry.get("role") or "")
        if schema not in (LEGACY_SCHEMA, CONTEXT_SCHEMA):
            raise FirstPersonServingContractError(
                f"contract entry for {name!r} has an unknown schema {schema!r}"
            )
        if role not in (ROLE_LEGACY, ROLE_CONTEXT):
            raise FirstPersonServingContractError(
                f"contract entry for {name!r} has an unknown role {role!r}"
            )
        expected_fields = (
            LEGACY_REQUIRED_PAYLOAD_FIELDS
            if role == ROLE_LEGACY
            else CONTEXT_REQUIRED_PAYLOAD_FIELDS
        )
        fields = entry.get("required_payload_fields")
        if not isinstance(fields, list) or not fields:
            raise FirstPersonServingContractError(
                f"contract entry for {name!r} declares no required_payload_fields"
            )
        missing = [f for f in expected_fields if f not in fields]
        if missing:
            raise FirstPersonServingContractError(
                f"contract entry for {name!r} omits required payload fields: {missing}"
            )
        out[str(name)] = CollectionContract(
            name=str(name),
            schema=schema,
            role=role,
            corpus_version=str(entry.get("corpus_version") or ""),
            required_payload_fields=tuple(str(f) for f in fields),
            evidence_policy=str(entry.get("evidence_policy") or ""),
            source=str(contract_path),
        )
    return out


# ---------------------------------------------------------------------------
# v10-only mode
# ---------------------------------------------------------------------------
def legacy_slot_aliases_context(legacy_collection: object, context_collection: object) -> bool:
    """True when the legacy slot and the context slot name the same collection.

    Only a real ``str`` can alias: a test double or an unset value never does.
    """
    if not isinstance(legacy_collection, str) or not isinstance(context_collection, str):
        return False
    legacy_name = legacy_collection.strip()
    return bool(legacy_name) and legacy_name == context_collection.strip()


def v10_only_mode_active(
    *,
    legacy_collection: object,
    context_collection: object,
    context_harness_enabled: object,
    context_terminal_enabled: object,
) -> bool:
    """True for the owner's v10-only serving posture (2026-10-30).

    All three must hold: the legacy slot names the context collection, the
    context harness is on, and the terminal flag is on. The terminal flag is
    what makes the harness the only reader (``FirstPersonPipeline`` abstains
    instead of falling through to the legacy store). ``is True`` on the
    terminal flag matches the pipeline's own check, so a patched or mock
    settings object cannot switch the mode on.
    """
    return (
        legacy_slot_aliases_context(legacy_collection, context_collection)
        and bool(context_harness_enabled)
        and context_terminal_enabled is True
    )


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
def validate_serving_contract(
    *,
    contract: Mapping[str, CollectionContract],
    legacy_collection: str,
    context_collection: str = "",
    context_harness_enabled: bool = False,
    legacy_route_enabled: bool = True,
    context_terminal_enabled: bool = False,
) -> ContractReport:
    """Check a configuration against the declared contract. Never raises.

    ``context_terminal_enabled`` admits exactly one exception to the
    "two slots, two collections" rule: v10-only mode (see
    :func:`v10_only_mode_active`). There the legacy slot may name the context
    collection, because the legacy path is never reached. Every context-side
    check still runs, and without the harness AND the terminal flag the
    aliasing stays an error.
    """
    errors: list[str] = []
    warnings: list[str] = []

    legacy_name = str(legacy_collection or "").strip()
    context_name = str(context_collection or "").strip()
    v10_only = v10_only_mode_active(
        legacy_collection=legacy_name,
        context_collection=context_name,
        context_harness_enabled=context_harness_enabled,
        context_terminal_enabled=context_terminal_enabled,
    )

    if not legacy_name:
        errors.append("legacy first-person collection must be non-empty")
        legacy_entry: Optional[CollectionContract] = None
    elif v10_only:
        # The legacy slot is an alias of the context collection. Its entry is
        # validated below as the context entry; here we only need it for the
        # fingerprint, and we record that the legacy path is inert.
        legacy_entry = contract.get(legacy_name)
        warnings.append(
            f"v10-only mode: legacy first-person slot aliases context collection "
            f"{legacy_name!r}; the context harness is terminal and no legacy clip is served"
        )
    else:
        legacy_entry = contract.get(legacy_name)
        if legacy_entry is None:
            errors.append(
                f"legacy collection {legacy_name!r} is not declared in the serving contract"
            )
        else:
            if legacy_entry.schema == CONTEXT_SCHEMA:
                errors.append(
                    f"legacy first-person store points at {legacy_name!r}, which is an "
                    "fp-context collection; the legacy path filters on "
                    "first_person_eligible, a field the fp-context schema does not carry"
                )
            if legacy_entry.role != ROLE_LEGACY:
                errors.append(
                    f"legacy first-person store points at {legacy_name!r}, whose declared "
                    f"role is {legacy_entry.role!r} (expected {ROLE_LEGACY!r})"
                )
            if not legacy_entry.required_payload_fields:
                errors.append(
                    f"legacy collection {legacy_name!r} declares no required payload fields"
                )
            if not legacy_entry.corpus_version:
                errors.append(f"legacy collection {legacy_name!r} declares no corpus version")
            if not legacy_entry.evidence_policy:
                errors.append(f"legacy collection {legacy_name!r} declares no evidence policy")

    context_entry: Optional[CollectionContract] = None
    if context_name:
        context_entry = contract.get(context_name)
        if context_entry is None:
            errors.append(
                f"context collection {context_name!r} is not declared in the serving contract"
            )
        else:
            if context_entry.schema == LEGACY_SCHEMA:
                errors.append(
                    f"context first-person store points at {context_name!r}, which is a "
                    "legacy-only collection; the context path requires the fp-context "
                    "parent/child schema"
                )
            if context_entry.role != ROLE_CONTEXT:
                errors.append(
                    f"context first-person store points at {context_name!r}, whose declared "
                    f"role is {context_entry.role!r} (expected {ROLE_CONTEXT!r})"
                )
            if not context_entry.required_payload_fields:
                errors.append(
                    f"context collection {context_name!r} declares no required payload fields"
                )
            if not context_entry.corpus_version:
                errors.append(f"context collection {context_name!r} declares no corpus version")
            if not context_entry.evidence_policy:
                errors.append(f"context collection {context_name!r} declares no evidence policy")
    elif context_harness_enabled:
        errors.append(
            "the first-person context harness is enabled but no context collection is set"
        )

    if legacy_name and context_name and legacy_name == context_name and not v10_only:
        errors.append(
            f"the legacy and context first-person stores both point at {legacy_name!r}; "
            "one collection cannot satisfy two payload schemas"
        )

    if legacy_route_enabled and legacy_entry is None and legacy_name:
        warnings.append(
            f"legacy first-person route is enabled against undeclared collection "
            f"{legacy_name!r}; it will refuse to serve"
        )

    fingerprint = fingerprint_components(legacy_entry)
    missing_fingerprint = [
        key for key in REQUIRED_FINGERPRINT_COMPONENTS if not fingerprint.get(key)
    ]
    if legacy_entry is not None and missing_fingerprint:
        errors.append(
            f"the serving-policy fingerprint is missing required components: {missing_fingerprint}"
        )

    return ContractReport(
        errors=tuple(errors),
        warnings=tuple(warnings),
        legacy_collection=legacy_name,
        context_collection=context_name,
        legacy_ok=not errors,
        context_ok=not errors,
        fingerprint_components=fingerprint,
    )


def fingerprint_components(
    entry: Optional[CollectionContract], release_version: Optional[int | str] = None
) -> dict[str, str]:
    """The cache-fingerprint inputs for a collection contract."""
    rel_ver = str(
        release_version
        if release_version is not None
        else (getattr(entry, "release_version", "") or "")
    )
    if entry is None:
        return {
            "collection": "",
            "schema": "",
            "corpus_version": "",
            "evidence_policy": "",
            "release_version": rel_ver,
        }
    return {
        "collection": entry.name,
        "schema": entry.schema,
        "corpus_version": entry.corpus_version,
        "evidence_policy": entry.evidence_policy,
        "release_version": rel_ver,
    }


def assert_startup_safe(
    report: ContractReport,
    *,
    is_production: bool,
    legacy_route_enabled: bool,
    context_harness_enabled: bool,
) -> None:
    """Fail closed where an unsafe configuration could actually serve.

    * In production every error stops the process: a deployment that cannot
      state which schema it serves must not take traffic at all.
    * Outside production the **context harness** path stops the process when
      its contract is broken, because the harness would otherwise serve
      context records through a mismatched collection.
    * Outside production the **legacy** path does not stop the whole
      application. It fails closed at the path instead: the first-person
      pipeline refuses to serve and reports
      ``serving_contract_violation``. Taking the entire backend down for a
      first-person mis-configuration would be a larger blast radius than the
      defect, and the safe behaviour (serve nothing) is unchanged.

    The path-scoped behaviour is covered by tests, not by assumption.
    """
    if not report.errors:
        return
    if is_production:
        raise FirstPersonServingContractError(
            "Unsafe first-person serving configuration in production:\n- "
            + "\n- ".join(report.errors)
        )
    if context_harness_enabled and any(
        error.startswith("context") or "fp-context" in error for error in report.errors
    ):
        raise FirstPersonServingContractError(
            "Unsafe first-person context configuration:\n- " + "\n- ".join(report.errors)
        )
    # legacy_route_enabled is intentionally not a raise trigger outside
    # production: the legacy path fails closed on its own (see
    # legacy_store_preflight and FirstPersonPipeline._serving_contract_error).
    _ = legacy_route_enabled


def legacy_store_preflight(
    *,
    contract: Mapping[str, CollectionContract],
    legacy_collection: str,
    context_collection: str = "",
    context_harness_enabled: bool = False,
    context_terminal_enabled: bool = False,
) -> ContractReport:
    """Check the legacy store's own collection before it searches.

    The legacy route calls this per request (it is a dict lookup, not a network
    call). An incompatible collection means the route refuses to serve instead
    of reading context records through a legacy path.

    The three ``context_*`` arguments matter only for v10-only mode, where the
    legacy slot aliases the context collection. Callers pass them when (and only
    when) the two slots name the same collection; otherwise the check is the
    legacy-only check it always was.
    """
    return validate_serving_contract(
        contract=contract,
        legacy_collection=legacy_collection,
        context_collection=context_collection,
        context_harness_enabled=context_harness_enabled,
        legacy_route_enabled=True,
        context_terminal_enabled=context_terminal_enabled,
    )


# ---------------------------------------------------------------------------
# live probe (ops use only; never on the request path)
# ---------------------------------------------------------------------------
def probe_collection_payload_fields(
    client: Any,
    collection: str,
    required_fields: Iterable[str],
    *,
    sample_size: int = 32,
) -> dict[str, Any]:
    """Read a bounded sample of a collection and report which fields are absent.

    Read-only. Used by the ops verification script to prove that the declared
    required payload fields really exist in the live collection.
    """
    required = list(required_fields)
    records = client.scroll(
        collection_name=collection,
        limit=sample_size,
        with_payload=True,
        with_vectors=False,
    )
    payload_rows = records if isinstance(records, list) else records[0]
    seen_fields: set[str] = set()
    sampled = 0
    for record in payload_rows:
        payload = getattr(record, "payload", None) or {}
        sampled += 1
        seen_fields.update(str(key) for key in payload)
    missing = [name for name in required if name not in seen_fields]
    return {
        "collection": collection,
        "sampled_points": sampled,
        "required_fields": required,
        "missing_fields": missing,
        "compatible": not missing,
    }


__all__ = [
    "CONTEXT_REQUIRED_PAYLOAD_FIELDS",
    "CONTEXT_SCHEMA",
    "CollectionContract",
    "ContractReport",
    "DEFAULT_CONTRACT_PATH",
    "FirstPersonServingContractError",
    "LEGACY_REQUIRED_PAYLOAD_FIELDS",
    "LEGACY_SCHEMA",
    "REQUIRED_FINGERPRINT_COMPONENTS",
    "ROLE_CONTEXT",
    "ROLE_LEGACY",
    "assert_startup_safe",
    "fingerprint_components",
    "legacy_slot_aliases_context",
    "legacy_store_preflight",
    "load_contract",
    "probe_collection_payload_fields",
    "v10_only_mode_active",
    "validate_serving_contract",
]
