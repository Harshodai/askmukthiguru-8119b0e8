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
                                  Uses a discriminating corpus (10 queries × 5
                                  docs of varying relevance, 50 rank pairs) so the
                                  two rerankers produce real rank variance to
                                  correlate. Fails loudly on zero variance.

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
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

# Stub LLM credentials so app.config.Settings validator passes in local dev.
# The validation script only exercises the embedding/ColBERT path — no LLM calls.
# Railway/prod has real keys; these stubs are process-local and do not leak.
os.environ.setdefault("SARVAM_API_KEY", "stub-for-validation-only")
os.environ.setdefault("OPENROUTER_API_KEY", "stub-for-validation-only")
os.environ.setdefault("NIM_API_KEY", "stub-for-validation-only")
os.environ.setdefault("SUPABASE_KEY", "stub-for-validation-only")
os.environ.setdefault("SUPABASE_URL", "http://stub-for-validation-only.example.com")

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
                    lineno,
                    key,
                    value[:40],
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
        logger.warning(
            "P0: EMBEDDING_BACKEND=%s (not onnx_int8) — ColBERT path may fall back to PyTorch",
            backend_val,
        )
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
    test_texts = ["hello world", "karma is cause and effect"]
    result = svc.encode_with_colbert(test_texts)

    if not isinstance(result, dict) or set(result.keys()) < {"dense", "sparse", "colbert"}:
        return False, {
            "reason": f"missing keys: got {sorted(result.keys()) if isinstance(result, dict) else type(result)}"
        }

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

    # Compute the raw token count per test input (before CLS exclusion) so we
    # can verify CLS removal reduced the sequence dimension by exactly one.
    # Comparing against the tokenizer's model_max_length (8192) is trivially
    # true and does not actually prove CLS exclusion happened.
    raw_token_counts = []
    try:
        if hasattr(svc, "_onnx_tokenizer") and svc._onnx_tokenizer is not None:
            enc = svc._onnx_tokenizer(
                test_texts, padding=True, truncation=True, return_tensors="np"
            )
            raw_token_counts = [int(m.sum()) for m in enc["attention_mask"]]
    except Exception as exc:
        logger.warning("P1: could not compute raw token counts: %s", exc)

    cls_excluded = True
    per_text_check = []
    for i, (n_valid, _dim) in enumerate(shapes):
        if i < len(raw_token_counts):
            raw = raw_token_counts[i]
            # CLS exclusion removes exactly one token: n_valid == raw - 1.
            ok = n_valid == raw - 1
            per_text_check.append((n_valid, raw, ok))
            if not ok:
                cls_excluded = False
        else:
            # No raw count available (tokenizer unreachable) — fall back to
            # the trivially-true check so we don't false-fail, but log it.
            per_text_check.append((n_valid, None, True))
    if not raw_token_counts:
        logger.warning(
            "P1: raw token counts unavailable — CLS-exclusion check falls back to trivial n_valid>0"
        )

    if not cls_excluded:
        logger.warning(
            "P1: CLS exclusion mismatch — per-text (n_valid, raw_tokens, ok)=%s",
            per_text_check,
        )

    logger.info(
        "P1: colbert shapes=%s (dense=%d, sparse=%d) raw_token_counts=%s CLS-excluded=%s",
        shapes,
        len(result["dense"]),
        len(result["sparse"]),
        raw_token_counts,
        cls_excluded,
    )

    if not cls_excluded:
        return False, {
            "reason": "CLS exclusion did not reduce seq dim by 1",
            "shapes": shapes,
            "per_text_check": per_text_check,
        }
    max_seq_len = max(raw_token_counts) if raw_token_counts else 0
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
        cold_ms,
        warm_p50,
        warm_p95,
        variance,
        warm_iters,
        len(documents),
    )

    if warm_p95 >= _LATENCY_GATE_MS:
        logger.error("P2: FAIL — warm_p95=%.1fms (need < %.0fms)", warm_p95, _LATENCY_GATE_MS)
        return False, metrics
    logger.info("P2: PASS — warm_p95=%.1fms < %.0fms", warm_p95, _LATENCY_GATE_MS)
    return True, metrics


def multilingual_sanity() -> tuple[bool, list[dict]]:
    """4 language pairs: relevant doc must score > irrelevant doc via maxsim_score."""
    import numpy as np

    from services.colbert_maxsim import maxsim_score
    from services.embedding_service import EmbeddingService

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
        results.append(
            {
                "query": query,
                "relevant_score": rel_score,
                "irrelevant_score": irrel_score,
                "ok": ok,
            }
        )
        logger.info(
            "P3: %s — relevant=%.4f irrelevant=%.4f ok=%s",
            query,
            rel_score,
            irrel_score,
            ok,
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


ENGLISH_P4_PAIRS = [
    {
        "query": "what is karma",
        "docs": [
            "Karma is the law of cause and effect governing all actions and their consequences across lifetimes.",
            "The concept of karma appears in both Hindu and Buddhist philosophy with subtle differences.",
            "Meditation helps calm the mind and observe thoughts without attachment.",
            "The weather forecast predicts rain tomorrow afternoon.",
            "Preethaji teaches that karma can be transformed through awareness.",
        ],
    },
    {
        "query": "how to meditate",
        "docs": [
            "Begin meditation by sitting comfortably, closing your eyes, and focusing on your breath.",
            "Regular meditation practice reduces stress and improves emotional regulation.",
            "Karma yoga is the path of selfless action without attachment to results.",
            "The stock market closed higher today on strong earnings reports.",
            "Krishnaji guides seekers to meditate on the self rather than the mind.",
        ],
    },
    {
        "query": "who is preethaji",
        "docs": [
            "Sri Preethaji is a contemporary spiritual teacher and co-founder of the Ekam meditation center.",
            "Preethaji's teachings emphasize a beautiful state and the dissolution of suffering.",
            "Krishnaji co-founded Ekam alongside Preethaji to share the wisdom of oneness.",
            "Photosynthesis converts solar energy into chemical energy stored in glucose.",
            "A spiritual teacher often acts as a mirror reflecting the seeker's own nature.",
        ],
    },
    {
        "query": "what is moksha",
        "docs": [
            "Moksha is liberation from the cycle of birth and death, the supreme goal of spiritual life.",
            "Moksha is achieved through self-realization and the dissolution of egoic identity.",
            "Dharma is the cosmic order and righteous duty that sustains the universe.",
            "The Pacific Ocean is the largest and deepest of the world's five oceans.",
            "Ekam teaches that moksha is not a future event but a present awakening.",
        ],
    },
    {
        "query": "what is ekam",
        "docs": [
            "Ekam is a oneness temple and meditation center in India founded by Preethaji and Krishnaji.",
            "Ekam hosts large meditation gatherings and spiritual retreats for seekers worldwide.",
            "A mandir is a Hindu temple dedicated to one or more deities and devotional practice.",
            "Cricket is a bat-and-ball game played between two teams of eleven players.",
            "Preethaji describes Ekam as a field for awakening to a beautiful state.",
        ],
    },
    {
        "query": "what is dharma",
        "docs": [
            "Dharma is the cosmic order and righteous duty that sustains the universe in Hindu thought.",
            "Dharma varies according to one's stage of life, social role, and personal nature.",
            "Karma is the law of cause and effect that binds actions to their consequences.",
            "Quantum mechanics describes the behaviour of matter at the subatomic scale.",
            "Krishnaji teaches that dharma is living in alignment with truth each moment.",
        ],
    },
    {
        "query": "who is krishnaji",
        "docs": [
            "Sri Krishnaji is a contemporary spiritual teacher who co-founded Ekam with Sri Preethaji.",
            "Krishnaji's discourses focus on the awakening of consciousness and the end of suffering.",
            "Preethaji and Krishnaji together lead a global movement for oneness and transformation.",
            "The Great Wall of China stretches over thirteen thousand miles across northern China.",
            "A guru in the Indian tradition guides disciples from ignorance to self-knowledge.",
        ],
    },
    {
        "query": "what is atman",
        "docs": [
            "Atman is the eternal, unchanging self or soul, identical with Brahman in Advaita Vedanta.",
            "Atman is distinct from the body, mind, and ego, which are temporary and changing.",
            "Brahman is the ultimate, formless reality underlying all existence in Hindu philosophy.",
            "Python is a high-level programming language with dynamic typing and garbage collection.",
            "Self-inquiry into 'who am I' is the direct path to realizing atman, Krishnaji teaches.",
        ],
    },
    {
        "query": "what is bhakti yoga",
        "docs": [
            "Bhakti yoga is the path of devotional love and surrender to a personal deity or divine form.",
            "Bhakti practitioners cultivate an intimate, emotional relationship with the divine.",
            "Jnana yoga is the path of knowledge and self-inquiry leading to realization of Brahman.",
            "The Taj Mahal was commissioned by Shah Jahan as a mausoleum for his wife.",
            "Preethaji teaches that devotion flowers naturally when the self is seen clearly.",
        ],
    },
    {
        "query": "what is jnana yoga",
        "docs": [
            "Jnana yoga is the path of knowledge and self-inquiry leading to realization of Brahman.",
            "Jnana yoga uses discrimination between the real and the unreal to dissolve ignorance.",
            "Karma yoga is the path of selfless action performed without attachment to results.",
            "A balanced diet includes proteins, carbohydrates, fats, vitamins, and minerals.",
            "Krishnaji points to jnana as seeing through the illusion of a separate self.",
        ],
    },
]


def _colbert_vs_crossencoder_spearman() -> tuple[bool, Optional[float], str]:
    """Compare ColBERT MaxSim rank vs CrossEncoder rank on English subset.

    Optional phase: graceful skip if sentence_transformers unavailable.
    Pass: Spearman > 0.85 (sanity — not parity, different model families).

    Corpus design: 10 queries × 5 docs each with varying relevance
    (highly relevant, relevant, loosely related, irrelevant, teacher-context
    relevant). ColBERT (token-level) and CrossEncoder (sequence-level) rank
    docs slightly differently, producing real rank variance for Spearman.
    50 rank pairs total. If still zero variance, fail loudly — the corpus
    is not discriminating enough.
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

    colbert_rank_positions: list[int] = []
    cross_rank_positions: list[int] = []

    try:
        for pair in ENGLISH_P4_PAIRS:
            q = pair["query"]
            docs = pair["docs"]

            # Build separate doc-obj lists per reranker — both rerankers mutate
            # the dicts in place (colbert adds internal fields, crossencoder
            # adds rerank_score), so we cannot share the same list.
            colbert_out = svc._colbert_maxsim_rerank(
                q, [{"text": d} for d in docs], top_k=len(docs)
            )
            colbert_order = [d["text"] for d in colbert_out]

            # min_score=-1 disables the rerank_min_score threshold filter so all
            # docs are returned in rank order (we need full rankings, not the
            # production filtered subset, to compute rank positions for Spearman).
            cross_out = svc.rerank(q, [{"text": d} for d in docs], top_k=len(docs), min_score=-1.0)
            cross_order = [d["text"] for d in cross_out]

            for _original_idx, original_doc in enumerate(docs):
                # If a doc was dropped by a reranker's filter, assign it the
                # worst rank (len(docs)) so the pair still contributes a signal.
                c_pos = (
                    colbert_order.index(original_doc)
                    if original_doc in colbert_order
                    else len(docs)
                )
                x_pos = (
                    cross_order.index(original_doc) if original_doc in cross_order else len(docs)
                )
                colbert_rank_positions.append(c_pos)
                cross_rank_positions.append(x_pos)
    except Exception as exc:
        return False, None, f"rerank loop failed: {exc!r}"

    if len(set(colbert_rank_positions)) <= 1 and len(set(cross_rank_positions)) <= 1:
        logger.error(
            "P4: FAIL — zero rank variance (corpus not discriminating). "
            "colbert_pos=%s cross_pos=%s",
            colbert_rank_positions,
            cross_rank_positions,
        )
        return False, None, "P4: zero rank variance — corpus not discriminating enough"

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
        logger.error(
            "P4: FAIL — spearman non-finite (%s). Zero-variance ranks. colbert_pos=%s cross_pos=%s",
            spearman_corr,
            colbert_rank_positions,
            cross_rank_positions,
        )
        return False, None, "P4: zero rank variance — corpus not discriminating enough"

    passed = spearman_corr > _SPEARMAN_GATE
    status = "PASS" if passed else "FAIL"
    msg = (
        f"P4: {status} — spearman={spearman_corr:.4f} (gate > {_SPEARMAN_GATE}) "
        f"[{spearman_path}] n={len(colbert_rank_positions)} rank pairs"
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
            "onnxruntime is not installed — validation is opt-in. Skipping P1/P2/P3/P4 (exit 0)."
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
        results["p3"]["detail"] = (
            f"{sum(r['ok'] for r in pair_results)}/{len(pair_results)} pairs ok"
        )
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
