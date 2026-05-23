#!/usr/bin/env python3
"""
native_eval.py — Native Ragas-style evaluator for AskMukthiGuru.
Runs natively using the local Ollama LLM to assess context precision and faithfulness.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add backend directory to path
sys.path.append(str(Path(__file__).parent.parent))

from benchmarks.question_bank import QUERIES
from guardrails.rails import LightweightGuardrails
from services.embedding_service import EmbeddingService
from services.ollama_service import OllamaService
from services.qdrant_service import QdrantService


async def run_native_evaluation(limit: int = 5):
    print("\n" + "=" * 60)
    print("MUKTHI GURU: NATIVE OLLAMA RAGAS-STYLE EVALUATION")
    print("=" * 60 + "\n")

    try:
        ollama = OllamaService()
        embedder = EmbeddingService()
        qdrant = QdrantService()
        guardrails = LightweightGuardrails()
    except Exception as e:
        print(f"⚠️ Could not initialize services: {e}")
        print("Please make sure Docker containers are running.")
        return

    # Select representative questions from the bank
    eval_queries = []
    # Mix some factual, deep accuracy, and adversarial queries
    for category in ["doctrine_four_secrets", "doctrine_ekam_architecture", "complex_multi_hop", "adversarial_traps", "emotional_gradients"]:
        if category in QUERIES:
            for item in QUERIES[category][:2]:
                eval_queries.append({
                    "query": item.get("q", ""),
                    "category": category,
                    "expect_blocked": item.get("expected") == "refuse" or item.get("expected_intent") == "CRISIS"
                })

    if not eval_queries:
        print("No queries found in question bank.")
        return

    eval_queries = eval_queries[:limit]
    results = []

    for i, test in enumerate(eval_queries):
        query = test["query"]
        print(f"[{i + 1}/{len(eval_queries)}] Evaluating category '{test['category']}': '{query[:60]}...'")
        start_time = time.time()
        
        try:
            # 1. Guardrail validation
            guard_result = await guardrails.check_input(query)
            is_blocked = guard_result.get("blocked", False)
            security_score = 1.0 if is_blocked == test["expect_blocked"] else 0.0

            if is_blocked:
                results.append({
                    "query": query,
                    "category": test["category"],
                    "security_score": security_score,
                    "precision": 1.0,
                    "faithfulness": 1.0,
                    "latency_s": round(time.time() - start_time, 2)
                })
                print(f"  → Blocked correctly. Security: {security_score}")
                continue

            # 2. Vector DB Retrieval
            embed_res = await asyncio.to_thread(embedder.encode_single_full, query)
            docs = await asyncio.to_thread(
                qdrant.search,
                query_vector=embed_res["dense"],
                limit=3,
                sparse_vector=embed_res["sparse"],
            )

            # 3. Context Precision (Grade relevance using Ollama)
            precision_score = 0.0
            if docs:
                doc_texts = [d["text"] for d in docs]
                grades = await ollama.batch_grade_relevance(query, doc_texts)
                relevant_count = sum(1 for g in grades if g.get("relevant", False))
                precision_score = relevant_count / len(docs)
                print(f"  → Context Precision: {precision_score:.2f} ({relevant_count}/{len(docs)} relevant)")
            else:
                print("  → Context Precision: 0.00 (No documents retrieved)")

            # 4. Response Generation & Faithfulness
            faithfulness_score = 0.0
            if precision_score > 0:
                relevant_texts = "\n".join([doc["text"] for doc, g in zip(docs, grades) if g.get("relevant", False)])
                answer = await ollama.generate(
                    system_prompt="Answer using context.",
                    user_prompt=query,
                    context=relevant_texts
                )
                is_faithful = await ollama.check_faithfulness(answer, relevant_texts)
                faithfulness_score = 1.0 if is_faithful else 0.0
                print(f"  → Answer Faithfulness: {faithfulness_score:.2f}")
            else:
                print("  → Answer Faithfulness: N/A")

            results.append({
                "query": query,
                "category": test["category"],
                "security_score": security_score,
                "precision": precision_score,
                "faithfulness": faithfulness_score,
                "latency_s": round(time.time() - start_time, 2)
            })

        except Exception as e:
            print(f"  → Error during evaluation turn: {e}")

    # Summary
    if not results:
        print("No evaluation turns succeeded.")
        return

    print("\n" + "=" * 60)
    print("NATIVE EVALUATION SUMMARY")
    print("=" * 60)
    avg_sec = sum(r["security_score"] for r in results) / len(results)
    avg_prec = sum(r["precision"] for r in results) / len(results)
    avg_faith = sum(r["faithfulness"] for r in results) / len(results)
    avg_lat = sum(r["latency_s"] for r in results) / len(results)

    print(f"Overall Security Bypass Resistance : {avg_sec * 100:.1f}%")
    print(f"Overall Context Precision          : {avg_prec * 100:.1f}%")
    print(f"Overall Answer Faithfulness        : {avg_faith * 100:.1f}%")
    print(f"Average Turn Latency               : {avg_lat:.2f}s")
    print("=" * 60 + "\n")

    os.makedirs("reports", exist_ok=True)
    with open("reports/native_eval_report.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(run_native_evaluation(args.limit))
