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
    RAGAS_ANON_SESSION_TIMEOUT  Timeout (s) for POST /api/auth/anon-session
                    (default: 15; a 5s margin is added before use)
    RAGAS_CHAT_TIMEOUT  Timeout (s) for POST /api/chat (default: 120; a 5s
                    margin is added before use)

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
import re
import sys
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

# Client timeouts. A 5s margin is added at each call site so the harness's own
# timeout never races the service-side deadline (repo convention).
ANON_SESSION_TIMEOUT = float(os.environ.get("RAGAS_ANON_SESSION_TIMEOUT", "15"))
CHAT_TIMEOUT = float(os.environ.get("RAGAS_CHAT_TIMEOUT", "120"))

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


# ── R3: claim→source ledger + CitationFaithfulness-style audit (eval-only) ──
# Pure-stdlib sentence→context-span linking. Runs offline on collected answers;
# never touches retrieval or generation. The FP never-cites invariant is hard:
# first-person spans are context-only (citable=False) and ANY citation marker
# found in an FP answer is reported as an fp_citation violation.

_CLAIM_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(\[])")
_CITATION_RES = (
    re.compile(r"\[(\d{1,3})\]"),  # [1], [12]
    re.compile(r"\(sources?:[^)]*\)", re.IGNORECASE),  # (Source: ...), (sources: ...)
    re.compile(r"【[^】]*】"),  # CJK bracket citations
)
_FP_MARKER_RE = re.compile(
    r"\bI\s+(am|guide|teach|tell|bless|invite|ask|urge)\b"
    r"|as\s+(?:Sri\s+)?(?:Preethaji|Krishnaji)\s*,?\s+I\b",
    re.IGNORECASE,
)
_LEDGER_STOPWORDS = frozenset(
    "a an the and or but of to in on for with is are was were be been it its "
    "this that these those you your we our they their he she his her as at by "
    "from I me my".split()
)
_MIN_OVERLAP = 0.25  # claim-token fraction that must appear in a context to count as grounded


def split_claims(answer: str) -> list[str]:
    """Split an answer into factual-claim sentences (eval ledger granularity)."""
    parts = _CLAIM_SPLIT_RE.split((answer or "").strip())
    return [p.strip() for p in parts if len(p.split()) >= 3]


def _claim_tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _LEDGER_STOPWORDS}


def link_claims_to_spans(
    answer: str,
    contexts: list[str],
    min_overlap: float = _MIN_OVERLAP,
) -> list[dict]:
    """Link every claim sentence to its best-supporting context span.

    Returns ledger rows: {claim, best_context_idx|None, overlap, grounded}.
    `citable` is filled in by the audit (False for all FP spans — hard invariant).
    """
    claims = split_claims(answer)
    ctx_token_sets = [_claim_tokens(c) for c in contexts]
    ctx_norm = [re.sub(r"\s+", " ", (c or "").lower()).strip() for c in contexts]
    ledger: list[dict] = []
    for claim in claims:
        toks = _claim_tokens(claim)
        best_idx: int | None = None
        best_overlap = 0.0
        norm_claim = re.sub(r"\s+", " ", claim.lower()).strip()
        for i, (ctoks, cnorm) in enumerate(zip(ctx_token_sets, ctx_norm)):
            if not toks:
                continue
            overlap = len(toks & ctoks) / len(toks)
            if norm_claim and norm_claim in cnorm:
                overlap = max(overlap, 1.0)
            if overlap > best_overlap:
                best_overlap, best_idx = overlap, i
        ledger.append(
            {
                "claim": claim,
                "best_context_idx": best_idx if best_overlap >= min_overlap else None,
                "overlap": round(best_overlap, 3),
                "grounded": best_overlap >= min_overlap,
            }
        )
    return ledger


def detect_first_person(answer: str, voice: str | None = None) -> bool:
    """True when the answer speaks as the guru (FP route) vs about the guru."""
    if voice and str(voice).strip().lower() in {"first_person", "first-person", "fp"}:
        return True
    return bool(_FP_MARKER_RE.search(answer or ""))


def citation_faithfulness_audit(
    answer: str,
    contexts: list[str],
    is_first_person: bool = False,
    min_overlap: float = _MIN_OVERLAP,
) -> dict:
    """CitationFaithfulness-style audit: flag 'cited but ungrounded' spans.

    - General path: each ``[n]`` marker must resolve to contexts[n-1] AND the
      citing claim must overlap that context; otherwise it is a
      cited_but_ungrounded violation.
    - FP path: spans stay context-only (citable=False); any citation marker at
      all is an fp_citation violation. Assert zero in tests / fixture output.
    """
    ledger = link_claims_to_spans(answer, contexts, min_overlap=min_overlap)
    for row in ledger:
        row["citable"] = not is_first_person

    markers: list[dict] = []
    for rx in _CITATION_RES:
        for m in rx.finditer(answer or ""):
            markers.append({"marker": m.group(0), "pos": m.start()})

    cited_but_ungrounded: list[dict] = []
    fp_citations: list[dict] = []
    if is_first_person:
        fp_citations = [{"marker": m["marker"], "reason": "fp_never_cites"} for m in markers]
    else:
        num_re = _CITATION_RES[0]
        for m in num_re.finditer(answer or ""):
            n = int(m.group(1))
            target = n - 1
            if target < 0 or target >= len(contexts):
                cited_but_ungrounded.append({"marker": m.group(0), "reason": "target_out_of_range"})
                continue
            # The claim carrying the marker must be grounded IN THE CITED span.
            carrying = [r for r in ledger if m.group(0) in r["claim"]]
            ctoks = _claim_tokens(contexts[target])
            ok = False
            for row in carrying or [{"claim": "", "grounded": False}]:
                toks = _claim_tokens(row["claim"].replace(m.group(0), ""))
                if toks and ctoks and len(toks & ctoks) / len(toks) >= min_overlap:
                    ok = True
                    break
            if not ok:
                cited_but_ungrounded.append(
                    {
                        "marker": m.group(0),
                        "reason": "cited_span_does_not_support_claim",
                        "cited_context_idx": target,
                    }
                )

    return {
        "n_claims": len(ledger),
        "n_grounded": sum(1 for r in ledger if r["grounded"]),
        "n_citation_markers": len(markers),
        "cited_but_ungrounded": cited_but_ungrounded,
        "fp_citations": fp_citations,
        "is_first_person": is_first_person,
        "ledger": ledger,
    }


# Tiny offline fixture for `--fixture` runs (no backend, no LLM, stdlib only).
_FIXTURE_CONTEXTS = [
    "Sri Preethaji teaches that a Beautiful State is a state of consciousness "
    "free from suffering, marked by stillness, joy, and connectedness.",
    "Sri Krishnaji teaches the Serene Mind practice: three minutes of breath, "
    "emotion, and thought direction with attention at the eyebrow center.",
]
FIXTURE_SAMPLES = [
    {
        "id": "fx-grounded",
        "answer": ("A Beautiful State is free from suffering and marked by stillness and joy [1]."),
        "contexts": _FIXTURE_CONTEXTS,
        "is_first_person": False,
    },
    {
        "id": "fx-ungrounded-cite",
        "answer": ("A Beautiful State requires strict fasting every new moon [5]."),
        "contexts": _FIXTURE_CONTEXTS,
        "is_first_person": False,
    },
    {
        "id": "fx-fp-clean",
        "answer": (
            "I am with you. Rest your attention in stillness and let the "
            "noise of the mind settle on its own."
        ),
        "contexts": _FIXTURE_CONTEXTS,
        "is_first_person": True,
    },
]


def run_fixture(output_path: str) -> int:
    """Run the R3 ledger+audit on the tiny offline fixture. Always stdlib-only."""
    audits = []
    for sample in FIXTURE_SAMPLES:
        audit = citation_faithfulness_audit(
            sample["answer"],
            sample["contexts"],
            is_first_person=sample["is_first_person"],
        )
        audits.append({"id": sample["id"], **audit})
        logger.info(
            "[%s] claims=%d grounded=%d markers=%d ungrounded=%d fp_cites=%d",
            sample["id"],
            audit["n_claims"],
            audit["n_grounded"],
            audit["n_citation_markers"],
            len(audit["cited_but_ungrounded"]),
            len(audit["fp_citations"]),
        )
    fp_total = sum(len(a["fp_citations"]) for a in audits if a["is_first_person"])
    logger.info("FP citation invariant: %d fp_citations in FP audit output", fp_total)

    report = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "mode": "fixture",
        "n_samples": len(audits),
        "fp_citation_total": fp_total,
        "audits": audits,
    }
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(report, f, indent=2)
    logger.info("Fixture report written to %s", out)
    return 0


async def _get_anon_session_token(client: httpx.AsyncClient) -> str:
    """Mint a server-signed anon session token via POST /api/auth/anon-session.

    Production resolve_anon_identity() rejects bare client-chosen session ids,
    so the harness must exchange the signed token it returns and echo it back
    as session_id."""
    resp = await client.post(
        "/api/auth/anon-session", timeout=ANON_SESSION_TIMEOUT + 5.0
    )
    resp.raise_for_status()
    return resp.json()["token"]


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

    async with httpx.AsyncClient(
        base_url=BACKEND_URL, timeout=CHAT_TIMEOUT + 5.0, follow_redirects=False
    ) as client:
        token = await _get_anon_session_token(client)
        payload = {
            "messages": [],
            "user_message": question,
            "session_id": token,
        }
        resp = await client.post("/api/chat", json=payload, headers=headers)
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
    claim_audits = []  # R3 eval-only: parallel to samples, never fed to RAGAS

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
        # R3 ledger+audit: eval-only, stdlib, no retrieval/generation impact.
        fp = detect_first_person(answer, voice=resp.get("voice"))
        audit = citation_faithfulness_audit(answer, context_strs, is_first_person=fp)
        claim_audits.append({"id": qid, **audit})
        logger.info(
            "[%s] ledger: %d/%d claims grounded, %d cited-but-ungrounded, %d fp_citations",
            qid, audit["n_grounded"], audit["n_claims"],
            len(audit["cited_but_ungrounded"]), len(audit["fp_citations"]),
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
        "claim_audits": claim_audits,
        "fp_citation_total": sum(
            len(a["fp_citations"]) for a in claim_audits if a["is_first_person"]
        ),
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
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Offline R3 check: run claim ledger + citation audit on the tiny "
        "built-in fixture (no backend, no LLM) and exit 0.",
    )
    args = parser.parse_args()

    if args.fixture:
        sys.exit(run_fixture(args.output))
    sys.exit(asyncio.run(main(args)))
