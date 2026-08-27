#!/usr/bin/env python3
"""Benchmark harness for the two Langhanam guru-voice variants.

Variant A (prompt): ``render_langhanam_system_prompt`` persona injection
into the generation system prompt.
Variant B (adapter): ``apply_langhanam_tone`` rule-based rewrite of the raw
generation output (filler stripping + sentence cadence).

Each response is scored two ways:
1. Rule-based heuristics (filler count, sentence length, direct address,
   Sanskrit terms, single-teaching, rhythm) — always available.
2. LLM-as-judge over STYLE_RUBRIC — used only when an LLM provider with
   credentials is configured (default provider from settings).

Degrades gracefully: without an LLM key the harness scores the cleaned
REFERENCE_VOICE paragraphs as synthetic responses, marks the report
``degraded: true``, and records the reason.

Usage:
    .venv/bin/python benchmarks/guru_voice_benchmark.py \
        --queries 6 \
        --output benchmarks/reports/guru_voice_benchmark_2026_07_30.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

TEST_QUERIES = [
    "What is langhanam?",
    "How do I stop negative thoughts?",
    "Tell me about fasting for health.",
    "How do I speak more powerfully?",
    "What should I do when I feel restless?",
    "Explain the four langhanams.",
]

STYLE_RUBRIC = {
    "direct_address": ("Uses direct address: I want you to, Listen, Try this", 1.0),
    "sanskrit_terms": ("Uses Sanskrit terms naturally", 1.0),
    "indian_english": ("Has Indian-English phrasing", 1.0),
    "no_fillers": ("No American fillers", 1.0),
    "single_teaching": ("Does not combine unrelated sources", 1.0),
    "rhythm": ("Short rhythmic sentences with repetition allowed", 1.0),
}

_CRITERIA = list(STYLE_RUBRIC)

# Rubric mean is reported on a 0-5 scale (5.0 = perfect on all six
# criteria), matching the "gate at >= 4.0/5.0" criterion in the brief.
# Criterion-level scores stay 0-1; only the aggregated mean is scaled.
_RUBRIC_SCALE = 5.0

_DIRECT_ADDRESS_RE = re.compile(
    r"\b(?:i want you to|listen|try this|notice|observe|imagine|practice)\b",
    re.IGNORECASE,
)
_INDIAN_ENGLISH_RE = re.compile(
    r"\b(?:ancients|in india|our ancients|fasting|practice)\b", re.IGNORECASE
)
_RHYTHM_GATES = ((20, 1.0), (30, 0.66), (40, 0.33))

# Filler words flagged by the LLM-as-judge prompt (mirrors LANGHANAM_FILLERS).
_FILLER_LIST = "like, you know, basically, totally, I think, kind of, sort of, I mean, literally"


def _bootstrap_env() -> None:
    """Export backend/.env KEY=VALUE pairs into os.environ (no-op if set).

    The repo ships a ``dotenv`` stub under backend/ that shadows
    python-dotenv, so pydantic-settings never reads .env itself. Setting the
    values into os.environ here (before any Settings import) restores
    normal config resolution for standalone script runs.
    """
    env_path = _BACKEND_DIR / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def _rule_scores(answer: str) -> dict[str, float]:
    """Heuristic scoring: filler count, cadence, address, terms, focus."""
    from services.guru_voice_langhanam import (
        contains_sanskrit_terms,
        count_fillers,
        detect_combined_teachings,
        has_direct_address,
        mean_sentence_length,
    )

    fillers = count_fillers(answer)
    msl = mean_sentence_length(answer)
    rhythm = 1.0
    for ceiling, score in _RHYTHM_GATES:
        if msl <= ceiling:
            rhythm = score
            break
    return {
        "direct_address": 1.0 if has_direct_address(answer) else 0.0,
        "sanskrit_terms": 1.0 if contains_sanskrit_terms(answer) else 0.0,
        "indian_english": 1.0 if _INDIAN_ENGLISH_RE.search(answer) else 0.0,
        "no_fillers": max(0.0, 1.0 - 0.33 * fillers),
        "single_teaching": 0.0 if detect_combined_teachings(answer) else 1.0,
        "rhythm": rhythm,
    }


_JUDGE_PROMPT = """You are a strict style judge. Score the guru's answer below against a
six-criterion rubric, one score per criterion, on a 0-1 scale (0 = absent,
1 = fully present).

Rubric:
- direct_address: Uses direct address to the seeker (I want you to, Listen, Try this).
- sanskrit_terms: Uses Sanskrit terms naturally (langhanam, vaak Shakti, prana, shuddhi).
- indian_english: Has Indian-English phrasing (e.g. "Our ancients in India used one very simple principle").
- no_fillers: No American conversational fillers ({fillers}).
- single_teaching: Does not combine or genericize teachings; stays with the one teaching asked about.
- rhythm: Short rhythmic sentences; repetition allowed for emphasis.

Seeker query: {query}

Answer:
{answer}

Do NOT restate or quote the rubric. Reply with ONLY the JSON object, no
markdown fences, no prose:
{{"direct_address": 0.0, "sanskrit_terms": 0.0, "indian_english": 0.0, "no_fillers": 1.0, "single_teaching": 1.0, "rhythm": 0.0}}"""


def _parse_judge_scores(raw: str) -> Optional[dict[str, float]]:
    if not raw:
        return None
    try:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        payload = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return None
    scores: dict[str, float] = {}
    for criterion in _CRITERIA:
        value = payload.get(criterion)
        if not isinstance(value, (int, float)):
            return None
        scores[criterion] = max(0.0, min(1.0, float(value)))
    return scores


def _mean(scores: dict[str, float]) -> float:
    return sum(scores.values()) / len(scores) if scores else 0.0


async def _llm_judge(query: str, answer: str, provider: Any) -> Optional[dict[str, float]]:
    try:
        raw = await asyncio.wait_for(
            provider.generate(
                system_prompt="You are a rigorous, unbiased style judge.",
                user_prompt=_JUDGE_PROMPT.format(query=query, answer=answer, fillers=_FILLER_LIST),
                temperature=0.0,
                max_tokens=700,
            ),
            timeout=60.0,
        )
    except (TimeoutError, Exception):
        return None
    return _parse_judge_scores(raw)


async def _generate(query: str, system_prompt: str, provider: Any) -> str:
    response = await asyncio.wait_for(
        provider.generate(
            system_prompt=system_prompt,
            user_prompt=f"Question: {query}\n\nAnswer in the voice of the guru.",
            temperature=0.4,
            max_tokens=600,
        ),
        timeout=90.0,
    )
    return (response or "").strip()


async def _score_response(query: str, answer: str, provider: Optional[Any]) -> dict[str, Any]:
    rule = _rule_scores(answer)
    entry: dict[str, Any] = {
        "response": answer,
        "rule_scores": rule,
        "rule_mean": round(_mean(rule) * _RUBRIC_SCALE, 3),
    }
    if provider is not None:
        judge = await _llm_judge(query, answer, provider)
        entry["judge_scores"] = judge
        entry["judge_mean"] = round(_mean(judge) * _RUBRIC_SCALE, 3) if judge else None
    return entry


async def _run_variant(
    queries: list[str],
    base_system_prompt: str,
    provider: Optional[Any],
    variant: str,
) -> tuple[list[dict[str, Any]], float]:
    from services.guru_voice_langhanam import render_langhanam_system_prompt

    results: list[dict[str, Any]] = []
    for query in queries:
        if variant == "prompt":
            system_prompt = render_langhanam_system_prompt(base_system_prompt)
            answer = await _generate(query, system_prompt, provider)
        elif variant == "adapter":
            from services.guru_voice_langhanam import strip_fillers

            raw = await _generate(query, base_system_prompt, provider)
            answer = strip_fillers(raw)
        else:
            answer = await _generate(query, base_system_prompt, provider)
        results.append(await _score_response(query, answer, provider))
    means = [r["rule_mean"] for r in results]
    return results, (sum(means) / len(means) if means else 0.0)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=int, default=len(TEST_QUERIES))
    parser.add_argument("--output", default="")
    parser.add_argument(
        "--skip-llm-judge",
        action="store_true",
        help="Score with rule-based heuristics only (no LLM-as-judge call).",
    )
    args = parser.parse_args()

    _bootstrap_env()

    from app.config import settings
    from rag.prompts import GURU_SYSTEM_PROMPT

    queries = TEST_QUERIES[: max(1, min(args.queries, len(TEST_QUERIES)))]
    output_path = Path(
        args.output
        or getattr(settings, "guru_voice_benchmark_output", "")
        or "benchmarks/reports/guru_voice_benchmark.json"
    )

    provider: Optional[Any] = None
    degraded = False
    degrade_reason = ""
    try:
        if not args.skip_llm_judge:
            from services.llm import LLMProviderFactory

            provider = LLMProviderFactory.create_provider(settings.llm_provider)
            # Smoke-test the provider so missing credentials surface here.
            await asyncio.wait_for(
                provider.generate(
                    system_prompt="Reply with the single word: ok",
                    user_prompt="ok",
                    max_tokens=5,
                ),
                timeout=30.0,
            )
    except Exception as exc:  # noqa: BLE001 - graceful degradation is the contract
        degraded = True
        degrade_reason = f"{type(exc).__name__}: {exc}"
        provider = None

    if degraded or provider is None:
        # Synthetic mode: score the cleaned reference voice as both variants'
        # response corpus so the harness still exercises the rubric + adapter.
        from services.guru_voice_langhanam import REFERENCE_VOICE

        results: dict[str, list[dict[str, Any]]] = {}
        means: dict[str, float] = {}
        for variant in ("prompt", "adapter"):
            answers = [
                "\n\n".join(REFERENCE_VOICE.split("\n\n")[: i + 1]) for i in range(len(queries))
            ]
            variant_results = [await _score_response(q, a, None) for q, a in zip(queries, answers)]
            results[variant] = variant_results
            means[variant] = round(
                sum(r["rule_mean"] for r in variant_results) / len(variant_results), 3
            )
    else:
        results = {}
        means = {}
        for variant in ("prompt", "adapter"):
            variant_results, mean = await _run_variant(
                queries, GURU_SYSTEM_PROMPT, provider, variant
            )
            results[variant] = variant_results
            means[variant] = round(mean, 3)

    gate_score = float(getattr(settings, "guru_voice_gate_score", 4.0))
    winner = max(means, key=means.get)
    # The gate only counts on a live run — synthetic (degraded) runs score
    # the cleaned reference voice, not real generations, so they must never
    # flip the feature flag.
    gate_met = not degraded and means[winner] >= gate_score

    def _judge_mean(variant: str) -> Optional[float]:
        judged = [r["judge_mean"] for r in results[variant] if r.get("judge_mean") is not None]
        if not judged:
            return None
        return round(sum(judged) / len(judged), 3)

    judge_summary = {
        "variant_a_prompt_judge_mean": _judge_mean("prompt"),
        "variant_b_adapter_judge_mean": _judge_mean("adapter"),
    }

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "config": {
            "langhanam_voice_enabled": bool(settings.langhanam_voice_enabled),
            "guru_voice_mode": settings.guru_voice_mode,
            "gate_score": gate_score,
            "llm_provider": settings.llm_provider if not degraded else "unavailable",
        },
        "degraded": degraded,
        "degrade_reason": degrade_reason,
        "judge": {
            "llm_available": provider is not None,
            "method": "LLM-as-judge over STYLE_RUBRIC"
            if provider is not None
            else "rule-based only",
        },
        "rubric": STYLE_RUBRIC,
        "queries": [
            {
                "query": queries[i],
                "variant_a_prompt": results["prompt"][i],
                "variant_b_adapter": results["adapter"][i],
            }
            for i in range(len(queries))
        ],
        "summary": {
            "variant_a_prompt_mean": means["prompt"],
            "variant_b_adapter_mean": means["adapter"],
            "winner": "prompt" if winner == "prompt" else "adapter",
            "gate_met": bool(gate_met),
            **judge_summary,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Guru voice benchmark — {len(queries)} queries")
    if degraded:
        print(f"  degraded: {degrade_reason} (synthetic REFERENCE_VOICE corpus, rule-based scores)")
    print(f"  variant A (prompt)   mean: {means['prompt']:.3f}/5.0")
    print(f"  variant B (adapter)  mean: {means['adapter']:.3f}/5.0")
    print(f"  winner: {report['summary']['winner']} | gate (>= {gate_score}/5.0): {gate_met}")
    print(f"  report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
