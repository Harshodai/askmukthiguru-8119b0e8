"""OKF Compiler — build a single compiled index from OKF markdown entries.

Walks memory/okf/, validates frontmatter, computes embeddings, and writes
memory/okf/compiled.json for fast runtime loading.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from pathlib import Path, PurePath
from typing import Any

logger = logging.getLogger(__name__)

# parents[3] resolved to `/memory/okf` inside the image (backend/ IS /app there, so
# the fourth parent is `/`), so POST /admin/okf/compile wrote where retrieval never
# reads. okf_store owns the one resolver that handles both layouts.
from services.memory.okf_store import OKF_DIR as _OKF_DIR
from services.memory.okf_store import _extract_key_teachings

_COMPILED_PATH = _OKF_DIR / "compiled.json"

# --- compile-time dedup (OKF quality audit 2026-10-04) ------------------------
# The OKF tree holds bulk-extracted entries at the repo root AND graduated
# copies under the teacher subdirs (shared/, sri-preethaji/, sri-krishnaji/).
# The store walk reads both, so 32 titles compiled twice and ~57% of entries
# had a >=0.9-Jaccard near-twin. The stages below collapse each redundant
# group to its single best-provenance copy BEFORE embedding (saves compute
# and stops duplicated doctrine from out-voting itself at retrieval).
_HEADING_RE = re.compile(
    r"#{1,6}\s*(summary|key teachings|quotes|related concepts|source context)\b"
)
_JACCARD_THRESHOLD = 0.9
# A graduated (subdir) copy wins a redundant group unless its body is shorter
# than this fraction of the longest root copy — graduation is a review
# signal, but not worth losing substantive content over.
_GRADUATED_LENGTH_GUARD = 0.7
_GRADUATED_DIRS = frozenset({"shared", "sri-preethaji", "sri-krishnaji"})
_VIDEO_ID_RE = re.compile(r"[?&]v=([A-Za-z0-9_-]{6,})")


def _normalize_body(body: str) -> str:
    """Lowercase + whitespace-collapsed body for content hashing."""
    return re.sub(r"\s+", " ", (body or "").lower()).strip()


def _content_hash(body: str) -> str:
    return hashlib.sha256(_normalize_body(body).encode("utf-8")).hexdigest()


def _body_word_set(body: str) -> set[str]:
    """Template-stripped word set so shared section headings don't inflate overlap."""
    text = _HEADING_RE.sub(" ", (body or "").lower())
    return set(re.findall(r"[a-z0-9]+", text))


def _is_graduated(entry: dict[str, Any]) -> bool:
    """True when the entry was compiled from a canonical teacher subdir."""
    parts = PurePath(str(entry.get("path", ""))).parts
    return any(part in _GRADUATED_DIRS for part in parts)


def _has_video_id(entry: dict[str, Any]) -> bool:
    return bool(_VIDEO_ID_RE.search(str(entry.get("source", ""))))


def _provenance_rank(entry: dict[str, Any]) -> tuple:
    """Higher wins: graduated copy, video provenance, longer body, more teachings."""
    return (
        _is_graduated(entry),
        _has_video_id(entry),
        len(str(entry.get("body") or "")),
        len(entry.get("key_teachings") or []),
    )


def _pick_best(group: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep one copy per redundant group.

    The graduated (teacher-subdir) copy wins as the reviewed canonical entry,
    unless it is substantially shorter than the root copy — then the longer
    root copy wins so content is not lost to a thinner graduation.
    """
    graduated = [e for e in group if _is_graduated(e)]
    roots = [e for e in group if not _is_graduated(e)]
    if graduated and roots:
        best_sub = max(graduated, key=_provenance_rank)
        best_root = max(roots, key=_provenance_rank)
        if len(str(best_sub.get("body") or "")) >= _GRADUATED_LENGTH_GUARD * max(
            1, len(str(best_root.get("body") or ""))
        ):
            return best_sub
        return best_root
    return max(group, key=_provenance_rank)


def dedupe_okf_entries(
    entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Collapse redundant OKF entries, keeping the best-provenance copy.

    Stages: same filename (root-vs-subdir doubles) → exact title →
    exact content-hash → greedy Jaccard>=0.9 on template-stripped word sets
    (best-ranked entry survives; every >=0.9 neighbor of a survivor is dropped).
    Returns (deduped_entries, stats).
    """
    from collections import defaultdict

    stats: dict[str, int] = {"n_before": len(entries)}

    by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in entries:
        by_file[PurePath(str(e.get("path", ""))).name].append(e)
    stats["filename_groups"] = sum(1 for g in by_file.values() if len(g) > 1)
    kept = [_pick_best(g) if len(g) > 1 else g[0] for g in by_file.values()]
    stats["n_after_filename"] = len(kept)

    by_title: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in kept:
        by_title[str(e.get("title", "")).strip().lower()].append(e)
    stats["exact_title_groups"] = sum(1 for g in by_title.values() if len(g) > 1)
    kept = [_pick_best(g) if len(g) > 1 else g[0] for g in by_title.values()]
    stats["n_after_exact_title"] = len(kept)

    by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in kept:
        by_hash[_content_hash(str(e.get("body") or ""))].append(e)
    stats["content_hash_groups"] = sum(1 for g in by_hash.values() if len(g) > 1)
    kept = [_pick_best(g) if len(g) > 1 else g[0] for g in by_hash.values()]
    stats["n_after_content_hash"] = len(kept)

    word_sets = {id(e): _body_word_set(str(e.get("body") or "")) for e in kept}
    ordered = sorted(kept, key=_provenance_rank, reverse=True)
    alive: list[dict[str, Any]] = []
    alive_sets: list[set[str]] = []
    for e in ordered:
        words = word_sets[id(e)]
        is_twin = False
        for known in alive_sets:
            union = words | known
            if union and len(words & known) / len(union) >= _JACCARD_THRESHOLD:
                is_twin = True
                break
        if not is_twin:
            alive.append(e)
            alive_sets.append(words)
    stats["jaccard_dropped"] = len(kept) - len(alive)
    stats["n_after"] = len(alive)
    return alive, stats


def _load_okf_entries() -> list[dict[str, Any]]:
    from services.memory.okf_store import OKFStore

    store = OKFStore()
    return [
        {
            "path": str(e.path),
            "type": e.type,
            "title": e.title,
            "description": e.description,
            "embed_text": e.embed_text,
            "tags": e.tags,
            "source": e.source,
            "resource": e.resource,
            "teacher": e.teacher,
            "body": e.body,
            "status": e.status,
            "generated": e.generated,
            "verified": e.verified,
            "sources": e.sources,
        }
        for e in store.list_entries()
    ]


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Return dense embeddings using the project's EmbeddingService."""
    from services.embedding_service import get_embedding_service

    svc = get_embedding_service()
    # Blocking call — run in thread so caller can await if desired
    return svc.encode(texts)


def compile_okf() -> Path:
    """Compile OKF entries into compiled.json. Returns the output path."""
    entries = _load_okf_entries()
    if not entries:
        logger.warning("No OKF entries found in %s", _OKF_DIR)
        _COMPILED_PATH.write_text("{}", encoding="utf-8")
        return _COMPILED_PATH

    entries, dedup_stats = dedupe_okf_entries(entries)
    logger.info(
        "OKF dedup: %d -> %d entries "
        "(filename_groups=%d exact_title_groups=%d content_hash_groups=%d "
        "jaccard_dropped=%d)",
        dedup_stats["n_before"],
        dedup_stats["n_after"],
        dedup_stats["filename_groups"],
        dedup_stats["exact_title_groups"],
        dedup_stats["content_hash_groups"],
        dedup_stats["jaccard_dropped"],
    )
    logger.info("Compiling %d OKF entries", len(entries))
    # Embed title + description, not the bare title. A seeker asks "why do I keep
    # suffering?"; matching that against the string "Inner Truth" is close to noise.
    # Fall back to the title when a producer supplies neither (OKF: description is
    # recommended, not required).
    embeddings = _embed_texts([e.get("embed_text") or e["title"] for e in entries])

    # ponytail: guard against silent EmbeddingService failure —
    # compiled.json had empty embeddings despite this code looking correct.
    embed_ok = bool(embeddings) and any(
        isinstance(e, (list, tuple)) and len(e) > 0 and any(e) for e in embeddings
    )
    if not embed_ok:
        logger.warning(
            "OKF embeddings are empty or all-zero — EmbeddingService may be "
            "unavailable. Compiled index will lack semantic search capability."
        )

    compiled: list[dict[str, Any]] = []
    for idx, emb in enumerate(embeddings):
        e = entries[idx]
        compiled.append(
            {
                "path": e["path"],
                "type": e["type"],
                "title": e["title"],
                "description": e.get("description", ""),
                "tags": e["tags"],
                "source": e["source"],
                "resource": e.get("resource", e["source"]),
                "teacher": e.get("teacher", "both"),
                "body": e["body"][:2000],
                "key_teachings": _extract_key_teachings(e),
                "embedding": emb if embed_ok else [],
                "status": e.get("status", "stable"),
                "generated": e.get("generated"),
                "verified": e.get("verified"),
                "sources": e.get("sources", []),
            }
        )

    output = {"version": 2, "entries": compiled}
    _COMPILED_PATH.write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")
    logger.info("OKF compiled → %s", _COMPILED_PATH)
    return _COMPILED_PATH


def score_staged_entry(entry: dict[str, Any]) -> float:
    """Score a staged OKF entry for quality (0.0-1.0).

    Scoring criteria:
    - Has non-empty title (+0.1)
    - Has non-empty description (+0.2)
    - Has non-empty body (+0.2)
    - Has source URL (+0.15)
    - Has teacher attribution (+0.1)
    - No extraction artifacts (+0.15)
    - Body > 100 chars (+0.1)
    """
    score = 0.0

    title = (entry.get("title") or "").strip()
    description = (entry.get("description") or "").strip()
    body = (entry.get("body") or "").strip()
    source = (entry.get("source") or "").strip()
    teacher = (entry.get("teacher") or "").strip()

    if title:
        score += 0.1
    if description:
        score += 0.2
    if body:
        score += 0.2
    if source:
        from urllib.parse import urlparse

        parsed = urlparse(source)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            score += 0.15
    if teacher:
        score += 0.1
    if len(body) > 100:
        score += 0.1

    # Check for extraction artifacts
    artifacts = ["RAPTOR Level:", "_(Source:", "extract", "prompt"]
    has_artifacts = any(artifact.lower() in body.lower() for artifact in artifacts)
    if not has_artifacts:
        score += 0.15

    return min(1.0, score)


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
