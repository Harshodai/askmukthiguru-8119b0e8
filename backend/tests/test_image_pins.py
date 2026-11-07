"""T1-14 / SEC-006: no floating ``:latest`` images; Dockerfile bases pinned by digest."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
_COMPOSE_FILES = [
    _BACKEND / "docker-compose.yml",
    _BACKEND / "docker-compose.dev.yml",
    _BACKEND / "docker-compose.graded.yml",
    _ROOT / "docker-compose.prod.yml",
]
#: Our own images may default to ``latest`` when IMAGE_TAG is unset. Third-party images may not.
_OWN_IMAGE_PREFIX = "ghcr.io/"


class _ComposeLoader(yaml.SafeLoader):
    """Compose merge tags (!override, !reset) are plain data for this test."""


def _passthrough(loader, tag_suffix, node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_scalar(node)


_ComposeLoader.add_multi_constructor("!", _passthrough)


def _images(path: Path) -> list[tuple[str, str]]:
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=_ComposeLoader) or {}  # noqa: S506
    return [
        (name, svc["image"])
        for name, svc in (data.get("services") or {}).items()
        if isinstance(svc, dict) and "image" in svc
    ]


def test_compose_third_party_images_have_an_explicit_non_latest_tag():
    bad = []
    for path in _COMPOSE_FILES:
        if not path.exists():
            continue
        for name, image in _images(path):
            if image.startswith(_OWN_IMAGE_PREFIX):
                continue
            tag = image.rsplit("/", 1)[-1].partition(":")[2]
            if not tag or tag == "latest" or tag.endswith("-latest"):
                bad.append(f"{path.name}:{name}: {image}")
    assert bad == [], bad


def test_own_images_default_only_through_image_tag_variable():
    bad = []
    for path in _COMPOSE_FILES:
        if not path.exists():
            continue
        for name, image in _images(path):
            if image.startswith(_OWN_IMAGE_PREFIX) and ":${IMAGE_TAG" not in image:
                bad.append(f"{path.name}:{name}: {image}")
    assert bad == [], bad


def test_dockerfile_bases_are_pinned_by_digest():
    bad = []
    for df in (_BACKEND / "Dockerfile", _BACKEND / "Dockerfile.railway"):
        stages: set[str] = set()
        for line in df.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^FROM\s+(\S+)(?:\s+AS\s+(\S+))?", line, re.IGNORECASE)
            if not m:
                continue
            ref, alias = m.groups()
            if ref not in stages and "@sha256:" not in ref:
                bad.append(f"{df.name}: {line.strip()}")
            if alias:
                stages.add(alias)
    assert bad == [], bad


def test_backend_claude_md_does_not_tell_readers_to_use_latest():
    text = (_BACKEND / "CLAUDE.md").read_text(encoding="utf-8")
    assert "memgraph-mage:latest" not in text
    assert "memgraph/memgraph-mage:2.20.1" in text
