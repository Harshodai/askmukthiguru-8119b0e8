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


# ---------------------------------------------------------------------------
# NEW-K8S-2 drift checks (K8S-03, K8S-04, K8S-05).
#
# Real drift exists today and fixing it is NEW-K8S-3 (only if D-PK8S1 chooses
# "fix"). Until then each known violation is listed below. The lists are
# RATCHETS: a new violation fails, and a listed one that no longer occurs must
# be deleted. Never add an entry to make a check pass.
# ---------------------------------------------------------------------------

PLAIN_YAML = (
    K8S_DIR / "backend-deployment.yaml",
    K8S_DIR / "skaffold.yaml",
    CHART / "values.yaml",
    CHART / "values-minikube.yaml",
    CHART / "values-production.yaml",
    REPO_ROOT / "infrastructure" / "k8s_deployment.yaml",
    REPO_ROOT / "infrastructure" / "vllm-deployment.yaml",
    REPO_ROOT / "backend" / "infrastructure" / "k8s.yaml",
)


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _docs(path: Path) -> list:
    return [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d is not None]


def _find_keys(node, key: str):
    """Yield every value stored under `key` anywhere in a parsed YAML tree."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key:
                yield v
            yield from _find_keys(v, key)
    elif isinstance(node, list):
        for item in node:
            yield from _find_keys(item, key)


def _probe_path_violations() -> set[str]:
    bad: set[str] = set()
    for path in PLAIN_YAML:
        for doc in _docs(path):
            probes = list(_find_keys(doc, "livenessProbe"))
            # The Helm values file keeps them under `probes: {liveness: ...}`.
            probes += [p["liveness"] for p in _find_keys(doc, "probes") if "liveness" in p]
            for probe in probes:
                http = (probe or {}).get("httpGet") or {}
                got = http.get("path") or (probe or {}).get("path")
                if got != "/api/healthz":
                    bad.add(f"{_rel(path)} liveness={got}")
    return bad


def _image_violations() -> set[str]:
    bad: set[str] = set()
    for path in PLAIN_YAML:
        if path.name == "skaffold.yaml":
            continue  # artifact names; skaffold stamps the tag at build time
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"^\s*-?\s*image:\s*(\S+)\s*$", text, re.MULTILINE):
            image = match.group(1).strip("\"'")
            tag = image.rsplit(":", 1)[1] if ":" in image.rsplit("/", 1)[-1] else ""
            if tag in ("", "latest") or "REPLACE" in image:
                bad.add(f"{_rel(path)} image={image}")
        for node in _docs(path):
            for image in _find_keys(node, "image"):
                if isinstance(image, dict) and image.get("tag") in (
                    "",
                    "latest",
                    None,
                    "latest-dev",
                ):
                    if image.get("repository"):
                        bad.add(f"{_rel(path)} image={image['repository']}:{image.get('tag')}")
    return bad


def _qdrant_tag_violations() -> set[str]:
    compose = (REPO_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    want = re.search(r"qdrant/qdrant:(v[\w.\-]+)", compose)
    assert want, "docker-compose.prod.yml no longer pins a Qdrant image"
    bad: set[str] = set()
    for path in PLAIN_YAML:
        text = path.read_text(encoding="utf-8")
        for got in re.findall(r"qdrant/qdrant:(v[\w.\-]+)", text):
            if got != want.group(1):
                bad.add(f"{_rel(path)} qdrant={got} (compose={want.group(1)})")
    values = _values()
    tag = str(values.get("qdrant", {}).get("image", {}).get("tag", ""))
    if tag != want.group(1):
        bad.add(f"{_rel(CHART / 'values.yaml')} qdrant={tag} (compose={want.group(1)})")
    return bad


# Each entry: the check that finds it. Closed by NEW-K8S-3, or by retiring the files.
KNOWN_PROBE_DRIFT: set[str] = {
    "backend/infrastructure/k8s.yaml liveness=/",
    "backend/infrastructure/k8s.yaml liveness=/health",
    "infrastructure/k8s/backend-deployment.yaml liveness=/api/health",
    "infrastructure/k8s/helm/mukthiguru/values.yaml liveness=/api/health",
    "infrastructure/k8s_deployment.yaml liveness=/api/health",
}
KNOWN_IMAGE_DRIFT: set[str] = {
    "backend/infrastructure/k8s.yaml image=mukthi-guru/backend-gpu:latest",
    "backend/infrastructure/k8s.yaml image=mukthi-guru/backend:latest",
    "backend/infrastructure/k8s.yaml image=mukthi-guru/frontend:latest",
    "infrastructure/k8s/backend-deployment.yaml image=ghcr.io/harshodai/askmukthiguru-backend:v1.0.0@sha256:REPLACE_WITH_REAL_DIGEST",
    "infrastructure/k8s/helm/mukthiguru/values-minikube.yaml image=mukthiguru-backend:latest",
    "infrastructure/k8s/helm/mukthiguru/values-minikube.yaml image=mukthiguru-frontend:latest",
    "infrastructure/k8s/helm/mukthiguru/values-production.yaml image=<YOUR_REGISTRY>/mukthiguru-backend:latest",
    "infrastructure/k8s/helm/mukthiguru/values-production.yaml image=<YOUR_REGISTRY>/mukthiguru-frontend:latest",
    "infrastructure/k8s/helm/mukthiguru/values.yaml image=mukthiguru-backend:latest",
    "infrastructure/k8s/helm/mukthiguru/values.yaml image=mukthiguru-frontend:latest",
    "infrastructure/k8s_deployment.yaml image=mukthiguru/api:latest",
    "infrastructure/k8s_deployment.yaml image=mukthiguru/backend:latest",
}
KNOWN_QDRANT_DRIFT: set[str] = set()


def _ratchet(found: set[str], known: set[str], what: str) -> None:
    new = sorted(found - known)
    stale = sorted(known - found)
    assert not new, f"new {what} drift:\n" + "\n".join(new)
    assert not stale, f"remove from the known-drift list ({what}):\n" + "\n".join(stale)


def test_liveness_probes_use_api_healthz():
    _ratchet(_probe_path_violations(), KNOWN_PROBE_DRIFT, "probe")


def test_images_are_pinned_not_latest():
    _ratchet(_image_violations(), KNOWN_IMAGE_DRIFT, "image tag")


def test_qdrant_tag_matches_the_prod_compose_file():
    _ratchet(_qdrant_tag_violations(), KNOWN_QDRANT_DRIFT, "qdrant tag")


def _settings_env_names() -> set[str]:
    from app.config import Settings

    names: set[str] = set()
    for name, field in Settings.model_fields.items():
        names.add(name.upper())
        for alias in (field.alias, field.validation_alias):
            if isinstance(alias, str):
                names.add(alias.upper())
            elif alias is not None and hasattr(alias, "choices"):
                names.update(c.upper() for c in alias.choices if isinstance(c, str))
    return names


def _env_name_violations() -> set[str]:
    known = _settings_env_names()
    bad: set[str] = set()
    for name in ("configmap.yaml", "secrets.yaml"):
        text = (TEMPLATES / name).read_text(encoding="utf-8")
        for key in re.findall(r"^  ([A-Z][A-Z0-9_]+):", text, re.MULTILINE):
            if key not in known:
                bad.add(f"templates/{name} {key}")
    return bad


KNOWN_ENV_DRIFT: set[str] = {
    "templates/configmap.yaml JAEGER_AGENT_HOST",
    "templates/configmap.yaml JAEGER_AGENT_PORT",
    "templates/configmap.yaml NEO4J_BOLT_URL",
    "templates/configmap.yaml OLLAMA_URL",
}


def test_chart_env_names_are_settings_fields():
    _ratchet(_env_name_violations(), KNOWN_ENV_DRIFT, "env name")
