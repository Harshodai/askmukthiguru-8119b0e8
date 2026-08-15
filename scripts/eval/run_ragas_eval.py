#!/usr/bin/env python3
"""Standalone RAGAS evaluation runner — no pytest required.

Connects to the live backend to fetch chat completions, evaluates them with
RAGAS metrics (faithfulness, answer_relevancy, context_precision), and writes
a timestamped JSON report to scripts/eval/reports/.

Usage:
    # From repo root (local backend)
    cd backend && python ../scripts/eval/run_ragas_eval.py

    # Against a remote backend over HTTPS (TEST_KEY is ignored unless the host
    # is allowlisted via RAGAS_TEST_KEY_ALLOWED_HOSTS)
    RAGAS_LLM_API_KEY=sk-... \
    BACKEND_URL=https://mukthi.up.railway.app \
    SUPABASE_JWT=<jwt> \
    python scripts/eval/run_ragas_eval.py --output reports/eval_$(date +%Y%m%d).json

    # CI usage (fails if mean_faithfulness < 0.6)
    python scripts/eval/run_ragas_eval.py --ci --threshold 0.6

Environment variables:
    BACKEND_URL     Base URL (default: http://localhost:8000)
    TEST_KEY        X-Test-Key for benchmark auth bypass (local hosts, or HTTPS
                    hosts allowlisted via RAGAS_TEST_KEY_ALLOWED_HOSTS)
    RAGAS_TEST_KEY_ALLOWED_HOSTS  Comma-separated HTTPS hostnames allowed to
                    receive X-Test-Key (default: empty — remote hosts get
                    SUPABASE_JWT instead)
    SUPABASE_JWT    Full JWT token (alternative to TEST_KEY for production)
    RAGAS_LLM_API_KEY   Key for the RAGAS LLM/embedding provider (defaults to
                    OPENAI_API_KEY)
    RAGAS_LLM_MODEL     LLM model for metric scoring (default: gpt-4o-mini)
    RAGAS_EMBEDDINGS_MODEL  Embeddings model for metric scoring
                    (default: text-embedding-3-small)

    Privacy note: evaluation sends the collected chat answers and retrieved
    contexts to the configured LLM/embedding provider (e.g. OpenAI) for metric
    computation.

Requires:
    pip install ragas langchain-openai httpx rich
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger("ragas_eval")

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
TEST_KEY = os.environ.get("TEST_KEY", "")
SUPABASE_JWT = os.environ.get("SUPABASE_JWT", "")
# Remote HTTPS hosts allowed to receive the X-Test-Key benchmark bypass.
# Default empty: remote hosts always use SUPABASE_JWT instead.
ALLOWED_TEST_KEY_HOSTS = {
    h.strip().lower()
    for h in os.environ.get("RAGAS_TEST_KEY_ALLOWED_HOSTS", "").split(",")
    if h.strip()
}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
RAGAS_LLM_API_KEY = os.environ.get("RAGAS_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
RAGAS_LLM_MODEL = os.environ.get("RAGAS_LLM_MODEL", "gpt-4o-mini")
RAGAS_EMBEDDINGS_MODEL = os.environ.get("RAGAS_EMBEDDINGS_MODEL", "text-embedding-3-small")

# Golden evaluation set — 5 queries with ground truth answers.
# Add new queries here to expand the eval set; do NOT change existing ground
# truth without a corresponding review because baselines will diverge.
GOLDEN_SET = [
    {
        "id": "gs-01",
        "question": "What is Beautiful State according to Sri Preethaji?",
        "ground_truth": (
            "Beautiful State is a state of consciousness free from suffering, where one experiences "
            "profound stillness, joy, and connectedness. Sri Preethaji describes it as humanity's "
            "natural birthright — the inner space from which compassionate action flows."
        ),
    },
    {
        "id": "gs-02",
        "question": "How does one connect with universal intelligence through meditation?",
        "ground_truth": (
            "Sri Krishnaji teaches that connecting with universal intelligence requires moving beyond "
            "thought-based consciousness into a state of pure awareness. Specific practices include "
            "the Ekam meditation, focused attention on the space between thoughts, and cultivating a "
            "receptive stillness rather than effortful concentration."
        ),
    },
    {
        "id": "gs-03",
        "question": "What is the role of suffering in spiritual awakening?",
        "ground_truth": (
            "In the Ekam teachings, suffering is understood as arising from identification with the "
            "egoic mind and its patterns of separation. Awakening does not require suffering — instead, "
            "meeting suffering with awareness rather than resistance transforms it into a gateway to "
            "deeper consciousness."
        ),
    },
    {
        "id": "gs-04",
        "question": "Explain the practice of stillness as taught by Ekam.",
        "ground_truth": (
            "Ekam's stillness practice involves settling awareness into the present moment without "
            "mental labeling. It begins with physical relaxation, then releasing effort in breath, "
            "then resting attention in the natural silence beneath thought. This is not suppression "
            "of thought but a shift of identity from thinker to awareness itself."
        ),
    },
    {
        "id": "gs-05",
        "question": "What is inner peace consciousness awareness?",
        "ground_truth": (
            "Inner peace consciousness is described as a state of awareness that is not dependent on "
            "external conditions. It is the recognition of one's true nature as pure consciousness — "
            "prior to thought, judgment, or circumstance — and is cultivated through consistent "
            "contemplative practice and guidance from an awakened teacher."
        ),
    },
]


async def query_backend(question: str) -> dict:
    """POST to /api/chat and return the full response JSON."""
    try:
        import httpx
    except ImportError:
        logger.error("httpx not installed. pip install httpx")
        sys.exit(1)

    headers: dict[str, str] = {"Content-Type": "application/json"}
    # X-Test-Key is a benchmark auth bypass and must never reach production:
    # send it only for local hosts, or remote HTTPS hosts explicitly
    # allowlisted via RAGAS_TEST_KEY_ALLOWED_HOSTS (default empty).
    parsed = urlsplit(BACKEND_URL)
    host = (parsed.hostname or "").lower()
    test_key_allowed = host in LOCAL_HOSTS or (
        parsed.scheme == "https" and host in ALLOWED_TEST_KEY_HOSTS
    )
    if test_key_allowed and TEST_KEY:
        headers["X-Test-Key"] = TEST_KEY
    elif SUPABASE_JWT:
        # Never send a JWT over plaintext HTTP to a remote host — it would be
        # readable in transit. https or a loopback host only.
        if parsed.scheme == "https" or host in LOCAL_HOSTS:
            headers["Authorization"] = f"Bearer {SUPABASE_JWT}"
        else:
            logger.error(
                "Refusing to send SUPABASE_JWT over plaintext HTTP to %r — "
                "use https, a local host, or set TEST_KEY",
                f"{parsed.scheme}://{host}",
            )
            sys.exit(1)
    else:
        logger.warning("No auth configured — request may be rejected. Set TEST_KEY or SUPABASE_JWT.")

    payload = {
        "messages": [],
        "user_message": question,
        "session_id": f"eval_{uuid.uuid4().hex}",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{BACKEND_URL}/api/chat", json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


def evaluate_with_ragas(samples: list[dict]) -> dict:
    """Run RAGAS evaluation on collected samples."""
    try:
        from datasets import Dataset
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        from ragas import evaluate
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import answer_relevancy, context_precision, faithfulness
    except ImportError:
        logger.error(
            "RAGAS / datasets not installed. pip install ragas datasets langchain-openai"
        )
        sys.exit(1)

    if not RAGAS_LLM_API_KEY:
        logger.error(
            "Missing API key for RAGAS evaluation. Set RAGAS_LLM_API_KEY "
            "(or OPENAI_API_KEY)."
        )
        sys.exit(1)

    llm = LangchainLLMWrapper(ChatOpenAI(model=RAGAS_LLM_MODEL, api_key=RAGAS_LLM_API_KEY))
    embeddings = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(model=RAGAS_EMBEDDINGS_MODEL, api_key=RAGAS_LLM_API_KEY)
    )

    dataset = Dataset.from_list(samples)
    logger.info("Running RAGAS evaluation on %d samples...", len(samples))
    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision],
        llm=llm,
        embeddings=embeddings,
    )
    df = result.to_pandas()
    # RAGAS result frames can carry non-numeric columns (e.g. string ids) —
    # aggregate only numeric columns so .mean() never raises or yields garbage.
    numeric = df.select_dtypes(include="number")
    if numeric.shape[1] == 0:
        logger.error("RAGAS result contains no numeric metric columns — cannot aggregate.")
        return {}
    return numeric.mean().to_dict()


async def main(args: argparse.Namespace) -> int:
    logger.info("=== RAGAS Evaluation -- %s ===", datetime.now(tz=timezone.utc).isoformat())
    logger.info("Backend: %s", BACKEND_URL)

    samples = []
    failures = []

    for item in GOLDEN_SET:
        qid = item["id"]
        question = item["question"]
        ground_truth = item["ground_truth"]
        logger.info("[%s] Querying: %s...", qid, question[:60])

        try:
            resp = await query_backend(question)
        except Exception as exc:
            logger.error("[%s] Backend error: %s", qid, exc)
            failures.append(qid)
            continue

        answer = resp.get("answer") or resp.get("response") or resp.get("final_answer") or ""
        contexts = resp.get("sources") or resp.get("contexts") or resp.get("citations") or []
        if isinstance(contexts, list):
            context_strs = [c.get("text", c) if isinstance(c, dict) else str(c) for c in contexts]
        else:
            context_strs = [str(contexts)]

        if not answer:
            logger.warning("[%s] Empty answer from backend", qid)
            failures.append(qid)
            continue

        samples.append(
            {
                "question": question,
                "answer": answer,
                "contexts": context_strs,
                "ground_truth": ground_truth,
                "reference": ground_truth,
            }
        )
        logger.info("[%s] Got answer (%d chars, %d contexts)", qid, len(answer), len(context_strs))

    if not samples:
        logger.error("No samples collected — check backend connectivity.")
        return 1

    if failures:
        logger.warning("%d query failures: %s", len(failures), failures)

    metrics = evaluate_with_ragas(samples)
    logger.info("RAGAS metrics: %s", json.dumps(metrics, indent=2))

    report = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "backend_url": BACKEND_URL,
        "n_samples": len(samples),
        "n_failures": len(failures),
        "metrics": metrics,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info("Report written to %s", output_path)

    # CI gate
    if args.ci:
        if failures:
            logger.error("CI FAIL: %d query failures: %s", len(failures), failures)
            return 1
        faithfulness_score = metrics.get("faithfulness")
        if faithfulness_score is None or not math.isfinite(faithfulness_score):
            logger.error("CI FAIL: faithfulness missing or non-finite")
            return 1
        if faithfulness_score < args.threshold:
            logger.error(
                "CI FAIL: faithfulness %.3f < threshold %.3f",
                faithfulness_score,
                args.threshold,
            )
            return 1
        logger.info("CI PASS: faithfulness %.3f >= %.3f", faithfulness_score, args.threshold)

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAGAS evaluation runner")
    parser.add_argument(
        "--output",
        default=f"scripts/eval/reports/eval_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}.json",
        help="Output JSON report path",
    )
    parser.add_argument("--ci", action="store_true", help="Exit 1 if metrics below threshold")
    parser.add_argument("--threshold", type=float, default=0.6, help="CI faithfulness threshold")
    args = parser.parse_args()

    sys.exit(asyncio.run(main(args)))
