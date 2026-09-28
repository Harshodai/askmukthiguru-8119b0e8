#!/usr/bin/env python3
"""Offline seeker-question generation for first-person clips (plan rev 2, card C1).

Port of ~/mukthiguru_attribution_data/bakeoff_2026-09-25/genq.py into the repo
(.claude/tasks/OFFLINE_LLM_ASSIST_PLAN.md step 1), with two changes:
  - every question must pass services.text_quality_filter.find_artifact();
  - the doc2query-- filter runs the REAL first-person retriever
    (FirstPersonStore.search_hybrid, dense + sparse RRF), not a numpy copy of it:
    a question is kept only if it retrieves its own clip in the top 5.

Output is a JSON staging file for HUMAN REVIEW. This script never writes Qdrant;
filling question_dense is a later, approved index build (plan step 4). The LLM
never produces anything a seeker sees -- only retrieval keys.

  .venv/bin/python -m scripts.ops.generate_first_person_questions \
      --collection first_person_v6 --out ~/mukthiguru_attribution_data/genq/first_person_v6.json [--limit 20]
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import re
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "..")))

BATCH = 8
QUESTIONS_PER_CLIP = 5
SELF_RETRIEVAL_TOP_K = 5
_MIN_Q_CHARS, _MAX_Q_CHARS = 12, 200

SYSTEM = "You write retrieval training questions. Return only JSON."
PROMPT_TMPL = """For EACH passage below (a verbatim excerpt from a spoken spiritual teaching), write
{n} short, natural questions a seeker might ask that this exact passage would answer.
Paraphrase -- do not copy the passage's wording. Return ONLY a JSON object mapping
each passage id to an array of exactly {n} question strings. No other text.

{passages}
"""


def build_prompt(batch: list[dict[str, Any]], n: int = QUESTIONS_PER_CLIP) -> str:
    body = "\n".join(f'ID: {c["point_id"]}\nTEXT: "{c["verbatim_text"]}"\n' for c in batch)
    return PROMPT_TMPL.format(n=n, passages=body)


def parse_llm_json(text: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", (text or "").strip(), re.S)
    if not m:
        return {}
    try:
        parsed = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def clean_questions(raw: Any, find_artifact: Callable[[str], Any]) -> list[str]:
    """Keep well-formed, artifact-free, de-duplicated questions ending in '?'."""
    if not isinstance(raw, list):
        return []
    out, seen = [], set()
    for q in raw:
        q = " ".join(str(q).split())
        key = q.lower()
        if (
            _MIN_Q_CHARS <= len(q) <= _MAX_Q_CHARS
            and q.endswith("?")
            and key not in seen
            and find_artifact(q) is None
        ):
            seen.add(key)
            out.append(q)
    return out[:QUESTIONS_PER_CLIP]


async def self_retrieves(
    question: str, owner_point_id: str, search: Callable[[str], Awaitable[list[str]]]
) -> bool:
    """doc2query--: keep a question only if it retrieves its own clip."""
    return owner_point_id in (await search(question))[:SELF_RETRIEVAL_TOP_K]


async def run(clips, llm_call, search, find_artifact, out_path: Path, concurrency: int = 4) -> dict[str, Any]:
    state = json.loads(out_path.read_text()) if out_path.exists() else {"raw": {}, "kept": {}}
    todo = [c for c in clips if c["point_id"] not in state["raw"]]
    sem = asyncio.Semaphore(concurrency)

    async def one_batch(batch):
        async with sem:
            try:
                parsed = parse_llm_json(await llm_call(build_prompt(batch)))
            except Exception as e:  # noqa: BLE001 -- a failed batch is retried on the next run
                print(f"  batch failed ({len(batch)} clips): {e}", flush=True)
                return
        for c in batch:
            qs = clean_questions(parsed.get(c["point_id"]), find_artifact)
            state["raw"][c["point_id"]] = qs
            state["kept"][c["point_id"]] = [q for q in qs if await self_retrieves(q, c["point_id"], search)]
        out_path.write_text(json.dumps(state, indent=1, ensure_ascii=False))  # checkpoint

    await asyncio.gather(*(one_batch(todo[i:i + BATCH]) for i in range(0, len(todo), BATCH)))
    n_raw = sum(len(v) for v in state["raw"].values())
    n_kept = sum(len(v) for v in state["kept"].values())
    state["summary"] = {
        "clips_attempted": len(state["raw"]),
        "raw_questions": n_raw,
        "kept_questions": n_kept,
        "keep_rate": round(n_kept / n_raw, 3) if n_raw else 0.0,
        "review_status": "UNREVIEWED -- human review required before any index build",
        "updated_at": dt.datetime.now(dt.UTC).isoformat(),
    }
    out_path.write_text(json.dumps(state, indent=1, ensure_ascii=False))
    return state["summary"]


def _load_clips(store, limit: int | None) -> list[dict[str, Any]]:
    clips, offset = [], None
    while True:
        points, offset = store.client.scroll(store.collection, limit=256, offset=offset, with_payload=True, with_vectors=False)
        clips += [{"point_id": str(p.id), "verbatim_text": (p.payload or {}).get("verbatim_text", "")} for p in points]
        if offset is None or (limit and len(clips) >= limit):
            return clips[:limit] if limit else clips


async def _amain(args) -> int:
    from app.config import settings
    from services.embedding_service import get_embedding_service
    from services.first_person_store import FirstPersonStore
    from services.llm_factory import LLMServiceFactory
    from services.text_quality_filter import find_artifact

    store = FirstPersonStore(collection=args.collection)
    llm = LLMServiceFactory.create(settings.llm_provider)
    embedder = get_embedding_service()

    async def llm_call(prompt: str) -> str:
        # ponytail: _generate_fast is the small classify model on every provider
        # (OpenRouter: llama-3.1-8b), same model genq.py used.
        return await llm._generate_fast(SYSTEM, prompt, max_tokens=900, temperature=0.4)

    async def search(q: str) -> list[str]:
        enc = await embedder.encode_single_full_async(q)
        sparse = enc.get("sparse") or {}
        hits = store.search_hybrid(
            enc["dense"],
            {"indices": list(sparse.keys()), "values": list(sparse.values())} if sparse else None,
            limit=SELF_RETRIEVAL_TOP_K * 4,
            dedup_limit=SELF_RETRIEVAL_TOP_K,
        )
        return [h["point_id"] for h in hits]

    clips = _load_clips(store, args.limit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    summary = await run(clips, llm_call, search, find_artifact, args.out)
    print(json.dumps(summary, indent=1), f"\n-> {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--collection", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=None)
    return asyncio.run(_amain(ap.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
