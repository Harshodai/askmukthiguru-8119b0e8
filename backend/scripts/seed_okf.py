#!/usr/bin/env python3
"""CLI: write a properly-formatted OKF markdown entry to memory/okf/.

Does NOT auto-generate doctrine content (zero-hallucination constraint: data
source is only the gurus' approved videos). This scaffolds the file with the
required YAML frontmatter (`type` is mandatory) and a body you supply via
--body-file or stdin. Use to grow memory/okf/ from approved transcripts.

Usage:
  python -m scripts.seed_okf --title "Oneness" --type teaching \
      --video-id "abc123" --body-file path/to/body.md
  echo "body text" | python -m scripts.seed_okf --title X --type glossary

# ponytail: full auto-extraction from transcripts (NLP summarisation of approved
# YouTube transcripts into OKF entries) is a future task; this CLI only formats
# author-supplied content so we never fabricate teachings.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

_OKF_DIR = _BACKEND.parent / "memory" / "okf"
_VALID_TYPES = {"teaching", "practice", "glossary", "qa", "reflection"}


def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return s or "entry"


def write_entry(title: str, type_: str, body: str, video_id: str | None,
                source: str | None, tags: list[str]) -> Path:
    if type_ not in _VALID_TYPES:
        raise ValueError(f"invalid type {type_!r}; must be one of {_VALID_TYPES}")
    if not title.strip() or not body.strip():
        raise ValueError("title and body must be non-empty")
    fm = ["---", f"type: {type_}", f'title: "{title}"']
    if source:
        fm.append(f'source: "{source}"')
    if video_id:
        fm.append(f"video_id: {video_id}")
    if tags:
        fm.append(f"tags: [{', '.join(tags)}]")
    fm.append("---")
    content = "\n".join(fm) + "\n\n# " + title + "\n\n" + body.strip() + "\n"
    path = _OKF_DIR / f"{_slug(title)}.md"
    _OKF_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def main() -> int:
    p = argparse.ArgumentParser(description="Seed an OKF markdown entry (no content fabrication).")
    p.add_argument("--title", required=True)
    p.add_argument("--type", required=True, choices=sorted(_VALID_TYPES))
    p.add_argument("--video-id", default=None)
    p.add_argument("--source", default=None)
    p.add_argument("--tags", default="", help="comma-separated tags")
    p.add_argument("--body-file", default=None, help="path to body markdown; stdin if omitted")
    args = p.parse_args()
    body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else sys.stdin.read()
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    src = args.source or (f"YouTube https://www.youtube.com/watch?v={args.video_id}" if args.video_id else None)
    path = write_entry(args.title, args.type, body, args.video_id, src, tags)
    print(f"OKF entry written → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())