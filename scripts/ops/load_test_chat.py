#!/usr/bin/env python3
"""Capacity load generator for POST /api/chat (202 + poll_url), LOCAL targets only.

Each simulated user gets an anonymous session (POST /api/auth/anon-session), sends distinct
questions (never an exact-cache hit), follows poll_url the way src/lib/chat/transport.ts does
(250 ms, +250 ms per poll, capped 1 s) and honours Retry-After on 429/503 (3 retries, as the
frontend's fetchWithRetry). Reports p50/p95/p99 end-to-end, throughput, status-code mix,
server-side queue wait and, with --pid, CPU/RSS of the backend process.

  --think-time 0   one message per user, all at once (spike)
  --think-time 60  each user sends a message every ~60 s for --duration seconds

Refuses any --base-url that is not loopback: this must never be pointed at Railway or a
production domain.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
import uuid
from collections import Counter
from urllib.parse import urlparse

import httpx

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}
TOPICS = [
    "how do I stop overthinking at night",
    "what is the beautiful state",
    "how can I forgive someone who hurt me",
    "why do I feel anxious about the future",
    "how do I deal with anger at my family",
    "what does suffering teach us",
    "how can I be present with my children",
    "how do I meditate when my mind is restless",
    "what is the difference between pain and suffering",
    "how do I handle a difficult boss with peace",
    "how to let go of regret",
    "what is the role of gratitude in daily life",
    "how can I find purpose when I feel lost",
    "how do I break free from fear of failure",
    "what is ego and how does it hold me back",
    "how do I deal with grief after losing a parent",
    "how can I bring more compassion into my marriage",
    "what is a connected state of mind",
    "why do I keep comparing myself with others",
    "how do I stay calm when everything goes wrong",
]
FRAMES = ["{t}?", "Please help me understand {t}.", "I have been wondering {t}", "Guru, {t}?"]


def require_local(url: str) -> None:
    host = urlparse(url).hostname or ""
    if host not in LOCAL_HOSTS:
        sys.exit(f"refusing non-local --base-url host {host!r}: load tests are local-only")


def safe_poll_path(poll_url: object) -> str:
    """poll_url must be a host-relative path: an absolute or scheme-relative URL would send the
    session token to whatever host the server named."""
    if not isinstance(poll_url, str) or not poll_url.startswith("/") or poll_url.startswith("//"):
        raise ValueError(f"refusing non-relative poll_url {poll_url!r}")
    return poll_url


def question(user: int, n: int) -> str:
    t = random.choice(TOPICS)
    # a unique tail keeps every message distinct so the exact cache never answers it
    return random.choice(FRAMES).format(t=t) + f" (ref {user}-{n}-{uuid.uuid4().hex[:6]})"


def pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return round(s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))], 3)


class Stats:
    def __init__(self) -> None:
        self.first_status: Counter[str] = Counter()
        self.poll_status: Counter[str] = Counter()
        self.outcome: Counter[str] = Counter()
        self.grounding: Counter[str] = Counter()
        self.e2e: list[float] = []
        self.queue_wait: list[float] = []
        self.run_time: list[float] = []
        self.server_latency: list[float] = []
        self.polls = 0
        self.completed_at: list[float] = []


async def one_message(
    c: httpx.AsyncClient, st: Stats, a: argparse.Namespace, u: int, n: int, token: str, xff: str
) -> None:
    hdr = {"X-Forwarded-For": xff}
    body = {"messages": [], "user_message": question(u, n), "session_id": token, "language": "en"}
    t0 = time.monotonic()
    r = None
    for attempt in range(1 + a.retries):
        try:
            r = await c.post("/api/chat", json=body, headers=hdr)
        except httpx.HTTPError:
            st.first_status["conn_error" if attempt == 0 else "retry_conn_error"] += 1
            st.outcome["conn_error"] += 1
            return
        if attempt == 0:
            st.first_status[str(r.status_code)] += 1
        if r.status_code in (429, 503) and attempt < a.retries:
            await asyncio.sleep(float(r.headers.get("retry-after", 3)) + random.random())
            continue
        break
    assert r is not None
    if r.status_code != 202:
        st.outcome[f"final_{r.status_code}"] += 1
        return
    try:
        poll_url = safe_poll_path(r.json().get("poll_url"))
    except ValueError:
        st.outcome["bad_poll_url"] += 1
        return
    delay, deadline = 0.25, t0 + a.poll_timeout
    ph = {**hdr, "X-Session-Id": token}
    while time.monotonic() < deadline:
        await asyncio.sleep(delay)
        delay = min(1.0, delay + 0.25)
        st.polls += 1
        try:
            p = await c.get(poll_url, headers=ph)
        except httpx.HTTPError:
            st.poll_status["conn_error"] += 1
            continue
        st.poll_status[str(p.status_code)] += 1
        if p.status_code != 200:
            if p.status_code in (401, 403, 404):
                st.outcome[f"poll_{p.status_code}"] += 1
                return
            continue
        j = p.json()
        if j["status"] == "completed":
            now = time.monotonic()
            st.e2e.append(now - t0)
            st.completed_at.append(now)
            if j.get("started_at") and j.get("created_at"):
                st.queue_wait.append(j["started_at"] - j["created_at"])
            if j.get("completed_at") and j.get("started_at"):
                st.run_time.append(j["completed_at"] - j["started_at"])
            res = j.get("result") or {}
            st.grounding[str(res.get("grounding_state"))] += 1
            if res.get("latency_ms"):
                st.server_latency.append(res["latency_ms"] / 1000)
            st.outcome["ok"] += 1
            return
        if j["status"] in ("failed", "cancelled"):
            st.outcome[f"job_{j['status']}"] += 1
            return
    st.outcome["client_timeout"] += 1


async def user_loop(c, st, a, u, t_start, stop_at) -> None:
    await asyncio.sleep(random.random() * a.ramp_s)
    hdr = {
        "X-Forwarded-For": "10.0.0.1"
        if a.same_ip
        else f"10.{u // 250}.{u % 250}.{random.randint(1, 250)}"
    }
    s = await c.post("/api/auth/anon-session", headers=hdr)
    s.raise_for_status()
    token = s.json()["token"]
    n = 0
    while True:
        await one_message(c, st, a, u, n, token, hdr["X-Forwarded-For"])
        n += 1
        if a.think_time <= 0 or n >= a.messages_per_user:
            break
        wait = a.think_time * random.uniform(0.7, 1.3)
        if time.monotonic() + wait > stop_at:
            break
        await asyncio.sleep(wait)


async def sample_proc(
    pid: int, out: list[tuple[float, float, int, float]], stop: asyncio.Event
) -> None:
    import psutil

    p = psutil.Process(pid)
    prev = (time.monotonic(), sum(p.cpu_times()[:2]))
    out.append((prev[0], 0.0, p.memory_info().rss, prev[1]))
    while not stop.is_set():
        await asyncio.sleep(1.0)
        try:
            now, cpu_s = time.monotonic(), sum(p.cpu_times()[:2])
            out.append((now, (cpu_s - prev[1]) / (now - prev[0]), p.memory_info().rss, cpu_s))
            prev = (now, cpu_s)
        except psutil.Error:
            return


async def main_async(a: argparse.Namespace) -> dict:
    st = Stats()
    limits = httpx.Limits(max_connections=a.users * 2 + 20, max_keepalive_connections=a.users + 10)
    samples: list[tuple[float, float, int, float]] = []
    stop = asyncio.Event()
    async with httpx.AsyncClient(base_url=a.base_url, timeout=60.0, limits=limits) as c:
        t0 = time.monotonic()
        sampler = asyncio.create_task(sample_proc(a.pid, samples, stop)) if a.pid else None
        stop_at = t0 + a.duration
        await asyncio.gather(*(user_loop(c, st, a, u, t0, stop_at) for u in range(a.users)))
        wall = time.monotonic() - t0
        stop.set()
        if sampler:
            await sampler
    ok = st.outcome["ok"]
    rep = {
        "users": a.users,
        "think_time_s": a.think_time,
        "duration_s": a.duration,
        "wall_s": round(wall, 2),
        "same_ip": a.same_ip,
        "messages_sent": sum(st.first_status.values()),
        "completed": ok,
        "throughput_per_s": round(ok / wall, 3) if wall else None,
        "first_attempt_status": dict(st.first_status),
        "outcome": dict(st.outcome),
        "poll_status": dict(st.poll_status),
        "polls": st.polls,
        "grounding_state": dict(st.grounding),
        "e2e_s": {
            "p50": pct(st.e2e, 50),
            "p95": pct(st.e2e, 95),
            "p99": pct(st.e2e, 99),
            "max": pct(st.e2e, 100),
            "mean": round(statistics.fmean(st.e2e), 3) if st.e2e else None,
        },
        "queue_wait_s": {
            "p50": pct(st.queue_wait, 50),
            "p95": pct(st.queue_wait, 95),
            "max": pct(st.queue_wait, 100),
        },
        "job_run_s": {"p50": pct(st.run_time, 50), "p95": pct(st.run_time, 95)},
        "server_latency_s_p50": pct(st.server_latency, 50),
    }
    if samples:
        cpus = [s[1] for s in samples]
        rss = [s[2] for s in samples]
        rep["backend_cpu_cores"] = {
            "mean": round(statistics.fmean(cpus), 2),
            "peak": round(max(cpus), 2),
        }
        rep["backend_rss_mb_peak"] = round(max(rss) / 1e6)
        cpu_total = samples[-1][3] - samples[0][3]
        rep["backend_cpu_seconds_total"] = round(cpu_total, 2)
        rep["backend_cpu_seconds_per_completed"] = round(cpu_total / ok, 3) if ok else None
    return rep


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--base-url", default="http://127.0.0.1:8100")
    ap.add_argument("--users", type=int, default=10)
    ap.add_argument(
        "--duration", type=float, default=60.0, help="seconds; only bounds think-time runs"
    )
    ap.add_argument(
        "--think-time",
        type=float,
        default=0.0,
        help="mean seconds between a user's messages; 0 = one message",
    )
    ap.add_argument("--messages-per-user", type=int, default=1000)
    ap.add_argument(
        "--ramp-s", type=float, default=0.0, help="spread user start over this many seconds"
    )
    ap.add_argument("--retries", type=int, default=3, help="retries on 429/503 (frontend does 3)")
    ap.add_argument("--poll-timeout", type=float, default=120.0)
    ap.add_argument(
        "--same-ip",
        action="store_true",
        help="all users share one client IP (per-IP rate-limit test)",
    )
    ap.add_argument(
        "--pid", type=int, default=0, help="backend PID to sample CPU/RSS (host process)"
    )
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    require_local(a.base_url)
    rep = asyncio.run(main_async(a))
    print(json.dumps(rep, indent=2))
    if a.out:
        with open(a.out, "w") as fh:
            json.dump(rep, fh, indent=2)


if __name__ == "__main__":
    main()
