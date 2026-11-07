"""NEW-LOV-06: src/CLAUDE.md carries the rule Lovable edits must follow."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_src_claude_md_lists_the_contracts_lovable_must_keep():
    text = (REPO_ROOT / "src" / "CLAUDE.md").read_text(encoding="utf-8")
    assert "## Lovable edits" in text
    for needle in (
        "chatStorage",
        "profileStorage",
        "askmukthiguru_stream_checkpoint",
        "T1-16",
        "T1-17",
        "T1-19",
        "T6-10",
        "src/integrations/supabase/",
    ):
        assert needle in text, needle
