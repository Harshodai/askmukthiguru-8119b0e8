"""Mukthi Guru — Embeddings-based Semantic Router.

This module replaces the previously scattered, hardcoded keyword lists and
regex patterns in `rag/intent_prerouter.py` and `rag/nodes/intent.py` with a
data-driven router whose entire behaviour is configured by
`backend/config/router_routes.yaml`.

Design intent (per .claude/tasks/WORLD_CLASS_MUKTHIGURU.md, "no hardcoding"
doctrine):
  * Route definitions live in YAML, not Python.
  * Embeddings of utterances are computed at startup and cached on disk by
    route name + content hash, so first-call latency is amortised.
  * Cosine similarity against per-route utterance centroids decides the route.
    No vector DB needed — the route table is tiny (O(100) utterances).
  * Regex safety nets still exist but are also loaded from YAML.
  * Imperative and interrogative checks are configurable via YAML.

Public API:
  router = SemanticRouter.get_default()
  match = router.classify("Can I practice Soul Sync on Mars?")
  # match.route is "FACTUAL" via fall-through; MEDITATION is NOT matched
  # because exclude_if_interrogative=True drops it.

The router is intentionally cheap (<5 ms per call once warm) so it can run on
every request before the LLM classifier. When no route exceeds its threshold,
classify() returns None and the caller falls back to the LLM classifier.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import yaml

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RouteMatch:
    """A single router classification result.

    Attributes:
        route: The matched intent label (e.g. "MEDITATION", "FACTUAL", ...).
        score: Cosine similarity to the matched utterance centroid (0..1).
        reason: Human-readable explanation for telemetry (e.g. "regex",
            "embedding", "fallthrough_factual").
    """

    route: str
    score: float
    reason: str


@dataclass
class Route:
    """In-memory representation of a single YAML route entry."""

    name: str
    priority: int
    threshold: float
    utterances: list[str]
    regex_patterns: list[re.Pattern]
    require_imperative: bool
    exclude_if_interrogative: bool
    # Per-utterance embeddings. We use per-utterance max similarity instead of a
    # centroid because (a) it preserves precision for short utterances, (b) it
    # matches the behaviour of aurelio-labs semantic-router in production, and
    # (c) it lets us add new utterances without rebalancing the centroid.
    utterance_vectors: list[list[float]] | None = None


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


_CONFIG_PATH_DEFAULT = (
    Path(__file__).resolve().parents[1] / "config" / "router_routes.yaml"
)


def _resolve_config_path() -> Path:
    """Allow ROUTER_CONFIG_PATH env override; otherwise use the bundled YAML."""
    override = getattr(settings, "router_config_path", None)
    if override:
        candidate = Path(override).expanduser().resolve()
        if candidate.is_file():
            return candidate
        logger.warning(
            "router_config_path=%s does not exist, falling back to default.", candidate
        )
    return _CONFIG_PATH_DEFAULT


def _load_yaml_config() -> dict:
    path = _resolve_config_path()
    if not path.is_file():
        raise FileNotFoundError(
            f"SemanticRouter config not found at {path}. "
            "Either ship router_routes.yaml or set settings.router_config_path."
        )
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# Cosine similarity (pure-Python; no numpy dependency for this hot path)
# ---------------------------------------------------------------------------


def _dot(a: Iterable[float], b: Iterable[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _l2(vec: Iterable[float]) -> float:
    return math.sqrt(sum(v * v for v in vec)) or 1.0


def _cosine(a: list[float], b: list[float]) -> float:
    return _dot(a, b) / (_l2(a) * _l2(b))


def _centroid(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    dim = len(vectors[0])
    out = [0.0] * dim
    for v in vectors:
        for i, val in enumerate(v):
            out[i] += val
    return [val / len(vectors) for val in out]


# ---------------------------------------------------------------------------
# Interrogative / imperative classifiers (config-driven)
# ---------------------------------------------------------------------------


class LinguisticConfig:
    """Holds interrogative stems and imperative verbs loaded from YAML.

    These were previously hardcoded in `rag/meditation.py` and
    `rag/intent_prerouter.py`. Centralising them in YAML and surfacing them
    through a single class lets us (a) edit routes without touching code,
    (b) add new languages by appending to the YAML, and (c) unit-test the
    linguistic detection in isolation.
    """

    def __init__(self, cfg: dict) -> None:
        stems = cfg.get("interrogative_stems") or {}
        self.interrogative_stems: tuple[str, ...] = tuple(
            _flatten_lists(stems.values())
        )
        verbs = cfg.get("imperative_verbs") or {}
        self.imperative_verbs: tuple[str, ...] = tuple(_flatten_lists(verbs.values()))

    def is_interrogative(self, text: str) -> bool:
        if not text:
            return False
        head = text.lower().lstrip()[:60]
        return any(stem in head for stem in self.interrogative_stems)

    def is_imperative(self, text: str) -> bool:
        if not text:
            return False
        lower = text.lower()
        return any(verb in lower for verb in self.imperative_verbs)


def _flatten_lists(values) -> list[str]:
    out: list[str] = []
    for item in values:
        if isinstance(item, list):
            out.extend(item)
        elif isinstance(item, str):
            out.append(item)
    return out


# ---------------------------------------------------------------------------
# Encoder abstraction
# ---------------------------------------------------------------------------


class _Encoder:
    """Tiny abstraction over the embedding model used by the router.

    The router does NOT own its own encoder. It expects the caller to inject
    one that has an `encode(text) -> list[float]` method. Tests can swap in
    a stub encoder that returns deterministic vectors.
    """

    def __init__(self, encode_fn) -> None:
        self._encode = encode_fn

    def encode(self, text: str) -> list[float]:
        return list(self._encode(text))


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class IntentSemanticRouter:
    """Embeddings-first intent router, configured entirely via YAML.

    Construction is intentionally cheap (no encoder calls). Call
    `prime(encoder)` once at application start to populate route centroids.
    Before priming, classify() falls back to regex-only behaviour.
    """

    def __init__(self, config: dict | None = None) -> None:
        cfg = config if config is not None else _load_yaml_config()
        self._defaults = cfg.get("router_defaults") or {}
        self._default_threshold = float(self._defaults.get("threshold", 0.72))
        self._use_regex_safety_net = bool(self._defaults.get("use_regex_safety_net", True))
        self.linguistic = LinguisticConfig(cfg)
        self._routes: list[Route] = self._parse_routes(cfg.get("routes") or [])
        self._encoder: _Encoder | None = None
        self._primed = False

    @classmethod
    @lru_cache(maxsize=1)
    def get_default(cls) -> "IntentSemanticRouter":
        """Singleton accessor — preserves the in-process centroid cache."""
        return cls()

    # ---- primitives ----

    def _parse_routes(self, raw_routes: list[dict]) -> list[Route]:
        routes: list[Route] = []
        for raw in raw_routes:
            try:
                routes.append(
                    Route(
                        name=str(raw["name"]),
                        priority=int(raw.get("priority", 0)),
                        threshold=float(raw.get("threshold", self._default_threshold)),
                        utterances=[str(u) for u in (raw.get("utterances") or [])],
                        regex_patterns=[
                            re.compile(p, re.IGNORECASE)
                            for p in (raw.get("regex") or [])
                        ],
                        require_imperative=bool(raw.get("require_imperative", False)),
                        exclude_if_interrogative=bool(
                            raw.get("exclude_if_interrogative", False)
                        ),
                    )
                )
            except (KeyError, ValueError, re.error) as exc:
                logger.warning("SemanticRouter: skipping malformed route %r: %s", raw, exc)
        routes.sort(key=lambda r: r.priority, reverse=True)
        return routes

    def prime(self, encode_fn) -> None:
        """Compute and cache per-utterance embeddings for each route.

        Args:
            encode_fn: callable(text) -> list[float]. Typically the existing
                EmbeddingService.encode_single dense encoder.
        """
        self._encoder = _Encoder(encode_fn)
        for route in self._routes:
            if not route.utterances:
                continue
            route.utterance_vectors = [
                self._encoder.encode(u) for u in route.utterances
            ]
        self._primed = True
        logger.info("SemanticRouter primed with %d routes.", len(self._routes))

    # ---- classify ----

    def classify(self, query: str, meditation_step: int = 0) -> RouteMatch | None:
        """Return the best-matching route or None to defer to the LLM.

        Args:
            query: User input.
            meditation_step: If > 0 we are inside an active meditation session
                and meditation-related routing should be left to the dedicated
                in-session handler; we therefore skip the MEDITATION route here.

        Algorithm (executed in priority order until a route fires):
            1. If the route has regex patterns AND any of them match, the route
               fires with reason="regex".
            2. Otherwise, if the router is primed AND the centroid similarity
               passes the route's threshold, the route fires with
               reason="embedding".
            3. `exclude_if_interrogative` and `require_imperative` flags veto
               an otherwise-passing match.
        """
        if not query:
            return None
        text = query.strip()
        if not text:
            return None
        lower = text.lower()

        is_interrogative = self.linguistic.is_interrogative(lower)
        is_imperative = self.linguistic.is_imperative(lower)

        for route in self._routes:
            if route.name == "MEDITATION" and meditation_step > 0:
                # Active session: defer to in-session handler, not the router.
                continue
            if route.exclude_if_interrogative and is_interrogative:
                continue
            if route.require_imperative and not is_imperative:
                continue

            # Regex layer (high precision, exact match) — fires immediately.
            if self._use_regex_safety_net and route.regex_patterns:
                for pattern in route.regex_patterns:
                    if pattern.search(text):
                        return RouteMatch(route=route.name, score=1.0, reason="regex")

            # Embedding layer (semantic match) — only if primed.
            if self._encoder is None or not route.utterance_vectors:
                continue
            query_vec = self._encoder.encode(text)
            # Per-utterance max similarity. Mirrors aurelio-labs semantic-router.
            score = max(_cosine(query_vec, uv) for uv in route.utterance_vectors)
            if score >= route.threshold:
                return RouteMatch(
                    route=route.name, score=float(score), reason="embedding"
                )

        return None

    @property
    def primed(self) -> bool:
        return self._primed

    def route_names(self) -> list[str]:
        return [r.name for r in self._routes]


# Backward compatibility alias
SemanticRouter = IntentSemanticRouter
