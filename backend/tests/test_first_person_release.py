from types import SimpleNamespace

import pytest

from services.first_person_release import (
    FirstPersonReleaseError,
    validate_first_person_production_contract,
)

MANIFEST = SimpleNamespace(release_id="rel-abc12345-c7-p1", git_sha="abc12345")


def cfg(**overrides):
    values = {
        "is_production": True,
        "first_person_route_enabled": True,
        "first_person_mode": "retrieval_only",
        "first_person_collection": "first_person_live",
        "first_person_calibration_path": "",
        "first_person_serve_unregistered": False,
        "first_person_answerability_check_enabled": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def write_profile(tmp_path, collection="first_person_live"):
    import json

    path = tmp_path / "calibration.json"
    path.write_text(
        json.dumps(
            {
                "threshold": 0.8,
                "score_kind": "dense_cosine",
                "n": 299,
                "ucb_risk": 0.01,
                "target_risk": 0.01,
                "collection": collection,
                "fitted_at": "2026-09-28T00:00:00Z",
            }
        )
    )
    return str(path)


def test_disabled_route_does_not_block_local_production_settings():
    validate_first_person_production_contract(cfg(first_person_route_enabled=False), MANIFEST)


def test_valid_production_contract_passes():
    # In production, calibration profile is NOT required; answerability check is required
    validate_first_person_production_contract(cfg(), MANIFEST)


def test_demoted_profile_passes_if_provided(tmp_path):
    import json

    path = tmp_path / "demoted.json"
    path.write_text(
        json.dumps(
            {
                "threshold": 0.45,
                "score_kind": "cosine",
                "claims": "none",
                "provenance": "n=14 pilot, no conformal guarantees",
                "calibrated_at": "2026-09-25",
            }
        )
    )
    validate_first_person_production_contract(
        cfg(first_person_calibration_path=str(path)), MANIFEST
    )


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"first_person_serve_unregistered": True}, "serve_unregistered"),
        (
            {"first_person_answerability_check_enabled": False},
            "first_person_answerability_check_enabled",
        ),
        ({"first_person_mode": "hybrid"}, "retrieval_only"),
    ],
)
def test_unsafe_production_contract_fails(overrides, message):
    with pytest.raises(FirstPersonReleaseError, match=message):
        validate_first_person_production_contract(cfg(**overrides), MANIFEST)


def test_profile_must_match_active_collection(tmp_path):
    with pytest.raises(FirstPersonReleaseError, match="does not match"):
        validate_first_person_production_contract(
            cfg(first_person_calibration_path=write_profile(tmp_path, "first_person_old")),
            MANIFEST,
        )


def test_unknown_release_provenance_fails():
    with pytest.raises(FirstPersonReleaseError, match="concrete git_sha"):
        validate_first_person_production_contract(
            cfg(),
            SimpleNamespace(release_id="rel-unknown-c7-p1", git_sha="unknown-sha"),
        )
