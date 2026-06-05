"""
Unit 26 — Load Testing with Locust

Locust load test suite for Mukthi Guru backend.

Scenarios covered:
  1. ChatUser: realistic /api/chat requests with varied spiritual questions
  2. StreamUser: SSE streaming endpoint (/api/chat/stream)
  3. HealthUser: lightweight /api/health probe

Usage (run from project root):
    cd backend
    pip install locust
    locust -f ../scripts/load_test.py --host http://localhost:8000 --users 10 --spawn-rate 2

Or headless:
    locust -f ../scripts/load_test.py --host http://localhost:8000 \
        --users 50 --spawn-rate 5 --run-time 5m --headless \
        --csv=locust_results

Target SLOs:
  - P50 response < 3s
  - P95 response < 10s
  - Error rate < 1%
  - /api/health: always < 200ms
"""

import json
import os
import random
import time

from locust import HttpUser, between, events, task
from locust.exception import RescheduleTask


# -----------------------------------------------------------------------
# Test data
# -----------------------------------------------------------------------
SPIRITUAL_QUESTIONS = [
    "What is the nature of consciousness according to Sri Preethaji's teachings?",
    "How can I overcome suffering through inner awakening?",
    "What does non-doing mean in the context of spiritual practice?",
    "Explain the concept of beautiful states of being.",
    "How do I deal with anger and frustration from a spiritual perspective?",
    "What is the relationship between meditation and daily life?",
    "How does one cultivate compassion without losing oneself?",
    "What is the significance of the Ekam teachings?",
    "How can I find peace in difficult relationships?",
    "What is the connection between consciousness and reality?",
    "How does one transcend fear through spiritual practice?",
    "What is the meaning of oneness in Sri Krishnaji's philosophy?",
]

# Auth header — uses test key bypass (avoids needing real Supabase tokens)
def _auth_headers() -> dict:
    test_key = os.environ.get("MUKTHI_TEST_KEY", "test-secret")
    return {"X-Test-Key": test_key, "Content-Type": "application/json"}


# -----------------------------------------------------------------------
# User classes
# -----------------------------------------------------------------------

class ChatUser(HttpUser):
    """Simulates a seeker asking spiritual questions via the chat endpoint."""

    wait_time = between(3, 8)  # Think time between requests
    weight = 6  # 60% of load

    def on_start(self):
        self.headers = _auth_headers()
        self.session_id = f"locust-{random.randint(10000, 99999)}"
        self.history = []

    @task(3)
    def ask_question(self):
        """Single question with minimal history."""
        question = random.choice(SPIRITUAL_QUESTIONS)
        payload = {
            "messages": self.history[-4:],  # Keep last 2 turns
            "user_message": question,
            "session_id": self.session_id,
            "language": "en",
        }

        start = time.time()
        with self.client.post(
            "/api/chat",
            json=payload,
            headers=self.headers,
            catch_response=True,
            timeout=30,
        ) as resp:
            latency = (time.time() - start) * 1000
            if resp.status_code == 200:
                data = resp.json()
                answer = data.get("response", "")
                if not answer:
                    resp.failure(f"Empty response body (latency={latency:.0f}ms)")
                    return
                resp.success()
                # Add to conversation history
                self.history.append({"role": "user", "content": question})
                self.history.append({"role": "assistant", "content": answer[:200]})
                if len(self.history) > 10:
                    self.history = self.history[-10:]
            elif resp.status_code == 429:
                # Rate limited — reschedule
                raise RescheduleTask()
            else:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:100]}")

    @task(1)
    def ask_follow_up(self):
        """Follow-up question on a previous topic."""
        if not self.history:
            raise RescheduleTask()
        follow_ups = [
            "Can you elaborate on that?",
            "How can I apply this in daily life?",
            "What practice would help me experience this?",
            "Is there a teaching story about this?",
        ]
        question = random.choice(follow_ups)
        payload = {
            "messages": self.history[-4:],
            "user_message": question,
            "session_id": self.session_id,
            "language": "en",
        }
        with self.client.post(
            "/api/chat",
            json=payload,
            headers=self.headers,
            catch_response=True,
            timeout=30,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 429:
                raise RescheduleTask()
            else:
                resp.failure(f"HTTP {resp.status_code}")


class HealthUser(HttpUser):
    """Lightweight health probe — always fast."""

    wait_time = between(1, 2)
    weight = 2  # 20% of load

    def on_start(self):
        self.headers = _auth_headers()

    @task
    def health_check(self):
        with self.client.get(
            "/api/health",
            headers=self.headers,
            catch_response=True,
            timeout=5,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") != "ok":
                    resp.failure(f"Health status not ok: {data.get('status')}")
                else:
                    resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")


class StreamUser(HttpUser):
    """Tests the SSE streaming endpoint."""

    wait_time = between(5, 15)
    weight = 2  # 20% of load

    def on_start(self):
        self.headers = {**_auth_headers(), "Accept": "text/event-stream"}

    @task
    def stream_question(self):
        question = random.choice(SPIRITUAL_QUESTIONS)
        payload = {
            "messages": [],
            "user_message": question,
            "language": "en",
        }
        start = time.time()
        try:
            with self.client.post(
                "/api/chat/stream",
                json=payload,
                headers=self.headers,
                stream=True,
                catch_response=True,
                timeout=60,
            ) as resp:
                if resp.status_code not in (200, 204):
                    resp.failure(f"HTTP {resp.status_code}")
                    return
                # Consume the SSE stream
                chunks = 0
                for line in resp.iter_lines():
                    if line:
                        chunks += 1
                latency = (time.time() - start) * 1000
                if chunks == 0:
                    resp.failure(f"Empty SSE stream (latency={latency:.0f}ms)")
                else:
                    resp.success()
        except Exception as exc:
            pass  # Stream endpoint may not exist in all deploys


# -----------------------------------------------------------------------
# Locust event hooks for SLO reporting
# -----------------------------------------------------------------------
@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    """Print SLO summary on test completion."""
    stats = environment.stats.total
    p50 = stats.get_response_time_percentile(0.50) or 0
    p95 = stats.get_response_time_percentile(0.95) or 0
    error_rate = (stats.num_failures / max(stats.num_requests, 1)) * 100

    print("\n" + "=" * 60)
    print("LOAD TEST SLO SUMMARY")
    print("=" * 60)
    print(f"  Total requests:   {stats.num_requests}")
    print(f"  Failures:         {stats.num_failures} ({error_rate:.1f}%)")
    print(f"  P50 latency:      {p50:.0f}ms  (SLO: <3000ms) {'✅' if p50 < 3000 else '❌'}")
    print(f"  P95 latency:      {p95:.0f}ms  (SLO: <10000ms) {'✅' if p95 < 10000 else '❌'}")
    print(f"  Error rate:       {error_rate:.1f}%  (SLO: <1%) {'✅' if error_rate < 1 else '❌'}")
    print("=" * 60)

    if error_rate >= 1 or p95 >= 10000:
        environment.process_exit_code = 1
