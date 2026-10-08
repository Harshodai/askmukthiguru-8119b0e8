#!/usr/bin/env python3
"""Prove every query cache is empty (`make verify-cache-empty`).

Run this after `make flush-cache` and before any live benchmark that claims to
be uncached. It reports, read-only:

* Redis DBSIZE (context only -- queues, quotas and sessions live there too).
* Key counts, via SCAN (never KEYS), for every cache prefix the backend writes:
    - ``mukthiguru:cache:*``            exact-query cache (services/cache/redis_adapter.py)
    - ``mukthiguru:semcache:*``         semantic-cache payload/index (services/cache/semantic_adapter.py,
                                        services/semantic_cache.py)
    - ``cache:first_person_exact:*``    first-person exact cache (services/first_person_pipeline.py)
* Point counts of the Qdrant semantic-cache collections ("absent" on 404).

Exit status is the contract (L-OPS-EXIT-STATUS-1):
    0  every count is zero / absent
    1  something is cached
    2  Redis or Qdrant could not be reached -- unreachable is NOT empty

Not covered (no shared store, so not verifiable from outside): the in-process
hot cache, the in-memory semantic cache, the TurboQuant vector cache and the
doctrine cache. `make flush-cache` restarts the backend to clear those.

Config (host mode): REDIS_URL (default redis://localhost:6379/0), REDIS_PASSWORD,
QDRANT_URL (default http://localhost:6333), QDRANT_API_KEY, EMBEDDING_DIMENSION
(default 1024). If Redis is password-protected and not published to the host,
use ``--redis-via docker`` (runs redis-cli inside the compose Redis container;
the password goes via REDISCLI_AUTH, never argv).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union
from urllib.parse import urlsplit, urlunsplit

REDIS_PATTERNS = (
    "mukthiguru:cache:*",
    "mukthiguru:semcache:*",
    "cache:first_person_exact:*",
)

EXIT_EMPTY = 0
EXIT_NOT_EMPTY = 1
EXIT_UNREACHABLE = 2


class Unreachable(Exception):
    """A store could not be queried; the result is unknown, not empty."""


class HttpStatus(Exception):
    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")
        self.status = status


def qdrant_collections(dimension: int) -> List[str]:
    """Every Qdrant collection that has held semantic-cache points."""
    names = [
        f"mukthi_semantic_cache_{dimension}d",  # active (services/cache/semantic_adapter.py)
        os.getenv("SEMANTIC_CACHE_QDRANT_COLLECTION", "semantic_cache"),  # config default name
        "semantic_query_cache",  # historical name flushed by flush_cache.py
    ]
    seen: List[str] = []
    for n in names:
        if n and n not in seen:
            seen.append(n)
    return seen


# --------------------------------------------------------------------------- redis


def count_redis(client: Any) -> Dict[str, Any]:
    """Count keys per cache prefix with SCAN. `client` needs dbsize() and scan_iter()."""
    patterns = {p: sum(1 for _ in client.scan_iter(match=p, count=500)) for p in REDIS_PATTERNS}
    return {"dbsize": int(client.dbsize()), "patterns": patterns}


class _DockerRedis:
    """Minimal redis-cli-in-container client (host cannot reach a protected, unpublished Redis)."""

    def __init__(self, container: str, password: str, db: str = "0"):
        self.container, self.password, self.db = container, password, db

    def _run(self, *redis_args: str) -> str:
        cmd = ["docker", "exec"]
        if self.password:
            cmd += ["-e", f"REDISCLI_AUTH={self.password}"]
        cmd += [self.container, "redis-cli", "-n", self.db, *redis_args]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Unreachable(f"redis (docker exec {self.container}): {exc}") from exc
        out = (proc.stdout or "") + (proc.stderr or "")
        # redis-cli exits 0 on auth/connection errors, so inspect the text too.
        if proc.returncode != 0 or out.startswith(("NOAUTH", "WRONGPASS", "ERR ", "Error", "Could not")):
            raise Unreachable(f"redis (docker exec {self.container}): {out.strip()[:200]}")
        return proc.stdout

    def dbsize(self) -> int:
        return int(self._run("DBSIZE").strip().split()[-1])

    def scan_iter(self, match: str, count: int = 500) -> Iterable[str]:
        return [ln for ln in self._run("--scan", "--pattern", match, "--count", str(count)).splitlines() if ln]


def _read_env_file_var(name: str) -> str:
    """Last-resort: read NAME from backend/.env without sourcing it (values may hold shell chars)."""
    env = Path(__file__).resolve().parents[2] / "backend" / ".env"
    try:
        for line in env.read_text().splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return ""


def _redis_password() -> str:
    return os.getenv("REDIS_PASSWORD") or _read_env_file_var("REDIS_PASSWORD")


def _host_redis_client():
    try:
        import redis as redis_lib
    except ImportError as exc:
        raise Unreachable("redis python package not installed (try --redis-via docker)") from exc
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    kwargs: Dict[str, Any] = {"socket_connect_timeout": 5, "socket_timeout": 30, "decode_responses": True}
    pw = _redis_password()
    if pw and "@" not in urlsplit(url).netloc:
        kwargs["password"] = pw
    client = redis_lib.from_url(url, **kwargs)
    try:
        client.ping()
    except Exception as exc:
        raise Unreachable(f"redis ({_safe_url(url)}): {exc}") from exc
    return client


def _safe_url(url: str) -> str:
    parts = urlsplit(url)
    if "@" in parts.netloc:
        parts = parts._replace(netloc="***@" + parts.netloc.rsplit("@", 1)[1])
    return urlunsplit(parts)


def _redis_counts(args: argparse.Namespace) -> Dict[str, Any]:
    via = getattr(args, "redis_via", "auto")
    errors: List[str] = []
    if via in ("auto", "host"):
        try:
            return count_redis(_host_redis_client())
        except Unreachable as exc:
            errors.append(str(exc))
        except Exception as exc:  # redis errors mid-scan
            errors.append(f"redis: {exc}")
        if via == "host":
            raise Unreachable("; ".join(errors))
    container = os.getenv("REDIS_CONTAINER", "mukthiguru-redis")
    try:
        return count_redis(_DockerRedis(container, _redis_password()))
    except Unreachable as exc:
        errors.append(str(exc))
        raise Unreachable("; ".join(errors)) from exc


# --------------------------------------------------------------------------- qdrant

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _http_json(url: str, method: str = "GET", body: Optional[dict] = None,
               api_key: Optional[str] = None, timeout: int = 10) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)  # noqa: S310 - operator-supplied Qdrant URL
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("api-key", api_key)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:  # noqa: S310  # nosec B310
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        raise HttpStatus(exc.code) from exc


def count_qdrant(base_url: str, collections: Iterable[str], api_key: Optional[str]) -> Dict[str, Union[int, str]]:
    out: Dict[str, Union[int, str]] = {}
    base = base_url.rstrip("/")
    for name in collections:
        try:
            res = _http_json(f"{base}/collections/{name}/points/count", "POST", {"exact": True}, api_key)
            out[name] = int(res["result"]["count"])
        except HttpStatus as exc:
            if exc.status == 404:
                out[name] = "absent"
            else:
                raise Unreachable(f"qdrant {name}: HTTP {exc.status}") from exc
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise Unreachable(f"qdrant ({base}): {exc}") from exc
    return out


def _qdrant_counts(args: argparse.Namespace) -> Dict[str, Union[int, str]]:
    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    key = os.getenv("QDRANT_API_KEY") or _read_env_file_var("QDRANT_API_KEY") or None
    dim = int(os.getenv("EMBEDDING_DIMENSION", "1024"))
    return count_qdrant(url, qdrant_collections(dim), key)


# --------------------------------------------------------------------------- main


def _nonzero(v: Union[int, str]) -> bool:
    return isinstance(v, int) and v > 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--redis-via", choices=("auto", "host", "docker"), default="auto",
                    help="auto: host Redis client, falling back to docker exec (default)")
    args = ap.parse_args(argv)

    print("=" * 72 + "\n  AskMukthiGuru cache-empty verification\n" + "=" * 72)
    not_empty: List[str] = []
    unreachable: List[str] = []

    try:
        r = _redis_counts(args)
        print(f"Redis DBSIZE (all keys, context only): {r['dbsize']}")
        for pattern, n in r["patterns"].items():
            print(f"  {pattern:<32} {n}")
            if _nonzero(n):
                not_empty.append(f"redis {pattern}={n}")
    except Unreachable as exc:
        print(f"Redis: UNREACHABLE -- {exc}")
        unreachable.append("redis")

    try:
        q = _qdrant_counts(args)
        print("Qdrant semantic-cache collections:")
        for name, n in q.items():
            print(f"  {name:<32} {n}")
            if _nonzero(n):
                not_empty.append(f"qdrant {name}={n}")
    except Unreachable as exc:
        print(f"Qdrant: UNREACHABLE -- {exc}")
        unreachable.append("qdrant")

    print()
    if not_empty:
        print("NOT EMPTY: " + ", ".join(not_empty))
        print("Run `make flush-cache`, then re-run this check.")
        return EXIT_NOT_EMPTY
    if unreachable:
        print("UNVERIFIED: could not reach " + ", ".join(unreachable) + ". Unreachable is not empty.")
        print("Check REDIS_URL / REDIS_PASSWORD / QDRANT_URL, or use --redis-via docker.")
        return EXIT_UNREACHABLE
    print("OK: all query caches are empty (in-process caches are cleared by the backend restart, not checked here).")
    return EXIT_EMPTY


if __name__ == "__main__":
    sys.exit(main())
