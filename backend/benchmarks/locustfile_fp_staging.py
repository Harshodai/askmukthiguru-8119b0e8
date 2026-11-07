"""Locust file for the staging load test with the real provider (NEW-LOAD-1).

Plan and pass conditions: audits/audit-output-2026-11-04/specifications/LOAD_AND_COST_MODEL.md
section 6. NOTHING HAS BEEN RUN. This file is for STAGING with an approved spend cap (D-PE7).
It refuses production hosts and needs LOAD_CONFIRM_STAGING=yes.

    export LOAD_CONFIRM_STAGING=yes BENCHMARK_SECRET=...      # staging with ENABLE_TEST_AUTH
    export METRICS_SCRAPE_TOKEN=...  SPEND_CAP_USD=<usd>      # optional: AB-1 stops at 80 percent. Unset = no stop, cost still logged
    locust -f benchmarks/locustfile_fp_staging.py --headless --tags s2 \
        -u 12 -r 1 -t 8m --host https://<staging-host>

Stages are tags: s0 smoke, s1 cache-hit, s2 uncached, s3 abstain, s4 crisis, s5 mixed
(use the section 6.4 ramp), s6 burst. Run one stage per invocation. Cold stages need
LATENCY_BENCHMARK_CACHE_DISABLED=true on the server (P5). The identity bypass (X-Test-Key)
is sent only when BENCHMARK_SECRET is set; production refuses it.

The run stops itself on AB-1 (spend), AB-3 (5xx rate), AB-5 (out-of-corpus served) and
AB-6 (crisis not routed as crisis). Take /internal/metrics snapshots around each stage with
scripts/ops/load_run_report.py.
"""

from __future__ import annotations

import os
import random
import time
import urllib.request
from pathlib import Path

import gevent
from locust import HttpUser, between, events, tag, task

from benchmarks import fp_staging_load as L

_REPO = Path(__file__).resolve().parents[2]
_POOLS = L.load_pools(_REPO)
_RULES = L.AbortRules()
_SEEN: list[str] = []  # questions already asked, for the cache-hit scenario
_ABORT: dict[str, str] = {}


def _spend_watcher(environment) -> None:
    """Poll provider-reported cost, log it, and stop at 80 percent of SPEND_CAP_USD if one is set."""
    token = os.environ.get("METRICS_SCRAPE_TOKEN")
    if not token or not environment.host:
        return
    raw_cap = os.environ.get("SPEND_CAP_USD", "").strip()
    cap = float(raw_cap) if raw_cap else None
    base = None
    while True:
        gevent.sleep(15)
        try:
            req = urllib.request.Request(
                environment.host.rstrip("/") + "/internal/metrics",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - operator-supplied staging URL
                text = resp.read().decode("utf-8")
        except OSError:
            continue
        total = sum(v for n, _, v in _parse(text) if n == "guru_provider_reported_cost_usd_total")
        base = total if base is None else base
        print(f"[cost-log] provider-reported spend this run: {total - base:.4f} USD", flush=True)
        if L.spend_exceeded(total - base, cap):
            _ABORT["AB-1"] = f"spend {total - base:.2f} of cap {cap:.2f}"
            environment.runner.quit()
            return


def _parse(text: str):
    import re

    pat = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{.*\})?\s+(\S+)$")
    for line in text.splitlines():
        m = pat.match(line.strip())
        if m and not line.startswith("#"):
            try:
                yield m.group(1), m.group(2) or "", float(m.group(3))
            except ValueError:
                pass


@events.test_start.add_listener
def _guard(environment, **kwargs) -> None:
    why = L.host_refusal(environment.host or "", confirm=os.environ.get("LOAD_CONFIRM_STAGING", ""))
    if why:
        raise SystemExit(why)
    gevent.spawn(_spend_watcher, environment)


@events.test_stop.add_listener
def _report_aborts(environment, **kwargs) -> None:
    if _ABORT:
        print(f"ABORT RULES FIRED: {_ABORT}")
        environment.process_exit_code = 3


class FPStagingUser(HttpUser):
    wait_time = between(
        2, 6
    )  # [INF] reading time; S2 uses 0.5 to 2 s: set via --tags s2 and the env below

    def on_start(self) -> None:
        if os.environ.get("S2_FAST_THINK") == "1":
            self.wait_time = between(0.5, 2.0)
        secret = os.environ.get("BENCHMARK_SECRET")
        self._headers = {"Content-Type": "application/json"}
        if secret:
            self._headers["X-Test-Key"] = secret

    def _ask(self, kind: str, text: str) -> None:
        payload = {
            "messages": [{"role": "user", "content": text}],
            "user_message": text,
            "language": "en",
            "session_id": str(int(time.time() * 1000) % (2**31)),
        }
        with self.client.post(
            "/api/chat",
            json=payload,
            headers=self._headers,
            catch_response=True,
            name=f"chat:{kind}",
        ) as resp:
            try:
                body = resp.json()
            except ValueError:
                body = resp.text
            outcome = L.classify(resp.status_code, resp.headers, body)
            broken = L.violation(kind, outcome)
            if outcome == "shed":
                resp.success()  # controlled shed; PC-11 judges it, not a failure here
            elif outcome in {"error", "rate_limited"} or broken:
                resp.failure(f"{outcome}{' ' + broken if broken else ''}")
            else:
                resp.success()
            stop = _RULES.observe(kind, outcome, now=time.time())
            if stop and stop not in _ABORT:
                _ABORT[stop] = f"{kind} -> {outcome}"
                self.environment.runner.quit()
        if kind in {"on_topic", "on_topic_cold"}:
            _SEEN.append(text)

    # ---- single-scenario tasks (S1 to S4, S6) -----------------------------------------

    @tag("s0", "s2")
    @task(0)
    def on_topic_uncached(self) -> None:
        self._ask("on_topic", random.choice(_POOLS["on_topic"]))

    @tag("s1")
    @task(0)
    def cache_hit(self) -> None:
        pool = _SEEN or _POOLS["on_topic"]
        self._ask("on_topic", random.choice(pool))

    @tag("s0", "s3")
    @task(0)
    def out_of_corpus(self) -> None:
        self._ask("out_of_corpus", random.choice(_POOLS["abstain"]))

    @tag("s0", "s4")
    @task(0)
    def crisis(self) -> None:
        self._ask("crisis", random.choice(_POOLS["crisis"]))

    @tag("s6")
    @task(0)
    def burst(self) -> None:
        self._ask("on_topic", random.choice(_POOLS["on_topic"]))

    # ---- S5 mixed target: task weights are the section 6.4 percentages ----------------

    @tag("s5")
    @task(L.S5_MIX["on_topic_cold"])
    def s5_on_topic_cold(self) -> None:
        self._ask("on_topic_cold", random.choice(_POOLS["on_topic"]))

    @tag("s5")
    @task(L.S5_MIX["cache_hit"])
    def s5_cache_hit(self) -> None:
        self._ask("on_topic", random.choice(_SEEN or _POOLS["on_topic"]))

    @tag("s5")
    @task(L.S5_MIX["out_of_corpus"])
    def s5_out_of_corpus(self) -> None:
        self._ask("out_of_corpus", random.choice(_POOLS["abstain"]))

    @tag("s5")
    @task(L.S5_MIX["greeting_off_topic"])
    def s5_greeting(self) -> None:
        self._ask("greeting_off_topic", random.choice(_POOLS["greeting_off_topic"]))

    @tag("s5")
    @task(L.S5_MIX["crisis"])
    def s5_crisis(self) -> None:
        self._ask("crisis", random.choice(_POOLS["crisis"]))

    @tag("s5")
    @task(L.S5_MIX["other"])
    def s5_other(self) -> None:
        self._ask("other", random.choice(_POOLS["other"]))
