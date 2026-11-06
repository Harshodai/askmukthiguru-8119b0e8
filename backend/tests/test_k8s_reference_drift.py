"""NEW-K8S-5 (K8S-06): the Helm chart ships no default passwords.

Static checks only. Helm is not installed here and nothing renders the chart,
so a real `helm template` run stays an owner step (UNPROVEN until it is run).
The tests never print a password value.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CHART = REPO_ROOT / "infrastructure" / "k8s" / "helm" / "mukthiguru"
TEMPLATES = CHART / "templates"


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
