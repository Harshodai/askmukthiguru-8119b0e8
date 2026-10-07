"""Production release gates for the first-person verbatim route.

This module intentionally contains only deterministic, side-effect-free policy
checks. It does not query Qdrant or mutate a collection; those operations belong
to the release controller. The application uses it at startup so an unsafe
first-person configuration cannot silently serve public traffic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FirstPersonReleaseError(ValueError):
    """Raised when a production first-person release is unsafe."""


_REQUIRED_PROFILE_KEYS = {
    "threshold",
    "score_kind",
    "n",
    "ucb_risk",
    "target_risk",
    "collection",
    "fitted_at",
}


def _profile_errors(path: str, collection: str) -> list[str]:
    errors: list[str] = []
    profile_path = Path(path)
    if not profile_path.is_file():
        return [f"calibration profile does not exist: {profile_path}"]
    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"calibration profile is unreadable: {exc}"]
    if not isinstance(data, dict):
        return ["calibration profile must be a JSON object"]

    # ponytail: accept demoted operational profile (claims="none", no conformal guarantees)
    if data.get("claims") == "none":
        threshold = data.get("threshold")
        if (
            threshold is None
            or isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
        ):
            errors.append("calibration profile threshold must be numeric")
        if data.get("score_kind") not in ("cosine", "dense_cosine"):
            errors.append("calibration profile score_kind must be cosine or dense_cosine")
        if data.get("collection") and data.get("collection") != collection:
            errors.append(
                "calibration profile collection does not match "
                f"configured collection {collection!r}"
            )
        return errors

    missing = sorted(_REQUIRED_PROFILE_KEYS - data.keys())
    if missing:
        errors.append(f"calibration profile missing keys: {', '.join(missing)}")
    if data.get("score_kind") != "dense_cosine":
        errors.append("calibration profile score_kind must be dense_cosine")
    if data.get("collection") != collection:
        errors.append(
            f"calibration profile collection does not match configured collection {collection!r}"
        )
    for key in ("threshold", "ucb_risk", "target_risk"):
        if key in data and (isinstance(data[key], bool) or not isinstance(data[key], (int, float))):
            errors.append(f"calibration profile {key} must be numeric")
    if isinstance(data.get("target_risk"), (int, float)) and data["target_risk"] > 0.01:
        errors.append("calibration profile target_risk exceeds 0.01")
    if (
        isinstance(data.get("ucb_risk"), (int, float))
        and isinstance(data.get("target_risk"), (int, float))
        and data["ucb_risk"] > data["target_risk"]
    ):
        errors.append("calibration profile ucb_risk exceeds target_risk")
    return errors


def validate_first_person_production_contract(
    config: Any,
    release_manifest: Any,
) -> None:
    """Fail closed when the public first-person route lacks release controls.

    Development/test configurations and a disabled route are intentionally
    allowed to omit a profile. Once the route is enabled in production, every
    listed invariant is mandatory.
    """
    if not getattr(config, "is_production", False):
        return
    if not getattr(config, "first_person_route_enabled", False):
        return

    errors: list[str] = []
    mode = str(getattr(config, "first_person_mode", "")).strip().lower()
    collection = str(getattr(config, "first_person_collection", "")).strip()
    if mode != "retrieval_only":
        errors.append(f"production first-person route must use retrieval_only mode; got {mode!r}")
    if not collection:
        errors.append("first_person_collection must be non-empty")
    if getattr(config, "first_person_serve_unregistered", False):
        errors.append("first_person_serve_unregistered must be false in production")

    # ponytail: (§C audit fix) Production gate requires honest abstention via
    # first_person_answerability_check_enabled, not an unproven calibration profile.
    # Calibration claims demoted to claims: none.
    if not getattr(config, "first_person_answerability_check_enabled", False):
        errors.append("first_person_answerability_check_enabled must be true in production")

    calibration_path = str(getattr(config, "first_person_calibration_path", "") or "").strip()
    if calibration_path and collection:
        errors.extend(_profile_errors(calibration_path, collection))

    release_id = str(getattr(release_manifest, "release_id", "")).strip()
    git_sha = str(getattr(release_manifest, "git_sha", "")).strip()
    if not release_id or release_id.startswith("rel-unknown"):
        errors.append("release manifest must contain a concrete release_id")
    if not git_sha or git_sha in {"unknown", "unknown-sha", "dev"}:
        errors.append("release manifest must contain a concrete git_sha")

    if errors:
        raise FirstPersonReleaseError(
            "Unsafe first-person production release:\n- " + "\n- ".join(errors)
        )
