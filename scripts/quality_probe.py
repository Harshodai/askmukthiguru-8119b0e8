#!/usr/bin/env python3
"""
Quality probe v3: bypass answerability to see QuoteWeaver output quality.
The answerability gate needs an LLM service, which the full backend provides.
This probe disables it to isolate the retrieval → integrity → QuoteWeaver path.
"""
import sys, os, json, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Disable answerability so we can see QuoteWeaver output without needing LLM
os.environ["FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED"] = "false"
# Disable LLM rerank (no LLM in probe)
os.environ["FIRST_PERSON_LLM_RERANK_ENABLED"] = "false"

QUERIES = [
    "What is the Beautiful State and how does it heal suffering?",
    "How can I overcome anxiety?",
    "What is the relationship between consciousness and suffering?",
    "What are the two states of being?",
    "How do I find inner peace?",
]

def main():
    from services.first_person_pipeline import FirstPersonPipeline, load_calibration_profile
    from services.first_person_store import FirstPersonStore
    from services.embedding_service import get_embedding_service
    from app.config import settings

    print("=" * 80)
    print("QUALITY PROBE v3 — First-Person Pipeline (answerability OFF for probing)")
    print("=" * 80)
    print(f"  Collection:        {settings.first_person_collection}")
    print(f"  Mode:              {settings.first_person_mode}")
    print(f"  Uncalib Direct:    {settings.first_person_uncalibrated_direct_enabled}")
    print(f"  Answerability:     {settings.first_person_answerability_check_enabled}")
    print(f"  LLM Rerank:        {settings.first_person_llm_rerank_enabled}")
    print(f"  Boundary Guard:    auto-enabled for v7")
    print()

    store = FirstPersonStore()
    embed_svc = get_embedding_service()

    pipeline = FirstPersonPipeline(store=store)
    print(f"  Profile loaded:    {pipeline._profile is not None}")
    if pipeline._profile:
        print(f"  Threshold:         {pipeline._profile.get('threshold')}")
    print(f"  Boundary guard:    {pipeline._boundary_guard_enabled}")
    print(f"  Content quality:   {pipeline._content_quality_gate_enabled}")
    print("=" * 80)

    failed_queries: list[str] = []
    for i, query in enumerate(QUERIES, 1):
        print(f"\n{'='*80}")
        print(f"QUERY {i}: {query}")
        print(f"{'='*80}")
        t0 = time.monotonic()
        try:
            embed_result = embed_svc.encode_batch([query])
            query_dense = embed_result["dense"][0] if embed_result["dense"] else []
            query_sparse = embed_result["sparse"][0] if embed_result.get("sparse") else None

            result = pipeline.execute(
                query=query,
                query_dense_vector=query_dense,
                query_sparse_vector=query_sparse,
            )
            total_time = (time.monotonic() - t0) * 1000
            print(f"  Status:         {result.status}")
            print(f"  is_direct:      {result.is_direct_answer}")
            print(f"  Total time:     {total_time:.0f}ms")
            print(f"  Citations:      {len(result.citations)}")
            if result.citations:
                for ci, c in enumerate(result.citations):
                    vid = c.get('video_id', '?')
                    ts = c.get('timestamp_seconds', '?')
                    spk = c.get('speaker', '?')
                    url = c.get('url') or f"https://youtube.com/watch?v={vid}&t={ts}s"
                    print(f"    [{ci+1}] {spk} — {vid} @ {ts}s")
                    print(f"        {url}")
            print(f"\n  --- ANSWER TEXT ---")
            answer = result.answer_text or "(empty)"
            for line in answer.split('\n'):
                print(f"  {line}")
            print(f"  --- END ({len(answer)} chars) ---")
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            print(f"  ERROR ({elapsed:.0f}ms): {e}")
            import traceback
            traceback.print_exc()
            failed_queries.append(query)

    if failed_queries:
        print(f"\n{len(failed_queries)}/{len(QUERIES)} queries failed:")
        for query in failed_queries:
            print(f"  - {query}")
        sys.exit(1)

if __name__ == "__main__":
    main()
