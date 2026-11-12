"""lessons.md stays short; nothing it used to hold is lost; cited lesson ids resolve.

2026-11-07: sections older than the cut moved, unchanged, to docs/agent/lessons-archive/.
"""

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LESSONS = REPO / "lessons.md"
ARCHIVE = REPO / "docs" / "agent" / "lessons-archive" / "lessons-archive-2026-11-07.md"
MAX_LESSONS_LINES = 1500  # shrink-only ceiling for the live file
#: Cited in a code comment but never written down, before the archive existed. Shrink-only.
KNOWN_UNRESOLVED = {"L-env-driven"}


def _both() -> str:
    return LESSONS.read_text(encoding="utf-8") + "\n" + ARCHIVE.read_text(encoding="utf-8")


def test_live_file_is_short_and_points_to_the_archive():
    text = LESSONS.read_text(encoding="utf-8")
    assert len(text.splitlines()) <= MAX_LESSONS_LINES
    assert "docs/agent/lessons-archive/lessons-archive-2026-11-07.md" in text
    assert text.splitlines()[0].startswith("<!-- lessons.md")  # newest-on-top rule kept


def test_archive_keeps_the_old_sections_unchanged():
    text = ARCHIVE.read_text(encoding="utf-8")
    assert "## Oct 24, 2026 — v10 speaker evidence on the Mac" in text
    assert (
        len(re.findall(r"^### L-", _both(), flags=re.M)) >= 1162
    )  # all lesson headings before the move


def test_every_cited_lesson_id_resolves():
    out = subprocess.run(
        [
            "git",
            "grep",
            "-hoE",
            r"lessons\.md[^A-Za-z]{1,6}L-[A-Za-z0-9-]+",
            "--",
            "backend",
            "scripts",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    ).stdout
    ids = {
        m.group(1).rstrip("-")
        for line in out.splitlines()
        if (m := re.search(r"(L-[A-Za-z0-9-]+)", line))
    }
    both = _both()
    missing = {i for i in ids if i not in both}
    assert missing <= KNOWN_UNRESOLVED, f"cited but in neither lessons file: {sorted(missing)}"
