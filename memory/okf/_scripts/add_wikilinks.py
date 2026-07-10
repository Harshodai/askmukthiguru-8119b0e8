import re
from pathlib import Path

okf = Path(__file__).resolve().parent.parent

# Build concept name → wiki-link ID map
TITLE_TO_WIKI = {}
for md_file in okf.rglob("*.md"):
    if md_file.name in ("index.md", "log.md") or "_scripts" in md_file.parts or "staging" in md_file.parts:
        continue
    text = md_file.read_text(encoding="utf-8")
    if not text.startswith("---"):
        continue
    m = re.search(r'^title:\s*"?(.+?)"?\s*$', text.split("---", 2)[1], re.MULTILINE)
    if m:
        title = m.group(1).strip().strip('"')
        short = title.split(" — ")[0]
        rel = str(md_file.relative_to(okf)).replace(".md", "")
        TITLE_TO_WIKI[title] = rel
        if short != title:
            TITLE_TO_WIKI[short] = rel

TITLE_TO_WIKI.update({
    "Beautiful State": "sri-preethaji/beautiful_state",
    "Serene Mind": "sri-krishnaji/serene_mind_practice",
    "Universal Intelligence": "shared/universal_intelligence",
    "Inner Truth": "shared/inner_truth_and_being",
    "Stillness": "shared/stillness_and_inner_truth",
    "Three-Question Meditation": "sri-preethaji/three_question_meditation",
})


RC_LINE = re.compile(r"^(- \*\*)([^*]+?)(\*\*:.*)$")
BOLD = re.compile(r"\*\*([^*]+?)\*\*")


def add_rc_wikilinks(text: str) -> str:
    """Add [[wiki_id]] to each Related Concepts list item."""
    lines = text.split("\n")
    new_lines = []
    in_rc = False
    changed = False
    for line in lines:
        if re.match(r"^## (Related Concepts|See Also|Cross-References)", line):
            in_rc = True
        elif line.startswith("## ") and not line.startswith("### "):
            in_rc = False

        if in_rc:
            m = RC_LINE.match(line)
            if m:
                concept = m.group(2)
                wiki_id = TITLE_TO_WIKI.get(concept)
                if wiki_id and f"[[{wiki_id}" not in line:
                    line = f'{m.group(1)}{m.group(2)}** ([[{wiki_id}]]): {m.group(3)[4:]}'
                    changed = True

        new_lines.append(line)

    return "\n".join(new_lines), changed


def add_body_wikilinks(text: str) -> tuple:
    """Add [[wiki_id|name]] to bold concept references outside Related Concepts."""
    lines = text.split("\n")
    new_lines = []
    in_rc = False
    changed = False
    for line in lines:
        if re.match(r"^## (Related Concepts|See Also|Cross-References)", line):
            in_rc = True
        elif line.startswith("## ") and not line.startswith("### "):
            in_rc = False

        if not in_rc:
            def replace_bold(m):
                word = m.group(1)
                wid = TITLE_TO_WIKI.get(word)
                if wid and f"[[{wid}" not in m.group(0):
                    return f"[[{wid}|{word}]]"
                return m.group(0)

            new_line = BOLD.sub(replace_bold, line)
            if new_line != line:
                changed = True
            line = new_line

        new_lines.append(line)

    return "\n".join(new_lines), changed


for md_file in sorted(okf.rglob("*.md")):
    if md_file.name in ("index.md", "log.md") or "_scripts" in md_file.parts or "staging" in md_file.parts:
        continue
    text = md_file.read_text(encoding="utf-8")
    if not text.startswith("---"):
        continue
    parts = text.split("---", 2)
    if len(parts) < 3:
        continue

    fm, body = parts[1], parts[2]
    body1, c1 = add_rc_wikilinks(body)
    body2, c2 = add_body_wikilinks(body1)

    if c1 or c2:
        md_file.write_text(f"---{fm}---{body2}", encoding="utf-8")
        print(f"  WIKIFIED: {md_file.relative_to(okf.parent)}")
    else:
        print(f"  SKIP:     {md_file.relative_to(okf.parent)}")

print("\nDone")
