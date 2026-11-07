"""NEW-LOV-07: the frontend hosting fact sheet exists and the stale
"hosted on Lovable" comment is gone."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "docs" / "operations" / "frontend-hosting.md"


def test_fact_sheet_covers_every_build_and_marks_unknowns():
    text = DOC.read_text(encoding="utf-8")
    for needle in (
        "Vercel",
        "Lovable preview",
        "Lovable publish",
        "Native (Capacitor)",
        "VITE_BACKEND_URL",
        "Railway",
        "UNKNOWN",
        "src/lib/backendUrl.ts",
    ):
        assert needle in text, needle


def test_build_deploy_no_longer_says_the_frontend_is_hosted_on_lovable():
    text = (REPO_ROOT / ".github" / "workflows" / "build-deploy.yml").read_text(encoding="utf-8")
    assert "The frontend is hosted on Lovable" not in text
    assert "docs/operations/frontend-hosting.md" in text
