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
import threading
import time
from typing import Any, ClassVar

from app.config import settings
from services.native_inference_gate import NativeInferenceBusy, native_inference

# Slack added to the caller's own verification budget when waiting for the
# shared torch module.
_PREDICT_LOCK_SLACK_S = 2.0
_PREDICT_LOCK_FALLBACK_S = 10.0


def _predict_lock_timeout() -> float:
    """How long to wait for the shared detector before shedding.

    Deliberately tied to `faithfulness_verification_timeout` (default 8s), which
    is the budget `_score_faithfulness_bounded` gives this call. A longer wait is
    not patience, it is a leak: that wrapper uses `asyncio.wait_for` over
    `asyncio.to_thread`, and cancelling a `wait_for` does NOT stop the thread.
    A thread parked on this lock after its caller has already given up still
    occupies a threadpool slot and will still run a now-worthless NLI pass when
    the lock frees. An earlier draft of this used a flat 120s, which under load
    would queue threads for two minutes on behalf of callers that left after
    eight seconds.
    """
    try:
        from app.config import settings

        budget = float(getattr(settings, "faithfulness_verification_timeout", 0) or 0)
    except Exception:  # pragma: no cover - config must never break scoring
        budget = 0.0
    return (budget + _PREDICT_LOCK_SLACK_S) if budget > 0 else _PREDICT_LOCK_FALLBACK_S


logger = logging.getLogger(__name__)


# S3: pinned commit SHA for the LettuceDetect English ModernBERT model,
# resolved 2026-08-11 from the HF API (https://huggingface.co/api/models/
# KRLabsOrg/lettucedect-base-modernbert-en-v1). HF model pinning invariant
# (see root AGENTS.md "Security Invariants"): never download a mutable repo
# head — a later commit can silently change weights/tokenizer/licence.
_LETTUCE_MODEL_ID = "KRLabsOrg/lettucedect-base-modernbert-en-v1"
_LETTUCE_MODEL_REVISION = (
    "bbd77832f52f9bd87546a3924c032467921f5c34"  # resolved 2026-08-11; do not bump to a repo head
)


_SOURCES_BLOCK_RE = re.compile(r"📚 \*Sources & Teachings:\*.*", re.DOTALL)
# Inline attribution the formatter injects: "[Source: <title>]", "[CITE:2]", "[3]".
_INLINE_CITE_RE = re.compile(r"\[\s*(?:source\s*:[^\]]*|cite\s*:\s*\d+|\d+)\s*\]", re.IGNORECASE)
# A bracketed link must be consumed whole: stripping the URL first leaves the
# opening "[" behind, because \S+ swallows the closing bracket.
_BRACKETED_URL_RE = re.compile(r"[ \t]*\[\s*https?://[^\]]*\]")
# The paren form of the same thing. Its absence was not cosmetic: the greedy
# _URL_RE below matches \S+, so it swallowed the closing paren of a markdown
# link and left a bare "(" behind -- which then failed the CTA-line pattern
# (anchored at end of line) and was scored as an unsupported claim. A live
# 2026-09-15 trace shows "Watch more here:(" alone dropping faithfulness
# from 1.0 to 0.88 and forcing a redaction pass on a fully grounded answer.
_PAREN_URL_RE = re.compile(r"[ \t]*\(\s*https?://[^)]*\)")
_URL_RE = re.compile(r"https?://\S+")
# An empty pair left behind once the marker inside it is removed ("[[1]]" -> "[]").
_EMPTY_BRACKETS_RE = re.compile(r"[ \t]*(?:\[\s*\]|\(\s*\))")
# Trailing call-to-action lines the formatter appends. Matched only when the
# line is a CTA and nothing else, so a teaching that happens to contain the word
# "watch" is never dropped.
# A call-to-action fragment left at the end of a line once its link is gone
# ("Watch more here:"). Anchored to end-of-line and required to close on
# here/more/below so an ordinary teaching — "we watch the breath carefully" —
# is never touched.
_CTA_LINE_RE = re.compile(
    r"[ \t]*\b(?:watch|listen|read|see|learn|explore)\b[^.\n]{0,40}?\b(?:here|more|below)\b\s*:?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_attribution_markup(answer: str) -> str:
    """Remove citation markup and link chrome before scoring.

    A span detector has no way to ground "[Source: <video title>]" or a bare
    YouTube URL in the retrieved context, so it flags them as hallucinated and
    they sink otherwise-grounded answers. Three of five rejected claims in the
    2026-09-12 trace were markers; a later trace scored the whole line
    "Watch more here: [https://youtube.com/...]" at 0.00 and counted it against
    the answer. None of this is a claim the model made about the teachings — it
    is formatter output, and stripping it tightens nothing and loosens nothing.
    """
    text = _SOURCES_BLOCK_RE.sub("", answer or "")
    text = _INLINE_CITE_RE.sub("", text)
    text = _BRACKETED_URL_RE.sub("", text)
    text = _PAREN_URL_RE.sub("", text)
    text = _URL_RE.sub("", text)
    text = _EMPTY_BRACKETS_RE.sub("", text)
    text = _CTA_LINE_RE.sub("", text)
    return text.strip()


def _norm_for_span_match(text: str) -> str:
    """Normalise a span or claim for substring comparison.

    Detector spans carry leading/trailing whitespace and their own casing;
    collapse both so a span can be located inside the claim it came from.
    """
    return re.sub(r"\s+", " ", (text or "").strip().lower())


# Pastoral openers the persona is *instructed* to produce. `system.py:90` tells
# the guru to "End with a reflective or encouraging closing sentence", and the
# faithfulness gate was then scoring that sentence as an unsupported factual
# claim -- a direct contradiction that cost roughly one claim in eight on every
# answer and pushed otherwise-grounded teachings below `faithfulness_floor`.
# A live 2026-09-15 trace on "Explain the first sacred secret." scored
# "Reflect on this deeply." at 0.348/unsupported and shipped the excerpt
# boilerplate instead of the teaching.
#
# ponytail: prefix list, not a POS tagger. A verb-first imperative needs real
# parsing to detect in general; these are the forms this persona actually
# emits. If the closing vocabulary broadens, move to spaCy's tagger rather
# than growing this list indefinitely.
_NON_ASSERTION_PREFIXES = (
    "reflect",
    "consider",
    "notice",
    "observe",
    "take a moment",
    "take a deep breath",
    "sit with",
    "allow yourself",
    "ask yourself",
    "breathe",
    "pause",
    "let this",
    "may you",
    "close your eyes",
    "bring your attention",
    "feel into",
    "hold space",
    "remember that",
    "rest in",
    "gently",
    "quietly",
    "with each breath",
    "as you reflect",
    "in your journey",
    "in your daily life",
    "stay in this",
)


# An optative ("may this ...", "may your ...") is a blessing, not a claim. The
# prefix tuple above only caught the exact string "may you", so the persona's
# very common closing line -- "May this knowledge bring a smile to your heart as
# you continue your journey." -- was scored as a factual assertion, matched
# against doctrine, and returned 0.005. Measured live 2026-09-18 on a memory
# recall answer: two claims, the real one at 1.00 and the blessing at 0.005,
# averaged to 0.50, fell under the 0.60 floor, and sent a correct answer down
# the grounded_partial_evidence path.
#
# Excluding it is not a weaker gate. A blessing has no truth value, so there is
# nothing for the scorer to match and its low score carries no information --
# it is indistinguishable from a fabrication while being the opposite of one.
# The month "May" is excluded by requiring a pronoun/determiner after it.
_OPTATIVE_RE = re.compile(
    r"^may\s+(?:you|your|this|these|that|those|the|it|we|our|all|he|she|they|his|her|their)\b",
    re.IGNORECASE,
)
# Kept deliberately narrow. A bare "blessings" prefix would also swallow
# "Blessings are described in the teachings as ...", which IS a checkable claim
# about doctrine -- and dropping a real claim from the denominator is the one
# direction that weakens the gate rather than de-noising it.
_BENEDICTION_PREFIXES = (
    "wishing you",
    "blessings to you",
    "blessings upon",
    "with love and blessings",
    "go well",
)


def _is_assertion(sentence: str) -> bool:
    """True when a sentence states something that could be checked against sources.

    A question cannot hallucinate and an invitation to the seeker asserts
    nothing about the teachings, so neither belongs in a faithfulness
    denominator. Scoring them does not make the gate stricter -- it makes it
    noisier, because the scorer has nothing to match them against and reports a
    low similarity that reads identically to a fabricated claim.
    """
    stripped = (sentence or "").strip()
    if not stripped:
        return False
    if stripped.endswith("?"):
        return False
    lowered = stripped.lower()
    # Strip leading non-alphanumerics (emojis, list bullets, numbers, quotes)
    lowered = re.sub(r"^[^\w]+", "", lowered).strip()
    # Strip conversational addressing/salutations
    lowered = re.sub(r"^(?:dear one|beloved|friend|seeker)[,\s]+", "", lowered).strip()
    if _OPTATIVE_RE.match(lowered):
        return False
    if lowered.startswith(_BENEDICTION_PREFIXES):
        return False
    return not lowered.startswith(_NON_ASSERTION_PREFIXES)


def _split_claims(text: str) -> list[str]:
    """Split into checkable claims, dropping questions and pastoral imperatives.

    Falls back to the unfiltered sentences when filtering would empty the list:
    an answer made entirely of non-assertions has not been *verified*, and
    returning zero claims would score it a perfect 1.0.
    """
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 10]
    assertions = [s for s in sentences if _is_assertion(s)]
    return assertions or sentences


# ---------------------------------------------------------------------------
# Contradiction Detection Invariants & Classification (Workstream W5)
# ---------------------------------------------------------------------------

_CANONICAL_DOCTRINE_CONTRADICTIONS = (
    (
        re.compile(
            r"\b(?:three|four|five|six|seven|eight|nine|ten|\d+)\s+states\s+of\s+being\b",
            re.IGNORECASE,
        ),
        "Doctrine invariant: Ekam/Oneness doctrine asserts only two states of being (suffering and beautiful state).",
    ),
    (
        re.compile(r"\b(?:multiple|many|several)\s+states\s+of\s+being\b", re.IGNORECASE),
        "Doctrine invariant: Ekam/Oneness doctrine asserts only two states of being.",
    ),
    (
        re.compile(
            r"\bsuffering\s+is\s+(?:the\s+)?natural(?:\s+state|\s+to\b|\s+for\b)",
            re.IGNORECASE,
        ),
        "Doctrine invariant: Suffering is not natural to human consciousness.",
    ),
    (
        re.compile(
            r"\b(?:escape|retreat|flee)\s+to\s+(?:the\s+)?(?:himalayas|mountains|forests|caves)\b",
            re.IGNORECASE,
        ),
        "Doctrine invariant: The teachings do not advocate renunciation or escaping to the mountains.",
    ),
    (
        re.compile(
            r"\brenounce\s+(?:the\s+world|your\s+family|all\s+possessions|marriage|society)\b",
            re.IGNORECASE,
        ),
        "Doctrine invariant: The teachings do not advocate renouncing worldly life or family.",
    ),
    (
        re.compile(
            r"\b(?:wealth|money)\s+is\s+(?:evil|bad|sinful|unspiritual|a\s+sin)\b",
            re.IGNORECASE,
        ),
        "Doctrine invariant: Wealth creation from a beautiful state is encouraged, not evil.",
    ),
    (
        re.compile(
            r"\bthinking\s+about\s+yourself\s+is\s+(?:evil|sinful|a\s+sin)\b",
            re.IGNORECASE,
        ),
        "Doctrine invariant: Self-absorption causes suffering, but is not considered a sin or evil.",
    ),
)

_NUM_WORDS: dict[str, int] = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "single": 1,
}

_NUM_PHRASE_RE = re.compile(
    r"\b(?:only\s+)?(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)\s+([a-z]{3,20}(?:\s+[a-z]{3,20}){0,3})\b",
    re.IGNORECASE,
)

_NUM_IGNORED_ENTITIES = {
    "minutes",
    "hours",
    "days",
    "weeks",
    "months",
    "years",
    "seconds",
    "percent",
    "times",
    "people",
    "persons",
    "participants",
    "questions",
    "pages",
    "chapters",
    "verses",
    "lines",
}


def _parse_num(tok: str) -> int | None:
    tok_clean = tok.strip().lower()
    if tok_clean.isdigit():
        return int(tok_clean)
    return _NUM_WORDS.get(tok_clean)


def _extract_num_phrases(text: str) -> list[tuple[int, str]]:
    phrases: list[tuple[int, str]] = []
    for match in _NUM_PHRASE_RE.finditer(text):
        num_str, entity = match.group(1), match.group(2)
        num_val = _parse_num(num_str)
        if num_val is None:
            continue
        norm_entity = " ".join(entity.lower().split())
        first_word = norm_entity.split()[0]
        if first_word in _NUM_IGNORED_ENTITIES or norm_entity in _NUM_IGNORED_ENTITIES:
            continue
        phrases.append((num_val, norm_entity))
    return phrases


_NEGATION_WORDS = {
    "not",
    "no",
    "never",
    "cannot",
    "can't",
    "neither",
    "nor",
    "isn't",
    "aren't",
    "wasn't",
    "weren't",
    "doesn't",
    "don't",
    "didn't",
    "won't",
    "wouldn't",
    "hardly",
    "scarcely",
    "barely",
}

_STOP_WORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "and",
    "or",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "that",
    "this",
    "these",
    "those",
    "it",
    "its",
    "as",
    "from",
    "into",
    "also",
    "than",
    "then",
    "there",
    "here",
}

_ANTONYM_PAIRS = {
    ("natural", "unnatural"),
    ("natural", "artificial"),
    ("permanent", "temporary"),
    ("connected", "disconnected"),
    ("peace", "conflict"),
    ("truth", "illusion"),
    ("conscious", "unconscious"),
    ("separable", "inseparable"),
}


def _detect_contradiction(
    claim: str,
    context: str,
    context_chunks: list[str] | None = None,
) -> tuple[bool, str | None]:
    """Check if an assertion directly contradicts context or canonical doctrine.

    Returns (True, reason) if contradictory, (False, None) otherwise.
    Optatives, blessings, questions, and non-assertions always return (False, None)
    per L-VERIFY-4.
    """
    if not _is_assertion(claim):
        return False, None

    clean_claim = claim.strip()
    if not clean_claim:
        return False, None

    # 1. Canonical doctrine invariants
    for pattern, reason in _CANONICAL_DOCTRINE_CONTRADICTIONS:
        if pattern.search(clean_claim):
            return True, reason

    # 2. Numerical mutual exclusivity against context
    claim_nums = _extract_num_phrases(clean_claim)
    if claim_nums and context:
        ctx_nums = _extract_num_phrases(context)
        for c_val, c_ent in claim_nums:
            for ctx_val, ctx_ent in ctx_nums:
                if c_val != ctx_val:
                    # Match exact entity or substantial substring overlap
                    if c_ent == ctx_ent or (
                        len(c_ent) >= 6 and (c_ent in ctx_ent or ctx_ent in c_ent)
                    ):
                        return (
                            True,
                            f"Numerical mutual exclusivity contradiction on '{c_ent}': "
                            f"context asserts {ctx_val}, claim asserts {c_val}.",
                        )

    # 3. Contextual polarity inversion & antonym opposition
    if not context:
        return False, None

    claim_tokens = [w.lower() for w in re.findall(r"\b[a-z]{2,}\b", clean_claim)]
    claim_negations = [w for w in claim_tokens if w in _NEGATION_WORDS]
    claim_content = set(
        w for w in claim_tokens if w not in _STOP_WORDS and w not in _NEGATION_WORDS
    )
    if len(claim_content) < 3:
        return False, None

    claim_neg = len(claim_negations) % 2 == 1

    # Split context into sentences and clauses for fine-grained alignment
    ctx_sentences = [
        s.strip()
        for s in re.split(r"[.!?\n]+|;\s*|,\s+(?:and|but|while|whereas)\s+", context)
        if len(s.strip()) > 10
    ]

    for ctx_sent in ctx_sentences:
        ctx_tokens = [w.lower() for w in re.findall(r"\b[a-z]{2,}\b", ctx_sent)]
        ctx_negations = [w for w in ctx_tokens if w in _NEGATION_WORDS]
        ctx_content = set(
            w for w in ctx_tokens if w not in _STOP_WORDS and w not in _NEGATION_WORDS
        )
        if len(ctx_content) < 3:
            continue

        overlap = claim_content & ctx_content
        recall = len(overlap) / len(claim_content)
        jaccard = (
            len(overlap) / len(claim_content | ctx_content)
            if (claim_content | ctx_content)
            else 0.0
        )

        # High lexical overlap means both sentences make a claim about the same core entities/predicates
        if len(overlap) >= 3 and (recall >= 0.70 or jaccard >= 0.50):
            ctx_neg = len(ctx_negations) % 2 == 1
            if claim_neg != ctx_neg:
                return (
                    True,
                    f"Polarity inversion contradiction: context states '{ctx_sent}', "
                    f"but claim asserts opposite polarity: '{clean_claim}'",
                )

        # Antonym opposition check
        for ant1, ant2 in _ANTONYM_PAIRS:
            matched_c = ant1 if ant1 in claim_content else (ant2 if ant2 in claim_content else None)
            matched_ctx = ant2 if matched_c == ant1 else (ant1 if matched_c == ant2 else None)
            if matched_c and matched_ctx and matched_ctx in ctx_content:
                rem_c = claim_content - {matched_c}
                rem_ctx = ctx_content - {matched_ctx}
                rem_overlap = rem_c & rem_ctx
                if len(rem_overlap) >= 2 and (len(rem_overlap) / len(rem_c) >= 0.60):
                    ctx_neg = len(ctx_negations) % 2 == 1
                    if claim_neg == ctx_neg:
                        return (
                            True,
                            f"Antonym contradiction on '{matched_c}' vs '{matched_ctx}': "
                            f"context states '{ctx_sent}', but claim asserts '{clean_claim}'",
                        )

    return False, None


class LettuceDetectService:
    """Faithfulness scorer with a real span-level detector behind a flag.

    ``lettucedetect_enabled=True`` activates the RAGTruth-trained
    ModernBERT detector; ``False`` (default) keeps the historical
    heuristic so the build does not hard-depend on torch/transformers.
    """

    # Shared across every instance in the process -- see _load_real_detector.
    _shared_detector: ClassVar[Any] = None
    _shared_load_attempted: ClassVar[bool] = False
    # score_faithfulness is sync and runs via asyncio.to_thread, so concurrent
    # requests hit _load_real_detector from separate threadpool threads.
    _shared_load_lock: ClassVar[threading.Lock] = threading.Lock()
    # AMK-B-002, re-root-caused 2026-09-18: the backend was NOT dying of memory
    # exhaustion. It died of `Fatal Python error: Segmentation fault` with the
    # faulting thread inside torch's Linear.forward under
    # modeling_modernbert.py, at 4.1GB of a 6GB limit with OOMKilled=false.
    #
    # `_shared_detector` is a ClassVar: ONE torch module object for the whole
    # process. A transformers model is not safe to run `forward()` on from
    # several threads at once, and score_faithfulness is called from a thread
    # per in-flight chat. Two concurrent verifications on one module raced and
    # took the interpreter down — which is why bounding MEMORY did not help and
    # why every observed crash dump named modernbert/lettucedetect.
    #
    # Inference on the shared module is therefore exclusive. This is a real
    # throughput ceiling on the verification path and it is the correct trade:
    # the faithfulness gate must never be skipped, and a queued verification is
    # strictly better than a segfault that drops every in-flight request.
    _shared_predict_lock: ClassVar[threading.Lock] = threading.Lock()

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
            logger.info(
                "LettuceDetectService: heuristic fallback active (lettucedetect_enabled=False)."
            )

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
        # Class-level cache: the loaded detector is shared by EVERY instance in
        # the process. It was previously per-instance, so the startup warm-up in
        # app/main.py loaded the model into a throwaway LettuceDetectService
        # while the pipeline's own instance still paid the full load on its
        # first real request. Measured live 2026-09-17: three requests hit
        # "Faithfulness scorer exceeded 8.0s deadline" while completed scorings
        # took only 1.5-3.3ms -- the gap was the model load, not inference.
        # That deadline fails CLOSED, so each timeout rejected a good answer and
        # triggered a regeneration, doubling that request's latency AND token
        # cost. Ingestion also builds many instances per run (same lesson as
        # OpenRouterService's shared rate limiter), each of which would
        # otherwise reload the model.
        if LettuceDetectService._shared_load_attempted:
            return LettuceDetectService._shared_detector

        # Double-checked locking. The flag must only become True AFTER the
        # load fully resolves (success or failure) -- setting it any earlier
        # means a thread can observe "attempted" from OUTSIDE the lock (the
        # fast-path check above) while the load is still in progress inside
        # another thread's held lock, and get None back even though the real
        # detector finishes loading moments later. That was the bug found
        # 2026-09-18: `_shared_load_attempted = True` was set before the ~8s
        # load (see L-WARM-1) even started, so ANY concurrent request during
        # that window silently downgraded to the heuristic scorer with no
        # warning. Startup warm-up (app/main.py) covers the common case, but
        # this is still a genuine race for a request landing before warm-up
        # completes, or after a runtime config flip re-enables
        # lettucedetect_enabled. `finally` guarantees the flag flips exactly
        # once, still inside the lock, regardless of which branch returns.
        with LettuceDetectService._shared_load_lock:
            if LettuceDetectService._shared_load_attempted:
                return LettuceDetectService._shared_detector

            try:
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

                # Pin the revision via snapshot_download, then load from the
                # local dir. This is the same pattern as OnnxReranker._load —
                # the package's TransformerDetector calls from_pretrained on
                # the path we give it, so the pinned snapshot is what loads.
                local_path = snapshot_download(
                    repo_id=_LETTUCE_MODEL_ID,
                    revision=_LETTUCE_MODEL_REVISION,
                    resume_download=True,
                )
                LettuceDetectService._shared_detector = HallucinationDetector(
                    method="transformer",
                    model_path=local_path,
                )
                logger.info(
                    "LettuceDetect real detector loaded: %s @ %s",
                    _LETTUCE_MODEL_ID,
                    _LETTUCE_MODEL_REVISION,
                )
                return LettuceDetectService._shared_detector
            except Exception as e:
                logger.warning(
                    "LettuceDetect real detector failed to load (%s: %s). "
                    "Falling back to heuristic for this process.",
                    type(e).__name__,
                    e,
                )
                return None
            finally:
                LettuceDetectService._shared_load_attempted = True

    # ------------------------------------------------------------------
    # Public contract
    # ------------------------------------------------------------------

    def score_faithfulness(
        self,
        query: str,
        context: str,
        answer: str,
        *,
        semantic: bool = True,
    ) -> dict:
        """Evaluate whether the generated answer is faithful to the context.

        ``semantic=False`` selects a bounded lexical-only check for latency
        sensitive fast-tier responses. It deliberately bypasses both the real
        detector and embedding inference; deeper verification keeps the
        default semantic path.
        """
        if semantic and getattr(settings, "lettucedetect_enabled", False):
            detector = self._load_real_detector()
            if detector is not None:
                return self._score_with_real_detector(detector, query, context, answer)
        return self._score_heuristic(query, context, answer, use_semantic=semantic)

    # ------------------------------------------------------------------
    # Real detector path (S3)
    # ------------------------------------------------------------------

    def _score_with_real_detector(self, detector, query: str, context: str, answer: str) -> dict:
        """Run the real LettuceDetect span-level detector."""
        start = time.time()
        if not answer.strip() or not context.strip():
            return {
                "is_faithful": False,
                "score": 0.0,
                "details": "Empty input.",
                "unsupported_sentences": [],
                "claims": [],
                "has_contradiction": False,
                "contradictions": [],
            }

        # Strip the source citation block the formatter appends — it is
        # not a claim the detector should score against the context.
        clean_answer = _strip_attribution_markup(answer)
        if not clean_answer:
            return {
                "is_faithful": False,
                "score": 0.0,
                "details": "Empty answer after citation strip.",
                "unsupported_sentences": [],
                "claims": [],
                "has_contradiction": False,
                "contradictions": [],
            }

        try:
            # Two bounds, for two different hazards:
            #   _shared_predict_lock -- EXCLUSIVE access to this one torch
            #                        module, because concurrent forward() on it
            #                        segfaults (see the ClassVar comment above).
            #   native_inference  -- process-wide memory ceiling shared with the
            #                        embedding encoder and the ONNX reranker.
            #
            # ORDER MATTERS, and it is model-lock first. Taking the gate first
            # parks every waiting verification inside a scarce inference slot,
            # so N queued NLI passes hold N slots while exactly one of them
            # works -- starving the embedding encoder and the reranker of the
            # gate entirely. This way a waiter holds nothing, and only the
            # thread that will actually run consumes a slot.
            #
            # No deadlock risk: nothing anywhere acquires the gate and then
            # reaches for this lock, so the two are always taken in this order.
            lock_timeout = _predict_lock_timeout()
            if not self._shared_predict_lock.acquire(timeout=lock_timeout):
                raise NativeInferenceBusy(
                    f"LettuceDetect model lock not acquired within "
                    f"{lock_timeout:.1f}s; shedding to the heuristic scorer"
                )
            try:
                with native_inference("lettuce_nli"):
                    predictions = detector.predict(
                        context=[context],
                        question=query if query else None,
                        answer=clean_answer,
                        output_format="spans",
                    )
            finally:
                self._shared_predict_lock.release()
        except NativeInferenceBusy as e:
            # Load shedding, not a detector failure. The heuristic scorer is a
            # real faithfulness check, so the answer is still gated — it is not
            # waved through. Never weaken the gate to save latency.
            logger.warning(
                "LettuceDetect shed under load (%s). Falling back to heuristic scorer.", e
            )
            return self._score_heuristic(query, context, answer)
        except Exception as e:
            logger.warning(
                "LettuceDetect real detector.predict failed (%s: %s). Falling back to heuristic.",
                type(e).__name__,
                e,
            )
            return self._score_heuristic(query, context, answer)

        duration = (time.time() - start) * 1000
        claims_list = _split_claims(clean_answer)

        if not predictions:
            claims = []
            contradictions = []
            for claim in claims_list:
                is_contra, contra_reason = _detect_contradiction(claim, context)
                if is_contra:
                    contradictions.append(contra_reason or claim)
                    claims.append(
                        {
                            "text": claim,
                            "score": 0.0,
                            "supported": False,
                            "classification": "contradiction",
                            "contradiction": True,
                            "contradiction_reason": contra_reason,
                        }
                    )
                else:
                    claims.append(
                        {
                            "text": claim,
                            "score": 1.0,
                            "supported": True,
                            "classification": "entailment",
                            "contradiction": False,
                            "contradiction_reason": None,
                        }
                    )

            if contradictions:
                return {
                    "is_faithful": False,
                    "score": 0.0,
                    "has_contradiction": True,
                    "contradictions": contradictions,
                    "max_span_confidence": 1.0,
                    "details": (
                        f"real LettuceDetect: doctrinal contradiction detected ({duration:.1f}ms): "
                        + " | ".join(contradictions)
                    ),
                    "unsupported_sentences": [c["text"] for c in claims if c.get("contradiction")],
                    "claims": claims,
                }

            return {
                "is_faithful": True,
                "score": 1.0,
                "has_contradiction": False,
                "contradictions": [],
                "details": f"real LettuceDetect: no hallucinated spans ({duration:.1f}ms)",
                "unsupported_sentences": [],
                "claims": claims,
            }

        max_conf = max(
            (float(p.get("confidence", 0.0)) for p in predictions),
            default=0.0,
        )
        span_texts = [p.get("text", "") for p in predictions]
        claims = []
        contradictions = []
        for claim in claims_list:
            claim_norm = _norm_for_span_match(claim)
            # Spans come back with surrounding whitespace and their own casing;
            # matching them raw against the claim missed every one, so `claims`
            # reported all-supported while `unsupported_sentences` listed spans.
            claim_spans = [
                p
                for p in predictions
                if (sp := _norm_for_span_match(p.get("text") or ""))
                and (sp in claim_norm or claim_norm in sp)
            ]
            claim_confidence = max(
                (float(p.get("confidence", 0.0)) for p in claim_spans),
                default=0.0,
            )
            is_contra, contra_reason = _detect_contradiction(claim, context)
            if is_contra:
                contradictions.append(contra_reason or claim)
                claims.append(
                    {
                        "text": claim,
                        "score": 0.0,
                        "supported": False,
                        "classification": "contradiction",
                        "contradiction": True,
                        "contradiction_reason": contra_reason,
                    }
                )
            elif not claim_spans:
                claims.append(
                    {
                        "text": claim,
                        "score": 1.0 - claim_confidence,
                        "supported": True,
                        "classification": "entailment",
                        "contradiction": False,
                        "contradiction_reason": None,
                    }
                )
            else:
                claims.append(
                    {
                        "text": claim,
                        "score": 1.0 - claim_confidence,
                        "supported": False,
                        "classification": "neutral",
                        "contradiction": False,
                        "contradiction_reason": None,
                    }
                )

        if contradictions:
            return {
                "is_faithful": False,
                "score": 0.0,
                "has_contradiction": True,
                "contradictions": contradictions,
                "max_span_confidence": max_conf,
                "details": (
                    "real LettuceDetect: doctrinal contradiction detected: "
                    + " | ".join(contradictions)
                ),
                "unsupported_sentences": span_texts
                + [
                    c["text"]
                    for c in claims
                    if c.get("contradiction") and c["text"] not in span_texts
                ],
                "claims": claims,
            }

        # `score` is compared against settings.faithfulness_floor, which is a
        # grounded-proportion threshold. `1 - max_span_confidence` is not that:
        # one confidently-flagged span drove it to ~0 no matter how much of the
        # answer was grounded, so any answer with a single span failed the floor.
        # Report the supported-claim ratio instead; `is_faithful` below stays
        # zero-tolerance, so this loosens nothing that gates on it.
        supported_claims = [c for c in claims if c["supported"]]
        grounded_ratio = len(supported_claims) / len(claims) if claims else 0.0
        return {
            "is_faithful": False,
            "score": grounded_ratio,
            "has_contradiction": False,
            "contradictions": [],
            "max_span_confidence": max_conf,
            "details": (
                f"real LettuceDetect: {len(predictions)} hallucinated spans "
                f"(max_conf={max_conf:.3f}, {duration:.1f}ms): "
                + " | ".join(f"'{s}'" for s in span_texts if s)
            ),
            "unsupported_sentences": span_texts,
            "claims": claims,
        }

    # ------------------------------------------------------------------
    # Heuristic fallback path (original logic, C2 emoji branch removed)
    # ------------------------------------------------------------------

    def _score_heuristic(
        self,
        query: str,
        context: str,
        answer: str,
        *,
        use_semantic: bool = True,
    ) -> dict:
        """Sentence-split + cosine (or word-overlap) heuristic. Original path."""
        start = time.time()
        if not answer.strip() or not context.strip():
            return {
                "is_faithful": False,
                "score": 0.0,
                "details": "Empty input.",
                "unsupported_sentences": [],
                "claims": [],
                "has_contradiction": False,
                "contradictions": [],
            }

        # Clean answer to remove source citation lists to prevent false negatives
        clean_answer = _strip_attribution_markup(answer)

        # Same splitter as the real-detector path. This was a duplicated regex,
        # so a fix applied to one path silently left the other scoring
        # questions and imperatives as claims.
        sentences = _split_claims(clean_answer)
        if not sentences:
            return {
                "is_faithful": False,
                "score": 0.0,
                "details": "No testable sentences.",
                "unsupported_sentences": [],
                "claims": [],
                "has_contradiction": False,
                "contradictions": [],
            }

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
        claims: list[dict[str, object]] = []
        contradictions: list[str] = []

        if self.embedder and use_semantic:
            try:
                # Encode context and answer sentences in two batch calls. The
                # previous per-sentence encode_single_full loop made a normal
                # 1,400-character answer perform one ONNX inference per sentence;
                # in production that added roughly 39 seconds after generation.
                context_embeddings = self.embedder.encode_batch(context_chunks)["dense"]
                sentence_embeddings = self.embedder.encode_batch(sentences)["dense"]
                if len(sentence_embeddings) != len(sentences):
                    raise ValueError("embedding batch returned the wrong sentence count")
                import numpy as np

                for sentence, sentence_emb in zip(sentences, sentence_embeddings):
                    # Compute cosine similarity with all context chunks
                    similarities = []
                    for c_emb in context_embeddings:
                        s_norm = np.array(sentence_emb) / (np.linalg.norm(sentence_emb) + 1e-10)
                        c_norm = np.array(c_emb) / (np.linalg.norm(c_emb) + 1e-10)
                        similarities.append(float(np.dot(s_norm, c_norm)))

                    max_sim = max(similarities) if similarities else 0.0

                    threshold = getattr(settings, "lettuce_detect_threshold", 0.25)
                    supported = max_sim >= threshold

                    is_contra, contra_reason = _detect_contradiction(
                        sentence, context, context_chunks
                    )
                    if is_contra:
                        contradictions.append(contra_reason or sentence)
                        scores.append(0.0)
                        claims.append(
                            {
                                "text": sentence,
                                "score": 0.0,
                                "supported": False,
                                "classification": "contradiction",
                                "contradiction": True,
                                "contradiction_reason": contra_reason,
                            }
                        )
                        unsupported_sentences.append((sentence, 0.0))
                    elif supported:
                        scores.append(max_sim)
                        claims.append(
                            {
                                "text": sentence,
                                "score": max_sim,
                                "supported": True,
                                "classification": "entailment",
                                "contradiction": False,
                                "contradiction_reason": None,
                            }
                        )
                    else:
                        scores.append(max_sim)
                        claims.append(
                            {
                                "text": sentence,
                                "score": max_sim,
                                "supported": False,
                                "classification": "neutral",
                                "contradiction": False,
                                "contradiction_reason": None,
                            }
                        )
                        unsupported_sentences.append((sentence, max_sim))
            except Exception as e:
                logger.warning(
                    f"LettuceDetect: Semantic scoring failed ({e}), falling back to lexical overlap."
                )
                # Fallback to token-level overlap matching
                for sentence in sentences:
                    overlap = self._compute_lexical_overlap(sentence, context)
                    supported = overlap >= 0.45
                    is_contra, contra_reason = _detect_contradiction(
                        sentence, context, context_chunks
                    )
                    if is_contra:
                        contradictions.append(contra_reason or sentence)
                        scores.append(0.0)
                        claims.append(
                            {
                                "text": sentence,
                                "score": 0.0,
                                "supported": False,
                                "classification": "contradiction",
                                "contradiction": True,
                                "contradiction_reason": contra_reason,
                            }
                        )
                        unsupported_sentences.append((sentence, 0.0))
                    elif supported:
                        scores.append(overlap)
                        claims.append(
                            {
                                "text": sentence,
                                "score": overlap,
                                "supported": True,
                                "classification": "entailment",
                                "contradiction": False,
                                "contradiction_reason": None,
                            }
                        )
                    else:
                        scores.append(overlap)
                        claims.append(
                            {
                                "text": sentence,
                                "score": overlap,
                                "supported": False,
                                "classification": "neutral",
                                "contradiction": False,
                                "contradiction_reason": None,
                            }
                        )
                        unsupported_sentences.append((sentence, overlap))
        else:
            # Word overlap fallback
            for sentence in sentences:
                overlap = self._compute_lexical_overlap(sentence, context)
                supported = overlap >= 0.45
                is_contra, contra_reason = _detect_contradiction(sentence, context, context_chunks)
                if is_contra:
                    contradictions.append(contra_reason or sentence)
                    scores.append(0.0)
                    claims.append(
                        {
                            "text": sentence,
                            "score": 0.0,
                            "supported": False,
                            "classification": "contradiction",
                            "contradiction": True,
                            "contradiction_reason": contra_reason,
                        }
                    )
                    unsupported_sentences.append((sentence, 0.0))
                elif supported:
                    scores.append(overlap)
                    claims.append(
                        {
                            "text": sentence,
                            "score": overlap,
                            "supported": True,
                            "classification": "entailment",
                            "contradiction": False,
                            "contradiction_reason": None,
                        }
                    )
                else:
                    scores.append(overlap)
                    claims.append(
                        {
                            "text": sentence,
                            "score": overlap,
                            "supported": False,
                            "classification": "neutral",
                            "contradiction": False,
                            "contradiction_reason": None,
                        }
                    )
                    unsupported_sentences.append((sentence, overlap))

        has_contradiction = bool(contradictions)
        if has_contradiction:
            avg_score = 0.0
            is_faithful = False
        else:
            avg_score = sum(scores) / len(scores) if scores else 1.0
            is_faithful = len(unsupported_sentences) == 0

        duration = (time.time() - start) * 1000

        details = f"Scored {len(sentences)} sentences in {duration:.2f}ms. "
        if has_contradiction:
            details += f"Doctrinal contradiction detected: {'; '.join(contradictions)}"
        elif not is_faithful:
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
            "has_contradiction": has_contradiction,
            "contradictions": contradictions,
            "details": details,
            "unsupported_sentences": [s for s, _ in unsupported_sentences],
            "claims": claims,
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
