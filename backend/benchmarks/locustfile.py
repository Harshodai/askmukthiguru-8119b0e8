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

import os

from locust import HttpUser, between, task
from locust.clients import ResponseContextManager


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
        # 503 with Retry-After is expected backpressure, not a failure — the
        # admission semaphore trips at max_concurrent_chat; the nightly gate
        # counts 503s separately from hard 5xx failures.
        if resp.status_code >= 500:
            resp.failure(f"5xx: {resp.status_code}")

    @staticmethod
    def _session_token() -> int:
        import time

        return int(time.time() * 1000) % (2**31)
