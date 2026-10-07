"""Regression guard: the owner-approved crisis helplines must reach the container.

``services/crisis_helplines.py:_resolve_config_path()`` resolves the default
config to ``/config/helplines.yaml`` inside the image (``Path(__file__)``
lives at ``/app/services/`` there, so ``.parents[2]`` is the filesystem root,
not ``/app``). Neither ``backend/Dockerfile`` nor ``backend/Dockerfile.railway``
copied ``config/helplines.yaml`` there, so the crisis/safety path silently fell
back to the in-code helpline list instead of the reviewed one (live log:
``crisis_helplines: /config/helplines.yaml not found; using in-code fallback
list``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOCKERFILES = [
    _REPO_ROOT / "backend" / "Dockerfile",
    _REPO_ROOT / "backend" / "Dockerfile.railway",
]


@pytest.mark.parametrize("dockerfile", _DOCKERFILES, ids=lambda p: p.name)
def test_dockerfile_copies_helplines_config(dockerfile: Path):
    """Each backend image must copy config/helplines.yaml to /config/helplines.yaml."""
    assert dockerfile.exists(), f"{dockerfile} is missing"
    body = dockerfile.read_text(encoding="utf-8")
    assert re.search(
        r"^COPY\s+(?:--\S+\s+)*config/helplines\.yaml\s+/config/helplines\.yaml\s*$",
        body,
        re.MULTILINE,
    ), (
        f"{dockerfile.name} does not copy config/helplines.yaml to "
        "/config/helplines.yaml — the safety path silently serves the "
        "in-code fallback helpline list instead of the reviewed one"
    )


def test_compose_mounts_helplines_config_read_only():
    """Local dev (docker compose) must also see the reviewed helplines file."""
    compose_path = _REPO_ROOT / "backend" / "docker-compose.yml"
    assert compose_path.exists()
    body = compose_path.read_text(encoding="utf-8")
    assert "../config:/config:ro" in body, (
        "docker-compose.yml no longer mounts ../config:/config:ro for the "
        "backend service — the crisis-helplines path falls back to the "
        "in-code list in local Docker dev"
    )


def test_helpline_content_unchanged():
    """This fix must not touch the owner-approved helpline data itself."""
    helplines_path = _REPO_ROOT / "config" / "helplines.yaml"
    assert helplines_path.exists()
    import yaml

    data = yaml.safe_load(helplines_path.read_text(encoding="utf-8"))
    total_entries = len(data.get("crisis_helplines") or []) + len(
        data.get("domestic_violence_helplines") or []
    )
    assert total_entries == 15, (
        "config/helplines.yaml entry count changed — this task must only "
        "provision the existing file into the image, never edit its content"
    )


if __name__ == "__main__":
    # ponytail: runnable self-check, no framework needed beyond what's already imported.
    for dockerfile in _DOCKERFILES:
        test_dockerfile_copies_helplines_config(dockerfile)
    test_compose_mounts_helplines_config_read_only()
    test_helpline_content_unchanged()
    print("OK")
