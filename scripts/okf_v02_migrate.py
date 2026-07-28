#!/usr/bin/env python3
"""Batch-migrate memory/okf/ entries from OKF v0.1 to v0.2 frontmatter."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import yaml

OKF_DIR = Path(__file__).parents[1] / "memory" / "okf"
EXCLUDED_PARTS = {"staging", "_scripts"}
RESERVED = {"index.md", "log.md"}


def _load_frontmatter(text: str) -> Optional[Tuple[dict, str]]:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    try:
        meta = yaml.safe_load(text[4:end])
    except Exception:
        return None
    return meta, text[end + 5 :]


def migrate_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    parsed = _load_frontmatter(text)
    if not parsed:
        print(f"SKIP (no frontmatter): {path}")
        return False
    meta, body = parsed
    if not isinstance(meta, dict) or meta.get("type") in {None}:
        print(f"SKIP (no type): {path}")
        return False

    updated = meta.get("updated") or "2026-07-10"
    resource = meta.get("resource") or meta.get("source")
    source = meta.get("source") or resource
    title = meta.get("title") or path.stem.replace("_", " ").title()

    new_meta: dict = {
        "type": meta["type"],
        "title": title,
        "description": meta.get("description"),
        "resource": resource,
        "source": source,
        "teacher": meta.get("teacher"),
        "tags": meta.get("tags", []),
        "updated": updated,
        "status": meta.get("status", "stable"),
        "generated": meta.get("generated", {"by": "human:curator", "at": f"{updated}T00:00:00Z"}),
        "verified": meta.get("verified", {"by": "human:curator", "at": f"{updated}T00:00:00Z"}),
        "sources": meta.get(
            "sources",
            [
                {
                    "id": "primary",
                    "resource": resource,
                    "title": title,
                }
            ],
        ),
    }

    # Drop empty optional values
    if not new_meta["description"]:
        del new_meta["description"]
    if not new_meta["teacher"]:
        del new_meta["teacher"]
    if not new_meta["tags"]:
        del new_meta["tags"]

    out = "---\n" + yaml.safe_dump(new_meta, sort_keys=False, allow_unicode=True) + "---\n" + body
    path.write_text(out, encoding="utf-8")
    print(f"MIGRATED: {path}")
    return True


def main() -> None:
    migrated = 0
    for path in sorted(OKF_DIR.rglob("*.md")):
        if path.name in RESERVED:
            continue
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        if migrate_file(path):
            migrated += 1

    index_path = OKF_DIR / "index.md"
    index_text = index_path.read_text(encoding="utf-8")
    if not index_text.startswith("---") or "okf_version" not in index_text:
        index_path.write_text(
            '---\nokf_version: "0.2"\n---\n\n' + index_text.lstrip("-").lstrip(),
            encoding="utf-8",
        )
        print(f"MIGRATED INDEX: {index_path}")

    print(f"Total migrated: {migrated}")


if __name__ == "__main__":
    main()
