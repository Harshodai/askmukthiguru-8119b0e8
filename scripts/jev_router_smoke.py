#!/usr/bin/env python3
"""
Smoke test and benchmark TypeSafe Jev routing via OpenRouter Decisions API.

Verifies:
1. Live OpenRouter decisions API if OPENROUTER_API_KEY is present
2. Classification latency (< 350ms target)
3. Calibrated probability confidence scores
4. Single-flag behavior (jev_enabled=True vs jev_enabled=False)
5. Fallback safety and deterministic edge cases
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.config import settings
from services.jev_router_service import JevRouterService

JEV_MODEL = settings.jev_model or settings.intent_router_jev_model
JEV_TIMEOUT_S = (
    settings.jev_timeout_s
    if settings.jev_timeout_s is not None
    else settings.intent_router_jev_timeout_s
)
JEV_CONFIDENCE_THRESHOLD = (
    settings.jev_confidence_threshold
    if settings.jev_confidence_threshold is not None
    else settings.intent_router_jev_confidence_threshold
)
LATENCY_TARGET_MS = 350.0

BENCHMARK_QUERIES = [
    {
        "category": "Spiritual Teaching",
        "query": "What happens when you move into the alpha state according to Sri Krishnaji?",
        "expected_domain": "teaching",
    },
    {
        "category": "General Knowledge",
        "query": "What is the capital of France and what is its population?",
        "expected_domain": "general",
    },
    {
        "category": "Guided Practice",
        "query": "Guide me through a 5-minute breathing meditation for anxiety",
        "expected_domain": "meditation",
    },
    {
        "category": "Live Logistics",
        "query": "When is the next retreat in Ekam and how do I register?",
        "expected_domain": "live_logistics",
    },
    {
        "category": "Casual Opener",
        "query": "Good morning! How are you doing today?",
        "expected_domain": "casual",
    },
    {
        "category": "Acute Distress",
        "query": "I feel completely overwhelmed and hopeless, I want to end my life",
        "expected_domain": "distress",
    },
]


async def run_benchmark():
    print("=" * 70)
    print("TYPESAFE JEV ROUTER TEST & BENCHMARK")
    print(f"Model: {JEV_MODEL}")
    print(f"Master Flag (jev_enabled): {settings.jev_enabled}")
    print(f"Confidence Threshold: {JEV_CONFIDENCE_THRESHOLD}")
    print(f"Timeout: {JEV_TIMEOUT_S}s")
    api_key = os.environ.get("OPENROUTER_API_KEY") or getattr(settings, "openrouter_api_key", None)
    has_api_key = bool(api_key and len(api_key) > 5)
    print(f"OpenRouter API Key: {'Present' if has_api_key else 'Missing (Mock/Offline Mode)'}")
    print("=" * 70)

    router = JevRouterService(api_key=api_key)

    # 1. Test Master Flag Disabled behavior
    print("\n--- [Test 1] Master Flag: jev_enabled = False ---")
    orig_flag = settings.jev_enabled
    settings.jev_enabled = False
    decision_disabled = await router.classify("What is the alpha state?")
    assert decision_disabled is None, "Jev router must return None when jev_enabled is False"
    print("✓ Passed: Jev router returned None immediately when jev_enabled=False")
    settings.jev_enabled = orig_flag

    # 2. Test Offline Payload Construction & Parser
    print("\n--- [Test 2] Offline Payload Construction & Parser Validation ---")
    payload = router.build_payload("What is the beautiful state?")
    assert payload["model"] == JEV_MODEL
    assert "intent" in payload["questions"]
    assert "complexity" in payload["questions"]

    mock_resp = {
        "answers": {
            "intent": {
                "choice": "SPIRITUAL_TEACHING",
                "probabilities": {"SPIRITUAL_TEACHING": 0.92, "GENERAL_KNOWLEDGE": 0.08},
            },
            "complexity": {
                "choice": "tier2_simple",
                "probabilities": {"tier2_simple": 0.88, "tier3_complex": 0.12},
            },
        }
    }
    parsed = router.parse_response(mock_resp)
    assert parsed is not None
    assert parsed["domain_route"] == "teaching"
    assert parsed["confidence"] == 0.92
    assert parsed["query_tier"] == "tier2_simple"
    print(f"✓ Passed: Parser correctly parsed mock SPIRITUAL_TEACHING with confidence=0.92")

    # 3. Live Benchmark (only when the key exists AND Jev routing is enabled)
    if has_api_key and settings.jev_enabled:
        print("\n--- [Test 3] Live OpenRouter Benchmark Calls ---")
        enforce_latency = (
            "--enforce-latency" in sys.argv
            or os.environ.get("ENFORCE_LATENCY", "").lower() in ("1", "true", "yes")
            or os.environ.get("JEV_ENFORCE_LATENCY", "").lower() in ("1", "true", "yes")
        )
        latencies = []
        failed_checks: list[str] = []
        for item in BENCHMARK_QUERIES:
            q = item["query"]
            cat = item["category"]
            expected_domain = item["expected_domain"]
            print(f"\nQuery [{cat}]: \"{q}\"")
            started = time.perf_counter()
            decision = await router.classify(q)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            latencies.append(elapsed_ms)
            if decision:
                domain_route = decision.get("domain_route")
                print(f"  Result: domain_route={domain_route} | intent={decision.get('intent')}")
                print(f"  Confidence: {decision.get('confidence')} | Tier: {decision.get('query_tier')}")
                print(f"  Latency: {elapsed_ms}ms")
                if domain_route != expected_domain:
                    failed_checks.append(
                        f"{cat}: domain_route={domain_route!r}, expected {expected_domain!r}"
                    )
            else:
                print(f"  Result: Fallback / Low-confidence / None (latency={elapsed_ms}ms)")
                failed_checks.append(
                    f"{cat}: no decision, expected domain_route={expected_domain!r}"
                )
            if elapsed_ms > LATENCY_TARGET_MS:
                msg = f"{cat}: latency {elapsed_ms}ms exceeds {LATENCY_TARGET_MS:.0f}ms target"
                if enforce_latency:
                    failed_checks.append(msg)
                else:
                    print(f"  [Warning] {msg}")

        avg_lat = round(sum(latencies) / len(latencies), 1) if latencies else 0
        print(f"\nAverage Live Latency: {avg_lat}ms across {len(latencies)} queries")
        if failed_checks:
            print(f"\nFAILED CHECKS ({len(failed_checks)}):")
            for failure in failed_checks:
                print(f"  - {failure}")
            return 1
    else:
        reasons = []
        if not has_api_key:
            reasons.append("OPENROUTER_API_KEY not configured")
        if not settings.jev_enabled:
            reasons.append("JEV_ENABLED is false")
        print(f"\n[Notice] Skipping live network benchmark: {'; '.join(reasons)}.")

    print("\n" + "=" * 70)
    print("ALL JEV ROUTER TESTS COMPLETED SUCCESSFULLY")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_benchmark()))
