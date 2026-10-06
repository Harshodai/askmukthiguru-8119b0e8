#!/usr/bin/env python3
"""
live_query_test.py — End-to-end test runner for First-Person Pipeline & OKF

Routes THROUGH FirstPersonPipeline.execute() (same as /api/first-person in prod).
No bypasses. Content quality gate, integrity gate, all production logic applies.

Saves full unabridged responses to:
  docs/FIRST_PERSON_AND_GENERAL_CHAT_RESPONSES.md
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ── Path setup ────────────────────────────────────────────────────────────────
_BACKEND = Path(__file__).resolve().parent.parent  # .../backend
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# ── Environment overrides for local run ───────────────────────────────────────
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("QDRANT_COLLECTION", "spiritual_wisdom_contextual")
os.environ.setdefault("REDIS_URL", f"redis://:{os.environ['REDIS_PASSWORD']}@localhost:6379/0")
os.environ.setdefault("LLM_PROVIDER", "openrouter")
os.environ.setdefault("FIRST_PERSON_COLLECTION", "first_person_v7")
os.environ.setdefault("FIRST_PERSON_ROUTE_ENABLED", "true")
os.environ.setdefault("FIRST_PERSON_MODE", "retrieval_only")
os.environ.setdefault("FIRST_PERSON_BOUNDARY_GUARD_ENABLED", "true")
os.environ.setdefault("FIRST_PERSON_CONTENT_QUALITY_GATE_ENABLED", "true")

# Point to v7 calibration profile if it exists
CALIB = str(_BACKEND / "config" / "first_person_calibration_v7.json")
os.environ.setdefault("FIRST_PERSON_CALIBRATION_PATH", CALIB)

from qdrant_client import QdrantClient

from services.first_person_pipeline import FirstPersonPipeline
from services.first_person_store import FirstPersonStore
from services.memory.okf_store import OKF_DIR, match_okf_entries

QDRANT_URL = "http://localhost:6333"
FP_COLLECTION = "first_person_v7"
WISDOM_COLLECTION = "spiritual_wisdom_contextual"
OUT_DOC = _BACKEND.parent / "docs" / "FIRST_PERSON_AND_GENERAL_CHAT_RESPONSES.md"

QUESTIONS = [
    "I want to experience deeper inner peace. What teachings or practices do you suggest?",
    "How do I overcome suffering and discover love in my relationships?",
    "What is the beautiful state that Sri Preethaji and Sri Krishnaji speak of?",
    "Why do I keep suffering even though I know better? What is the root cause?",
    "How do I move from a stressful mind to a peaceful mind in my daily life?",
]


# ── Embedding ─────────────────────────────────────────────────────────────────
def get_embedding_for_query(query: str) -> tuple[list[float] | None, dict[str, Any] | None]:
    """Encode with BGE-M3 ONNX; return (dense, sparse)."""
    try:
        import asyncio

        from services.embedding_service import get_embedding_service

        svc = get_embedding_service()
        result = asyncio.run(svc.encode_single_full_async(query))
        dense = result.get("dense")
        raw_sparse = result.get("sparse") or {}
        sp_vec = (
            {
                "indices": [int(k) for k in raw_sparse.keys()],
                "values": [float(v) for v in raw_sparse.values()],
            }
            if raw_sparse
            else None
        )
        if dense and len(dense) == 1024:
            print(f"    [embed] BGE-M3 real vector ({len(dense)}d, {len(raw_sparse)} sparse terms)")
            return dense, sp_vec
    except Exception as e:
        print(f"    [embed] BGE-M3 unavailable ({e})")
    # Fallback: first OKF embedding as proxy
    try:
        with open(OKF_DIR / "compiled.json") as f:
            data = json.load(f)
        for e in data.get("entries", []):
            emb = e.get("embedding", [])
            if len(emb) == 1024:
                print("    [embed] FALLBACK: using OKF seed vector (wrong query, test only)")
                return emb, None
    except Exception:
        pass
    return None, None


# ── General Chat: Qdrant wisdom_contextual ────────────────────────────────────
def search_wisdom_qdrant(
    client: QdrantClient, dense_vec: list[float], limit: int = 5
) -> list[dict]:
    """Direct Qdrant search against spiritual_wisdom_contextual using 'dense' vector."""
    try:
        results = client.query_points(
            collection_name=WISDOM_COLLECTION,
            query=dense_vec,
            using="dense",
            limit=limit,
            with_payload=True,
            score_threshold=0.35,
        )
        docs = []
        for r in results.points:
            p = r.payload or {}
            meta = p.get("metadata", {}) or {}
            docs.append(
                {
                    "video_id": p.get("video_id") or meta.get("video_id", ""),
                    "speaker": p.get("speaker") or meta.get("speaker", "Teacher"),
                    "text": p.get("text") or p.get("content") or p.get("chunk_text", ""),
                    "source_url": p.get("source_url") or meta.get("source_url", ""),
                    "video_title": p.get("video_title") or meta.get("title", ""),
                    "start_ms": p.get("start_ms") or meta.get("start_ms", 0),
                    "score": r.score,
                }
            )
        return docs
    except Exception as e:
        print(f"    [qdrant wisdom] search error: {e}")
        return []


def build_general_chat_answer(
    query: str,
    wisdom_docs: list[dict],
    okf_entries: list[dict],
) -> str:
    """
    General Chat: verbatim chunks from spiritual_wisdom_contextual.
    OKF entries are shown as TOPIC CONTEXT only — never as guru words.
    """
    lines = [f"**Query:** *{query}*\n"]

    # OKF: topic context only — clearly labelled, not displayed as guru words
    if okf_entries:
        lines.append("**Related Topics from Teachings:**\n")
        for e in okf_entries[:2]:
            teacher_label = {
                "sri-preethaji": "Sri Preethaji",
                "sri-krishnaji": "Sri Krishnaji",
            }.get(e.get("teacher", ""), "Sri Preethaji & Sri Krishnaji")
            lines.append(f"— *{e['title']}* ({teacher_label})")
        lines.append("")

    # Verbatim corpus chunks — these are actual words from transcripts
    if wisdom_docs:
        lines.append("**From the teachings:**\n")
        for d in wisdom_docs[:3]:
            speaker = d.get("speaker") or "Teacher"
            text = (d.get("text") or "").strip()[:500]
            vid = d.get("video_id", "")
            start_s = (d.get("start_ms") or 0) // 1000
            src = d.get("source_url") or (
                f"https://www.youtube.com/watch?v={vid}&t={start_s}s" if vid else ""
            )
            title = d.get("video_title") or vid or "Discourse"
            if text:
                lines.append(f"**{speaker}** — [{title}]({src})\n\n{text}\n")
    else:
        lines.append("*No matching discourse chunks found in spiritual_wisdom_contextual.*")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    print("=" * 70)
    print("AskMukthiGuru — Live Query Test (routes through execute())")
    print(f"  first_person_v7  → {FP_COLLECTION}")
    print(f"  General Chat     → {WISDOM_COLLECTION}")
    print("  Content quality gate: ENABLED for v7")
    print("=" * 70)

    qdrant_client = QdrantClient(url=QDRANT_URL, timeout=15)

    # Verify collections exist
    try:
        fp_info = qdrant_client.get_collection(FP_COLLECTION)
        wisdom_info = qdrant_client.get_collection(WISDOM_COLLECTION)
        print(f"\n✓ first_person_v7: {fp_info.points_count} points")
        print(f"✓ spiritual_wisdom_contextual: {wisdom_info.points_count} points")
    except Exception as e:
        print(f"✗ Qdrant connection failed: {e}")
        sys.exit(1)

    # Load OKF
    okf_compiled = OKF_DIR / "compiled.json"
    okf_entry_count = 0
    if okf_compiled.exists():
        with open(okf_compiled) as f:
            okf_data = json.load(f)
        okf_entry_count = len(okf_data.get("entries", []))
        print(f"✓ OKF compiled.json: {okf_entry_count} entries (used for topic matching only)")

    # Build the production pipeline (same as /api/first-person route)
    # content_quality_gate_enabled is auto-set to True for first_person_v7
    store = FirstPersonStore()
    pipeline = FirstPersonPipeline(store=store, redis_client=None)
    print(f"  Pipeline content quality gate: {pipeline._content_quality_gate_enabled}")
    print(f"  Pipeline boundary guard:       {pipeline._boundary_guard_enabled}")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
    sections: list[str] = [
        "# AskMukthiGuru — First-Person & General Chat Full Responses\n",
        f"**Generated:** {timestamp}  ",
        f"**first_person_v7:** {fp_info.points_count} points  ",
        f"**spiritual_wisdom_contextual:** {wisdom_info.points_count} points  ",
        f"**OKF compiled.json:** {okf_entry_count} entries (topic matching only)  ",
        "**Pipeline:** routes through execute() — same as /api/first-person  ",
        "",
        "---",
        "",
    ]

    for qi, query in enumerate(QUESTIONS, 1):
        print(f"\n{'─' * 70}")
        print(f"Q{qi}: {query}")
        print("─" * 70)
        t0 = time.monotonic()

        # 1. Get embedding vector
        print("  → Getting embedding vector...")
        dense_vec, sparse_vec = get_embedding_for_query(query)
        if dense_vec is None:
            print("  ✗ Cannot proceed: no embedding vector")
            sections.append(
                f"## Question {qi}: {query}\n\n*Embedding unavailable — skipped.*\n\n---\n"
            )
            continue

        # 2. Run through production pipeline (execute() — NOT weaver.weave() bypass)
        print("  → Running through FirstPersonPipeline.execute() with hybrid multi-vector...")
        result = pipeline.execute(
            query=query,
            query_dense_vector=dense_vec,
            query_sparse_vector=sparse_vec,
        )

        elapsed_pipeline = (time.monotonic() - t0) * 1000
        print(
            f"    status={result.status} | is_direct={result.is_direct_answer} | "
            f"n_citations={len(result.citations)} | latency={result.latency_ms:.0f}ms"
        )
        for c in result.citations:
            text_preview = (c.get("verbatim_text") or "")[:80]
            print(
                f"      [{c.get('speaker', '?')}] {c.get('video_id', '')} @{(c.get('start_ms', 0)) // 1000}s: {text_preview}..."
            )

        fp_answer = result.answer_text or "*No teaching found for this query.*"

        # 3. OKF matching — for topic signal only
        print("  → Matching OKF entries (topic context only)...")
        okf_entries = match_okf_entries(
            query_dense_vector=dense_vec,
            top_k=3,
            min_similarity=0.40,
        )
        print(f"    Matched {len(okf_entries)} OKF entries (for General Chat context only)")
        for e in okf_entries:
            print(
                f"      [{e.get('type', '')}] {e.get('title', '')} (score={e.get('score', 0):.4f})"
            )

        # 4. Search spiritual_wisdom_contextual for General Chat
        print("  → Searching spiritual_wisdom_contextual...")
        wisdom_docs = search_wisdom_qdrant(qdrant_client, dense_vec, limit=5)
        print(f"    Retrieved {len(wisdom_docs)} wisdom chunks")

        # 5. Build General Chat answer (verbatim chunks + OKF topic labels only)
        gc_answer = build_general_chat_answer(query, wisdom_docs, okf_entries)

        elapsed_total = (time.monotonic() - t0) * 1000
        print(f"  ✓ Done in {elapsed_total:.0f}ms")

        # Citation table for clips
        clip_cite_rows = []
        for c in result.citations:
            vid = c.get("video_id", "")
            sec = (c.get("start_ms") or 0) // 1000
            spk = c.get("speaker", "Teacher")
            title = c.get("video_title") or c.get("title") or vid
            score = c.get("confidence") or c.get("score") or 0.0
            url = c.get("source_url") or f"https://www.youtube.com/watch?v={vid}&t={sec}s"
            clip_cite_rows.append(f"| {spk} | [{title}]({url}) | {sec}s | {score:.4f} |")

        clip_table = ""
        if clip_cite_rows:
            clip_table = (
                "\n\n**Retrieved Clips (post-gate):**\n\n"
                "| Speaker | Video | Timestamp | Score |\n"
                "|---------|-------|-----------|-------|\n" + "\n".join(clip_cite_rows)
            )

        section_text = "\n".join(
            [
                f"## Question {qi}",
                "",
                f"> {query}",
                "",
                f"*Pipeline: {elapsed_pipeline:.0f}ms | status={result.status} | "
                f"is_direct={result.is_direct_answer} | clips={len(result.citations)}*",
                clip_table,
                "",
                "---",
                "",
                "### First-Person Teaching (verbatim — first_person_v7)",
                "",
                fp_answer,
                "",
                "---",
                "",
                "### General Chat (spiritual_wisdom_contextual verbatim chunks)",
                "",
                gc_answer,
                "",
                "---",
                "",
            ]
        )
        sections.append(section_text)

        # Print preview
        print("\n  ── First-Person Answer Preview (first 800 chars) ──")
        print(fp_answer[:800])
        print("\n  ── General Chat Preview (first 400 chars) ──")
        print(gc_answer[:400])

    # Write to docs/
    OUT_DOC.parent.mkdir(parents=True, exist_ok=True)
    final_md = "\n".join(sections)
    OUT_DOC.write_text(final_md, encoding="utf-8")
    print(f"\n\n{'=' * 70}")
    print(f"✓ Responses written to: {OUT_DOC}")
    print(f"  {OUT_DOC.stat().st_size} bytes")
    print("=" * 70)


if __name__ == "__main__":
    main()
