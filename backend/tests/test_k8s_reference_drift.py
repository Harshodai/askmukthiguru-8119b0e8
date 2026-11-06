"""Kubernetes reference-manifest guards (NEW-K8S-5, NEW-K8S-1, NEW-K8S-2).

The manifests are REFERENCE ONLY: Railway (`.railway/railway.ts`) and
`docker-compose.prod.yml` are the deploy source of truth. Decision D-PK8S1
(keep as reference, fix, or retire) is open, so these tests keep the files
honest without changing any image, port or value.

NEW-K8S-5 (K8S-06): the Helm chart ships no default passwords.

Static checks only. Helm is not installed here and nothing renders the chart,
so a real `helm template` run stays an owner step (UNPROVEN until it is run).
The tests never print a password value.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
K8S_DIR = REPO_ROOT / "infrastructure" / "k8s"
CHART = K8S_DIR / "helm" / "mukthiguru"
TEMPLATES = CHART / "templates"

REFERENCE_HEADER = "REFERENCE ONLY. Not deployed."
# Loose Kubernetes files outside infrastructure/k8s/. Moving them under
# infrastructure/k8s/legacy/ needs owner approval (D-PK8S1), so they stay put.
LOOSE_FILES = (
    REPO_ROOT / "infrastructure" / "k8s_deployment.yaml",
    REPO_ROOT / "infrastructure" / "k8s_deploy.sh",
    REPO_ROOT / "infrastructure" / "vllm-deployment.yaml",
    REPO_ROOT / "backend" / "infrastructure" / "k8s.yaml",
)
# `_helpers.tpl` only defines named templates; a header comment there would not
# be rendered anywhere, so it is not required to carry one.
HEADER_EXEMPT = {"_helpers.tpl", "Chart.lock"}


def _values(name: str = "values.yaml") -> dict:
    return yaml.safe_load((CHART / name).read_text(encoding="utf-8"))


def _walk(node, path=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, (*path, str(key)))
    else:
        yield path, node


def test_values_files_hold_no_password_literal():
    offenders = []
    for name in ("values.yaml", "values-minikube.yaml", "values-production.yaml"):
        for path, value in _walk(_values(name)):
            if "password" in path[-1].lower() and isinstance(value, str) and value.strip():
                offenders.append(f"{name}: {'.'.join(path)}")
    assert not offenders, "password literals committed (K8S-06):\n" + "\n".join(offenders)


def test_templates_require_the_passwords_instead_of_defaulting():
    configmap = (TEMPLATES / "configmap.yaml").read_text(encoding="utf-8")
    neo4j = (TEMPLATES / "neo4j.yaml").read_text(encoding="utf-8")
    redis = (TEMPLATES / "redis.yaml").read_text(encoding="utf-8")
    secrets = (TEMPLATES / "secrets.yaml").read_text(encoding="utf-8")

    for name, text in (("configmap", configmap), ("redis", redis), ("secrets", secrets)):
        assert re.search(
            r"required\s+\"[^\"]*redis[^\"]*\"\s+\.Values\.redis\.auth\.password", text
        ), name
    assert re.search(r"required\s+\"[^\"]*neo4j[^\"]*\"\s+\.Values\.neo4j\.auth\.password", neo4j)


def test_secrets_template_does_not_fall_back_to_a_default_redis_password():
    secrets = (TEMPLATES / "secrets.yaml").read_text(encoding="utf-8")
    redis_line = next(line for line in secrets.splitlines() if "REDIS_PASSWORD" in line)
    assert "default (.Values.redis.auth.password" not in redis_line


def _manifest_files() -> list[Path]:
    found = set(LOOSE_FILES)
    for path in K8S_DIR.rglob("*"):
        if not path.is_file() or path.name in HEADER_EXEMPT:
            continue
        in_chart = path.is_relative_to(CHART)
        if in_chart and path.relative_to(CHART).parts[0] == "charts":
            continue  # vendored sub-charts
        found.add(path)
    return sorted(found)


def test_every_kubernetes_file_says_it_is_reference_only():
    missing = [
        str(p.relative_to(REPO_ROOT))
        for p in _manifest_files()
        if REFERENCE_HEADER not in "\n".join(p.read_text(encoding="utf-8").splitlines()[:6])
    ]
    assert not missing, "files without the REFERENCE ONLY header (K8S-01):\n" + "\n".join(missing)


def test_the_header_names_the_real_source_of_truth_and_both_exist():
    assert (REPO_ROOT / ".railway" / "railway.ts").is_file()
    assert (REPO_ROOT / "docker-compose.prod.yml").is_file()
    readme = (K8S_DIR / "README.md").read_text(encoding="utf-8")
    assert ".railway/railway.ts" in readme and "docker-compose.prod.yml" in readme
