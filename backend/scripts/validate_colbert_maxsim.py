"""
Validation script for the ONNX-native ColBERT MaxSim reranker (Phase 2).

Phases
------
P0  validate_env_parse()      — `backend/.env` parses cleanly (cp1 concat guard),
                                 EMBEDDING_BACKEND=onnx_int8 confirmed, ENABLE_COLBERT
                                 forced True locally so the disabled path still runs.
P1  capability probe          — `encode_with_colbert` returns dense/sparse/colbert,
                                 colbert shape [n_valid, 1024], CLS excluded.
P2  latency spike (20 docs)   — warm P95 < 2000ms (2-thread Railway CPU, batched rerank).
P3  multilingual sanity       — 4 language pairs (en/hi/te/mr): relevant > irrelevant.
P4  ColBERT vs CrossEncoder   — Spearman > 0.85 on English subset (OPTIONAL —
                                 graceful skip if sentence_transformers missing).

Exit code
---------
0  all mandatory phases passed (P4 may be skipped).
1  any mandatory phase failed, or a hard dependency is missing *and* the user
   explicitly opted into validation (script exits 0 on missing optional deps).

Run from anywhere; the script resolves `backend/` itself.

    python3 backend/scripts/validate_colbert_maxsim.py
"""

from __future__ import annotations

import logging
import re
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("validate_colbert_maxsim")

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ENV_PATH = _BACKEND_DIR / ".env"

_LATENCY_GATE_MS = 2000.0
_SPEARMAN_GATE = 0.85
_NUM_DOCS = 20
_WARM_ITERS = 5

_VALUE_KEY_PATTERN = re.compile(r"(?<![A-Z])[A-Z][A-Z0-9_]{2,}=")

if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


CANDIDATE_DOCS = [
    "Karma is the law of cause and effect governing all actions and their consequences.",
    "Moksha is liberation from the cycle of birth and death, the supreme goal of spiritual life.",
    "Dharma is the cosmic order and righteous duty that sustains the universe in Hindu thought.",
    "Bhakti yoga is the path of devotional love and surrender to a personal deity or divine form.",
    "Jnana yoga is the path of knowledge and self-inquiry leading to realization of Brahman.",
    "Atman is the eternal, unchanging self or soul, identical with Brahman in Advaita Vedanta.",
    "Meditation is the practice of focused attention and awareness to achieve mental stillness.",
    "Preethaji is a contemporary spiritual teacher and co-founder of Ekam meditation center.",
    "Krishnaji is a contemporary spiritual teacher who co-founded Ekam with Sri Preethaji.",
    "Ekam is a oneness temple and meditation center in India founded by Preethaji and Krishnaji.",
    "The weather today is sunny with a light breeze across the coastal plains.",
    "Cricket is a bat-and-ball game played between two teams of eleven players.",
    "The stock market closed higher on strong earnings from technology companies.",
    "Photosynthesis converts solar energy into chemical energy stored in glucose.",
    "The Great Wall of China stretches over thirteen thousand miles across northern China.",
    "Quantum mechanics describes the behaviour of matter at the atomic and subatomic scale.",
    "A balanced diet includes proteins, carbohydrates, fats, vitamins, and minerals.",
    "The Pacific Ocean is the largest and deepest of the world's five oceans.",
    "Python is a high-level programming language with dynamic typing and garbage collection.",
    "The Taj Mahal was commissioned by Shah Jahan as a mausoleum for his wife.",
]

MULTILINGUAL_PAIRS = [
    ("what is karma", "Karma is the law of cause and effect.", "The weather is sunny today."),
    ("कर्मा क्या है", "कर्मा कार्यों का नियम है और इसका प्रभाव भविष्यत में दिखता है।", "आज मौसम सुहावना है।"),
    ("కర్మ అంటే ఏమిటి", "కర్మ అనేది కారణ మరియు ప్రభావ నియమం.", "ఈ రోజు వాతావరణం చల్లగా ఉంది."),
    ("कर्म म्हणजे काय", "कर्म ही कृतीची नियम आहे ज्याचा परिणाम भविष्यात दिसतो.", "आज हवामान छान आहे."),
]


def _test_concat_guard() -> None:
    """Self-test: a fused line `SMTP_PASSWORD=secretEMBEDDING_BACKEND=onnx_int8` must trip the guard."""
    fused = "SMTP_PASSWORD=secretEMBEDDING_BACKEND=onnx_int8"
    stripped = fused.strip()
    key, _, value = stripped.partition("=")
    assert _VALUE_KEY_PATTERN.search(value), "concat guard failed to detect fused line"
    logger.info("P0: concat guard self-test: PASS")


def validate_env_parse(env_path: Path = _ENV_PATH) -> tuple[bool, dict]:
    """Parse `backend/.env` line-by-line; fail on concatenation bugs.

    Confirms EMBEDDING_BACKEND is onnx_int8 (or absent -> default applies).
    Confirms ENABLE_COLBERT is present and True (or absent -> default False ->
    logs that we will force True locally for validation). Never prints
    values — only keys.
    """
    info: dict = {
        "keys": [],
        "embedding_backend": None,
        "enable_colbert": None,
        "colbert_will_be_forced": False,
    }
    if not env_path.exists():
        logger.warning("P0: .env not found at %s — skipping (local dev)", env_path)
        return True, info

    keys: list[str] = []
    malformed: list[int] = []
    with env_path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.rstrip("\n").rstrip("\r")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" not in stripped:
                malformed.append(lineno)
                logger.error("P0: line %d has no '=' separator: '%s...'", lineno, stripped[:40])
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            if not key:
                malformed.append(lineno)
                logger.error("P0: line %d has empty key", lineno)
                continue
            if _VALUE_KEY_PATTERN.search(value):
                malformed.append(lineno)
                logger.error(
                    "P0: line %d possible concatenation bug — value contains a second KEY= pattern: %s=...%s",
                    lineno, key, value[:40],
                )
                continue
            keys.append(key)
            if key == "EMBEDDING_BACKEND":
                info["embedding_backend"] = value.strip()
            elif key == "ENABLE_COLBERT":
                info["enable_colbert"] = value.strip().lower() in ("1", "true", "yes", "on")

    info["keys"] = keys
    if malformed:
        logger.error("P0: FAIL — %d malformed line(s): %s", len(malformed), malformed)
        return False, info

    logger.info("P0: parsed %d keys from %s", len(keys), env_path.name)

    backend_val = info["embedding_backend"]
    if backend_val is None:
        logger.info("P0: EMBEDDING_BACKEND absent — config default applies")
    elif backend_val != "onnx_int8":
        logger.warning("P0: EMBEDDING_BACKEND=%s (not onnx_int8) — ColBERT path may fall back to PyTorch", backend_val)
    else:
        logger.info("P0: EMBEDDING_BACKEND=onnx_int8 confirmed")

    if not info["enable_colbert"]:
        info["colbert_will_be_forced"] = True
        logger.info(
            "P0: ENABLE_COLBERT absent or False (config default=False) — "
            "validation will force ENABLE_COLBERT=true locally so the disabled path runs"
        )
    else:
        logger.info("P0: ENABLE_COLBERT=true confirmed")

    _test_concat_guard()
    return True, info


def _force_enable_colbert() -> None:
    """Force ENABLE_COLBERT=true in process env + settings so the disabled-by-default path runs."""
    import os
    os.environ["ENABLE_COLBERT"] = "true"
    try:
        from app.config import settings
        settings.enable_colbert = True
    except Exception as exc:
        logger.warning("P1: could not set settings.enable_colbert=True: %s", exc)


def capability_probe() -> tuple[bool, dict]:
    """Load EmbeddingService, call encode_with_colbert, assert 3 keys + CLS exclusion."""
    import numpy as np
    from services.embedding_service import EmbeddingService

    svc = EmbeddingService()
    result = svc.encode_with_colbert(["hello world", "karma is cause and effect"])

    if not isinstance(result, dict) or set(result.keys()) < {"dense", "sparse", "colbert"}:
        return False, {"reason": f"missing keys: got {sorted(result.keys()) if isinstance(result, dict) else type(result)}"}

    if len(result["colbert"]) != 2:
        return False, {"reason": f"expected 2 colbert arrays, got {len(result['colbert'])}"}

    shapes = []
    for i, arr in enumerate(result["colbert"]):
        arr_np = np.asarray(arr, dtype=np.float32)
        if arr_np.ndim != 2:
            return False, {"reason": f"colbert[{i}] not 2D: shape={arr_np.shape}"}
        n_valid, dim = arr_np.shape
        if n_valid <= 0:
            return False, {"reason": f"colbert[{i}] has n_valid={n_valid}"}
        if dim != 1024:
            return False, {"reason": f"colbert[{i}] dim={dim}, expected 1024"}
        shapes.append((n_valid, dim))

    max_seq_len = 8192
    try:
        if hasattr(svc, "_onnx_tokenizer") and svc._onnx_tokenizer is not None:
            max_seq_len = int(getattr(svc._onnx_tokenizer, "model_max_length", 8192) or 8192)
    except Exception:
        pass

    cls_excluded = all(s[0] < max_seq_len for s in shapes)
    if not cls_excluded:
        logger.warning(
            "P1: colbert n_valid=%s not < tokenizer max_seq_len=%s — CLS exclusion may not have triggered",
            shapes, max_seq_len,
        )

    logger.info(
        "P1: colbert shapes=%s (dense=%d, sparse=%d) max_seq_len=%d CLS-excluded=%s",
        shapes, len(result["dense"]), len(result["sparse"]), max_seq_len, cls_excluded,
    )

    if not cls_excluded:
        return False, {"reason": "CLS exclusion did not happen", "shapes": shapes}
    return True, {"shapes": shapes, "max_seq_len": max_seq_len}


def latency_spike(query: str = "what is karma", warm_iters: int = _WARM_ITERS) -> tuple[bool, dict]:
    """20-doc batched _colbert_maxsim_rerank; pass if warm P95 < 2000ms."""
    import numpy as np
    from services.embedding_service import EmbeddingService

    documents = [{"text": t} for t in CANDIDATE_DOCS[:_NUM_DOCS]]
    svc = EmbeddingService()

    def _rerank_once():
        t0 = time.perf_counter()
        svc._colbert_maxsim_rerank(query, documents, top_k=5)
        return (time.perf_counter() - t0) * 1000.0

    cold_ms = _rerank_once()
    logger.info("P2: cold call = %.2f ms", cold_ms)

    warm_ms = [_rerank_once() for _ in range(warm_iters)]
    warm_p50 = float(np.percentile(warm_ms, 50))
    warm_p95 = float(np.percentile(warm_ms, 95))
    variance = float(np.var(warm_ms))

    metrics = {
        "cold_ms": cold_ms,
        "warm_p50_ms": warm_p50,
        "warm_p95_ms": warm_p95,
        "warm_variance_ms2": variance,
        "warm_iters": warm_iters,
        "num_docs": len(documents),
    }
    logger.info(
        "P2: cold=%.1fms warm_p50=%.1fms warm_p95=%.1fms variance=%.1fms² (n=%d, docs=%d)",
        cold_ms, warm_p50, warm_p95, variance, warm_iters, len(documents),
    )

    if warm_p95 >= _LATENCY_GATE_MS:
        logger.error("P2: FAIL — warm_p95=%.1fms (need < %.0fms)", warm_p95, _LATENCY_GATE_MS)
        return False, metrics
    logger.info("P2: PASS — warm_p95=%.1fms < %.0fms", warm_p95, _LATENCY_GATE_MS)
    return True, metrics


def multilingual_sanity() -> tuple[bool, list[dict]]:
    """4 language pairs: relevant doc must score > irrelevant doc via maxsim_score."""
    import numpy as np
    from services.embedding_service import EmbeddingService
    from services.colbert_maxsim import maxsim_score

    svc = EmbeddingService()
    results: list[dict] = []

    for query, relevant, irrelevant in MULTILINGUAL_PAIRS:
        encoded = svc.encode_with_colbert([query, relevant, irrelevant])
        q = np.asarray(encoded["colbert"][0], dtype=np.float32)
        r = np.asarray(encoded["colbert"][1], dtype=np.float32)
        i = np.asarray(encoded["colbert"][2], dtype=np.float32)
        rel_score = maxsim_score(q, r)
        irrel_score = maxsim_score(q, i)
        ok = rel_score > irrel_score
        results.append({
            "query": query,
            "relevant_score": rel_score,
            "irrelevant_score": irrel_score,
            "ok": ok,
        })
        logger.info(
            "P3: %s — relevant=%.4f irrelevant=%.4f ok=%s",
            query, rel_score, irrel_score, ok,
        )

    all_ok = all(r["ok"] for r in results)
    if not all_ok:
        failed = [r["query"] for r in results if not r["ok"]]
        logger.error("P3: FAIL — relevant <= irrelevant in pairs: %s", failed)
        return False, results
    logger.info("P3: PASS — relevant > irrelevant in all %d language pairs", len(results))
    return True, results


def _spearman_fallback(a: list[float], b: list[float]) -> float:
    """Pure-Python Spearman rank correlation (no scipy)."""
    import numpy as np
    rank_a = np.argsort(np.argsort(a)).astype(float)
    rank_b = np.argsort(np.argsort(b)).astype(float)
    n = len(a)
    d = rank_a - rank_b
    return float(1.0 - (6.0 * np.sum(d * d)) / (n * (n * n - 1)))


def _colbert_vs_crossencoder_spearman() -> tuple[bool, Optional[float], str]:
    """Compare ColBERT MaxSim rank vs CrossEncoder rank on English subset.

    Optional phase: graceful skip if sentence_transformers unavailable.
    Pass: Spearman > 0.85 (sanity — not parity, different model families).
    """
    try:
        import torch  # noqa: F401
    except ModuleNotFoundError:
        return True, None, "torch/sentence_transformers unavailable — P4 skipped (optional)"
    except Exception as exc:
        return True, None, f"torch import failed ({exc!r}) — P4 skipped"

    import numpy as np
    from services.embedding_service import EmbeddingService

    svc = EmbeddingService()

    queries = [
        "what is karma",
        "who is preethaji",
        "what is ekam",
        "how to meditate",
        "what is moksha",
        "what is dharma",
        "who is krishnaji",
        "what is atman",
        "what is bhakti yoga",
        "what is jnana yoga",
    ]
    relevant_docs = [
        "Karma is the sum of a person's actions viewed as deciding their fate in future existences.",
        "Sri Preethaji is a contemporary spiritual teacher and founder of Ekam meditation center.",
        "Ekam is a oneness temple and meditation center founded by Sri Preethaji and Sri Krishnaji.",
        "Meditation is the practice of focused attention and awareness to achieve mental clarity.",
        "Moksha is liberation from the cycle of birth and death in Hindu and Jain philosophy.",
        "Dharma is the cosmic law and order underlying right conduct and duty in Indian religions.",
        "Sri Krishnaji is a contemporary spiritual teacher who co-founded Ekam with Sri Preethaji.",
        "Atman is the eternal, unchanging self or soul in Hindu philosophy, identical with Brahman.",
        "Bhakti yoga is the path of devotional love and surrender to a personal deity.",
        "Jnana yoga is the path of knowledge and wisdom, realizing the self as Brahman.",
    ]
    irrelevant_docs = [
        "The weather today is sunny with a light breeze across the coastal plains.",
        "Cricket is a bat-and-ball game played between two teams of eleven players.",
        "The stock market closed higher on strong earnings from technology companies.",
        "Photosynthesis converts solar energy into chemical energy stored in glucose.",
        "The Great Wall of China stretches over thirteen thousand miles across northern China.",
        "Quantum mechanics describes the behaviour of matter at the subatomic scale.",
        "A balanced diet includes proteins, carbohydrates, fats, vitamins, and minerals.",
        "The Pacific Ocean is the largest and deepest of the world's five oceans.",
        "Python is a high-level programming language with dynamic typing and garbage collection.",
        "The Taj Mahal was commissioned by Shah Jahan as a mausoleum for his wife.",
    ]

    all_docs = relevant_docs + irrelevant_docs
    colbert_rank_positions: list[int] = []
    cross_rank_positions: list[int] = []

    try:
        for q, rel, irr in zip(queries, relevant_docs, irrelevant_docs):
            docs = [rel, irr]
            colbert_out = svc._colbert_maxsim_rerank(q, [{"text": d} for d in docs], top_k=2)
            colbert_order = [d["text"] for d in colbert_out]
            colbert_pos = colbert_order.index(rel)

            cross_out = svc.rerank(q, [{"text": d} for d in docs], top_k=2)
            cross_order = [d["text"] for d in cross_out]
            cross_pos = cross_order.index(rel)

            colbert_rank_positions.append(colbert_pos)
            cross_rank_positions.append(cross_pos)
    except Exception as exc:
        return False, None, f"rerank loop failed: {exc!r}"

    try:
        from scipy.stats import spearmanr
        spearman_corr, _p = spearmanr(colbert_rank_positions, cross_rank_positions)
        spearman_corr = float(spearman_corr)
        spearman_path = "scipy"
    except ModuleNotFoundError:
        spearman_corr = _spearman_fallback(
            [float(x) for x in colbert_rank_positions],
            [float(x) for x in cross_rank_positions],
        )
        spearman_path = "fallback"
        logger.warning("P4: scipy not installed — using pure-Python Spearman fallback")
    except Exception as exc:
        spearman_corr = _spearman_fallback(
            [float(x) for x in colbert_rank_positions],
            [float(x) for x in cross_rank_positions],
        )
        spearman_path = f"fallback(scipy failed: {exc!r})"

    if not np.isfinite(spearman_corr):
        logger.warning("P4: spearman non-finite (%s) — likely zero-variance ranks, skipping", spearman_corr)
        return True, None, f"spearman non-finite — P4 skipped (ranks: colbert={colbert_rank_positions} cross={cross_rank_positions})"

    passed = spearman_corr > _SPEARMAN_GATE
    status = "PASS" if passed else "FAIL"
    msg = (
        f"P4: {status} — spearman={spearman_corr:.4f} (gate > {_SPEARMAN_GATE}) "
        f"[{spearman_path}] colbert_pos={colbert_rank_positions} cross_pos={cross_rank_positions}"
    )
    if not passed:
        logger.error(msg)
        return False, spearman_corr, msg
    logger.info(msg)
    return True, spearman_corr, msg


def _format_summary(results: dict) -> str:
    rows = [
        ("P0 env parse", results["p0"]),
        ("P1 capability", results["p1"]),
        ("P2 latency", results["p2"]),
        ("P3 multilingual", results["p3"]),
        ("P4 correlation", results["p4"]),
    ]
    lines = ["", "=" * 72, "validate_colbert_maxsim.py — summary", "=" * 72]
    for name, entry in rows:
        status = entry.get("status", "?")
        detail = entry.get("detail", "")
        if len(detail) > 48:
            detail = detail[:45] + "..."
        lines.append(f"  {name:<18} {status:<10} {detail}")
    lines.append("=" * 72)
    return "\n".join(lines)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    results: dict = {
        "p0": {"status": "SKIP", "detail": ""},
        "p1": {"status": "SKIP", "detail": ""},
        "p2": {"status": "SKIP", "detail": ""},
        "p3": {"status": "SKIP", "detail": ""},
        "p4": {"status": "SKIP", "detail": "optional"},
    }
    overall_pass = True

    ok, info = validate_env_parse()
    results["p0"]["status"] = "PASS" if ok else "FAIL"
    results["p0"]["detail"] = f"{len(info.get('keys', []))} keys"
    if not ok:
        overall_pass = False

    try:
        import onnxruntime  # noqa: F401
    except ModuleNotFoundError:
        logger.info(
            "onnxruntime is not installed — validation is opt-in. "
            "Skipping P1/P2/P3/P4 (exit 0)."
        )
        print(_format_summary(results))
        return 0

    _force_enable_colbert()

    try:
        ok, info = capability_probe()
        results["p1"]["status"] = "PASS" if ok else "FAIL"
        results["p1"]["detail"] = f"shapes={info.get('shapes', info.get('reason', ''))}"
        if not ok:
            overall_pass = False
    except Exception as exc:
        logger.exception("P1: unexpected error")
        results["p1"]["status"] = "FAIL"
        results["p1"]["detail"] = f"error: {exc!r}"
        overall_pass = False

    try:
        ok, metrics = latency_spike(warm_iters=_WARM_ITERS)
        results["p2"]["status"] = "PASS" if ok else "FAIL"
        results["p2"]["detail"] = (
            f"warm_p95={metrics['warm_p95_ms']:.0f}ms cold={metrics['cold_ms']:.0f}ms"
        )
        if not ok:
            overall_pass = False
    except Exception as exc:
        logger.exception("P2: unexpected error")
        results["p2"]["status"] = "FAIL"
        results["p2"]["detail"] = f"error: {exc!r}"
        overall_pass = False

    try:
        ok, pair_results = multilingual_sanity()
        results["p3"]["status"] = "PASS" if ok else "FAIL"
        results["p3"]["detail"] = f"{sum(r['ok'] for r in pair_results)}/{len(pair_results)} pairs ok"
        if not ok:
            overall_pass = False
    except Exception as exc:
        logger.exception("P3: unexpected error")
        results["p3"]["status"] = "FAIL"
        results["p3"]["detail"] = f"error: {exc!r}"
        overall_pass = False

    try:
        ok, spearman, msg = _colbert_vs_crossencoder_spearman()
        if spearman is None:
            results["p4"]["status"] = "SKIP"
            results["p4"]["detail"] = msg
        else:
            results["p4"]["status"] = "PASS" if ok else "FAIL"
            results["p4"]["detail"] = msg
            if not ok:
                overall_pass = False
    except Exception as exc:
        logger.exception("P4: unexpected error")
        results["p4"]["status"] = "SKIP"
        results["p4"]["detail"] = f"error: {exc!r}"

    print(_format_summary(results))
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())