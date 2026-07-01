"""OKF Compiler — build a single compiled index from OKF markdown entries.

Walks memory/okf/, validates frontmatter, computes embeddings, and writes
memory/okf/compiled.json for fast runtime loading.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_OKF_DIR = Path(__file__).resolve().parents[2] / "memory" / "okf"
_COMPILED_PATH = _OKF_DIR / "compiled.json"


def _load_okf_entries() -> list[dict[str, Any]]:
    from services.memory.okf_store import OKFStore
    store = OKFStore()
    return [
        {
            "path": str(e.path),
            "type": e.type,
            "title": e.title,
            "tags": e.tags,
            "source": e.source,
            "body": e.body,
        }
        for e in store.list_entries()
    ]


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Return dense embeddings using the project's EmbeddingService."""
    from services.embedding_service import EmbeddingService
    svc = EmbeddingService()
    # Blocking call — run in thread so caller can await if desired
    return svc.encode(texts)


def compile_okf() -> Path:
    """Compile OKF entries into compiled.json. Returns the output path."""
    entries = _load_okf_entries()
    if not entries:
        logger.warning("No OKF entries found in %s", _OKF_DIR)
        _COMPILED_PATH.write_text("{}", encoding="utf-8")
        return _COMPILED_PATH

    logger.info("Compiling %d OKF entries", len(entries))
    titles = [e["title"] for e in entries]
    embeddings = _embed_texts(titles)

    compiled: list[dict[str, Any]] = []
    for idx, emb in enumerate(embeddings):
        e = entries[idx]
        compiled.append({
            "path": e["path"],
            "type": e["type"],
            "title": e["title"],
            "tags": e["tags"],
            "source": e["source"],
            "body": e["body"][:2000],  # truncate for size
            "embedding": emb,
        })

    output = {"version": 1, "entries": compiled}
    _COMPILED_PATH.write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")
    logger.info("OKF compiled → %s", _COMPILED_PATH)
    return _COMPILED_PATH


async def get_compiled_okf() -> list[dict[str, Any]]:
    """Return compiled OKF entries from disk (or empty list)."""
    if not _COMPILED_PATH.exists():
        return []
    try:
        data = json.loads(_COMPILED_PATH.read_text(encoding="utf-8"))
        return data.get("entries", [])
    except Exception as e:
        logger.warning("Failed to load compiled OKF: %s", e)
        return []


if __name__ == "__main__":  # ponytail: runnable self-check
    path = compile_okf()
    print(f"Compiled OKF → {path}")
    entries = asyncio.run(get_compiled_okf())
    print(f"Loaded {len(entries)} compiled entries")
    print("compiler OK")
