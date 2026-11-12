"""T1-01 / ANS-005: agent instruction files must not order teacher first-person text."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = ["CLAUDE.md", "AGENTS.md"]
FORBIDDEN = [
    r"Direct Sacred Presence",
    r"MUST be delivered directly in the first person",
    r"woven organically",
    r"delivered in the teacher'?s own words \(\"I\"\)",
    r"detached 3rd-person",
    r"According to Sri Krishnaji\.\.\.\".{0,40}strictly prohibited",
]


def _text(name):
    p = ROOT / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def test_no_teacher_first_person_directives():
    for name in FILES:
        text = _text(name)
        for pat in FORBIDDEN:
            assert not re.search(pat, text, re.I | re.S), f"{name} matches {pat!r}"


def test_voice_governance_rule_present():
    assert "never in a teacher's first person" in _text("CLAUDE.md")
