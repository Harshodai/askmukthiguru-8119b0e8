"""Owner decision 2026-11-20: production posture is the truth.

One machine-readable source (`PRODUCTION_POSTURE` in the serving contract) is compared
against `.railway/railway.ts` and `backend/.env.example`. The code defaults in
`app/config.py` are deliberately NOT compared (min score default stays 3, pinned by
test_first_person_relevance_calibration); the frozen graded compose is also excluded.
"""

import re
from pathlib import Path

from services.first_person_serving_contract import PRODUCTION_POSTURE

ROOT = Path(__file__).resolve().parents[2]
IAC = (ROOT / ".railway" / "railway.ts").read_text()
ENV_EXAMPLE = (ROOT / "backend" / ".env.example").read_text()


def _railway_effective() -> dict[str, str]:
    """Values railway.ts would pin: the block for the declared posture plus livePosture."""
    posture = re.search(r'const SERVING_POSTURE: ServingPosture = "(\w+)";', IAC).group(1)
    posture_block = IAC.split(f'SERVING_POSTURE === "{posture}"')[1].split(": SERVING_POSTURE")[0]
    live = IAC.split("const livePosture = {")[1].split("};")[0]
    backend_env = (
        IAC.split('service("askmukthiguru-8119b0e8"')[1].split("env: {")[1].split("\n    },")[0]
    )
    found = {"FIRST_PERSON_SERVING_POSTURE": posture}
    for blob in (posture_block, live, backend_env):
        found.update(re.findall(r'\b([A-Z][A-Z0-9_]+): "([^"]*)"', blob))
    return found


def _env_example_effective() -> dict[str, str]:
    return dict(re.findall(r"^([A-Z][A-Z0-9_]+)=(.*)$", ENV_EXAMPLE, re.M))


def test_railway_matches_production_posture():
    got = _railway_effective()
    drift = {k: (got.get(k), v) for k, v in PRODUCTION_POSTURE.items() if got.get(k) != v}
    assert not drift, f"railway.ts drift (got, want): {drift}"


def test_env_example_matches_production_posture():
    got = _env_example_effective()
    drift = {k: (got.get(k), v) for k, v in PRODUCTION_POSTURE.items() if got.get(k) != v}
    assert not drift, f".env.example drift (got, want): {drift}"


# Quality flags measured 2026-11-20: none beat production-config OFF on held-out paired
# judgements (LOOP_NOTES_2026_11_20.md "LEAD CORRECTION"), so they ship OFF everywhere.
# Turning one on needs a registered, repeated, held-out run; then update this list.
QUALITY_FLAGS_OFF = (
    "first_person_meta_followup_enabled",
    "first_person_relevance_exact_n_enabled",
    "first_person_context_seen_rerank_enabled",
    "first_person_answerability_prefetch_enabled",
    "first_person_multipart_enabled",
    "first_person_joint_sufficiency_enabled",
)
_DEPLOY_SOURCES = [
    ROOT / ".railway" / "railway.ts",
    ROOT / "backend" / ".env.example",
    *sorted((ROOT / "backend").glob("docker-compose*.yml")),
    *sorted(ROOT.glob("docker-compose*.yml")),
]


def test_quality_flags_default_off_in_code():
    from app.config import Settings

    on = [f for f in QUALITY_FLAGS_OFF if Settings.model_fields[f].default is not False]
    assert not on, f"quality flags must default OFF: {on}"


def test_quality_flags_not_enabled_by_deploy_config():
    hits = []
    for path in _DEPLOY_SOURCES:
        text = path.read_text()
        for flag in QUALITY_FLAGS_OFF:
            if re.search(rf"\b{flag.upper()}\b[\"']?\s*[:=]\s*[\"']?(?:true|1)\b", text, re.I):
                hits.append(f"{path.relative_to(ROOT)}: {flag.upper()}")
    assert not hits, f"quality flag turned on by deploy config: {hits}"
