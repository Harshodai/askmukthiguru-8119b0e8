#!/usr/bin/env python3
"""
Quality probe v4: first-person retrieval → integrity → QuoteWeaver path,
with explicit answerability-gate modes.

Gate modes (--gate):
  off (default) — sets FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED=false and
      injects NO llm_service. Isolates the retrieval → integrity → QuoteWeaver
      path only. Result answerability MUST be None (gate did not run); any
      non-None value is a harness-contract failure. A gate-off run proves
      NOTHING about refusal behavior (binding L-FP-HYBRID-SCAFFOLD-1).
  on — leaves the gate enabled and injects a REAL llm_service (same selection
      chain as backend/evaluation/first_person_harness.py: OpenRouter with key,
      else the container ollama factory). If no service is available the probe
      FAILS (nonzero exit) instead of silently running gateless. Every direct
      answer MUST carry answerability in {yes, no, indeterminate}; None on a
      direct answer is a failure (gate claimed on but did not run).

LLM rerank stays disabled in both modes (FIRST_PERSON_LLM_RERANK_ENABLED=false)
to isolate the answerability leg as the single variable.

Exit status: 0 only if every query executes AND every answerability assertion
holds. Any exception, contract violation, or gate-on-without-LLM exits nonzero.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

QUERIES = [
    "What is the Beautiful State and how does it heal suffering?",
    "How can I overcome anxiety?",
    "What is the relationship between consciousness and suffering?",
    "What are the two states of being?",
    "How do I find inner peace?",
]

# PipelineResult.answerability contract (first_person_pipeline.py):
# 'yes' | 'no' | 'indeterminate' when the gate ran; None = gate did not run.
VALID_VERDICTS = {"yes", "no", "indeterminate"}


def _make_llm_service():
    """Prod-equivalent LLM service for the answerability gate.

    Mirrors backend/evaluation/first_person_harness.py::_make_llm_service:
    OpenRouterService() construction is lazy (reads settings, no network);
    fallback is the same factory the app container uses for ollama.
    Returns (service, name) or (None, None).
    """
    try:
        from services.openrouter_service import OpenRouterService

        svc = OpenRouterService()
        if getattr(svc, "_api_key", None):
            return svc, "openrouter"
        print("[probe] OpenRouter has no API key; trying ollama chain", file=sys.stderr)
    except Exception as e:
        print(f"[probe] OpenRouterService unavailable: {e}", file=sys.stderr)
    try:
        from app.container import _create_llm_service

        svc = _create_llm_service()
        if svc is not None and hasattr(svc, "generate"):
            return svc, "ollama"
    except Exception as e:
        print(f"[probe] ollama chain unavailable: {e}", file=sys.stderr)
    return None, None


def main():
    parser = argparse.ArgumentParser(description="First-person quality probe (v4).")
    parser.add_argument(
        "--gate",
        choices=("on", "off"),
        default="off",
        help="answerability gate mode: 'on' requires a real llm_service, "
        "'off' forces the gate disabled and asserts answerability is None.",
    )
    args = parser.parse_args()
    gate_on = args.gate == "on"

    if gate_on:
        # Ensure the flag is enabled before app.config settings materialize.
        os.environ["FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED"] = "true"
    else:
        # Disable answerability so we can see QuoteWeaver output without an LLM.
        # Gateless by explicit choice, recorded on every row — not production.
        os.environ["FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED"] = "false"
    # Disable LLM rerank (isolate the answerability leg as the single variable).
    os.environ["FIRST_PERSON_LLM_RERANK_ENABLED"] = "false"

    from app.config import settings
    from services.embedding_service import get_embedding_service
    from services.first_person_pipeline import FirstPersonPipeline
    from services.first_person_store import FirstPersonStore

    llm_service, llm_name = None, None
    if gate_on:
        llm_service, llm_name = _make_llm_service()
        if llm_service is None:
            print(
                "[probe] FAIL: --gate on requires a real llm_service "
                "(OpenRouter key or ollama chain) and none is available. "
                "Refusing to run gateless.",
                file=sys.stderr,
            )
            sys.exit(2)

    print("=" * 80)
    print(f"QUALITY PROBE v4 — First-Person Pipeline (gate {args.gate.upper()})")
    print("=" * 80)
    print(f"  Collection:        {settings.first_person_collection}")
    print(f"  Mode:              {settings.first_person_mode}")
    print(f"  Uncalib Direct:    {settings.first_person_uncalibrated_direct_enabled}")
    print(f"  Answerability:     {settings.first_person_answerability_check_enabled}")
    print(f"  LLM service:       {llm_name or 'none (gate off)'}")
    print(f"  LLM Rerank:        {settings.first_person_llm_rerank_enabled}")
    print("  Boundary Guard:    auto-enabled for v7")
    if not gate_on:
        print("  NOTE: gate OFF — this run proves nothing about refusal behavior.")
    print()

    store = FirstPersonStore()
    embed_svc = get_embedding_service()

    pipeline = FirstPersonPipeline(store=store, llm_service=llm_service)
    print(f"  Profile loaded:    {pipeline._profile is not None}")
    if pipeline._profile:
        print(f"  Threshold:         {pipeline._profile.get('threshold')}")
    print(f"  Boundary guard:    {pipeline._boundary_guard_enabled}")
    print(f"  Content quality:   {pipeline._content_quality_gate_enabled}")
    print("=" * 80)

    failed_queries: list[str] = []
    verdict_counts: dict[str, int] = {}
    for i, query in enumerate(QUERIES, 1):
        print(f"\n{'=' * 80}")
        print(f"QUERY {i}: {query}")
        print(f"{'=' * 80}")
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
            ans = result.answerability  # 'yes'|'no'|'indeterminate'|None
            verdict_counts[str(ans)] = verdict_counts.get(str(ans), 0) + 1
            print(f"  Status:         {result.status}")
            print(f"  is_direct:      {result.is_direct_answer}")
            print(f"  answerability:  {ans}")
            print(f"  Total time:     {total_time:.0f}ms")
            print(f"  Citations:      {len(result.citations)}")
            if result.citations:
                for ci, c in enumerate(result.citations):
                    vid = c.get("video_id", "?")
                    ts = c.get("timestamp_seconds", "?")
                    spk = c.get("speaker", "?")
                    url = c.get("url") or f"https://youtube.com/watch?v={vid}&t={ts}s"
                    print(f"    [{ci + 1}] {spk} — {vid} @ {ts}s")
                    print(f"        {url}")

            # Answerability-field assertions (the gate contract).
            if gate_on:
                if result.is_direct_answer and ans not in VALID_VERDICTS:
                    print(
                        f"  ASSERT FAIL: gate ON + direct answer but "
                        f"answerability={ans!r} (expected one of {sorted(VALID_VERDICTS)})"
                    )
                    failed_queries.append(query + " [answerability not run]")
                # Non-direct answers legitimately skip the gate (pipeline only
                # gates direct candidates); record as not_run, not a failure.
            else:
                if ans is not None:
                    print(
                        f"  ASSERT FAIL: gate OFF but answerability={ans!r} "
                        f"(expected None — gate leaked on)"
                    )
                    failed_queries.append(query + " [gate leaked on]")

            print("\n  --- ANSWER TEXT ---")
            answer = result.answer_text or "(empty)"
            for line in answer.split("\n"):
                print(f"  {line}")
            print(f"  --- END ({len(answer)} chars) ---")
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            print(f"  ERROR ({elapsed:.0f}ms): {e}")
            import traceback

            traceback.print_exc()
            failed_queries.append(query)

    print(f"\n{'=' * 80}")
    print(f"  Answerability distribution: {verdict_counts} (gate {args.gate})")
    if gate_on and verdict_counts.get("indeterminate", 0) == len(QUERIES):
        print(
            "  WARNING: every verdict indeterminate (no LLM verdicts) — "
            "this run proves nothing about refusal behavior."
        )
    if not gate_on:
        print("  NOTE: gate-off run — refusal behavior unmeasured by design.")

    if failed_queries:
        print(f"\n{len(failed_queries)}/{len(QUERIES)} queries failed:")
        for query in failed_queries:
            print(f"  - {query}")
        sys.exit(1)


if __name__ == "__main__":
    main()
