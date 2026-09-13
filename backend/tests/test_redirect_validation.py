"""A7 guard: every redirect hop must pass _validate_redirect (SSRF)."""

import re


def test_redirect_hook_wired():
    import ingestion.web_ingest_pipeline as m

    src = open(m.__file__).read()
    assert "def _validate_redirect" in src
    non_def_refs = [
        line
        for line in src.splitlines()
        if "_validate_redirect" in line and "def _validate_redirect" not in line
    ]
    assert len(non_def_refs) >= 1, "zero callers: redirect targets never validated"
    assert "event_hooks" in src, "no httpx event_hooks wiring for per-hop validation"


def test_redirect_hop_cap_present():
    import ingestion.web_ingest_pipeline as m

    src = open(m.__file__).read()
    assert re.search(r"(MAX_REDIRECT|hop|history)", src, re.IGNORECASE), "no hop cap"
