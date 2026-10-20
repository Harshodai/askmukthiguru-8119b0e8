"""Locust load test for /api/chat (P1-OPS-7).

Sweeps concurrency 1→10→50→100 with a MOCK LLM (no LLM cost). Point the
backend at the canned stub via NIM_BASE_URL (see scripts/mock_llm_server.py):

    export LLM_PROVIDER=nim NIM_API_KEY=mock NIM_BASE_URL=http://127.0.0.1:9002/v1
    python scripts/mock_llm_server.py                 # terminal 1
    uvicorn app.main:app --port 8000                  # terminal 2 (X-Test-Key backdoor opt-in)
    locust -f benchmarks/locustfile.py --headless -u 100 -r 10 -t 5m \
        --host http://127.0.0.1:8000 --print-stats

Gates (nightly-load.yml asserts): p95 < 8s at concurrency 20; no 5xx;
backpressure 503s trip only when concurrent in-flight exceeds
max_concurrent_chat (default 20).

Auth: the benchmark X-Test-Key backdoor is REQUIRED locally (IS_PRODUCTION=false,
ENABLE_TEST_AUTH=true, BENCHMARK_SECRET set). CI nightly runs against staging
with the same env.
"""

import json
import os
from pathlib import Path

from locust.clients import ResponseContextManager
from locust import HttpUser, between, events, task


_EXPECTED_BACKPRESSURE_RESPONSES = 0


@events.test_stop.add_listener
def _write_backpressure_report(environment, **kwargs) -> None:
    """Publish deliberate capacity-shedding evidence for the c50 hard gate."""
    path = os.environ.get("BACKPRESSURE_REPORT_PATH")
    if not path:
        return
    try:
        Path(path).write_text(
            json.dumps({"expected_503": _EXPECTED_BACKPRESSURE_RESPONSES}),
            encoding="utf-8",
        )
    except OSError as exc:
        # The workflow gate will fail closed if the report is absent/unreadable.
        print(f"Could not write backpressure report: {type(exc).__name__}")


class ChatUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self):
        self._test_key = os.environ.get("BENCHMARK_SECRET", "dev-secret-not-set")
        self._headers = {
            "Content-Type": "application/json",
            "X-Test-Key": self._test_key,
        }

    @task(3)
    def ask_chat(self) -> None:
        with self.client.post(
            "/api/chat",
            json={
                "messages": [
                    {"role": "user", "content": "What is the essence of inner stillness?"}
                ],
                "user_message": "What is the essence of inner stillness?",
                "language": "en",
                "session_id": str(self._session_token()),
            },
            headers=self._headers,
            catch_response=True,
        ) as resp:
            self._check(resp)

    @task(1)
    def casual_chat(self) -> None:
        with self.client.post(
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": "Hi"}],
                "user_message": "Hi",
                "language": "en",
            },
            headers=self._headers,
            catch_response=True,
        ) as resp:
            self._check(resp)

    @task(1)
    def health_probe(self) -> None:
        self.client.get("/api/health")

    @staticmethod
    def _check(resp: ResponseContextManager) -> None:
        global _EXPECTED_BACKPRESSURE_RESPONSES
        # The c50 sweep may explicitly treat a correctly identified admission
        # shed as expected backpressure. We require both the precise response
        # contract and Retry-After; startup/queue/provider 503s remain failures.
        controlled_shed = (
            resp.status_code == 503
            and bool(resp.headers.get("Retry-After"))
            and "Server busy, try again shortly" in (resp.text or "")
        )
        if (
            controlled_shed
            and os.environ.get("ALLOW_EXPECTED_BACKPRESSURE") == "1"
        ):
            _EXPECTED_BACKPRESSURE_RESPONSES += 1
            resp.success()
            return
        if resp.status_code >= 500:
            resp.failure(f"5xx: {resp.status_code} {(resp.text or '')[:160]}")

    @staticmethod
    def _session_token() -> int:
        import time

        return int(time.time() * 1000) % (2**31)
