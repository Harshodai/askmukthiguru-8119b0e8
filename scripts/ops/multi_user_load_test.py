from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import time
from dataclasses import dataclass
from typing import Any

import requests

QUESTIONS = (
    "What is one evidence-based benefit of mindfulness, and what remains uncertain?",
    "Explain the difference between spiritual reflection and medical advice.",
    "What does AskMukthiGuru do when it cannot verify a teacher quotation?",
    "What is one simple grounding exercise that is not a substitute for professional care?",
    "What information should I avoid sharing in a public chat?",
    "What is a cautious way to think about long-exhale breathing?",
    "Can you answer without inventing a source or pretending to be a named teacher?",
    "How should I seek urgent professional help if I may be in danger?",
)


@dataclass(frozen=True)
class Session:
    token: str
    session_id: str


def bootstrap(base_url: str, index: int) -> Session:
    response = requests.post(
        f"{base_url}/api/auth/anon-session",
        json={},
        timeout=(5, 20),
        allow_redirects=False,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("token")
    session_id = payload.get("session_id")
    if not isinstance(token, str) or not isinstance(session_id, str):
        raise RuntimeError(f"anonymous bootstrap {index} returned invalid shape")
    return Session(token=token, session_id=session_id)


def chat_once(base_url: str, session: Session, question: str, index: int) -> dict[str, Any]:
    started = time.perf_counter()
    body = {
        "messages": [],
        "user_message": question,
        "session_id": session.token,
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
    try:
        response = requests.post(
            f"{base_url}/api/chat",
            json=body,
            headers={"Authorization": f"Bearer {session.token}"},
            timeout=(5, 75),
            allow_redirects=False,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        content_type = response.headers.get("content-type", "")
        preview: dict[str, Any] = {}
        if "json" in content_type:
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    preview = {
                        "keys": sorted(str(key) for key in payload.keys())[:30],
                        "answer_chars": len(
                            str(payload.get("answer", payload.get("response", "")))
                        ),
                        "error_code": payload.get("error_code"),
                        "quota_exceeded": payload.get("quota_exceeded"),
                        "intent": payload.get("intent"),
                    }
            except ValueError:
                preview = {"json_parse": "failed"}
        return {
            "index": index,
            "status": response.status_code,
            "latency_ms": elapsed_ms,
            "content_type": content_type,
            "response": preview,
            "success": 200 <= response.status_code < 300,
        }
    except requests.RequestException as exc:
        return {
            "index": index,
            "status": None,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "error_type": type(exc).__name__,
            "success": False,
        }


def health_once(base_url: str, index: int) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = requests.get(
            f"{base_url}/api/health",
            timeout=(5, 20),
            allow_redirects=False,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        ready = False
        payload: dict[str, Any] = {}
        if "json" in response.headers.get("content-type", ""):
            try:
                raw = response.json()
                if isinstance(raw, dict):
                    payload = raw
                    ready = raw.get("ready") is True
            except ValueError:
                pass
        return {
            "index": index,
            "status": response.status_code,
            "latency_ms": elapsed_ms,
            "ready": ready,
            "service_keys": sorted(str(key) for key in payload.get("services", {}).keys())[:20],
            "success": response.status_code == 200 and ready,
        }
    except requests.RequestException as exc:
        return {"index": index, "status": None, "error_type": type(exc).__name__, "success": False}


def run_wave(fn, items: list[Any], workers: int) -> list[dict[str, Any]]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fn, item, index) for index, item in enumerate(items)]
        return [future.result() for future in futures]


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded synthetic-user Railway load probe")
    parser.add_argument(
        "--base-url", default="https://askmukthiguru-8119b0e8-production.up.railway.app"
    )
    parser.add_argument("--users", type=int, default=8)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--health-requests", type=int, default=20)
    parser.add_argument("--chat-requests", type=int, default=8)
    args = parser.parse_args()
    if not 1 <= args.users <= 20 or not 1 <= args.workers <= 8:
        parser.error("users must be 1..20 and workers must be 1..8")
    if not 0 <= args.chat_requests <= args.users:
        parser.error("chat-requests must be between 0 and users")
    base_url = args.base_url.rstrip("/")

    started = time.perf_counter()
    sessions = run_wave(
        lambda _item, index: bootstrap(base_url, index),
        list(range(args.users)),
        args.workers,
    )
    health = run_wave(
        lambda _item, index: health_once(base_url, index),
        list(range(args.health_requests)),
        args.workers,
    )
    chats = run_wave(
        lambda session, index: chat_once(
            base_url, session, QUESTIONS[index % len(QUESTIONS)], index
        ),
        sessions[: args.chat_requests],
        args.workers,
    )

    health_latencies = [
        float(item["latency_ms"]) for item in health if item.get("latency_ms") is not None
    ]
    chat_latencies = [
        float(item["latency_ms"]) for item in chats if item.get("latency_ms") is not None
    ]
    summary = {
        "base_url": base_url,
        "users_bootstrapped": len(sessions),
        "health_requests": len(health),
        "health_successes": sum(bool(item.get("success")) for item in health),
        "chat_requests": len(chats),
        "chat_successes": sum(bool(item.get("success")) for item in chats),
        "chat_status_counts": {
            str(status): sum(item.get("status") == status for item in chats)
            for status in sorted({item.get("status") for item in chats}, key=str)
        },
        "health_p50_ms": (
            round(statistics.median(health_latencies), 1) if health_latencies else None
        ),
        "health_max_ms": round(max(health_latencies), 1) if health_latencies else None,
        "chat_p50_ms": round(statistics.median(chat_latencies), 1) if chat_latencies else None,
        "chat_max_ms": round(max(chat_latencies), 1) if chat_latencies else None,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "health_results": health,
        "chat_results": chats,
    }
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return (
        0
        if summary["users_bootstrapped"] == args.users
        and summary["health_successes"] == args.health_requests
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
