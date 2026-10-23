#!/usr/bin/env python
"""Head-to-head dry eval between two first_person Qdrant collections (v8 vs v9).

One new standalone script; modifies nothing, writes nothing to Qdrant/Redis/Neo4j,
makes NO LLM calls, no backend HTTP. READ-ONLY (query_points only).

Reuses the proven host-side in-process pattern from
`.work/autoresearch_fp/build_cache.py` (which mirrors the retrieval path of
services/first_person_pipeline.py::execute) and the same serve-time gates its
eval used:

    EmbeddingService.encode_single_full (query expansion incl.)
        -> FirstPersonStore.search_hybrid (limit=80, dedup_limit=40,
           teacher filter from requested_teacher())
        -> serve gates, in the exact order FirstPersonPipeline.execute runs them:

        1. crisis pre-check          (SereneMindEngine, assess_distress >= SEVERE)
        2. topic rail                (guardrails.lightweight_handler.match_blocked_topic)
        3. integrity gate            (_passes_integrity_gate; boundary_guard per settings;
                                     check_availability=False — no YouTube calls,
                                     exactly as build_cache.py froze it; live serve
                                     calls with check_availability=True)
        4. content-quality gate      (_passes_content_quality_gate; includes the
                                     standalone gate behind
                                     first_person_standalone_gate_enabled)
        5. quality allowlist/blocklist (opt-in settings paths; no-op when unset)
        6. top-N slice               (max_clips=3; 4 on practice intent — mirrors execute)

NOT executed (they are LLM-backed or stateful):
    - Haiku relevance scorer            (_relevance_select / relevance gate)
    - answerability gate                (_answerability_check, question-only LLM)
    - LLM rerank / facet decomposition  (LLM)
    - Redis exact cache / telemetry     (stateful side channels)

Because of that, every `is_showable` value in the report is a DRY SYSTEM
judgment: "deterministic gates passed and a top clip exists, so the request
would REACH the LLM relevance/answerability stage with this candidate". It is
NOT the full serve decision: skipping the Haiku relevance scorer and the
answerability gate can only OVERESTIMATE live serving. The report states this
explicitly (fields `is_showable_dry`, meta `no_llm_gates_skipped`).

Question bank default: `.work/autoresearch_fp/candidates.json` — 42 frozen
questions (29 on_topic = the showability bench, 13 ooc), the same bank the
autoresearch eval.py scored (train/heldout membership comes from split.json
in the same directory and is attached per question when found).

Usage (from backend/):
    .venv/bin/python scripts/ops/eval_v8_vs_v9.py \
        --collections first_person_v8,first_person_v9 \
        --questions ../.work/autoresearch_fp/candidates.json \
        --out ../.work/autoresearch_fp/eval_v8_vs_v9 \
        [--qdrant-url http://localhost:6333]

Deterministic: fixed question order, pre-encoded vectors reused across
collections, sorted outputs. Exits 0 after writing report.json + questions.tsv.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from qdrant_client import QdrantClient  # noqa: E402

from app.config import settings  # noqa: E402  (never print settings: it carries secrets)
from guardrails.lightweight_handler import match_blocked_topic  # noqa: E402
from services.embedding_service import EmbeddingService  # noqa: E402
from services.first_person_pipeline import (  # noqa: E402
    _cosine_similarity,
    _passes_content_quality_gate,
    _passes_integrity_gate,
    _quality_allowlist,
    _quality_blocklist,
    requested_teacher,
)
from services.first_person_store import FirstPersonStore  # noqa: E402
from services.serene_mind_engine import DistressLevel, SereneMindEngine  # noqa: E402

DEFAULT_QDRANT_URL = os.environ.get("FP_EVAL_QDRANT_URL", "http://localhost:6333")
DEFAULT_QUESTIONS = Path(__file__).resolve().parents[3] / ".work/autoresearch_fp/candidates.json"
TOP_N = 3  # max_clips at serve time
RETRIEVAL_LIMIT = 80  # execute(): max(80, effective_max_clips * 16)
RETRIEVAL_DEDUP_LIMIT = 40  # execute(): max(40, effective_max_clips * 8)
PRACTICE_KEYWORDS = (
    "practice",
    "meditation",
    "how to",
    "technique",
    "exercise",
    "sadhana",
    "kriya",
)


def has_practice_intent(text: str) -> bool:
    lowered = text.lower()
    return any(w in lowered for w in PRACTICE_KEYWORDS)


# ---------------------------------------------------------------- questions
def load_questions(path: Path) -> list[dict[str, Any]]:
    """Load the benchmark bank. Accepts the candidates.json bank shape
    ({"questions": [...]}) or a flat JSONL ({qid, question, kind, ...}/line)."""
    qs: list[dict[str, Any]] = []
    if path.suffix == ".jsonl":
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            qs.append(
                {
                    "qid": r.get("qid") or r.get("id") or f"q{len(qs):03d}",
                    "question": r["question"],
                    "kind": r.get("kind", "on_topic"),
                }
            )
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        qs = [
            {
                "qid": q["qid"],
                "question": q["question"],
                "kind": q.get("kind", "on_topic"),
            }
            for q in data["questions"]
        ]
    if not qs:
        raise SystemExit(f"FATAL: no questions parsed from {path}")
    return qs


def attach_split(qs: list[dict[str, Any]], questions_path: Path) -> str:
    """Tag train/heldout from split.json next to the question bank, when found."""
    split_path = questions_path.parent / "split.json"
    if not split_path.exists():
        for q in qs:
            q["split"] = None
        return "not_found"
    split = json.loads(split_path.read_text(encoding="utf-8"))
    heldout = set(split.get("heldout") or [])
    train = set(split.get("train") or [])
    n_tagged = 0
    for q in qs:
        q["split"] = "heldout" if q["qid"] in heldout else "train" if q["qid"] in train else None
        if q["split"] is not None:
            n_tagged += 1
    return f"tagged_{n_tagged}"


# ---------------------------------------------------------------- evaluation
def rail_reason(text: str, serene: SereneMindEngine) -> tuple[bool, str | None]:
    """Deterministic safety rails (Steps 1/1b of execute())."""
    assessment = serene.assess_distress(text)
    is_crisis = bool(assessment and assessment.level.value >= DistressLevel.SEVERE.value)
    if is_crisis:
        return True, "crisis"
    blocked = match_blocked_topic(text)
    if blocked is not None:
        return True, blocked[0]
    return False, None


def top3_clips(
    gated: list[dict[str, Any]],
    allow: frozenset[str] | None,
    blocked: frozenset[str] | None,
    n: int,
) -> list[dict[str, Any]]:
    """Serve-set slice applied in execute() order: allowlist -> blocklist -> top N.

    Fail-closed semantics preserved: a configured-but-unreadable list empties
    the serve set (inside _quality_allowlist/_quality_blocklist, mirrored below
    by the `blocked is None and path set` empties-the-set rule of execute())."""
    clips = gated
    if allow is not None:
        clips = [c for c in clips if str(c.get("point_id")) in allow]
    if blocked is not None:
        clips = [c for c in clips if str(c.get("point_id")) not in blocked]
    return clips[:n]


def eval_collection(
    collection: str,
    client: QdrantClient,
    encoded: dict[str, dict[str, Any]],
    questions: list[dict[str, Any]],
    serene: SereneMindEngine,
    flags: dict[str, Any],
) -> list[dict[str, Any]]:
    store = FirstPersonStore(collection=collection, client=client)
    info = client.get_collections().collections
    names = {c.name for c in info}
    if collection not in names:
        raise SystemExit(
            f"FATAL: collection {collection!r} does not exist on the Qdrant server. "
            f"Found: {sorted(names)}"
        )
    points = client.count(collection, exact=False).count
    print(f"[{collection}] exists, {points} points (approx)", flush=True)

    boundary_guard_active = bool(flags["boundary_guard"])
    cq_gate_active = bool(flags["content_quality_gate"])
    allow = _quality_allowlist()  # None == no allowlist configured
    block = _quality_blocklist()  # None == no blocklist configured

    rows: list[dict[str, Any]] = []
    for q in questions:
        text = q["question"]
        teacher = requested_teacher(text)
        crisis_rail, crisis_topic_rail = rail_reason(text, serene)
        enc = encoded[q["qid"]]
        dense = [float(x) for x in enc["dense"]]
        sp = enc.get("sparse") or {}
        sparse = (
            {"indices": [int(k) for k in sp], "values": [float(v) for v in sp.values()]}
            if sp
            else None
        )

        railed, rail = crisis_rail, crisis_topic_rail
        if railed:
            raw: list[dict[str, Any]] = []
            n_raw = 0
        else:
            raw = store.search_hybrid(
                dense,
                sparse,
                teacher_id=teacher,
                limit=RETRIEVAL_LIMIT,
                dedup_limit=RETRIEVAL_DEDUP_LIMIT,
                allow_same_video_distinct_spans=has_practice_intent(text),
            )
            n_raw = len(raw)

        # Gates, in execute() serve order.
        n_integrity_fail = 0
        n_cq_fail = 0
        gated: list[dict[str, Any]] = []
        for rrf_rank, clip in enumerate(raw):
            if not _passes_integrity_gate(
                clip,
                boundary_guard_enabled=boundary_guard_active,
                check_availability=False,  # no YouTube calls (build_cache frozen pattern)
            ):
                n_integrity_fail += 1
                continue
            if not _passes_content_quality_gate(clip, gate_enabled=cq_gate_active):
                n_cq_fail += 1
                continue
            gated.append({**clip, "rrf_rank": rrf_rank})
        serve_set = top3_clips(gated, allow, block, n=4 if has_practice_intent(text) else TOP_N)
        if railed:
            serve_set = []

        top1 = serve_set[0] if serve_set else None
        top1_cos = round(_cosine_similarity(dense, top1.get("passage_dense")), 6) if top1 else None
        railed_reason = None
        if railed:
            railed_reason = "crisis_redirect" if rail == "crisis" else "topic_blocked"
        elif not serve_set:
            railed_reason = "no_gated_clips"

        row = {
            "qid": q["qid"],
            "kind": q["kind"],
            "split": q.get("split"),
            "sampling": "dry_no_llm",
            "rail_blocked": railed,
            "rail": None if not railed else rail,
            "n_raw": n_raw,
            "n_integrity_fail": n_integrity_fail,
            "n_cq_fail": n_cq_fail,
            "n_gated": len(gated),
            "n_serve_set": len(serve_set),
            "top1_dense_cosine": top1_cos,
            "serve_set": [
                {
                    k: c[k]
                    for k in ("point_id", "video_id", "start_ms", "end_ms", "speaker", "rrf_rank")
                }
                for c in serve_set
            ],
            # DRY verdict — LLM relevance scorer + answerability gate SKIPPED.
            "is_showable_dry": bool(serve_set) and not railed,
            # None == live pipeline would proceed to the LLM stage here.
            "abstain_reason_dry": railed_reason,
        }
        rows.append(row)
        cos = row["top1_dense_cosine"]
        cos_s = f"{cos:.4f}" if cos is not None else "  -  "
        print(
            f"{q['qid']:6} rail={row['rail'] or '-':10.10} raw={row['n_raw']:3} "
            f"cqF={row['n_cq_fail']:3} gated={row['n_gated']:3} "
            f"showable_dry={str(row['is_showable_dry']):5} cos={cos_s} :: {text[:52]}",
            flush=True,
        )

    for r in rows:
        r["collection"] = collection
    return rows


# ---------------------------------------------------------------- reporting
def summarize(rows: list[dict[str, Any]], collection: str) -> dict[str, Any]:
    on = [r for r in rows if r["kind"] == "on_topic"]
    ooc = [r for r in rows if r["kind"] != "on_topic"]
    showable = [r for r in on if r["is_showable_dry"]]
    ooc_top = [r for r in ooc if r["is_showable_dry"]]
    cos_vals = [r["top1_dense_cosine"] for r in showable if r["top1_dense_cosine"] is not None]
    return {
        "collection": collection,
        "n_questions": len(rows),
        "n_on_topic": len(on),
        "n_ooc": len(ooc),
        "on_topic_showable_dry": len(showable),
        "on_topic_showable_dry_frac": round(len(showable) / len(on), 4) if on else 0.0,
        "on_topic_abstained_dry": len(on) - len(showable),
        "ooc_top1_qualify_dry": len(ooc_top),  # OOC: watch for leaks; LLM judge normally decides
        "rail_blocked": sum(1 for r in rows if r["rail_blocked"]),
        "no_gated_clips": sum(1 for r in rows if r["abstain_reason_dry"] == "no_gated_clips"),
        "integrity_fail_total": sum(r["n_integrity_fail"] for r in rows),
        "cq_fail_total": sum(r["n_cq_fail"] for r in rows),
        "top1_cos_mean_showable": round(statistics.mean(cos_vals), 4) if cos_vals else None,
        "top1_cos_median_showable": round(statistics.median(cos_vals), 4) if cos_vals else None,
    }


def print_side_by_side(v8: list[dict[str, Any]], v9: list[dict[str, Any]]) -> None:
    by8 = {r["qid"]: r for r in v8}
    by9 = {r["qid"]: r for r in v9}
    qids = [q["qid"] for q in QUESTIONS]
    print()
    print("=" * 118)
    print(
        "SIDE-BY-SIDE (deterministic, dry no-LLM)  split  |  v8: rail raw gated cos show  ||  v9: rail raw gated cos show"
    )
    print("=" * 118)
    print(
        f"{'qid':7}{'kind':5}{'split':7} | {'v8:':>3} raw  cqF gat  cos  show || {'v9:':>3} raw  cqF gat  cos  show"
    )
    print("-" * 118)
    for qid in qids:
        r8, r9 = by8[qid], by9[qid]

        def cell(r: dict[str, Any]) -> str:
            cos = r["top1_dense_cosine"]
            cos_s = f"{cos:5.4f}" if cos is not None else "  -  "
            return (
                f"{r['n_raw']:4} {r['n_cq_fail']:4} {r['n_gated']:4} {cos_s} "
                f"{'Y' if r['is_showable_dry'] else '.'}"
            )

        print(
            f"{qid:7}{r8['kind'][:4]:5}{str(r8['split'] or '-'):7} | {r8['rail'] or '-':9.9}  {cell(r8)}  ||  "
            f"{r9['rail'] or '-':9.9}  {cell(r9)}"
        )
    print("-" * 118)


def main() -> None:
    ap = argparse.ArgumentParser(description="dry head-to-head first_person collection eval")
    ap.add_argument("--collections", default="first_person_v8,first_person_v9")
    ap.add_argument("--questions", default=str(DEFAULT_QUESTIONS))
    ap.add_argument("--out", default=None)
    ap.add_argument(
        "--qdrant-url",
        default=DEFAULT_QDRANT_URL,
        help="Qdrant REST endpoint (default http://localhost:6333 or $FP_EVAL_QDRANT_URL); "
        "docker hostname 'qdrant:' is rejected",
    )
    args = ap.parse_args()

    qdrant_url = args.qdrant_url.rstrip("/")
    if "qdrant:" in qdrant_url.split("//")[-1].split("/")[0]:
        raise SystemExit(f"FATAL: refusing docker hostname in --qdrant-url: {qdrant_url}")

    out_dir = (
        Path(args.out)
        if args.out
        else Path(__file__).resolve().parents[3] / ".work/autoresearch_fp/eval_v8_vs_v9"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "report.json"
    tsv_path = out_dir / "questions.tsv"
    if report_path.exists():
        raise SystemExit(f"FATAL: refusing to overwrite fresh report {report_path}")

    global QUESTIONS
    questions = load_questions(Path(args.questions))
    QUESTIONS = questions
    split_state = attach_split(questions, Path(args.questions))
    print(f"[{qdrant_url}] questions: {len(questions)} (split: {split_state})", flush=True)

    print("Init embedding (host ONNX cache)...", flush=True)
    emb = EmbeddingService()
    encoded = {}
    for q in questions:
        encoded[q["qid"]] = emb.encode_single_full(q["question"])
    print(f"Pre-encoded {len(questions)} questions.", flush=True)

    serene = SereneMindEngine()
    flags = {
        "boundary_guard": getattr(settings, "first_person_boundary_guard_enabled", False),
        "content_quality_gate": getattr(
            settings, "first_person_content_quality_gate_enabled", True
        ),
        "standalone_gate": getattr(settings, "first_person_standalone_gate_enabled", True),
        "serve_unregistered": getattr(settings, "first_person_serve_unregistered", False),
        "question_dense": getattr(settings, "first_person_question_dense_enabled", False),
        "relevance_gate_enabled": getattr(settings, "first_person_relevance_gate_enabled", True),
        "answerability_enabled": getattr(
            settings, "first_person_answerability_check_enabled", True
        ),
    }
    # In this harness, LLM-backed gates are skipped by construction: no LLM call
    # site exists in eval_collection(), only deterministic regex/embedding gates.
    llm_gate_state = {
        "relevance_scorer": "SKIPPED (Haiku relevance gate not called; dry judgment only)",
        "answerability_gate": "SKIPPED (question-only LLM gate not called)",
        "llm_rerank": "SKIPPED",
        "facet_decomposition": "SKIPPED",
        "exact_cache": "NOT USED (no Redis)",
    }

    client = QdrantClient(url=qdrant_url)
    collections = [c.strip() for c in args.collections.split(",") if c.strip()]
    per_collection: dict[str, list[dict[str, Any]]] = {}
    for col in collections:
        per_collection[col] = eval_collection(col, client, encoded, questions, serene, flags)

    summaries = {c: summarize(rows, c) for c, rows in per_collection.items()}
    if len(collections) == 2:
        print_side_by_side(*[per_collection[c] for c in collections])

    print()
    print("=" * 118)
    print("SUMMARY (dry no-LLM)")
    for c in collections:
        s = summaries[c]
        print(
            f"{c}: n={s['n_questions']} on={s['n_on_topic']} ooc={s['n_ooc']} "
            f"showable_dry={s['on_topic_showable_dry']}/{s['n_on_topic']} "
            f"({s['on_topic_showable_dry_frac']:.4f}) abstained_dry={s['on_topic_abstained_dry']} "
            f"ooc_top1_qualify={s['ooc_top1_qualify_dry']} rail={s['rail_blocked']} "
            f"no_gated={s['no_gated_clips']} intF={s['integrity_fail_total']} "
            f"cqF={s['cq_fail_total']} cos_mean={s['top1_cos_mean_showable']}"
        )
    print(
        "is_showable_dry = deterministic gates passed AND a top-N gated clip exists "
        "(Haiku relevance scorer + answerability gate SKIPPED -> upper bound on serving, not a verdict)."
    )

    payload = {
        "meta": {
            "qdrant_url": qdrant_url,
            "collections": collections,
            "questions_path": str(args.questions),
            "split_state": split_state,
            "mode": "dry_no_llm",
            "llm_gates_skipped": llm_gate_state,
            "serve_flags_snapshot": flags,
            "retrieval": {
                "limit": RETRIEVAL_LIMIT,
                "dedup_limit": RETRIEVAL_DEDUP_LIMIT,
                "integrity_check_availability": False,
            },
            "top_n_served": TOP_N,
        },
        "summary": summaries,
        "questions": {c: rows for c, rows in per_collection.items()},
    }
    report_path.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    with tsv_path.open("w", encoding="utf-8") as f:
        f.write(
            "qid\tkind\tsplit\tcollection\trail\tn_raw\tn_integrity_fail\tn_cq_fail\tn_gated\t"
            "top1_dense_cosine\tis_showable_dry\tabstain_reason_dry\tserve_set_ids\n"
        )
        for c in collections:
            for r in sorted(per_collection[c], key=lambda x: x["qid"]):
                f.write(
                    f"{r['qid']}\t{r['kind']}\t{r['split']}\t{c}\t{r['rail'] or ''}\t"
                    f"{r['n_raw']}\t{r['n_integrity_fail']}\t{r['n_cq_fail']}\t{r['n_gated']}\t"
                    f"{r['top1_dense_cosine'] or ''}\t{r['is_showable_dry']}\t"
                    f"{r['abstain_reason_dry'] or ''}\t"
                    f"{','.join(str(x['point_id']) for x in r['serve_set'])}\n"
                )
    print(f"wrote {report_path}")
    print(f"wrote {tsv_path}")

    # Clean exit without onnx/thread shutdown abort (same pattern as eval_v5).
    os._exit(0)


if __name__ == "__main__":
    main()
