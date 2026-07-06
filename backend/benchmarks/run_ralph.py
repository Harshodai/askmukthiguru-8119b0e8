#!/usr/bin/env python3
"""
run_ralph.py — Batch CLI runner for the Ralph Loop (Teacher-Student prompt optimization).
"""

import asyncio
import sys
import json
import os
from pathlib import Path
from datetime import datetime, timezone

# Add backend directory to path
sys.path.append(str(Path(__file__).parent.parent))

from app.config import settings
from app.dependencies import get_container
from app.constants import FEEDBACK_LESSONS_FILE_PATH, PROMPT_PATCHES_VALIDATED_FILE_PATH
from app.core.refiner import mine_failed_session


async def run_batch_ralph():
    print("\n" + "=" * 60)
    print("MUKTHI GURU: RALPH PROMPT OPTIMIZATION SWEEP")
    print("=" * 60 + "\n")

    # Initialize DI Container
    try:
        # Require container builder to build singletons
        from app.dependencies import ServiceContainer
        container = get_container()
        print("✅ Service container initialized successfully.")
    except Exception as e:
        print(f"❌ Container initialization failed: {e}")
        sys.path.append(str(Path(__file__).parent.parent.parent))
        sys.exit(1)

    # 1. Read unvalidated failure lessons
    lessons = []
    if os.path.exists(FEEDBACK_LESSONS_FILE_PATH):
        try:
            with open(FEEDBACK_LESSONS_FILE_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if line_str:
                        try:
                            lessons.append(json.loads(line_str))
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            print(f"❌ Failed to read lessons file: {e}")
            sys.exit(1)

    if not lessons:
        print(f"ℹ️ No failure lessons found in {FEEDBACK_LESSONS_FILE_PATH}.")
        print("Generating a test failure lesson to verify the validation loop...")
        lessons = [
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "query": "Who is Lokaa's daughter?",
                "category": "hallucination",
                "analysis": "LLM claimed Lokaa has a daughter, violating Lokaa Rule.",
                "suggested_correction": "LOKAA RULE: Lokaa is the daughter OF Sri Krishnaji and Sri Preethaji. Do NOT state that Lokaa herself has a daughter — there is no such teaching. If asked about 'Lokaa's daughter', clarify this relationship.",
                "comment": "Self-harassment / incorrect family relationship",
            }
        ]

    # 2. Load already validated patches to prevent double-work
    validated_queries = set()
    if os.path.exists(PROMPT_PATCHES_VALIDATED_FILE_PATH):
        try:
            with open(PROMPT_PATCHES_VALIDATED_FILE_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if line_str:
                        try:
                            entry = json.loads(line_str)
                            validated_queries.add(entry.get("query"))
                        except json.JSONDecodeError:
                            continue
        except Exception:
            pass

    print(f"Loaded {len(lessons)} total failures. {len(validated_queries)} patches already validated.\n")

    unvalidated_count = 0
    validated_new = 0

    for idx, lesson in enumerate(lessons):
        query = lesson.get("query")
        suggested_correction = lesson.get("suggested_correction")
        
        if not query or not suggested_correction or suggested_correction in ("None", "N/A"):
            continue

        if query in validated_queries:
            continue

        unvalidated_count += 1
        print(f"[{unvalidated_count}] Processing failure: \"{query}\"")
        print(f"    Suggested correction: \"{suggested_correction}\"")

        # 3. Retrieve context from Qdrant
        try:
            query_embedding = container.embedding.embed_query(query)
            docs = container.qdrant.search(
                query_vector=query_embedding,
                limit=5,
                query=query
            )
            retrieved_context = "\n\n".join(d["text"] for d in docs)
            print(f"    Retrieved {len(docs)} document chunks from Qdrant.")
        except Exception as e:
            print(f"    ⚠️ Qdrant retrieval failed ({e}). Falling back to empty context.")
            retrieved_context = "No context available."

        # 4. Trigger validation run
        print("    Running Student validation...")
        
        try:
            result = await mine_failed_session(
                query=query,
                retrieved_context=retrieved_context,
                answer="Original failed response place-holder",
                comment=lesson.get("comment")
            )
            
            if result.get("validated"):
                validated_new += 1
                print(f"    ✅ Student validation PASSED (score={result.get('student_score')})")
            else:
                print(f"    ❌ Student validation FAILED (score={result.get('student_score')})")
        except Exception as exc:
            print(f"    ❌ Execution crashed: {exc}")
        print("-" * 60)

    print(f"\n🎉 Ralph Loop finished. New validated patches: {validated_new}/{unvalidated_count}")


if __name__ == "__main__":
    asyncio.run(run_batch_ralph())
