#!/usr/bin/env python3
"""
verify_custom_assistants.py — E2E validation script for Custom Assistants features.
Performs API queries and checks postgres database telemetry records.
"""

import argparse
import asyncio
import os
import sys
import uuid
import httpx
import subprocess
from pathlib import Path

# Add backend directory to path so app.config is importable when run standalone.
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings


def build_config(args: argparse.Namespace) -> dict:
    """Return runtime configuration from CLI args and environment."""
    return {
        "base_url": args.backend_url or os.getenv("BACKEND_URL", "http://localhost:8000"),
        "jwt_secret": args.jwt_secret or os.getenv("JWT_SECRET", settings.jwt_secret),
        "db_container": args.db_container or os.getenv("SUPABASE_DB_CONTAINER", "supabase_db"),
        "wait_telemetry": args.wait_telemetry,
    }


async def query_chat_api(config: dict, payload: dict) -> httpx.Response:
    async with httpx.AsyncClient(timeout=400.0) as client:
        headers = {"X-Test-Key": config["jwt_secret"]}
        response = await client.post(
            f"{config['base_url']}/api/chat",
            json=payload,
            headers=headers
        )
        return response


def check_db_telemetry(config: dict, expected_slug: str) -> bool:
    """Run a query inside the Supabase Postgres container to check telemetry."""
    sql = f"SELECT assistant_slug FROM public.chat_queries WHERE assistant_slug = '{expected_slug}' LIMIT 1;"
    cmd = [
        "docker", "exec", "-i", config["db_container"],
        "psql", "-U", "postgres", "-d", "postgres",
        "-c", sql
    ]
    try:
        env = os.environ.copy()
        env["PATH"] = f"/Users/harshodaikolluru/.docker/bin:{env.get('PATH', '')}"

        res = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            check=True
        )
        print(f"Postgres telemetry output:\n{res.stdout}")
        return expected_slug in res.stdout
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to check database telemetry: {e}")
        if e.stderr:
            print(f"Stderr: {e.stderr}")
        return False
    except FileNotFoundError as e:
        print(f"❌ Failed to check database telemetry: {e}")
        return False


async def main():
    parser = argparse.ArgumentParser(description="E2E validation for Custom Assistants.")
    parser.add_argument("--backend-url", default=None, help="Backend base URL (default: $BACKEND_URL or http://localhost:8000)")
    parser.add_argument("--db-container", default=None, help="Docker container name for Supabase Postgres (default: $SUPABASE_DB_CONTAINER or supabase_db)")
    parser.add_argument("--jwt-secret", default=None, help="JWT/test secret (default: $JWT_SECRET or settings.jwt_secret)")
    parser.add_argument("--wait-telemetry", type=float, default=2.0, help="Seconds to wait for telemetry sink (default: 2)")
    args = parser.parse_args()

    config = build_config(args)

    print("\n" + "=" * 60)
    print("MUKTHI GURU: CUSTOM ASSISTANTS SMOKE TEST")
    print("=" * 60 + "\n")

    test_id = str(uuid.uuid4())[:8]
    assistant_slug = f"test-assistant-{test_id}"

    # Scenario 1: No Assistant Block (baseline)
    print("Scenario 1: Sending request without assistant block (baseline)...")
    payload_baseline = {
        "messages": [{"role": "user", "content": "What is the Beautiful State?"}],
        "user_message": "What is the Beautiful State?"
    }
    resp1 = await query_chat_api(config, payload_baseline)
    if resp1.status_code == 200:
        print("✅ Baseline succeeded (200 OK)")
    else:
        print(f"❌ Baseline failed: {resp1.status_code}\n{resp1.text}")
        sys.exit(1)

    # Scenario 2: With assistant.knowledge_tags=["general"] (verify no sky chunks)
    print("\nScenario 2: Sending request with knowledge_tags=['general']...")
    payload_general = {
        "messages": [{"role": "user", "content": "Tell me about spiritual teachings."}],
        "user_message": "Tell me about spiritual teachings.",
        "assistant": {
            "slug": assistant_slug,
            "system_prompt": "You are a general spiritual assistant.",
            "knowledge_tags": ["general"]
        }
    }
    resp2 = await query_chat_api(config, payload_general)
    if resp2.status_code == 200:
        print("✅ Request with general tags succeeded (200 OK)")
        resp_data = resp2.json()
        citations = resp_data.get("citations", [])
        print(f"Retrieved {len(citations)} citations")
        sky_found = False
        for cit in citations:
            tags = cit.get("tags", [])
            tags_lower = [t.lower() for t in tags]
            if "sky" in tags_lower:
                print(f"❌ Sky chunk found in general tags citations: {cit}")
                sky_found = True
        if not sky_found:
            print("✅ Checked: No 'sky' chunks returned in general mode.")
        else:
            sys.exit(1)
    else:
        print(f"❌ General tags request failed: {resp2.status_code}\n{resp2.text}")
        sys.exit(1)

    # Scenario 3: Run with assistant.knowledge_tags=["sky"] on a corpus with zero SKY chunks
    print("\nScenario 3: Sending request with knowledge_tags=['sky'] (checking fallback)...")
    payload_sky = {
        "messages": [{"role": "user", "content": "Is there a sky teaching?"}],
        "user_message": "Is there a sky teaching?",
        "assistant": {
            "slug": f"sky-assistant-{test_id}",
            "system_prompt": "You are a sky teachings assistant.",
            "knowledge_tags": ["sky"]
        }
    }
    resp3 = await query_chat_api(config, payload_sky)
    if resp3.status_code == 200:
        print("✅ Request with sky tags succeeded (200 OK - graceful fallback, no 500)")
    elif resp3.status_code == 500:
        print("❌ Request failed with 500 Internal Server Error!")
        sys.exit(1)
    else:
        print(f"⚠️ Succeeded with fallback behavior/refusal or status: {resp3.status_code}")

    # Scenario 4: Verify chat_queries.assistant_slug is populated in telemetry
    print("\nScenario 4: Verifying telemetry record for assistant_slug...")
    await asyncio.sleep(config["wait_telemetry"])
    if check_db_telemetry(config, assistant_slug):
        print("✅ Verified: assistant_slug is populated in Supabase chat_queries telemetry!")
    else:
        print(f"❌ Failed: Could not find telemetry record with assistant_slug='{assistant_slug}'")
        sys.exit(1)

    print("\n🎉 ALL CUSTOM ASSISTANTS SMOKE TESTS PASSED!")
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
