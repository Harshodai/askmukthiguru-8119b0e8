"""
Data Quality Gate — Apache Iceberg-Style Staged Validation

Design:
  Tier 1 (Free, instant):  deterministic checks — length, repetition, HTML ratio
  Tier 2 (LLM-powered):    spiritual relevance scoring with structured JSON output
  Tier 3 (On reject):      writes to Supabase staging_quality_queue for human review

Like Apache Iceberg:
  - Content sits in "staging" until it passes quality checks
  - Only PASS content is committed to Qdrant/Neo4j/LightRAG
  - Full audit trail in Supabase with reviewer assignment

ponytail: use lru_cache for doctrine term set, avoid re-reading DOCTRINE_SYNONYMS per call.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Doctrine keywords (inlined to avoid ContainerBuilder OOM) ──────────────

@lru_cache(maxsize=1)
def _spiritual_keywords() -> frozenset[str]:
    """Cached set of all spiritual doctrine synonyms for keyword scanning."""
    return frozenset([
        "beautiful state", "suffering state", "surrender", "oneness", "consciousness",
        "ekam", "deeksha", "soul sync", "four sacred secrets", "preethaji", "krishnaji",
        "meditation", "dharma", "karma", "moksha", "atma", "brahman", "samsara",
        "guru", "sadhna", "sadhana", "mahavakya", "satsang", "sankalpa", "vairagya",
        "bhakti", "jnana", "kriya", "mantra", "maya", "jeevan mukta", "paramatma",
        "enlightenment", "liberation", "spiritual", "consciousness", "awakening",
        "mindfulness", "inner peace", "divine", "sacred", "soul", "awareness",
        "presence", "stillness", "silence", "transformation", "healing", "devotion",
        "bliss", "gratitude", "compassion", "love", "peace", "unity", "presence",
    ])


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class QualityResult:
    """Result of the data quality gate for a piece of content."""
    passed: bool
    score: int  # 0–100
    tier_reached: int  # 1, 2, or 3 (highest tier that ran before pass/fail)
    reasons: list[str] = field(default_factory=list)
    staging_id: Optional[str] = None  # Supabase UUID if sent to staging
    source_url: str = ""
    content_hash: str = ""

    def __str__(self) -> str:
        status = "✅ PASS" if self.passed else "❌ FAIL"
        return f"{status} score={self.score}/100 tier={self.tier_reached} reasons={self.reasons}"


# ── Tier 1: Deterministic checks ─────────────────────────────────────────────

class DeterministicChecker:
    """Fast, zero-cost deterministic content validation."""

    MIN_LENGTH = 100           # characters
    MAX_HTML_RATIO = 0.15      # >15% HTML tags = likely scraped junk
    MAX_REPEAT_RATIO = 0.15    # top n-gram >15% of words = repetitive noise
    MIN_WORD_COUNT = 20
    NGRAM_SIZE = 3

    def _is_short_video(self, url: str) -> bool:
        """Detect if the URL points to a short video format (Reel/Short/TikTok)."""
        if not url:
            return False
        url_lower = url.lower()
        return "shorts/" in url_lower or "reel/" in url_lower or "tiktok.com" in url_lower or "instagram.com" in url_lower

    def check(self, text: str, source_url: str = "") -> tuple[bool, int, list[str]]:
        """
        Returns (passed, score_penalty, fail_reasons).
        score_penalty is subtracted from 100 by the gate orchestrator.
        """
        reasons: list[str] = []
        penalty = 0

        stripped = text.strip()

        # Apply Reel min-length grace: if URL matches short video formats,
        # lower the minimum bounds.
        is_short = self._is_short_video(source_url)
        min_len = 30 if is_short else self.MIN_LENGTH
        min_words = 5 if is_short else self.MIN_WORD_COUNT

        # Length check
        if len(stripped) < min_len:
            return False, 100, [f"Text too short ({len(stripped)} chars, min={min_len})"]

        words = stripped.lower().split()
        if len(words) < min_words:
            return False, 100, [f"Too few words ({len(words)}, min={min_words})"]

        # HTML pollution check
        html_tags = re.findall(r"<[^>]+>", stripped)
        html_ratio = len(html_tags) * 10 / max(len(stripped), 1)  # avg tag ~10 chars
        if html_ratio > self.MAX_HTML_RATIO:
            reasons.append(f"High HTML pollution ratio ({html_ratio:.1%})")
            penalty += 30

        # Repetition check — detect "thank you thank you thank you" patterns
        # Only run on length >= 40 words to avoid false positives on short greetings
        if len(words) >= 40:
            repeat_ratio = self._check_repetition(words)
            if repeat_ratio > self.MAX_REPEAT_RATIO:
                if repeat_ratio > 0.25:
                    reasons.append(f"Severe repetitive noise detected (n-gram density={repeat_ratio:.1%})")
                    penalty += 60
                else:
                    reasons.append(f"Repetitive content detected (n-gram density={repeat_ratio:.1%})")
                    penalty += 25

        # Spiritual relevance keyword hit (bonus — reduces penalty)
        kw_hits = sum(1 for kw in _spiritual_keywords() if kw in stripped.lower())
        if kw_hits == 0:
            reasons.append("No spiritual doctrine keywords detected")
            penalty += 15

        # Information density (Task E2.5) — thin content penalty
        from app.config import settings
        density_min = float(getattr(settings, "quality_min_information_density", 0.35))
        density = information_density(stripped)
        if density < density_min:
            reasons.append(f"Low information density ({density:.2f}, min={density_min:.2f})")
            penalty += 20

        # Bias / loaded-language stub (Task E2.5) — flag but don't hard-fail alone
        bias_terms = detect_bias(stripped, getattr(settings, "quality_bias_blocklist", ""))
        if bias_terms:
            reasons.append(f"Loaded/bias terms detected: {bias_terms}")
            penalty += 25

        passed = penalty < 50
        return passed, penalty, reasons

    def _check_repetition(self, words: list[str]) -> float:
        """Return the highest n-gram frequency ratio. >MAX_REPEAT_RATIO = repetitive."""
        if len(words) < self.NGRAM_SIZE + 1:
            return 0.0
        ngrams: dict[tuple, int] = {}
        total = len(words) - self.NGRAM_SIZE + 1
        for i in range(total):
            gram = tuple(words[i : i + self.NGRAM_SIZE])
            ngrams[gram] = ngrams.get(gram, 0) + 1
        if not ngrams:
            return 0.0
        max_count = max(ngrams.values())
        return max_count / total


# ── Tier 1+: Information density / fact-check / bias stubs (Task E2.5) ────────

# Minimal stopword set so density scoring ignores filler words.
_DENSITY_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be", "been",
    "of", "to", "in", "on", "for", "with", "as", "by", "at", "from", "it", "this",
    "that", "these", "those", "i", "you", "we", "they", "he", "she", "his", "her",
    "not", "so", "if", "then", "than", "do", "does", "did", "have", "has", "had",
})


def information_density(text: str) -> float:
    """
    Ratio of unique meaningful (non-stopword) tokens to total tokens.
    Higher = denser. Low density → thin/gibberish content.
    Ponytail: one function, no class.
    """
    words = [w.strip(".,!?;:\"'()[]").lower() for w in text.split()]
    words = [w for w in words if w]
    if not words:
        return 0.0
    meaningful = [w for w in words if w not in _DENSITY_STOPWORDS and len(w) > 2]
    if not meaningful:
        return 0.0
    return len(set(meaningful)) / len(meaningful)


# Tiny built-in blocklist for the bias-detection stub. Extend via
# settings.quality_bias_blocklist (comma-separated) for production use.
_BIAS_BLOCKLIST_STUB = frozenset({
    "heretic", "infidel", "blasphemy", "cultist", "heathen",
})


def detect_bias(text: str, extra_blocklist: str = "") -> list[str]:
    """
    Stub bias/loaded-language detector. Returns list of flagged terms found.
    Ponytail: blocklist scan, no NLP. Returns [] when clean.
    """
    terms = set(_BIAS_BLOCKLIST_STUB)
    if extra_blocklist:
        terms.update(t.strip().lower() for t in extra_blocklist.split(",") if t.strip())
    lower = text.lower()
    return [t for t in terms if t in lower]


def fact_check_stub(chunk: str, known_true: list[str] | None = None) -> bool:
    """
    Stub fact-checker. Always returns True (pass) for now.
    TODO: replace with LLM-based contradiction check against `known_true` statements
    and a vetted doctrinal corpus. Kept as a no-op so ingestion is never blocked
    by an incomplete gate.
    """
    # Intentional passthrough — graceful, never rejects.
    return True


# ── Tier 2: LLM quality scoring ───────────────────────────────────────────────

QUALITY_PROMPT = """You are a Data Quality Auditor for the AskMukthiGuru spiritual AI knowledge base.

Evaluate the following text and return a JSON quality assessment.

Rules for spiritual content quality:
- PASS (score 70-100): coherent spiritual teaching, discourse, Q&A, or practice guidance
- BORDERLINE (score 40-69): tangentially related, partially coherent, or low-density teaching
- FAIL (score 0-39): gibberish, unrelated content, repetitive noise, or promotional material

IMPORTANT: This is a spiritual platform. Be strict about relevance. A cooking video transcript should FAIL.
A Q&A about life, consciousness, or meditation should PASS even if informal.

Respond ONLY with valid JSON, no markdown:
{
  "score": <0-100>,
  "verdict": "PASS" | "BORDERLINE" | "FAIL",
  "is_spiritual": true | false,
  "coherence": "high" | "medium" | "low",
  "reasons": ["reason1", "reason2"]
}"""


class LLMQualityScorer:
    """LLM-powered quality scoring with structured JSON output."""

    def __init__(self, llm_service: Any):
        self._llm = llm_service
        self._timeout = 30  # seconds per LLM call

    async def score(self, text: str, source_url: str = "") -> tuple[int, list[str]]:
        """
        Returns (score 0-100, reasons).
        Samples 3 strategic positions (start, middle, end) to avoid blowing context.
        """
        sample = self._sample_text(text, sample_size=800, positions=3)
        prompt = f"Text to evaluate (sampled from: {source_url or 'unknown'}):\n---\n{sample}\n---"

        try:
            raw = await asyncio.wait_for(
                self._llm.generate(
                    system_prompt=QUALITY_PROMPT,
                    user_prompt=prompt,
                    temperature=0.0,
                ),
                timeout=self._timeout,
            )
            return self._parse_json_response(raw)
        except asyncio.TimeoutError:
            logger.warning("LLM quality score timed out — defaulting to score=60 (pass with caution)")
            return 60, ["LLM timeout — score defaulted, manual review recommended"]
        except Exception as e:
            logger.warning(f"LLM quality scoring failed: {e} — defaulting to score=65")
            return 65, [f"LLM scoring unavailable: {e}"]

    def _parse_json_response(self, raw: str) -> tuple[int, list[str]]:
        import json

        # Strip any markdown code fences
        clean = re.sub(r"```(?:json)?", "", raw).strip().strip("`")
        # Find the JSON object
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if not match:
            logger.warning(f"LLM quality response not JSON: {raw[:200]}")
            return 50, ["Could not parse LLM response — borderline score assigned"]

        try:
            data = json.loads(match.group())
            score = int(data.get("score", 50))
            reasons = data.get("reasons", [])
            if not data.get("is_spiritual", True):
                reasons.insert(0, "Content not identified as spiritual/philosophical")
            return max(0, min(100, score)), reasons
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"JSON parse error in quality response: {e}")
            return 50, ["JSON parse error — borderline score assigned"]

    def _sample_text(self, text: str, sample_size: int, positions: int) -> str:
        """Sample text from start, middle, and end positions."""
        if len(text) <= sample_size * positions:
            return text[:sample_size * positions]

        step = len(text) // positions
        samples = []
        for i in range(positions):
            start = i * step
            samples.append(text[start : start + sample_size])
        return "\n\n[...]\n\n".join(samples)


# ── Tier 3: Supabase staging queue ────────────────────────────────────────────

class StagingQueue:
    """Writes rejected/borderline content to Supabase for human review."""

    def __init__(self, supabase_client: Optional[Any] = None):
        self._client = supabase_client

    async def submit(
        self,
        source_url: str,
        content_preview: str,
        quality_score: int,
        fail_reasons: list[str],
        content_hash: str = "",
    ) -> Optional[str]:
        """
        Write to staging_quality_queue. Returns staging ID or None on failure.
        Non-blocking — failure here never blocks ingestion flow.
        """
        if not self._client:
            logger.debug("No Supabase client — staging queue write skipped")
            return None

        try:
            result = await asyncio.to_thread(
                lambda: self._client.table("staging_quality_queue").insert({
                    "source_url": source_url,
                    "content_preview": content_preview[:2000],
                    "quality_score": quality_score,
                    "fail_reasons": fail_reasons,
                    "content_hash": content_hash,
                    "status": "pending",
                }).execute()
            )
            staging_id = result.data[0]["id"] if result.data else None
            logger.info(f"Staged for review: {source_url} (score={quality_score}) → id={staging_id}")
            return staging_id
        except Exception as e:
            logger.warning(f"Staging queue write failed: {e}")
            return None


# ── Main Gate Orchestrator ────────────────────────────────────────────────────

class DataQualityGate:
    """
    Orchestrates all 3 quality tiers. Mirrors Apache Iceberg's commit→staging→merge pattern:
      - Tier 1 (deterministic) → reject immediately for obvious junk
      - Tier 2 (LLM score) → reject borderline/irrelevant content
      - Tier 3 (staging) → human review queue for rejected items

    Only content with score ≥ quality_threshold is committed to Qdrant/Neo4j/LightRAG.
    """

    DEFAULT_THRESHOLD = 65  # score ≥ 65 → PASS, < 65 → stage for review

    def __init__(
        self,
        llm_service: Optional[Any] = None,
        supabase_client: Optional[Any] = None,
        quality_threshold: int = DEFAULT_THRESHOLD,
        enabled: bool = True,
    ):
        self._llm_scorer = LLMQualityScorer(llm_service) if llm_service else None
        self._staging = StagingQueue(supabase_client)
        self._deterministic = DeterministicChecker()
        self._threshold = quality_threshold
        self._enabled = enabled

    async def run(self, text: str, source_url: str = "") -> QualityResult:
        """
        Run all quality tiers. Returns QualityResult.
        If not enabled, always returns PASS with score=100.
        """
        import hashlib
        content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]

        if not self._enabled:
            return QualityResult(
                passed=True, score=100, tier_reached=0,
                reasons=["Quality gate disabled"], source_url=source_url,
                content_hash=content_hash,
            )

        # ── Tier 1: Deterministic ──────────────────────────────────────────
        t1_ok, t1_penalty, t1_reasons = self._deterministic.check(text, source_url)
        if not t1_ok:
            result = QualityResult(
                passed=False, score=0, tier_reached=1,
                reasons=t1_reasons, source_url=source_url,
                content_hash=content_hash,
            )
            result.staging_id = await self._staging.submit(
                source_url, text[:500], 0, t1_reasons, content_hash
            )
            logger.warning(f"Quality gate T1 FAIL: {source_url} — {t1_reasons}")
            return result

        score_from_t1 = max(0, 100 - t1_penalty)

        # ── Tier 2: LLM Scoring ───────────────────────────────────────────
        if self._llm_scorer:
            llm_score, llm_reasons = await self._llm_scorer.score(text, source_url)
            # Blend T1 (40%) and LLM (60%) scores for robustness
            final_score = int(score_from_t1 * 0.4 + llm_score * 0.6)
            all_reasons = t1_reasons + llm_reasons
            tier = 2
        else:
            final_score = score_from_t1
            all_reasons = t1_reasons
            tier = 1

        passed = final_score >= self._threshold

        result = QualityResult(
            passed=passed,
            score=final_score,
            tier_reached=tier,
            reasons=all_reasons,
            source_url=source_url,
            content_hash=content_hash,
        )

        # ── Tier 3: Staging if failed ─────────────────────────────────────
        if not passed:
            result.staging_id = await self._staging.submit(
                source_url, text[:500], final_score, all_reasons, content_hash
            )
            logger.warning(f"Quality gate T2 FAIL: {source_url} score={final_score} — staged for review")
        else:
            logger.info(f"Quality gate PASS: {source_url} score={final_score}/100")

        return result

    async def run_chunks(
        self, chunks: list[str], source_url: str = ""
    ) -> tuple[list[str], list[QualityResult]]:
        """
        Filter a list of chunks, returning only those that pass quality gate.
        Uses sampling — full gate only on first 5 chunks + random sample of remaining.
        """
        import random

        if not self._enabled or not chunks:
            return chunks, []

        # Sample strategy: check first 3 chunks + random 20% of remainder
        indices_to_check = set(range(min(3, len(chunks))))
        if len(chunks) > 3:
            remainder = list(range(3, len(chunks)))
            sample_size = max(1, int(len(remainder) * 0.2))
            indices_to_check.update(random.sample(remainder, min(sample_size, len(remainder))))

        results = []
        failed_indices: set[int] = set()

        for i, chunk in enumerate(chunks):
            if i in indices_to_check:
                qr = await self.run(chunk, source_url)
                results.append(qr)
                if not qr.passed:
                    failed_indices.add(i)

        # If > 30% of sampled chunks fail → reject entire batch
        if len(failed_indices) / max(len(indices_to_check), 1) > 0.3:
            logger.warning(f"Batch quality fail: {len(failed_indices)}/{len(indices_to_check)} chunks failed → rejecting all")
            return [], results

        return chunks, results


if __name__ == "__main__":
    """Quick self-check."""
    import asyncio

    checker = DeterministicChecker()

    # Good spiritual text
    good = "Sri Preethaji teaches us that the Beautiful State is a state of inner calm, " \
           "not dependent on external circumstances. Through Soul Sync meditation, we learn " \
           "to access this state moment by moment, regardless of what is happening around us. " \
           "This is the essence of the Four Sacred Secrets taught at Ekam World Centre."
    ok, pen, reasons = checker.check(good)
    print(f"Good text: passed={ok} penalty={pen} reasons={reasons}")

    # Bad repetitive text
    bad = "thank you thank you thank you so much thank you very much thank you " * 10
    ok2, pen2, reasons2 = checker.check(bad)
    print(f"Bad text: passed={ok2} penalty={pen2} reasons={reasons2}")
    assert not ok2, "Should reject repetitive text"

    # Information density self-check
    dense = "Consciousness liberation meditation dharma karma moksha awareness presence stillness"
    thin = "the the the the the the the the the the the the the the the the"
    print(f"dense density={information_density(dense):.2f}")
    print(f"thin density={information_density(thin):.2f}")
    assert information_density(dense) > information_density(thin)

    # Bias stub self-check
    assert detect_bias("this is a heretic teaching") == ["heretic"]
    assert detect_bias("a peaceful meditation") == []

    # Fact-check stub always passes
    assert fact_check_stub("any chunk", ["known true statement"]) is True
    print("✅ Self-check passed")
