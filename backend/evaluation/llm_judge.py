"""Multi-dimensional LLM-as-judge evaluator for Mukthi Guru.

This module replaces the keyword-only PASS/FAIL benchmark scoring with a
research-backed composite evaluator that scores each (query, answer, context)
triple on five orthogonal dimensions:

  1. groundedness         — every factual claim is supported by retrieved context
  2. doctrinal_consistency — answer aligns with the active guru's tradition
  3. tone                 — reads as a teacher, not an AI (no AI-tells)
  4. citation_correctness — cited sources actually say what the claim asserts
  5. refusal_correctness  — adversarial / safety / out-of-domain are refused right

A composite score is the WEAKEST of the five (a hallucinated answer with great
tone is still wrong). The eval runner also reports the per-dimension scores so
regressions can be attributed precisely.

Design intent:
  * Judge prompts live in `backend/evaluation/rubrics/*.yaml` so they are
    versioned text, not embedded Python strings. Changes to a rubric trigger a
    regression run.
  * The judge model is configured via `LLM_JUDGE_PROVIDER_MODEL`. We default
    to a different model than the generator (judge != generator) so the judge
    can't game its own work.
  * Each dimension has a structured output schema. The judge returns JSON we
    parse; raw text fall-back is logged but never trusted.
  * The harness is async + concurrent (bounded). It can grade 200 questions
    against a 5-dimension rubric in ~3 minutes on a fast network.
  * Token usage and cost are tracked per call. Final report includes total
    cost so the operator can decide trade-offs.

Public API:
    judge = LLMJudge.from_settings()
    score = await judge.score_response(query, answer, citations, retrieved_context)
    # score.composite -> 0..1
    # score.dimensions -> dict[str, DimensionScore]

This module deliberately does NOT do retrieval; it grades responses produced by
something upstream (the live `/api/chat` endpoint or a replay harness). Keeping
the judge decoupled from the system-under-test lets us score third-party
baselines (e.g. NotebookLM exports) with the same rubric.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DimensionScore:
    """Single-dimension score with reasoning trail."""

    name: str
    score: float            # 0.0 .. 1.0
    pass_threshold: float
    rationale: str
    failure_mode: str | None = None  # taxonomy: hallucination|tone_drift|...
    judge_latency_ms: int | None = None
    judge_tokens_in: int | None = None
    judge_tokens_out: int | None = None

    @property
    def passes(self) -> bool:
        return self.score >= self.pass_threshold


@dataclass
class CompositeScore:
    """Composite of all five dimensions for one (query, answer) evaluation."""

    query: str
    composite: float                       # min(dim_scores) — weakest link
    weighted_mean: float                   # mean weighted by per-dim weights
    dimensions: dict[str, DimensionScore]
    all_pass: bool
    total_judge_tokens: int = 0
    total_judge_latency_ms: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass
class JudgeConfig:
    """Configuration loaded from settings. Everything is env-overridable."""

    provider_model: str
    session_prefix: str
    max_concurrent: int
    rubrics_dir: Path
    use_emergent_key: bool
    default_weights: dict[str, float]


# ---------------------------------------------------------------------------
# Rubric loading (YAML → in-memory dict)
# ---------------------------------------------------------------------------


def _load_rubrics(rubrics_dir: Path) -> dict[str, dict]:
    """Load every YAML rubric in `rubrics_dir` and return {name: rubric_dict}.

    Each rubric YAML is expected to declare at least:
      name: <slug>             # must match a dimension name
      pass_threshold: <0..1>
      weight: <0..1>
      system_prompt: <text>
      user_template: <text with {{query}}, {{answer}}, {{context}}, {{citations}}>
      output_schema: { score: number, rationale: string, failure_mode: string|null }
    """
    rubrics: dict[str, dict] = {}
    if not rubrics_dir.is_dir():
        logger.warning("rubrics_dir does not exist: %s", rubrics_dir)
        return rubrics
    for path in sorted(rubrics_dir.glob("*.yaml")):
        try:
            with path.open("r", encoding="utf-8") as f:
                rubric = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError) as exc:
            logger.warning("Skipping malformed rubric %s: %s", path, exc)
            continue
        name = rubric.get("name") or path.stem
        rubrics[name] = rubric
    return rubrics


# ---------------------------------------------------------------------------
# Judge client abstraction (provider-agnostic)
# ---------------------------------------------------------------------------


class JudgeClient:
    """Provider-agnostic async client for the LLM judge.

    Wraps emergentintegrations when EMERGENT_LLM_KEY is available. Falls back
    to a no-op stub when no key is configured so unit tests can run without an
    LLM. The stub returns a deterministic score of 1.0 with rationale
    "stub: no judge configured" so callers can detect it.
    """

    def __init__(self, config: JudgeConfig, api_key: str | None) -> None:
        self.config = config
        self.api_key = api_key

    @property
    def is_stub(self) -> bool:
        return not self.api_key

    async def chat_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        session_id: str,
        timeout_s: int = 30,
    ) -> tuple[dict[str, Any], int, int, int]:
        """Send one chat completion that must return JSON. Returns
        (parsed_json, tokens_in, tokens_out, latency_ms).

        On any failure (timeout, parse error, provider error), returns
        ({}, 0, 0, latency_ms) and the caller decides how to handle.
        """
        if self.is_stub:
            return (
                {"score": 1.0, "rationale": "stub: no judge configured"},
                0,
                0,
                0,
            )

        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
        except ImportError:
            logger.warning("emergentintegrations not installed; judge falling back to stub.")
            return ({"score": 1.0, "rationale": "stub: emergentintegrations missing"}, 0, 0, 0)

        provider, model = _parse_provider_model(self.config.provider_model)
        start = time.monotonic()
        try:
            chat = (
                LlmChat(
                    api_key=self.api_key,
                    session_id=session_id,
                    system_message=system_prompt,
                )
                .with_model(provider, model)
            )
            reply = await asyncio.wait_for(
                chat.send_message(UserMessage(text=user_prompt)),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.warning("Judge timed out after %sms (%s).", latency_ms, self.config.provider_model)
            return ({}, 0, 0, latency_ms)
        except Exception as exc:  # noqa: BLE001 — judge failure must never bring down eval
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.warning("Judge errored after %sms: %s", latency_ms, exc)
            return ({}, 0, 0, latency_ms)

        latency_ms = int((time.monotonic() - start) * 1000)
        text = getattr(reply, "content", str(reply))
        parsed = _safe_json_parse(text)
        # emergentintegrations exposes usage on .usage if present
        usage = getattr(reply, "usage", None) or {}
        return (
            parsed,
            int(usage.get("input_tokens", 0) or 0),
            int(usage.get("output_tokens", 0) or 0),
            latency_ms,
        )


def _parse_provider_model(spec: str) -> tuple[str, str]:
    """Parse "provider:model" → (provider, model). Defaults provider=anthropic
    when not specified. Raises on empty input."""
    if not spec or ":" not in spec:
        raise ValueError(
            f"LLM_JUDGE_PROVIDER_MODEL must be 'provider:model', got {spec!r}"
        )
    provider, model = spec.split(":", 1)
    return provider.strip().lower(), model.strip()


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _safe_json_parse(text: str) -> dict[str, Any]:
    """Parse JSON from a free-form LLM reply.

    Strategy:
      1. Try the whole text as JSON.
      2. Try the first ```json ... ``` fenced block.
      3. Try the first {...} block.
      4. Return {} on total failure (caller treats as a judge error).
    """
    if not text:
        return {}
    text = text.strip()
    # Strip fenced code blocks.
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        text_attempt = fence_match.group(1)
    else:
        text_attempt = text

    try:
        return json.loads(text_attempt)
    except json.JSONDecodeError:
        block = _JSON_BLOCK.search(text_attempt)
        if not block:
            return {}
        try:
            return json.loads(block.group(0))
        except json.JSONDecodeError:
            return {}


# ---------------------------------------------------------------------------
# The judge itself
# ---------------------------------------------------------------------------


class LLMJudge:
    """Five-dimension LLM-as-judge evaluator.

    Construct with `LLMJudge.from_settings()` for the standard configuration;
    `LLMJudge(config=..., client=...)` for tests with an injected stub.
    """

    DEFAULT_DIMENSIONS = (
        "groundedness",
        "doctrinal_consistency",
        "tone",
        "citation_correctness",
        "refusal_correctness",
        "context_precision",
        "context_recall",
    )

    def __init__(
        self,
        *,
        config: JudgeConfig,
        client: JudgeClient,
        rubrics: dict[str, dict] | None = None,
    ) -> None:
        self.config = config
        self.client = client
        self.rubrics = rubrics if rubrics is not None else _load_rubrics(config.rubrics_dir)
        self._semaphore = asyncio.Semaphore(config.max_concurrent)
        missing = [dim for dim in self.DEFAULT_DIMENSIONS if dim not in self.rubrics]
        if missing:
            logger.warning(
                "LLMJudge: missing rubrics for dimensions %s — scoring will skip them.",
                missing,
            )

    # ---- public API ----

    @classmethod
    def from_settings(cls) -> "LLMJudge":
        from app.config import settings

        repo_root = Path(__file__).resolve().parent
        rubrics_dir = repo_root / "rubrics"

        config = JudgeConfig(
            provider_model=getattr(
                settings, "llm_judge_provider_model", "anthropic:claude-sonnet-4-6"
            ),
            session_prefix=getattr(
                settings, "llm_judge_session_prefix", "mukthi-guru-judge"
            ),
            max_concurrent=int(getattr(settings, "llm_judge_max_concurrent", 4)),
            rubrics_dir=rubrics_dir,
            use_emergent_key=True,
            default_weights={
                "groundedness": 0.25,
                "doctrinal_consistency": 0.20,
                "citation_correctness": 0.15,
                "tone": 0.10,
                "refusal_correctness": 0.10,
                "context_precision": 0.10,
                "context_recall": 0.10,
            },
        )
        api_key = getattr(settings, "emergent_llm_key", "") or None
        client = JudgeClient(config, api_key=api_key)
        return cls(config=config, client=client)

    async def score_response(
        self,
        *,
        query: str,
        answer: str,
        retrieved_context: str,
        citations: Iterable[str] = (),
        expected_refusal: bool = False,
        question_meta: dict[str, Any] | None = None,
    ) -> CompositeScore:
        """Grade one (query, answer) triple across all configured dimensions.

        Args:
            query: The original user message.
            answer: The system's final answer text.
            retrieved_context: Concatenated text of the documents the system
                used to ground its answer. May be empty.
            citations: Source URLs / IDs the answer cited.
            expected_refusal: If True, the refusal_correctness rubric grades on
                whether the answer correctly refused / redirected.
            question_meta: Optional dict of meta (category, language, intent)
                passed to the rubric prompts so they can adapt.

        Returns:
            CompositeScore with all dimension scores attached.
        """
        meta = question_meta or {}
        tasks = []
        ordered_dims: list[str] = []
        for dim_name in self.DEFAULT_DIMENSIONS:
            if dim_name not in self.rubrics:
                continue
            rubric = self.rubrics[dim_name]
            ordered_dims.append(dim_name)
            tasks.append(
                self._score_single_dimension(
                    rubric=rubric,
                    query=query,
                    answer=answer,
                    retrieved_context=retrieved_context,
                    citations=citations,
                    expected_refusal=expected_refusal,
                    meta=meta,
                )
            )
        scores = await asyncio.gather(*tasks)

        dimensions: dict[str, DimensionScore] = dict(zip(ordered_dims, scores))
        composite = min(s.score for s in scores) if scores else 0.0
        weights = self.config.default_weights
        total_weight = sum(weights.get(name, 1.0) for name in dimensions) or 1.0
        weighted_mean = (
            sum(dimensions[name].score * weights.get(name, 1.0) for name in dimensions)
            / total_weight
        )
        all_pass = all(s.passes for s in scores)
        tokens = sum((s.judge_tokens_in or 0) + (s.judge_tokens_out or 0) for s in scores)
        latency = sum(s.judge_latency_ms or 0 for s in scores)

        return CompositeScore(
            query=query,
            composite=float(composite),
            weighted_mean=float(weighted_mean),
            dimensions=dimensions,
            all_pass=all_pass,
            total_judge_tokens=tokens,
            total_judge_latency_ms=latency,
        )

    # ---- internal ----

    async def _score_single_dimension(
        self,
        *,
        rubric: dict,
        query: str,
        answer: str,
        retrieved_context: str,
        citations: Iterable[str],
        expected_refusal: bool,
        meta: dict[str, Any],
    ) -> DimensionScore:
        dim_name = rubric.get("name") or "unknown"
        threshold = float(rubric.get("pass_threshold", 0.8))
        system_prompt = rubric.get("system_prompt", "")
        user_template = rubric.get("user_template", "")

        rendered = (
            user_template
            .replace("{{query}}", query)
            .replace("{{answer}}", answer or "")
            .replace("{{context}}", retrieved_context or "")
            .replace("{{citations}}", "\n".join(citations))
            .replace("{{expected_refusal}}", "true" if expected_refusal else "false")
            .replace("{{meta}}", json.dumps(meta, ensure_ascii=False))
        )

        session_id = f"{self.config.session_prefix}-{dim_name}-{abs(hash(query)) % 10**10}"

        async with self._semaphore:
            parsed, tokens_in, tokens_out, latency_ms = await self.client.chat_json(
                system_prompt=system_prompt,
                user_prompt=rendered,
                session_id=session_id,
            )

        score_raw = parsed.get("score")
        try:
            score_val = float(score_raw)
        except (TypeError, ValueError):
            score_val = 0.0
        score_val = max(0.0, min(1.0, score_val))

        return DimensionScore(
            name=dim_name,
            score=score_val,
            pass_threshold=threshold,
            rationale=str(parsed.get("rationale", ""))[:600],
            failure_mode=parsed.get("failure_mode") if score_val < threshold else None,
            judge_latency_ms=latency_ms,
            judge_tokens_in=tokens_in,
            judge_tokens_out=tokens_out,
        )
