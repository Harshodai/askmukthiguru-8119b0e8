from __future__ import annotations

import argparse
import json
import time

import requests


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded SSE chat probe")
    parser.add_argument(
        "--base-url", default="https://askmukthiguru-8119b0e8-production.up.railway.app"
    )
    parser.add_argument(
        "--question",
        default="What is one evidence-based benefit of mindfulness, and what remains uncertain?",
    )
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    started = time.perf_counter()
    session_response = requests.post(
        f"{base_url}/api/auth/anon-session",
        json={},
        timeout=(5, 20),
        allow_redirects=False,
    )
    session_response.raise_for_status()
    session_payload = session_response.json()
    token = session_payload["token"]
    body = {
        "messages": [],
        "user_message": args.question,
        "session_id": token,
        "language": "en",
        "incognito": True,
        "meditation_step": 0,
        "response_preferences": {
            "tone": "balanced_guidance",
            "include_practice": False,
            "include_reflection": False,
            "action_depth": "none",
        },
    }
    event_count = 0
    event_types: list[str] = []
    response_status: int | None = None
    error: str | None = None
    try:
        with requests.post(
            f"{base_url}/api/chat/stream",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=(5, 75),
            stream=True,
            allow_redirects=False,
        ) as response:
            response_status = response.status_code
            for raw_line in response.iter_lines(decode_unicode=True):
                if raw_line is None:
                    continue
                line = raw_line.strip()
                if line.startswith("event:"):
                    event_count += 1
                    event_types.append(line.split(":", 1)[1].strip()[:80])
                if event_count >= 30 or (time.perf_counter() - started) > 70:
                    break
    except requests.RequestException as exc:
        error = type(exc).__name__
    result = {
        "base_url": base_url,
        "status": response_status,
        "event_count": event_count,
        "event_types": event_types,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "error_type": error,
        "received_events": event_count > 0,
    }
    print(json.dumps(result, indent=2))
    return 0 if response_status in (200, 202) and event_count > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
