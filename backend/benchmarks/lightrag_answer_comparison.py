#!/usr/bin/env python3
"""LightRAG vs Qdrant: Full Answer Quality Comparison.

For each spiritual/doctrine query:
  1. Retrieve docs WITH LightRAG → generate answer_A
  2. Retrieve docs WITHOUT LightRAG → generate answer_B
  3. Compare: length, citations, concept coverage, spiritual quality

Usage:
  cd backend && python -m benchmarks.lightrag_answer_comparison
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

from benchmarks.question_bank import QUERIES

SAMPLE_SIZE = int(os.getenv("LR_ANSWER_SAMPLE", "12"))
MAX_CONCURRENT = 2

DOCTRINE_CATEGORIES = [
    "doctrine_four_secrets",
    "doctrine_founders",
    "doctrine_manifest",
    "doctrine_deeksha",
    "doctrine_soul_sync",
    "doctrine_ekam_architecture",
    "doctrine_practices",
]


@dataclass
class AnswerComparison:
    query: str
    category: str
    must_mention: list[str] = field(default_factory=list)
    with_lightrag_answer: str = ""
    without_lightrag_answer: str = ""
    with_lightrag_latency_ms: float = 0.0
    without_lightrag_latency_ms: float = 0.0
    with_lightrag_doc_count: int = 0
    without_lightrag_doc_count: int = 0
    with_lightrag_citations: int = 0
    without_lightrag_citations: int = 0
    with_lightrag_concept_coverage: float = 0.0
    without_lightrag_concept_coverage: float = 0.0
    with_lightrag_word_count: int = 0
    without_lightrag_word_count: int = 0
    judge_verdict: str = ""  # "lightrag_better", "qdrant_better", "tie"
    judge_reasoning: str = ""
    error: str | None = None


@dataclass
class Report:
    total: int = 0
    lightrag_wins: int = 0
    qdrant_wins: int = 0
    ties: int = 0
    errors: int = 0
    samples: list[AnswerComparison] = field(default_factory=list)


def _count_citations(text: str) -> int:
    return text.count("【") if "【" in text else 0


def _concept_coverage(answer: str, concepts: list[str]) -> float:
    if not concepts:
        return 1.0
    a = answer.lower()
    hits = sum(1 for c in concepts if c.lower() in a)
    return hits / len(concepts)


JUDGE_SYSTEM_PROMPT = """You are a senior spiritual teacher evaluating two answers to a question about the teachings of Sri Preethaji and Sri Krishnaji. Your role is to determine which answer better serves a spiritual seeker.

Evaluate on these criteria (weighted):
1. **Doctrinal accuracy** (40%): Which answer is more faithful to the actual teachings? Look for correct terminology, no hallucinated concepts.
2. **Spiritual depth** (30%): Which answer provides deeper insight and practical wisdom, not just facts?
3. **Completeness** (20%): Which answer covers more relevant aspects of the teaching?
4. **Clarity** (10%): Which answer is clearer and more accessible to a seeker?

Respond with a JSON object:
{"verdict": "lightrag_better" | "qdrant_better" | "tie", "reasoning": "brief explanation"}
"""


async def _judge_answers(llm_service, query: str, answer_a: str, answer_b: str) -> dict:
    prompt = f"""Question: {query}

Answer with LightRAG:
{answer_a[:2000]}

Answer without LightRAG:
{answer_b[:2000]}

Which answer better reflects the spiritual teachings of Sri Preethaji and Sri Krishnaji? Respond with the JSON verdict only."""
    try:
        result = await llm_service.generate(JUDGE_SYSTEM_PROMPT, prompt)
        text = result if isinstance(result, str) else result.get("text", "")
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception:
        pass
    return {"verdict": "tie", "reasoning": "judge failed"}


def _format_context(docs: list[dict]) -> str:
    parts = []
    for d in docs:
        content = d.get("content", d.get("text", ""))
        doc_id = d.get("id", d.get("doc_id", "?"))
        source = d.get("source", d.get("metadata", {}).get("source", "unknown"))
        parts.append(f"[Doc {doc_id}] (source: {source})\n{content[:800]}")
    return "\n\n".join(parts)


async def compare_single_query(
    query_text: str,
    category: str,
    must_mention: list[str],
    *,
    embedder,
    qdrant,
    lightrag,
    llm_service,
) -> AnswerComparison:
    from rag.nodes.retrieval import retrieve_for_single_query

    comp = AnswerComparison(query=query_text, category=category, must_mention=must_mention)

    async def _run(lightrag_enabled: bool) -> tuple[list[dict], str, float]:
        start = time.perf_counter()
        docs = await retrieve_for_single_query(
            query=query_text,
            chat_history=[],
            hyde_text=None,
            intent="QUERY",
            selected_clusters=[],
            embedder=embedder,
            qdrant=qdrant,
            lightrag=lightrag if lightrag_enabled else None,
        )
        elapsed = (time.perf_counter() - start) * 1000
        return docs, _format_context(docs), elapsed

    try:
        with_docs, with_ctx, with_time = await _run(lightrag_enabled=True)
        without_docs, without_ctx, without_time = await _run(lightrag_enabled=False)

        comp.with_lightrag_doc_count = len(with_docs)
        comp.without_lightrag_doc_count = len(without_docs)
        comp.with_lightrag_latency_ms = round(with_time, 2)
        comp.without_lightrag_latency_ms = round(without_time, 2)

        GEN_SYSTEM = "You are a spiritual guide rooted in the teachings of Sri Preethaji and Sri Krishnaji. Answer the seeker's question clearly and compassionately using only the context provided."
        gen_prompt = f"Context:\n{with_ctx}\n\nQuestion: {query_text}"

        r_a = await llm_service.generate(GEN_SYSTEM, gen_prompt)
        comp.with_lightrag_answer = r_a if isinstance(r_a, str) else r_a.get("text", "")
        comp.with_lightrag_word_count = len(comp.with_lightrag_answer.split())
        comp.with_lightrag_citations = _count_citations(comp.with_lightrag_answer)
        comp.with_lightrag_concept_coverage = _concept_coverage(comp.with_lightrag_answer, must_mention)

        gen_prompt = f"Context:\n{without_ctx}\n\nQuestion: {query_text}"
        r_b = await llm_service.generate(GEN_SYSTEM, gen_prompt)
        comp.without_lightrag_answer = r_b if isinstance(r_b, str) else r_b.get("text", "")
        comp.without_lightrag_word_count = len(comp.without_lightrag_answer.split())
        comp.without_lightrag_citations = _count_citations(comp.without_lightrag_answer)
        comp.without_lightrag_concept_coverage = _concept_coverage(comp.without_lightrag_answer, must_mention)

        judge = await _judge_answers(llm_service, query_text, comp.with_lightrag_answer, comp.without_lightrag_answer)
        comp.judge_verdict = judge.get("verdict", "tie")
        comp.judge_reasoning = judge.get("reasoning", "")

    except Exception as exc:
        comp.error = f"{type(exc).__name__}: {exc}"

    return comp


async def run_comparison():
    from app.dependencies import get_container
    from services.embedding_service import EmbeddingService
    from services.lightrag_service import LightRAGService
    from services.qdrant_service import QdrantService

    container = get_container()
    embedder: EmbeddingService = container.embedding
    qdrant: QdrantService = container.qdrant
    lightrag: LightRAGService = getattr(container, "lightrag", None)
    llm_service = container.ollama or container.sarvam_cloud

    if not lightrag:
        print("WARNING: LightRAG service not available. Results will show no difference.")

    test_cases: list[tuple[str, str, list[str]]] = []
    for cat in DOCTRINE_CATEGORIES:
        items = QUERIES.get(cat, [])
        for item in items:
            if isinstance(item, dict):
                qtext = item.get("query") or item.get("q")
                if qtext:
                    test_cases.append((qtext, cat, item.get("must_mention", [])))

    import random
    random.seed(42)
    test_cases = test_cases[:min(SAMPLE_SIZE, len(test_cases))]

    print(f"\n{'='*70}")
    print(f"LIGHTRAG vs QDRANT: ANSWER QUALITY COMPARISON")
    print(f"{'='*70}")
    print(f"  Queries: {len(test_cases)} (doctrine categories)")
    print(f"  LightRAG: {'YES' if lightrag else 'N/A'}")
    print(f"  LLM: {type(llm_service).__name__}")
    print()

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    results: list[AnswerComparison] = []

    async def _bounded(qtext: str, cat: str, mm: list[str]):
        async with semaphore:
            return await compare_single_query(
                qtext, cat, mm, embedder=embedder, qdrant=qdrant, lightrag=lightrag, llm_service=llm_service
            )

    tasks = [_bounded(q, c, m) for q, c, m in test_cases]
    for coro in asyncio.as_completed(tasks):
        comp = await coro
        results.append(comp)

        if comp.error:
            status = "❌"
        elif comp.judge_verdict == "lightrag_better":
            status = "✨"
        elif comp.judge_verdict == "qdrant_better":
            status = "📖"
        else:
            status = "➖"

        print(f"  [{status}] {comp.query[:55]:<55}  LR+{comp.with_lightrag_doc_count - comp.without_lightrag_doc_count:+d} docs  {comp.judge_verdict}")

    report = Report()
    report.total = len(results)
    for r in results:
        if r.error:
            report.errors += 1
        elif r.judge_verdict == "lightrag_better":
            report.lightrag_wins += 1
        elif r.judge_verdict == "qdrant_better":
            report.qdrant_wins += 1
        else:
            report.ties += 1
    report.samples = results

    print(f"\n{'='*70}")
    print(f"ANSWER QUALITY SUMMARY")
    print(f"{'='*70}")
    print(f"  Total queries        : {report.total}")
    print(f"  Errors               : {report.errors}")
    print(f"  LightRAG better       : {report.lightrag_wins}")
    print(f"  Qdrant-only better    : {report.qdrant_wins}")
    print(f"  Tie                   : {report.ties}")

    print(f"\n{'='*70}")
    print(f"DETAILED COMPARISON")
    print(f"{'='*70}")
    for s in results:
        if s.error:
            print(f"\n--- ❌ {s.query} ---")
            print(f"  ERROR: {s.error}")
            continue

        verdict_icon = {"lightrag_better": "✨", "qdrant_better": "📖", "tie": "➖"}
        print(f"\n--- {verdict_icon.get(s.judge_verdict, '?')} {s.query} ---")
        print(f"  Category: {s.category}")
        print(f"  Latency:     LR={s.with_lightrag_latency_ms:.0f}ms  Qdrant={s.without_lightrag_latency_ms:.0f}ms  Δ={s.with_lightrag_latency_ms - s.without_lightrag_latency_ms:+.0f}ms")
        print(f"  Docs:        LR={s.with_lightrag_doc_count}  Qdrant={s.without_lightrag_doc_count}")
        print(f"  Words:       LR={s.with_lightrag_word_count}  Qdrant={s.without_lightrag_word_count}")
        print(f"  Citations:   LR={s.with_lightrag_citations}  Qdrant={s.without_lightrag_citations}")
        print(f"  Concepts:    LR={s.with_lightrag_concept_coverage:.0%}  Qdrant={s.without_lightrag_concept_coverage:.0%}")
        print(f"  Verdict:     {s.judge_verdict}")
        if s.judge_reasoning:
            print(f"  Reasoning:   {s.judge_reasoning}")
        print(f"\n  --- LR Answer (first 300 chars) ---")
        print(f"  {s.with_lightrag_answer[:300]}")
        print(f"\n  --- Qdrant Answer (first 300 chars) ---")
        print(f"  {s.without_lightrag_answer[:300]}")

    report_path = Path("benchmarks/reports/lightrag_answer_comparison.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    def _serialize(o):
        if hasattr(o, '__dict__'):
            return asdict(o)
        return str(o)

    report_path.write_text(json.dumps(asdict(report), indent=2, default=str), encoding="utf-8")
    print(f"\nFull report saved to: {report_path}")


if __name__ == "__main__":
    asyncio.run(run_comparison())
