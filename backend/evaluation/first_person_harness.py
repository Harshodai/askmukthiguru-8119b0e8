"""Pinned first-person evaluation harness.

One question file (SHA-256 pinned below), one scorer, one fixed denominator — so
"v2 vs v5" or "rerank on vs off" is decided by the same measurement every time.
Three earlier evaluations of the same 116 questions disagreed because each used a
different scratch scorer and a different denominator (83 vs 89).

It runs the real serving pipeline (FirstPersonPipeline), so top-1 is exactly the
clip a seeker would be served. Read-only against Qdrant; no Redis cache.

Honest limits (state them with every number):
- The questions are AI-authored from the indexed transcripts, not real seekers,
  so this measures ranking within the indexed set, not coverage.
- 89 answerable questions from 8 videos: the video-clustered 95% CI is wide.
- ``host_like`` is a text heuristic, not a human audit of who is speaking.

Usage (inside the backend container, which has Qdrant + the embedding model):
    python -m evaluation.first_person_harness run --collection first_person_v5 --out /tmp/v5.json
    python -m evaluation.first_person_harness run --collection first_person_v5 --rerank --out /tmp/v5r.json
    python -m evaluation.first_person_harness compare /tmp/v2.json /tmp/v5.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

from evaluation.gold.metrics import bootstrap_ci_by_video, passage_hits_ranges

QUESTIONS_PATH = Path(__file__).parent / "datasets" / "first_person_bakeoff_2026-09-25.json"
QUESTIONS_SHA256 = "acb635fc899dcd850ff0b7c9d2fb4bfddd6826e78baad71f32eecc2af16848c8"

# Phase 2 answerability gate pacing: OpenRouterService enforces
# settings.openrouter_rpm_limit (20) through ONE Redis sliding window shared by
# every process on this Redis. A gate call that trips the limiter sleeps inside
# generate() and blows the gate budget -> false indeterminate -> false
# abstention. 3.2s spacing keeps 116 questions under 20 calls/60s with headroom.
GATE_PACE_S = 3.2

GOLDEN_PARAPHRASE_PATH = (
    Path(__file__).parent / "datasets" / "first_person_golden_paraphrase_25.json"
)
GOLDEN_PARAPHRASE_SHA256 = "1cd211387f6470f9d3aa97b867b1534a73baa02953daa69b1d7c8be490298285"

PINNED_DATASETS: dict[str, str] = {
    QUESTIONS_PATH.name: QUESTIONS_SHA256,
    GOLDEN_PARAPHRASE_PATH.name: GOLDEN_PARAPHRASE_SHA256,
}

_HOST_STEMS = re.compile(
    r"^(so|now|and|what|why|how|when|is|are|do|does|can|could|would|will|namaste)\b", re.IGNORECASE
)


class HarnessError(RuntimeError):
    pass


def load_questions(
    path: Path = QUESTIONS_PATH,
    expected_sha256: str | None = None,
    pin_check: bool = True,
) -> list[dict]:
    raw = path.read_bytes()
    if pin_check:
        pin = expected_sha256 or PINNED_DATASETS.get(path.name)
        if pin is not None:
            actual = hashlib.sha256(raw).hexdigest()
            if actual != pin:
                raise HarnessError(
                    f"{path} sha256 {actual} != pinned {pin}; refusing to score a changed set"
                )
    parsed = json.loads(raw)
    questions = (
        parsed["questions"] if isinstance(parsed, dict) and "questions" in parsed else parsed
    )
    for q in questions:
        if "question" not in q and "query" in q:
            q["question"] = q["query"]
        elif "query" not in q and "question" in q:
            q["query"] = q["question"]
        for r in q.get("answer_ranges", []):
            if "video_id" not in r and "video_id" in q:
                r["video_id"] = q["video_id"]
    return questions


def looks_host_like(text: str) -> bool:
    """Bake-off heuristic (ported from scoring_lib.py): a question, or a short
    opener in a host's register. A proxy for host speech, not a speaker check."""
    t = (text or "").strip()
    if not t:
        return False
    if t.endswith("?"):
        return True
    first = re.split(r"(?<=[.!?])\s", t, maxsplit=1)[0]
    return len(first.split()) <= 14 and bool(_HOST_STEMS.match(first))


def score_row(question: dict, citation: dict | None) -> dict:
    """One row per question. A missing top-1 clip on an answerable question is a miss."""
    row = {
        "id": question["id"],
        "video_id": question["video_id"],
        "answerable": bool(question["answerable"]),
        "near_miss": bool(question.get("near_miss")),
        "paraphrase_group": question.get("paraphrase_group"),
        "top1": None,
        "hit": False,
        "host_like": False,
    }
    if citation:
        clip = {
            "video_id": citation["video_id"],
            "start": citation["start_ms"] / 1000.0,
            "end": citation["end_ms"] / 1000.0,
        }
        row["top1"] = {
            **clip,
            "speaker": citation.get("speaker"),
            "point_id": citation.get("point_id"),
        }
        row["host_like"] = looks_host_like(citation.get("verbatim_text", ""))
        if row["answerable"]:
            row["hit"] = passage_hits_ranges(clip, question["answer_ranges"])
    return row


def summarize(rows: list[dict], latencies_ms: list[float]) -> dict:
    answerable = [dict(r, hit=int(r["hit"])) for r in rows if r["answerable"]]
    out_of_scope = [r for r in rows if not r["answerable"]]
    served = [dict(r, host_like=int(r["host_like"])) for r in rows if r["top1"]]
    lat = sorted(latencies_ms)
    return {
        "n_questions": len(rows),
        "n_answerable": len(answerable),  # fixed denominator: misses and errors stay in
        "top1_hit": bootstrap_ci_by_video(answerable, "hit"),
        "host_like_top1": bootstrap_ci_by_video(served, "host_like") if served else None,
        "n_errors": sum(1 for r in rows if r.get("status") == "error"),
        "paraphrase_consistency": paraphrase_consistency(rows),
        "status_counts": _count(r.get("status") for r in rows),
        # Phase 2: subsets must be read separately — OOC status moving to
        # abstained is the INTENT, while the answerable subset's top1 must hold.
        "status_counts_by_subset": {
            "answerable": _count(r.get("status") for r in rows if r["answerable"]),
            "out_of_scope": _count(r.get("status") for r in out_of_scope),
        },
        "answerability_verdicts": _count(r.get("answerability") or "not_run" for r in rows),
        "latency_ms": {
            "p50": round(statistics.median(lat), 1) if lat else None,
            "p95": round(lat[min(len(lat) - 1, math.ceil(0.95 * len(lat)) - 1)], 1)
            if lat
            else None,
        },
    }


def paraphrase_consistency(rows: list[dict]) -> dict | None:
    """PCS: share of paraphrase groups (>=2 rewordings of one question) whose members
    all get the same top-1 video; same_clip_rate is the stricter same-point share.
    None when the question set has no paraphrase groups — never a made-up 1.0."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("paraphrase_group"):
            groups.setdefault(r["paraphrase_group"], []).append(r)
    groups = {g: m for g, m in groups.items() if len(m) >= 2}
    if not groups:
        return None

    def _same(members: list[dict], key: str) -> bool:
        values = {(m["top1"] or {}).get(key) for m in members}
        return len(values) == 1 and None not in values

    n = len(groups)
    return {
        "n_groups": n,
        "same_video_rate": round(sum(_same(m, "video_id") for m in groups.values()) / n, 4),
        "same_clip_rate": round(sum(_same(m, "point_id") for m in groups.values()) / n, 4),
    }


def _count(values) -> dict:
    out: dict[str, int] = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return out


def mcnemar_exact(a_rows: list[dict], b_rows: list[dict]) -> dict:
    """Paired comparison on answerable questions: exact two-sided binomial test on
    the discordant pairs (B right & A wrong vs A right & B wrong)."""
    a = {r["id"]: r for r in a_rows if r["answerable"]}
    b = {r["id"]: r for r in b_rows if r["answerable"]}
    if set(a) != set(b):
        raise HarnessError("runs were scored on different question sets")
    b_wins = sorted(q for q in a if b[q]["hit"] and not a[q]["hit"])
    a_wins = sorted(q for q in a if a[q]["hit"] and not b[q]["hit"])
    n, k = len(a_wins) + len(b_wins), min(len(a_wins), len(b_wins))
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2**n) if n else 1.0
    return {"a_wins": a_wins, "b_wins": b_wins, "n_discordant": n, "p_value_two_sided": round(p, 4)}


async def _runtime_fingerprint(embedding, settings) -> dict:
    """Identical builds differ by 2-4 top-1 questions across environments
    (L-EMBED-DRIFT-1). Record what produced the vectors: the encoder output on a
    fixed probe (hash of the rounded vector) plus library versions, so two runs
    are only compared when these match."""
    import platform
    from importlib.metadata import PackageNotFoundError, version

    probe = await embedding.encode_single_full_async("What is the Beautiful State?")
    rounded = ",".join(f"{x:.4f}" for x in probe["dense"])
    versions = {}
    for pkg in ("onnxruntime", "numpy", "qdrant-client", "tokenizers", "transformers"):
        try:
            versions[pkg] = version(pkg)
        except PackageNotFoundError:
            versions[pkg] = None
    return {
        "encoder_probe_sha256": hashlib.sha256(rounded.encode()).hexdigest(),
        "embedding_backend": getattr(settings, "embedding_backend", None),
        "embedding_model": getattr(settings, "embedding_model", None),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "versions": versions,
    }


def _git_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return None  # inside the container there is no .git; the run records None, not a guess


def _make_llm_service():
    """Prod-equivalent LLM service for the Phase 2 answerability gate.

    Mirrors the serving route's selection chain (app/api/first_person.py:
    container.openrouter -> nim -> ollama) without booting the app container:
    OpenRouterService() construction is lazy (reads settings, no network),
    `nim` no longer exists on the container (only openrouter/ollama are set),
    and the last resort is the same factory the container uses for `ollama`.

    Returns (service, name) or (None, None). A caller that gets (None, None)
    must REPORT the gate as disabled — never silently run gate-off while
    claiming production equivalence.
    """
    try:
        from services.openrouter_service import OpenRouterService

        svc = OpenRouterService()
        if getattr(svc, "_api_key", None):
            return svc, "openrouter"
        print("[harness] OpenRouter has no API key; trying ollama chain", file=sys.stderr)
    except Exception as e:
        print(f"[harness] OpenRouterService unavailable: {e}", file=sys.stderr)
    try:
        from app.container import _create_llm_service

        svc = _create_llm_service()
        if svc is not None and hasattr(svc, "generate"):
            return svc, "ollama"
    except Exception as e:
        print(f"[harness] ollama chain unavailable: {e}", file=sys.stderr)
    return None, None


async def run(
    collection: str,
    rerank: bool,
    questions_path: Path = QUESTIONS_PATH,
    pin_check: bool = True,
) -> dict:
    from app.api.first_person import _make_rerank_fn
    from app.config import settings
    from services.embedding_service import get_embedding_service
    from services.first_person_pipeline import _ANSWERABILITY_TIMEOUT_S, FirstPersonPipeline
    from services.first_person_store import FirstPersonStore

    questions = load_questions(path=questions_path, pin_check=pin_check)
    questions_sha256 = hashlib.sha256(questions_path.read_bytes()).hexdigest()
    embedding = get_embedding_service()
    store = FirstPersonStore(collection=collection)
    rerank_fn = (
        _make_rerank_fn(embedding, asyncio.get_running_loop(), timeout_s=30.0) if rerank else None
    )

    # Phase 2: the gate must see a production-equivalent llm_service, or the run
    # must say the gate was off. No silent third option.
    gate_flag = bool(settings.first_person_answerability_check_enabled)
    llm_service, llm_name = None, None
    gate_mode = "disabled_by_setting"
    if gate_flag:
        llm_service, llm_name = _make_llm_service()
        if llm_service is None:
            # In-process only (the harness exits after the run): fall back to
            # pre-gate behavior and record WHY, instead of abstaining on every
            # question and calling it a measurement.
            settings.first_person_answerability_check_enabled = False
            gate_mode = "disabled_no_llm_service"
        else:
            gate_mode = "enabled"

    # No Redis: every question is a real retrieval. No calibration profile override:
    # the pipeline loads whatever FIRST_PERSON_CALIBRATION_PATH points at, as serving does.
    pipeline = FirstPersonPipeline(
        store=store, redis_client=None, rerank_fn=rerank_fn, llm_service=llm_service
    )

    rows, latencies = [], []
    for q in questions:
        status, citation, answerability = "error", None, None
        try:
            enc = await embedding.encode_single_full_async(q["question"])
            sparse = enc.get("sparse") or {}
            res = await asyncio.to_thread(
                pipeline.execute,
                query=q["question"],
                query_dense_vector=enc["dense"],
                query_sparse_vector={"indices": list(sparse), "values": list(sparse.values())}
                if sparse
                else None,
                max_clips=3,
            )
            status = res.status
            latencies.append(res.latency_ms)
            citation = res.citations[0] if res.citations else None
            answerability = getattr(res, "answerability", None)
        except Exception as e:  # counted as a miss and reported, never dropped
            print(f"[harness] {q['id']} failed: {e}", file=sys.stderr)
        row = score_row(q, citation)
        row["status"] = status
        row["answerability"] = answerability
        rows.append(row)
        # Pace only the questions that actually spent shared RPM budget on a gate
        # call (answerability set = the gate ran); see GATE_PACE_S.
        if gate_mode == "enabled" and answerability is not None:
            await asyncio.sleep(GATE_PACE_S)

    return {
        "collection": collection,
        "rerank": rerank,
        "questions_path": str(questions_path),
        "questions_sha256": questions_sha256,
        "git_sha": _git_sha(),
        "runtime": await _runtime_fingerprint(embedding, settings),
        "serve_unregistered": bool(getattr(settings, "first_person_serve_unregistered", False)),
        "calibration_path": getattr(settings, "first_person_calibration_path", ""),
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "answerability_gate": {
            "mode": gate_mode,
            "flag_at_start": gate_flag,
            "llm_service": llm_name,
            "timeout_s": _ANSWERABILITY_TIMEOUT_S,
            "pace_s": GATE_PACE_S if gate_mode == "enabled" else 0,
        },
        "summary": summarize(rows, latencies),
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--collection", required=True)
    r.add_argument("--rerank", action="store_true")
    r.add_argument("--out", type=Path, required=True)
    r.add_argument(
        "--questions", type=Path, default=QUESTIONS_PATH, help="Path to question dataset JSON"
    )
    r.add_argument(
        "--no-pin-check",
        action="store_true",
        help="Bypass SHA-256 pin check for non-bakeoff datasets",
    )
    c = sub.add_parser("compare")
    c.add_argument("a", type=Path)
    c.add_argument("b", type=Path)
    args = ap.parse_args(argv)

    if args.cmd == "run":
        result = asyncio.run(
            run(
                args.collection,
                args.rerank,
                questions_path=args.questions,
                pin_check=not args.no_pin_check,
            )
        )
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(
            json.dumps(
                {k: result[k] for k in ("collection", "rerank", "answerability_gate", "summary")},
                indent=2,
            )
        )
        return 0

    a, b = (json.loads(p.read_text()) for p in (args.a, args.b))
    if a.get("questions_sha256") != b.get("questions_sha256"):
        raise HarnessError(
            f"runs were scored on different question files: {a.get('questions_sha256')} != {b.get('questions_sha256')}"
        )
    fa = (a.get("runtime") or {}).get("encoder_probe_sha256")
    fb = (b.get("runtime") or {}).get("encoder_probe_sha256")
    if fa != fb:
        raise HarnessError(
            f"runs used different encoders (probe {fa} vs {fb}); re-run both in one environment"
        )
    out = {
        "a": {k: a[k] for k in ("collection", "rerank")} | {"top1_hit": a["summary"]["top1_hit"]},
        "b": {k: b[k] for k in ("collection", "rerank")} | {"top1_hit": b["summary"]["top1_hit"]},
        "paired": mcnemar_exact(a["rows"], b["rows"]),
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
