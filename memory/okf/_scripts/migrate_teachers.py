"""Migrate OKF entries: add teacher field, restructure into teacher subdirectories."""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

OKF_DIR = Path(__file__).resolve().parents[1]

# Teacher attribution rules
TEACHER_MAP: dict[str, str] = {
    "beautiful_state.md": "sri-preethaji",
    "experiencing_the_divine_manifest_and_unmanifest.md": "sri-preethaji",
    "the_first_sacred_secret_live_with_a_spiritual_vision.md": "sri-preethaji",
    "the_voice_that_speaks_to_you_and_guides_you.md": "sri-preethaji",
    "three_question_meditation.md": "sri-preethaji",
    "inner_truth_of_suffering.md": "sri-preethaji",
    "serene_mind_practice.md": "sri-krishnaji",
    "awakening_to_compassion.md": "sri-krishnaji",
    "beautiful_state_and_health_challenges.md": "both",
    "beautiful_state_glossary.md": "both",
    "beautiful_state_practice.md": "both",
    "claiming_the_inner_state.md": "both",
    "connecting_to_universal_intelligence.md": "both",
    "feeling_one_with_universal_intelligence.md": "both",
    "finding_truth_in_chaos.md": "both",
    "gentle_spiritual_awakening.md": "both",
    "inner_peace_and_consciousness.md": "both",
    "inner_truth_and_being.md": "both",
    "power_of_collective_meditation.md": "both",
    "stillness_and_inner_truth.md": "both",
    "universal_intelligence.md": "both",
    "universal_intelligence_and_oneness.md": "both",
}

RESERVED = frozenset({"index.md", "log.md", "compiled.json"})


def _add_or_update_frontmatter(text: str, key: str, value: str) -> str:
    """Add or update a YAML frontmatter field."""
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return text
    fm = parts[1]
    # Replace existing field or append
    pattern = rf"^{key}:.*$"
    replacement = f'{key}: "{value}"'
    if re.search(pattern, fm, re.MULTILINE):
        new_fm = re.sub(pattern, replacement, fm, flags=re.MULTILINE)
    else:
        new_fm = fm.rstrip() + f"\n{replacement}\n"
    return f"---{new_fm}---{parts[2]}"


def migrate():
    # Create target dirs
    for d in ["sri-preethaji", "sri-krishnaji", "shared", "_scripts"]:
        (OKF_DIR / d).mkdir(exist_ok=True)

    for md_file in sorted(OKF_DIR.glob("*.md")):
        if md_file.name in RESERVED:
            continue

        teacher = TEACHER_MAP.get(md_file.name, "both")
        target_subdir = {"sri-preethaji": "sri-preethaji", "sri-krishnaji": "sri-krishnaji"}.get(
            teacher, "shared"
        )

        text = md_file.read_text(encoding="utf-8")
        text = _add_or_update_frontmatter(text, "teacher", teacher)
        text = _add_or_update_frontmatter(text, "updated", "2026-07-10")
        md_file.write_text(text, encoding="utf-8")

        target = OKF_DIR / target_subdir / md_file.name
        if target.exists():
            target.unlink()
        shutil.move(str(md_file), str(target))
        print(f"  {md_file.name} → {target_subdir}/  (teacher: {teacher})")

    print("\nDone. Remove empty migrated dirs if any.")


if __name__ == "__main__":
    migrate()
