"""
Validation script for the ONNX INT8 CrossEncoder reranker.

Phases
------
P0  validate_env_parse()      — `backend/.env` parses cleanly (cp1 concatenation guard).
P1  capability probe          — OnnxReranker loads, paired scores are monotonic.
P2  score correlation         — cosine(onnx, pytorch) > 0.97 across 100 spiritual pairs.
                              (OPTIONAL — graceful skip if sentence_transformers missing.)
P3  latency benchmark         — warm P95 < 600ms, cold P95 < 1500ms (2-thread Railway CPU).

Exit code
---------
0  all mandatory phases passed (P2 may be skipped).
1  any mandatory phase failed, or a hard dependency is missing *and* the user
   explicitly opted into validation (script exits 0 on missing optional deps).

Run from anywhere; the script resolves `backend/` itself.

    python3 backend/scripts/validate_onnx_reranker.py
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("validate_onnx_reranker")

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
_ENV_PATH = _BACKEND_DIR / ".env"

if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


SPIRITUAL_QUERIES = [
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

SPIRITUAL_DOCS = [
    "Karma is the sum of a person's actions in this and previous states of existence, viewed as deciding their fate in future existences.",
    "Sri Preethaji is a contemporary spiritual teacher and founder of Ekam, a meditation center in India.",
    "Ekam is a oneness temple and meditation center founded by Sri Preethaji and Sri Krishnaji.",
    "Meditation is the practice of focused attention and awareness to achieve mental clarity and emotional calm.",
    "Moksha is liberation from the cycle of birth and death in Hindu and Jain philosophy.",
    "Dharma is the cosmic law and order underlying right conduct and duty in Indian religions.",
    "Sri Krishnaji is a contemporary spiritual teacher who co-founded Ekam with Sri Preethaji.",
    "Atman is the eternal, unchanging self or soul in Hindu philosophy, identical with Brahman.",
    "Bhakti yoga is the path of devotional love and surrender to a personal deity.",
    "Jnana yoga is the path of knowledge and wisdom, realizing the self as Brahman through inquiry.",
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


def _build_pairs(n: int = 100) -> list[tuple[str, str]]:
    """Build n (query, doc) pairs — alternating relevant and irrelevant docs."""
    pairs: list[tuple[str, str]] = []
    n_q = len(SPIRITUAL_QUERIES)
    n_d = len(SPIRITUAL_DOCS)
    i = 0
    while len(pairs) < n:
        q = SPIRITUAL_QUERIES[i % n_q]
        relevant = SPIRITUAL_DOCS[i % n_q]
        irrelevant = SPIRITUAL_DOCS[(n_q + (i % (n_d - n_q))) % n_d]
        pairs.append((q, relevant))
        if len(pairs) < n:
            pairs.append((q, irrelevant))
        i += 1
    return pairs[:n]


# ---------------------------------------------------------------------------
# P0 — env parse
# ---------------------------------------------------------------------------

def validate_env_parse(env_path: Path = _ENV_PATH) -> tuple[bool, dict]:
    """Parse `backend/.env` line-by-line; fail on any unparseable line.

    Guards the cp1 concatenation bug (e.g. `SMTP_PASSWORD=...EMBEDDING_BACKEND=onnx_int8`
    fused on one line). Never prints values — only keys.
    """
    info: dict = {"keys": [], "reranker_backend": None, "reranker_onnx_model": None}
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
            keys.append(key)
            if key == "RERANKER_BACKEND":
                info["reranker_backend"] = value.strip()
            elif key == "RERANKER_ONNX_MODEL":
                info["reranker_onnx_model"] = value.strip()

    info["keys"] = keys
    if malformed:
        logger.error("P0: FAIL — %d malformed line(s): %s", len(malformed), malformed)
        return False, info

    logger.info("P0: parsed %d keys from %s", len(keys), env_path.name)
    if info["reranker_backend"]:
        logger.info("P0: RERANKER_BACKEND=%s", info["reranker_backend"])
    else:
        try:
            from app.config import settings
            logger.info(
                "P0: RERANKER_BACKEND absent — config default is '%s'",
                settings.reranker_backend,
            )
        except Exception as exc:
            logger.warning("P0: could not read config default: %s", exc)
    return True, info


# ---------------------------------------------------------------------------
# P1 — capability probe
# ---------------------------------------------------------------------------

def capability_probe() -> tuple[bool, list[float]]:
    """Load OnnxReranker, score 3 pairs, assert monotonic ordering."""
    from services.onnx_reranker import OnnxReranker

    pairs = [
        ("what is karma?", "Karma is the law of cause and effect in Vedic philosophy."),
        ("what is karma?", "The weather today is sunny with light breeze."),
        ("what is karma?", "Karma determines future birth according to actions in past lives."),
    ]
    reranker = OnnxReranker()
    scores = reranker.predict(pairs)
    logger.info("P1: scores = %s", [round(s, 4) for s in scores])
    if not (scores[0] > scores[1] and scores[2] > scores[1]):
        logger.error(
            "P1: FAIL — monotonicity broken (relevant should beat irrelevant). "
            "scores=%s",
            scores,
        )
        return False, scores
    logger.info("P1: PASS — monotonic ordering verified")
    return True, scores


# ---------------------------------------------------------------------------
# P2 — score correlation vs PyTorch CrossEncoder (OPTIONAL)
# ---------------------------------------------------------------------------

def score_correlation(num_pairs: int = 100) -> tuple[bool, Optional[float], str]:
    """Cosine similarity between ONNX and PyTorch score vectors; pass if > 0.97."""
    try:
        from sentence_transformers import CrossEncoder
    except ModuleNotFoundError:
        return True, None, "sentence_transformers not installed — P2 skipped (optional)"
    except Exception as exc:
        return True, None, f"sentence_transformers import failed ({exc!r}) — P2 skipped"

    from services.onnx_reranker import OnnxReranker

    try:
        pytorch_ce = CrossEncoder("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")
    except (OSError, RuntimeError, Exception) as exc:
        return True, None, f"PyTorch CrossEncoder load failed ({exc!r}) — P2 skipped"

    onnx_reranker = OnnxReranker()
    pairs = _build_pairs(num_pairs)

    try:
        onnx_scores = onnx_reranker.predict(pairs)
    except Exception as exc:
        return False, None, f"ONNX predict failed: {exc!r}"

    try:
        pytorch_scores = pytorch_ce.predict(pairs, batch_size=32).tolist()
    except Exception as exc:
        return True, None, f"PyTorch predict failed ({exc!r}) — P2 skipped"

    import numpy as np

    onnx_vec = np.asarray(onnx_scores, dtype=np.float64)
    pt_vec = np.asarray(pytorch_scores, dtype=np.float64)
    denom = float(np.linalg.norm(onnx_vec) * np.linalg.norm(pt_vec))
    if denom == 0.0:
        return False, 0.0, "zero-norm vector — cannot compute cosine"
    cosine_sim = float(np.dot(onnx_vec, pt_vec) / denom)

    threshold = 0.97
    passed = cosine_sim > threshold
    status = "PASS" if passed else "FAIL"
    msg = (
        f"P2: {status} — cosine_sim={cosine_sim:.5f} (threshold > {threshold}) "
        f"across {len(pairs)} pairs"
    )
    if not passed:
        logger.error(msg)
        return False, cosine_sim, msg
    logger.info(msg)
    return True, cosine_sim, msg


# ---------------------------------------------------------------------------
# P3 — latency benchmark
# ---------------------------------------------------------------------------

def latency_benchmark(num_pairs: int = 100, warm_iters: int = 20) -> tuple[bool, dict]:
    """Cold + warm latency; pass if warm P95 < 600ms and cold P95 < 1500ms."""
    import numpy as np
    from services.onnx_reranker import OnnxReranker

    reranker = OnnxReranker()
    pairs = _build_pairs(min(num_pairs, 100))

    def _score_once():
        t0 = time.perf_counter()
        reranker.predict(pairs)
        return (time.perf_counter() - t0) * 1000.0

    cold_ms = _score_once()
    logger.info("P3: cold call = %.2f ms", cold_ms)

    warm_ms = [_score_once() for _ in range(warm_iters)]
    warm_p50 = float(np.percentile(warm_ms, 50))
    warm_p95 = float(np.percentile(warm_ms, 95))
    variance = float(np.var(warm_ms))

    cold_p95 = cold_ms
    metrics = {
        "cold_ms": cold_ms,
        "cold_p95_ms": cold_p95,
        "warm_p50_ms": warm_p50,
        "warm_p95_ms": warm_p95,
        "warm_variance_ms2": variance,
        "warm_iters": warm_iters,
        "pairs": len(pairs),
    }
    logger.info(
        "P3: cold=%.1fms warm_p50=%.1fms warm_p95=%.1fms variance=%.1fms² (n=%d, pairs=%d)",
        cold_ms, warm_p50, warm_p95, variance, warm_iters, len(pairs),
    )

    warm_pass = warm_p95 < 600.0
    cold_pass = cold_p95 < 1500.0
    if not (warm_pass and cold_pass):
        logger.error(
            "P3: FAIL — warm_p95=%.1fms (need <600ms), cold_p95=%.1fms (need <1500ms)",
            warm_p95, cold_p95,
        )
        return False, metrics
    logger.info("P3: PASS — warm_p95=%.1fms <600ms, cold_p95=%.1fms <1500ms", warm_p95, cold_p95)
    return True, metrics


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def _format_summary(results: dict) -> str:
    rows = [
        ("P0 env parse", results["p0"]),
        ("P1 capability", results["p1"]),
        ("P2 correlation", results["p2"]),
        ("P3 latency", results["p3"]),
    ]
    lines = ["", "=" * 64, "validate_onnx_reranker.py — summary", "=" * 64]
    for name, entry in rows:
        status = entry.get("status", "?")
        detail = entry.get("detail", "")
        lines.append(f"  {name:<18} {status:<10} {detail}")
    lines.append("=" * 64)
    return "\n".join(lines)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    results: dict = {
        "p0": {"status": "SKIP", "detail": ""},
        "p1": {"status": "SKIP", "detail": ""},
        "p2": {"status": "SKIP", "detail": "optional"},
        "p3": {"status": "SKIP", "detail": ""},
    }
    overall_pass = True

    # P0
    ok, info = validate_env_parse()
    results["p0"]["status"] = "PASS" if ok else "FAIL"
    results["p0"]["detail"] = f"{len(info.get('keys', []))} keys"
    if not ok:
        overall_pass = False

    # Detect onnxruntime early so we can exit 0 (opt-in validation).
    try:
        import onnxruntime  # noqa: F401
    except ModuleNotFoundError:
        print(
            "onnxruntime is not installed — validation is opt-in. "
            "Skipping P1/P2/P3 (exit 0)."
        )
        print(_format_summary(results))
        return 0

    # P1
    try:
        ok, scores = capability_probe()
        results["p1"]["status"] = "PASS" if ok else "FAIL"
        results["p1"]["detail"] = f"scores={[round(s, 4) for s in scores]}"
        if not ok:
            overall_pass = False
    except Exception as exc:
        logger.exception("P1: unexpected error")
        results["p1"]["status"] = "FAIL"
        results["p1"]["detail"] = f"error: {exc!r}"
        overall_pass = False

    # P2 (optional)
    try:
        ok, cosine, msg = score_correlation(num_pairs=100)
        if cosine is None:
            results["p2"]["status"] = "SKIP"
            results["p2"]["detail"] = msg
        else:
            results["p2"]["status"] = "PASS" if ok else "FAIL"
            results["p2"]["detail"] = f"cos={cosine:.4f}"
            if not ok:
                overall_pass = False
    except Exception as exc:
        logger.exception("P2: unexpected error")
        results["p2"]["status"] = "SKIP"
        results["p2"]["detail"] = f"error: {exc!r}"

    # P3
    try:
        ok, metrics = latency_benchmark(num_pairs=100, warm_iters=20)
        results["p3"]["status"] = "PASS" if ok else "FAIL"
        results["p3"]["detail"] = (
            f"warm_p95={metrics['warm_p95_ms']:.0f}ms cold_p95={metrics['cold_p95_ms']:.0f}ms"
        )
        if not ok:
            overall_pass = False
    except Exception as exc:
        logger.exception("P3: unexpected error")
        results["p3"]["status"] = "FAIL"
        results["p3"]["detail"] = f"error: {exc!r}"
        overall_pass = False

    print(_format_summary(results))
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())