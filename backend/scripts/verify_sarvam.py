#!/usr/bin/env python3
"""Verify Sarvam Cloud API connectivity and report latency."""

import json
import os
import sys
import time
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings  # noqa: E402


def verify_sarvam() -> tuple[bool, str, float | None]:
    """Check Sarvam API with a minimal, authenticated call."""
    api_key = settings.sarvam_api_key
    base_url = settings.sarvam_base_url
    model = settings.sarvam_cloud_model
    provider = settings.llm_provider

    print("=" * 60)
    print("SARVAM CLOUD API VERIFICATION")
    print("=" * 60)
    print(f"  LLM Provider   : {provider}")
    print(f"  Base URL       : {base_url}")
    print(f"  Model          : {model}")
    print(f"  API Key        : {'***SET***' if api_key else 'MISSING'}")
    print()

    if provider.lower() != "sarvam_cloud":
        msg = f"LLM provider is '{provider}' (not 'sarvam_cloud') — skipping live API call"
        print(f"INFO: {msg}")
        return False, msg, None

    if not api_key:
        print("RESULT: FAIL — sarvam_api_key is empty (check .env)")
        return False, "Missing API key", None

    try:
        import urllib.request
    except ImportError:
        return False, "urllib not available", None

    # Sarvam uses api-subscription-key header, not Bearer
    headers = {
        "Content-Type": "application/json",
        "api-subscription-key": api_key,
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Say 'Sarvam API is live' and nothing else."}
        ],
        "max_tokens": 20,
        "temperature": 0.0,
    }

    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        start = time.time()
        with urllib.request.urlopen(req, timeout=30) as resp:
            latency = time.time() - start
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        latency = None
        body_str = e.read().decode("utf-8", errors="replace")
        print(f"RESULT: FAIL — HTTP {e.code}: {body_str[:200]}")
        return False, f"HTTP {e.code}", None
    except Exception as e:
        latency = None
        print(f"RESULT: FAIL — Request error: {e}")
        return False, str(e)[:100], None

    choices = body.get("choices", [{}])
    if choices:
        content = choices[0].get("message", {}).get("content", "")
    else:
        content = str(body)

    # Heuristic: non-empty response = success
    if content.strip():
        print(f"RESULT: PASS — API responded in {latency:.2f}s")
        print(f"  Response preview: {content[:120].strip()}")
        return True, content[:120], latency
    else:
        print(f"RESULT: WARN — Empty response from API")
        return False, "Empty response", latency


if __name__ == "__main__":
    success, message, latency = verify_sarvam()
    print()
    if success:
        print(f"✅ Sarvam API is LIVE (latency: {latency:.2f}s, model: {settings.sarvam_cloud_model})")
        sys.exit(0)
    else:
        print(f"❌ Sarvam API NOT LIVE — {message}")
        sys.exit(1)
