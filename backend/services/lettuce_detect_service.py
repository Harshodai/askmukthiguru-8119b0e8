"""
Mukthi Guru — LettuceDetect Faithfulness Service

Two detection paths, selected by ``settings.lettucedetect_enabled``:

1. **Real LettuceDetect (S3)** — when ``lettucedetect_enabled`` is True and the
   ``lettucedetect`` package imports cleanly. Loads the RAGTruth-trained
   ModernBERT token classifier (``KRLabsOrg/lettucedect-base-modernbert-en-v1``,
   MIT, KRLabsOrg) and asks it for span-level hallucination predictions over
   the (context, question, answer) triple. ``is_faithful`` is True iff the
   detector returns zero hallucinated spans; ``score`` is
   ``1 - max(span confidence)``. The detector is lazy-loaded on first
   ``score_faithfulness`` call so a missing torch/transformers at import time
   does not break process startup.

2. **Heuristic fallback** — the original sentence-split + cosine-similarity
   (or word-overlap when no embedder is wired) path. Used when
   ``lettucedetect_enabled`` is False, when the package fails to import, or
   when the model fails to load. This keeps the build working without the
   heavy ``lettucedetect`` dependency installed.

Contract (preserved across both paths, callers in
``rag/nodes/verification.py``, ``ingest/raptor.py``, ``ingest/quality_gate.py``)::

    score_faithfulness(query, context, answer) -> {
        "is_faithful": bool,
        "score": float,           # 0.0 - 1.0
        "details": str,
        "unsupported_sentences": list[str],   # heuristic path only
    }
"""

import logging
import re
import time

from app.config import settings

logger = logging.getLogger(__name__)


# S3: pinned commit SHA for the LettuceDetect English ModernBERT model,
# resolved 2026-08-11 from the HF API (https://huggingface.co/api/models/
# KRLabsOrg/lettucedect-base-modernbert-en-v1). HF model pinning invariant
# (see root AGENTS.md "Security Invariants"): never download a mutable repo
# head — a later commit can silently change weights/tokenizer/licence.
_LETTUCE_MODEL_ID = "KRLabsOrg/lettucedect-base-modernbert-en-v1"
_LETTUCE_MODEL_REVISION = "bbd77832f52f9bd87546a3924c032467921f5c34"  # resolved 2026-08-11; do not bump to a repo head


class LettuceDetectService:
    """Faithfulness scorer with a real span-level detector behind a flag.

    ``lettucedetect_enabled=True`` activates the RAGTruth-trained
    ModernBERT detector; ``False`` (default) keeps the historical
    heuristic so the build does not hard-depend on torch/transformers.
    """

    def __init__(self, embedder=None) -> None:
        """Initialize the service.

        :param embedder: Optional embedding service used by the heuristic
            fallback path for cosine-similarity scoring. Ignored by the real
            detector path.
        """
        self.embedder = embedder
        self._real_detector = None
        self._real_load_attempted = False
        if getattr(settings, "lettucedetect_enabled", False):
            # Lazy-load on first use, not at construction — model loading can
            # take 10-30s and block the event loop if done eagerly. The
            # ``_real_load_attempted`` flag ensures we only try once per
            # process lifetime so a transient import failure doesn't retry
            # on every chat turn.
            logger.info(
                "LettuceDetectService: real detector enabled (model=%s, revision=%s). "
                "Lazy-loading on first score_faithfulness call.",
                _LETTUCE_MODEL_ID,
                _LETTUCE_MODEL_REVISION,
            )
        else:
            logger.info("LettuceDetectService: heuristic fallback active (lettucedetect_enabled=False).")

    # ------------------------------------------------------------------
    # Real detector loading (S3)
    # ------------------------------------------------------------------

    def _load_real_detector(self):
        """Lazy-load the real LettuceDetect ``HallucinationDetector``.

        Returns the detector instance or ``None`` if the package is not
        importable or the model fails to load. Logs at WARNING level on
        failure so operators see the fallback, not just DEBUG noise.

        The LettuceDetect ``HallucinationDetector`` constructor delegates to
        ``TransformerDetector`` which calls ``AutoModelForTokenClassification
        .from_pretrained(model_path)``. ``from_pretrained`` accepts a
        ``revision=`` kwarg through ``**tok_kwargs``, but the
        ``HallucinationDetector`` facade passes ``**kwargs`` straight through,
        so we let ``huggingface_hub.snapshot_download`` pin the revision and
        hand the local snapshot dir to the detector as ``model_path`` —
        matching the ONNX reranker pattern (``services/onnx_reranker.py::_load``).
        """
        if self._real_load_attempted:
            return self._real_detector
        self._real_load_attempted = True

        try:
            from huggingface_hub import snapshot_download
            from lettucedetect.models.inference import HallucinationDetector
        except ImportError as e:
            logger.warning(
                "LettuceDetect real detector unavailable (ImportError: %s). "
                "Falling back to heuristic. Install lettucedetect>=0.2.2 to enable.",
                e,
            )
            return None

        try:
            # Pin the revision via snapshot_download, then load from the
            # local dir. This is the same pattern as OnnxReranker._load —
            # the package's TransformerDetector calls from_pretrained on
            # the path we give it, so the pinned snapshot is what loads.
            local_path = snapshot_download(
                repo_id=_LETTUCE_MODEL_ID,
                revision=_LETTUCE_MODEL_REVISION,
                resume_download=True,
            )
            self._real_detector = HallucinationDetector(
                method="transformer",
                model_path=local_path,
            )
            logger.info(
                "LettuceDetect real detector loaded: %s @ %s",
                _LETTUCE_MODEL_ID,
                _LETTUCE_MODEL_REVISION,
            )
            return self._real_detector
        except Exception as e:
            logger.warning(
                "LettuceDetect real detector failed to load (%s: %s). "
                "Falling back to heuristic for this process.",
                type(e).__name__,
                e,
            )
            return None

    # ------------------------------------------------------------------
    # Public contract
    # ------------------------------------------------------------------

    def score_faithfulness(self, query: str, context: str, answer: str) -> dict:
        """Evaluate if the generated answer is faithful to the context.

        Returns a dict with ``is_faithful`` (bool), ``score`` (float 0-1),
        ``details`` (str), and ``unsupported_sentences`` (list, heuristic
        path only — empty list on the real-detector path).

        Selects the real LettuceDetect detector when
        ``settings.lettucedetect_enabled`` is True and the package imports;
        otherwise falls back to the sentence-level heuristic below.
        """
        if getattr(settings, "lettucedetect_enabled", False):
            detector = self._load_real_detector()
            if detector is not None:
                return self._score_with_real_detector(detector, query, context, answer)
        return self._score_heuristic(query, context, answer)

    # ------------------------------------------------------------------
    # Real detector path (S3)
    # ------------------------------------------------------------------

    def _score_with_real_detector(self, detector, query: str, context: str, answer: str) -> dict:
        """Run the real LettuceDetect span-level detector."""
        start = time.time()
        if not answer.strip() or not context.strip():
            return {"is_faithful": False, "score": 0.0, "details": "Empty input.", "unsupported_sentences": []}

        # Strip the source citation block the formatter appends — it is
        # not a claim the detector should score against the context.
        clean_answer = re.sub(r"📚 \*Sources & Teachings:\*.*", "", answer, flags=re.DOTALL).strip()
        if not clean_answer:
            return {"is_faithful": False, "score": 0.0, "details": "Empty answer after citation strip.", "unsupported_sentences": []}

        try:
            predictions = detector.predict(
                context=[context],
                question=query if query else None,
                answer=clean_answer,
                output_format="spans",
            )
        except Exception as e:
            logger.warning(
                "LettuceDetect real detector.predict failed (%s: %s). Falling back to heuristic.",
                type(e).__name__,
                e,
            )
            return self._score_heuristic(query, context, answer)

        duration = (time.time() - start) * 1000
        if not predictions:
            return {
                "is_faithful": True,
                "score": 1.0,
                "details": f"real LettuceDetect: no hallucinated spans ({duration:.1f}ms)",
                "unsupported_sentences": [],
            }

        max_conf = max(
            (float(p.get("confidence", 0.0)) for p in predictions),
            default=0.0,
        )
        span_texts = [p.get("text", "") for p in predictions]
        return {
            "is_faithful": False,
            "score": 1.0 - max_conf,
            "details": (
                f"real LettuceDetect: {len(predictions)} hallucinated spans "
                f"(max_conf={max_conf:.3f}, {duration:.1f}ms): "
                + " | ".join(f"'{s}'" for s in span_texts if s)
            ),
            "unsupported_sentences": span_texts,
        }

    # ------------------------------------------------------------------
    # Heuristic fallback path (original logic, C2 emoji branch removed)
    # ------------------------------------------------------------------

    def _score_heuristic(self, query: str, context: str, answer: str) -> dict:
        """Sentence-split + cosine (or word-overlap) heuristic. Original path."""
        start = time.time()
        if not answer.strip() or not context.strip():
            return {"is_faithful": False, "score": 0.0, "details": "Empty input.", "unsupported_sentences": []}

        # Clean answer to remove source citation lists to prevent false negatives
        clean_answer = re.sub(r"📚 \*Sources & Teachings:\*.*", "", answer, flags=re.DOTALL).strip()

        # Split answer into sentences
        sentences = [
            s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_answer) if len(s.strip()) > 10
        ]
        if not sentences:
            return {"is_faithful": False, "score": 0.0, "details": "No testable sentences.", "unsupported_sentences": []}

        # C2: emoji auto-pass branch removed — it bypassed faithfulness scoring unconditionally.
        # (Previously: any answer >200 chars containing 📚 returned is_faithful=True, score=1.0
        # without scoring a single sentence. Unreachable at HEAD but a formatter could
        # reintroduce it; this comment documents the intentional removal.)

        # Split context into paragraphs/chunks
        context_chunks = [c.strip() for c in context.split("\n\n") if c.strip()]
        if not context_chunks:
            context_chunks = [context]

        unsupported_sentences = []
        scores = []

        if self.embedder:
            try:
                # Encode context chunks
                context_embeddings = self.embedder.encode_batch(context_chunks)["dense"]
                import numpy as np

                for sentence in sentences:
                    sentence_emb = self.embedder.encode_single_full(sentence)["dense"]

                    # Compute cosine similarity with all context chunks
                    similarities = []
                    for c_emb in context_embeddings:
                        s_norm = np.array(sentence_emb) / (np.linalg.norm(sentence_emb) + 1e-10)
                        c_norm = np.array(c_emb) / (np.linalg.norm(c_emb) + 1e-10)
                        similarities.append(float(np.dot(s_norm, c_norm)))

                    max_sim = max(similarities) if similarities else 0.0
                    scores.append(max_sim)

                    # S3: doctrine-vocabulary boost removed. It rewarded the surface
                    # feature a fluent fabrication reproduces (a sentence containing
                    # "deeksha" cleared over half the bar), weakening the grounding
                    # check it sat inside. Compare raw similarity to the threshold.
                    threshold = getattr(settings, "lettuce_detect_threshold", 0.25)
                    if max_sim < threshold:
                        unsupported_sentences.append((sentence, max_sim))
            except Exception as e:
                logger.warning(
                    f"LettuceDetect: Semantic scoring failed ({e}), falling back to lexical overlap."
                )
                # Fallback to token-level overlap matching
                for sentence in sentences:
                    overlap = self._compute_lexical_overlap(sentence, context)
                    scores.append(overlap)
                    if overlap < 0.45:
                        unsupported_sentences.append((sentence, overlap))
        else:
            # Word overlap fallback
            for sentence in sentences:
                overlap = self._compute_lexical_overlap(sentence, context)
                scores.append(overlap)
                if overlap < 0.45:
                    unsupported_sentences.append((sentence, overlap))

        avg_score = sum(scores) / len(scores) if scores else 1.0

        # Faithfulness determined by sentence-level scoring only (auto-pass removed)
        is_faithful = len(unsupported_sentences) == 0
        duration = (time.time() - start) * 1000

        details = f"Scored {len(sentences)} sentences in {duration:.2f}ms. "
        if not is_faithful:
            details += f"Hallucination detected in {len(unsupported_sentences)} sentences: "
            details += "; ".join([f"'{s}' (score: {sc:.2f})" for s, sc in unsupported_sentences])
        else:
            details += "All sentences successfully grounded in context."

        logger.info(
            f"LettuceDetect finished: faithful={is_faithful}, score={avg_score:.2f} in {duration:.1f}ms"
        )
        return {
            "is_faithful": is_faithful,
            "score": avg_score,
            "details": details,
            "unsupported_sentences": [s for s, _ in unsupported_sentences],
        }

    def _compute_lexical_overlap(self, sentence: str, context: str) -> float:
        """Calculate word-level overlap ratio between a sentence and context."""
        sentence_words = set(re.findall(r"\w+", sentence.lower()))
        context_words = set(re.findall(r"\w+", context.lower()))

        # Filter out common stop words
        stopwords = {
            "the",
            "and",
            "a",
            "of",
            "to",
            "is",
            "in",
            "that",
            "it",
            "you",
            "for",
            "on",
            "with",
            "as",
            "this",
            "are",
            "by",
        }
        sentence_words = sentence_words - stopwords
        context_words = context_words - stopwords

        if not sentence_words:
            return 1.0

        overlap = sentence_words.intersection(context_words)
        return len(overlap) / len(sentence_words)


if __name__ == "__main__":
    # Self-check: exercise both paths and print results.
    svc = LettuceDetectService(embedder=None)
    ctx = "The capital of France is Paris. The population of France is 67 million."
    faithful = "The capital of France is Paris."
    fabricated = "The capital of France is Paris. The population is 69 million."
    print("heuristic faithful:", svc.score_faithfulness("What is the capital?", ctx, faithful))
    print("heuristic fabricated:", svc.score_faithfulness("What is the capital?", ctx, fabricated))