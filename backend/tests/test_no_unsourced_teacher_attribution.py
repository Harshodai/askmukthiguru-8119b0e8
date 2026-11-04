"""T1-03: no unsourced teacher attribution in tips, courses or the concept bar.

Text attributed to a teacher needs a verifiable locator (video id + timestamp).
Fallback tips are assistant paraphrases, so they carry no teacher credit.
"""

import re
from pathlib import Path

from app.api.teachings import CURATED_FALLBACK_TIPS

ROOT = Path(__file__).resolve().parents[2]
FILES = [
    ROOT / "backend/app/api/teachings.py",
    ROOT / "src/lib/healingCourses.ts",
    ROOT / "src/components/chat/DeepenAndTuneBar.tsx",
]
PATTERN = re.compile(r"Sri (Krishnaji|Preethaji) (says|said|teaches)", re.IGNORECASE)


def test_fallback_tips_are_unattributed_paraphrases():
    assert CURATED_FALLBACK_TIPS
    for tip in CURATED_FALLBACK_TIPS:
        assert tip["teacher"] == ""
        assert tip["source"] == "paraphrase"


def test_no_says_teaches_literals():
    for path in FILES:
        assert not PATTERN.search(path.read_text(encoding="utf-8")), path.name
