"""Owner-only, file-backed first-person review candidate preview.

This is the **smallest safe testing surface**: it never contacts Qdrant, never
touches an alias, never writes to Redis and never calls an LLM to produce
teaching text. It reads the immutable candidate manifests produced by the
Phase-4 corpus-tier build and serves only the ``local_review_candidate`` tier.

What it is
----------
A local, owner-only way to *look at* the reviewed candidate corpus and to see
how the retrieval-only answer shape behaves: verbatim span text, exact audio
window, source link, and the evidence that backs the citation.

What it is NOT
--------------
* Not a public release. Every response carries
  the canonical two-line owner-only label (``REVIEW_LABEL_LINES``).
* Not human-certified attribution. The speaker evidence behind a citation is
  automated (a pinned ECAPA model scored against an anchor-derived reference),
  and the rights register is not yet owner-signed. Both are open blockers
  (B5, B7).
* Not a health or crisis service. The deterministic crisis/topic rails are
  preserved, but nothing here is clinical advice.

Fail-closed rules
-----------------
The service refuses to start when any pinned artifact is missing, unreadable,
or whose sha256 does not match the contract. It refuses to serve when the
source manifest, verdict manifest, rights manifest or serving contract is
absent. It never serves a span that is not in the exact candidate tier, and it
never cites a span whose text hash, audio window, speaker verdict or rights
status does not verify against the pinned artifacts.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

SCHEMA = "fp-local-review-contract-v1"
TIER_SCHEMA = "first-person-corpus-tier-v2"

# The canonical owner-only label. It is printed in the CLI, carried in the
# structured metadata, repeated on every citation and shown in the owner
# guide. Two lines, both mandatory: the first says what this is, the second
# says what the evidence behind it is NOT.
REVIEW_LABEL_LINES = (
    "REVIEW CANDIDATE — NOT PUBLIC RELEASE",
    "AUTOMATED EVIDENCE — NOT HUMAN-CERTIFIED ATTRIBUTION",
)
REVIEW_LABEL = "\n".join(REVIEW_LABEL_LINES)
EVIDENCE_POLICY = "automated_evidence_candidate"
TIER_NAME = "local_review_candidate"
COLLECTION_NAME = "file-backed:local_review_candidate"

# A query term present in more than this share of the candidate corpus carries
# no discriminating power and is dropped from the query.
MAX_DF_RATIO = 0.35

# Relevance floor for a lexical preview. A span must cover at least
# MIN_COVERAGE of the query's discriminating weight, and its score must reach
# MIN_SCORE_FRACTION of that weight. Both are RELATIVE to the query: an
# absolute score floor would be meaningless because the idf scale depends on
# the corpus size.
MIN_SCORE_FRACTION = 0.15
MIN_COVERAGE = 0.30

# The answer text is the teacher's stored span text, nothing else. No LLM
# writes a teaching sentence in this mode.
LLM_AUTHORED_ANSWER = False

_PUNCT_CATEGORIES = ("P", "S")

# English function words carry no retrieval signal and would otherwise let a
# generic span outrank a specific one (every span contains "what" and "is").
STOPWORDS = frozenset(
    """
    a about above after again against all am an and any are aren't as at be because been
    before being below between both but by can cannot could couldn't did didn't do does
    doesn't doing don't down during each few for from further had hadn't has hasn't have
    haven't having he her here hers herself him himself his how i i'm i've if in into is
    isn't it it's its itself just me more most mustn't my myself no nor not of off on
    once only or other ought our ours ourselves out over own same shan't she should
    shouldn't so some such than that that's the their theirs them themselves then there
    these they this those through to too under until up very was wasn't we were weren't
    what what's when when's where where's which while who who's whom why why's with
    won't would wouldn't you your yours yourself yourselves tell say says said explain
    give me know think like want need please help
    """.split()
)

# Teacher names are a FILTER, not a topic. They must not enter the query
# terms: they are rare in the corpus, so they would dominate the idf budget
# and make the relevance coverage look artificially low.
_TEACHER_TOKENS = frozenset(
    {"preethaji", "krishnaji", "preethaji's", "krishnaji's", "sri", "guru", "teacher"}
)


class LocalReviewError(RuntimeError):
    """Raised when the local review mode cannot start or must refuse to serve."""


class LocalReviewRefused(LocalReviewError):
    """Raised when a request must not be served (guardrail or contract)."""


# ---------------------------------------------------------------------------
# text handling — must mirror fp-norm-unicode-v1 (see
# backend/scripts/ops/rebuild_v10_asr_coordinates.py::normalize_text)
# ---------------------------------------------------------------------------
def normalize_text(text: str) -> str:
    """Versioned, Unicode-aware normalization (``fp-norm-unicode-v1``)."""
    t = unicodedata.normalize("NFKC", text).lower()
    t = re.sub(r"(\d+)\s*,\s*(\d+)", r"\1\2", t)
    t = re.sub(r"[-—–/]", " ", t)
    t = re.sub(r"[\u2018\u2019\u201c\u201d']", "", t)
    out: list[str] = []
    for ch in t:
        if ch.isalnum() or ch.isspace():
            out.append(ch)
        elif unicodedata.category(ch)[0] in _PUNCT_CATEGORIES:
            out.append(" ")
        else:
            out.append(ch)
    return " ".join("".join(out).split())


def tokenize(text: str) -> list[str]:
    return normalize_text(text).split()


def _is_latin_script(text: str) -> bool:
    """True when the text carries Latin letters.

    The pinned candidate corpus is English (Latin script). Term-coverage
    judgements are only meaningful for a Latin-script question; a Devanagari
    question must be judged by the relevance floor instead.
    """
    return any("LATIN" in unicodedata.name(ch, "") for ch in text if ch.isalpha())


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ArtifactPin:
    path: str
    sha256: str


@dataclass(frozen=True)
class LocalReviewConfig:
    """Everything the mode needs to start, with every artifact pinned."""

    contract_path: str
    repo_root: Path
    tiers_manifest: ArtifactPin
    tier: str
    verdicts: ArtifactPin
    rights_manifest: ArtifactPin
    rights_join: ArtifactPin
    speaker_conflicts: ArtifactPin
    serving_contract: ArtifactPin
    corpus_version: str
    review_label: str
    review_label_lines: tuple[str, ...]
    evidence_policy: str
    max_clips: int = 3
    enabled: bool = False
    allow_in_production: bool = False
    deterministic_id_collisions: Optional[ArtifactPin] = None

    @property
    def collection(self) -> str:
        return COLLECTION_NAME


def _resolve(repo_root: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def load_local_review_config(
    contract_path: str | Path | None = None,
    *,
    repo_root: str | Path | None = None,
) -> LocalReviewConfig:
    """Load and verify the local-review contract. Fails closed.

    The contract path and the repository root are passed in by the caller (the
    route reads them from ``settings``); this module never reads the
    environment directly, because every env value must reach the app through
    ``Settings`` (see ``tests/test_settings_guards.py``).
    """
    path = Path(
        contract_path
        or (Path(__file__).resolve().parents[1] / "config" / "first_person_local_review.json")
    )
    if not path.is_file():
        raise LocalReviewError(f"local-review contract is missing: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LocalReviewError(f"local-review contract is unreadable: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise LocalReviewError(
            f"local-review contract schema must be {SCHEMA!r}; got {raw.get('schema')!r}"
        )
    root = Path(repo_root) if repo_root else path.resolve().parent.parent.parent

    def _pin(name: str) -> ArtifactPin:
        entry = raw.get(name)
        if not isinstance(entry, dict) or not entry.get("path") or not entry.get("sha256"):
            raise LocalReviewError(f"local-review contract does not pin {name!r}")
        return ArtifactPin(path=str(entry["path"]), sha256=str(entry["sha256"]))

    # The label is canonical, not a per-deployment choice: a contract that
    # pins a DIFFERENT label is a stale contract and the mode refuses to
    # start. A contract that pins no label at all falls back to the canonical
    # one.
    pinned_label = str(raw.get("review_label") or "")
    if pinned_label and pinned_label != REVIEW_LABEL:
        raise LocalReviewError(
            "local-review contract pins a stale review label; the canonical label is "
            f"{REVIEW_LABEL!r}. Regenerate the contract."
        )

    config = LocalReviewConfig(
        contract_path=str(path),
        repo_root=root,
        tiers_manifest=_pin("tiers_manifest"),
        tier=str(raw.get("tier") or TIER_NAME),
        verdicts=_pin("verdicts"),
        rights_manifest=_pin("rights_manifest"),
        rights_join=_pin("rights_join"),
        speaker_conflicts=_pin("speaker_conflicts"),
        serving_contract=_pin("serving_contract"),
        corpus_version=str(raw.get("corpus_version") or ""),
        review_label=REVIEW_LABEL,
        review_label_lines=REVIEW_LABEL_LINES,
        evidence_policy=str(raw.get("evidence_policy") or EVIDENCE_POLICY),
        max_clips=int(raw.get("max_clips") or 3),
        enabled=bool(raw.get("enabled", False)),
        allow_in_production=bool(raw.get("allow_in_production", False)),
        deterministic_id_collisions=(
            _pin("deterministic_id_collisions") if raw.get("deterministic_id_collisions") else None
        ),
    )
    if config.tier != TIER_NAME:
        raise LocalReviewError(
            f"local-review contract must serve the {TIER_NAME!r} tier; got {config.tier!r}"
        )
    return config


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------
@dataclass
class _Doc:
    row: Mapping[str, Any]
    tokens: Counter
    length: int


class LocalReviewIndex:
    """A deterministic BM25 index over the candidate tier.

    Lexical on purpose: no embedding model, no network, no index server, and
    the same query always produces the same ranking. That is what makes the
    owner-test result reproducible and reviewable.
    """

    K1 = 1.5
    B = 0.75

    def __init__(self, rows: Iterable[Mapping[str, Any]]) -> None:
        self._rows = [dict(row) for row in rows]
        self._docs: list[_Doc] = []
        self._df: Counter = Counter()
        for row in self._rows:
            tokens = Counter(tokenize(str(row.get("text") or "")))
            self._docs.append(_Doc(row=row, tokens=tokens, length=sum(tokens.values())))
            for token in tokens:
                self._df[token] += 1
        self._avgdl = sum(doc.length for doc in self._docs) / len(self._docs) if self._docs else 0.0

    def __len__(self) -> int:
        return len(self._rows)

    @property
    def rows(self) -> list[dict[str, Any]]:
        return self._rows

    def _idf(self, token: str) -> float:
        n = len(self._docs)
        df = self._df.get(token, 0)
        if df == 0:
            return 0.0
        return math.log(1.0 + (n - df + 0.5) / (df + 0.5))

    def _query_terms(self, query: str) -> list[str]:
        """The query terms that can actually discriminate.

        A term that appears in more than ``MAX_DF_RATIO`` of the corpus
        ("meditation" in a meditation corpus) is dropped: it is satisfied by
        almost every span and would let a generic span outrank a specific one.
        """
        if not self._docs:
            return []
        max_df = max(5, int(len(self._docs) * MAX_DF_RATIO))
        terms: list[str] = []
        for token in tokenize(query):
            if len(token) < 2 or token in STOPWORDS or token in _TEACHER_TOKENS:
                continue
            if self._df.get(token, 0) > max_df:
                continue
            if token not in terms:
                terms.append(token)
        return terms

    def search(
        self,
        query: str,
        *,
        teacher_id: str = "both",
        limit: int = 3,
    ) -> list[tuple[dict[str, Any], float]]:
        """Rank the candidate tier for a query. Deterministic and bounded.

        Only spans that clear the relevance floor are returned: a lexical
        match on one rare word is not an answer. The floors
        (``MIN_SCORE``/``MIN_COVERAGE``) are what make an out-of-corpus
        question abstain instead of serving a coincidental match.
        """
        wanted = (teacher_id or "both").strip().lower()
        terms = self._query_terms(query)
        if not terms or not self._docs:
            return []
        total_idf = sum(self._idf(term) for term in terms)
        if total_idf <= 0:
            return []
        scored: list[tuple[dict[str, Any], float]] = []
        seen_videos: set[str] = set()
        for doc in self._docs:
            if wanted not in ("both", "all", "") and str(doc.row.get("guru_id")) != wanted:
                continue
            score = 0.0
            matched_idf = 0.0
            for term in terms:
                tf = doc.tokens.get(term, 0)
                if not tf:
                    continue
                denom = tf + self.K1 * (
                    1.0 - self.B + self.B * (doc.length / self._avgdl if self._avgdl else 0.0)
                )
                idf = self._idf(term)
                matched_idf += idf
                score += idf * (tf * (self.K1 + 1.0)) / denom
            if score <= 0.0:
                continue
            if total_idf > 0 and score < MIN_SCORE_FRACTION * total_idf:
                continue
            if total_idf > 0 and (matched_idf / total_idf) < MIN_COVERAGE:
                continue
            # At most one span per video (same rule as the production path):
            # three fragments of one talk is not three answers.
            video_id = str(doc.row.get("video_id") or "")
            if video_id and video_id in seen_videos:
                continue
            if video_id:
                seen_videos.add(video_id)
            scored.append((doc.row, score))
        scored.sort(key=lambda item: (-item[1], str(item[0].get("source_span_id"))))
        return scored[: max(0, limit)]

    def unmatched_terms(self, query: str) -> list[str]:
        """Query terms that appear in NO candidate span.

        A question whose vocabulary is largely absent from the corpus is
        out-of-corpus. One absent term in an otherwise well-covered question
        is not (morphology, typos).
        """
        terms = self._query_terms(query)
        if not terms:
            return []
        return [term for term in terms if self._df.get(term, 0) == 0]


# ---------------------------------------------------------------------------
# service
# ---------------------------------------------------------------------------
@dataclass
class LocalReviewAnswer:
    answer_text: str
    citations: list[dict[str, Any]]
    status: str
    abstain_reason: str
    metadata: dict[str, Any] = field(default_factory=dict)
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer_text": self.answer_text,
            "citations": self.citations,
            "status": self.status,
            "abstain_reason": self.abstain_reason,
            "cached": self.cached,
            "metadata": self.metadata,
        }


class LocalReviewService:
    """The owner-only, file-backed candidate preview."""

    def __init__(
        self,
        config: LocalReviewConfig,
        *,
        translator: Optional[Callable[[str], str]] = None,
        distress_assessor: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self.config = config
        self._translator = translator
        self._distress_assessor = distress_assessor
        self._artifact_hashes: dict[str, str] = {}
        self._index: Optional[LocalReviewIndex] = None
        self._verdicts: dict[str, Any] = {}
        self._rights: dict[str, Any] = {}
        self._rights_join: dict[str, Any] = {}
        self._conflicts: set[str] = set()
        self._collisions: set[str] = set()
        self._cache: dict[str, LocalReviewAnswer] = {}

    # -- lifecycle ----------------------------------------------------------
    def startup_check(self) -> dict[str, Any]:
        """Verify every pinned artifact. Raises when anything is missing/stale."""
        required = {
            "tiers_manifest": self.config.tiers_manifest,
            "verdicts": self.config.verdicts,
            "rights_manifest": self.config.rights_manifest,
            "rights_join": self.config.rights_join,
            "speaker_conflicts": self.config.speaker_conflicts,
            "serving_contract": self.config.serving_contract,
        }
        hashes: dict[str, str] = {}
        for name, pin in required.items():
            path = _resolve(self.config.repo_root, pin.path)
            if not path.is_file():
                raise LocalReviewError(f"pinned artifact is missing: {name} ({path})")
            actual = sha256_file(path)
            if pin.sha256 and actual != pin.sha256:
                raise LocalReviewError(
                    f"pinned artifact {name} is stale or modified: "
                    f"expected {pin.sha256[:16]}…, got {actual[:16]}… ({path})"
                )
            hashes[name] = actual

        tiers_path = _resolve(self.config.repo_root, self.config.tiers_manifest.path)
        try:
            tiers = json.loads(tiers_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LocalReviewError(f"tiers manifest is unreadable: {exc}") from exc
        tier_entry = (tiers.get("tiers") or {}).get(self.config.tier)
        if not isinstance(tier_entry, dict):
            raise LocalReviewError(f"tiers manifest does not declare the {self.config.tier!r} tier")
        tier_path = _resolve(self.config.repo_root, str(tier_entry.get("path") or ""))
        if not tier_path.is_file():
            raise LocalReviewError(f"tier manifest is missing: {tier_path}")
        tier_hash = sha256_file(tier_path)
        if str(tier_entry.get("sha256") or "") != tier_hash:
            raise LocalReviewError(
                f"tier manifest is stale or modified: expected "
                f"{str(tier_entry.get('sha256'))[:16]}…, got {tier_hash[:16]}…"
            )
        hashes["tier_manifest"] = tier_hash

        rows = self._read_jsonl(tier_path)
        for row in rows:
            if row.get("tier") != self.config.tier:
                raise LocalReviewError(
                    f"tier manifest contains a foreign row: tier={row.get('tier')!r}"
                )
        self._index = LocalReviewIndex(rows)

        verdict_doc = self._read_json(_resolve(self.config.repo_root, self.config.verdicts.path))
        verdicts = verdict_doc.get("verdicts")
        if not isinstance(verdicts, dict):
            raise LocalReviewError("verdict manifest has no 'verdicts' object")
        self._verdicts = verdicts

        rights_doc = self._read_json(
            _resolve(self.config.repo_root, self.config.rights_manifest.path)
        )
        self._rights = rights_doc if isinstance(rights_doc, dict) else {}

        self._rights_join = {
            str(row.get("source_span_id") or ""): row
            for row in self._read_jsonl(
                _resolve(self.config.repo_root, self.config.rights_join.path)
            )
        }

        self._conflicts = {
            str(row.get("source_span_id") or "")
            for row in self._read_jsonl(
                _resolve(self.config.repo_root, self.config.speaker_conflicts.path)
            )
        }

        # Deterministic-id collisions: two distinct source spans can share one
        # rebuilt id. The preview must not serve either of them, and the
        # pinned tier must not contain one.
        self._collisions: set[str] = set()
        collision_pin = self.config.deterministic_id_collisions
        if collision_pin is not None:
            collision_path = _resolve(self.config.repo_root, collision_pin.path)
            if not collision_path.is_file():
                raise LocalReviewError(
                    f"pinned artifact is missing: deterministic_id_collisions ({collision_path})"
                )
            collision_hash = sha256_file(collision_path)
            if collision_pin.sha256 and collision_hash != collision_pin.sha256:
                raise LocalReviewError(
                    "pinned artifact deterministic_id_collisions is stale or modified: "
                    f"expected {collision_pin.sha256[:16]}…, got {collision_hash[:16]}… "
                    f"({collision_path})"
                )
            hashes["deterministic_id_collisions"] = collision_hash
            for row in self._read_jsonl(collision_path):
                collided = str(row.get("collided_source_span_id") or "")
                if collided:
                    self._collisions.add(collided)
        leaked = sorted(self._collisions & {str(row.get("source_span_id") or "") for row in rows})
        if leaked:
            raise LocalReviewError(
                "the candidate tier contains a deterministic-id collision member: "
                f"{leaked}; the preview refuses to serve an id that identifies two spans"
            )

        self._artifact_hashes = hashes
        logger.info(
            "[LocalReview] started tier=%s spans=%d evidence_policy=%s corpus_version=%s "
            "collection=%s hashes=%s",
            self.config.tier,
            len(self._index),
            self.config.evidence_policy,
            self.config.corpus_version,
            self.config.collection,
            {k: v[:12] for k, v in sorted(hashes.items())},
        )
        return {
            "tier": self.config.tier,
            "span_count": len(self._index),
            "artifact_hashes": dict(sorted(hashes.items())),
            "evidence_policy": self.config.evidence_policy,
            "corpus_version": self.config.corpus_version,
            "collection": self.config.collection,
            "review_label": self.config.review_label,
        }

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise LocalReviewError(f"{path}:{lineno} is not valid JSON: {exc}") from exc
                if not isinstance(row, dict):
                    raise LocalReviewError(f"{path}:{lineno} is not a JSON object")
                rows.append(row)
        return rows

    @staticmethod
    def _read_json(path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LocalReviewError(f"cannot read JSON from {path}: {exc}") from exc

    # -- helpers ------------------------------------------------------------
    def _metadata(self, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
        meta = {
            "review_label": self.config.review_label,
            "review_label_lines": list(self.config.review_label_lines),
            "evidence_policy": self.config.evidence_policy,
            "tier": self.config.tier,
            "corpus_version": self.config.corpus_version,
            "collection": self.config.collection,
            "qdrant_reads": 0,
            "qdrant_writes": 0,
            "alias_changes": 0,
            "redis_operations": 0,
            "llm_generated_answer": LLM_AUTHORED_ANSWER,
            "attribution_status": (
                "automated speaker evidence (pinned ECAPA + impostor-calibrated floor); "
                "not human-certified"
            ),
            "rights_status": "owner-confirmed basis on file; register not yet owner-signed",
            "manifest_hashes": dict(sorted(self._artifact_hashes.items())),
        }
        if extra:
            meta.update(dict(extra))
        return meta

    def _cache_key(self, query: str, teacher_id: str) -> str:
        """The exact-cache key. Every serving-policy input rides in it."""
        norm = unicodedata.normalize("NFKC", query).strip().lower()
        digest = hashlib.sha256(
            "|".join(
                [
                    norm,
                    (teacher_id or "both").strip().lower(),
                    self.config.tier,
                    self.config.evidence_policy,
                    self.config.corpus_version,
                    self.config.collection,
                    *(f"{key}={value}" for key, value in sorted(self._artifact_hashes.items())),
                ]
            ).encode("utf-8")
        ).hexdigest()
        return f"local_review_exact:{digest}"

    # -- guardrails ---------------------------------------------------------
    def _guard(self, query: str) -> tuple[str, str] | None:
        """The deterministic safety rail. Returns (status, answer) when it fires."""
        try:
            from guardrails.lightweight_handler import SAFETY_TOPICS, match_blocked_topic
        except Exception as exc:  # noqa: BLE001 - a missing rail must fail closed
            logger.error("[LocalReview] safety rail unavailable: %s", exc)
            return ("abstained", "This local review mode cannot run its safety checks.")

        blocked = match_blocked_topic(query)
        if blocked is not None:
            topic, response = blocked
            status = "crisis_redirect" if topic in SAFETY_TOPICS else "abstained"
            return (status, response)

        if self._distress_assessor is not None:
            try:
                assessment = self._distress_assessor(query)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[LocalReview] distress assessment failed: %s", exc)
                assessment = None
            level = getattr(getattr(assessment, "level", None), "value", None)
            if level is not None and int(level) >= 3:
                try:
                    from services.crisis_helplines import format_helplines_block

                    return ("crisis_redirect", format_helplines_block())
                except Exception:  # noqa: BLE001
                    return (
                        "crisis_redirect",
                        "Please reach out to a crisis helpline or emergency services now.",
                    )
        return None

    @staticmethod
    def _requested_teacher(query: str) -> str:
        """Which teacher the question names, if any ('preethaji'/'krishnaji'/'')."""
        try:
            from services.first_person_pipeline import requested_teacher

            return str(requested_teacher(query) or "").strip().lower()
        except Exception:  # noqa: BLE001
            lowered = query.lower()
            if "krishnaji" in lowered and "preethaji" not in lowered:
                return "krishnaji"
            if "preethaji" in lowered and "krishnaji" not in lowered:
                return "preethaji"
            return ""

    # -- citation -----------------------------------------------------------
    def _citation(self, row: Mapping[str, Any]) -> dict[str, Any] | None:
        """Build a citation, or None when any evidence check fails."""
        span_id = str(row.get("source_span_id") or "")
        if not span_id:
            return None
        if span_id in self._conflicts:
            return None
        if span_id in self._collisions:
            # A rebuilt id that identifies two source spans is not citable.
            return None
        verdict = self._verdicts.get(span_id)
        if not isinstance(verdict, dict):
            return None
        if verdict.get("reason_code") != "verified":
            return None
        if str(verdict.get("source_text_hash") or "") != str(row.get("source_text_hash") or ""):
            return None
        if int(verdict.get("audio_start_ms") or -1) != int(row.get("audio_start_ms") or -2):
            return None
        if int(verdict.get("audio_end_ms") or -1) != int(row.get("audio_end_ms") or -2):
            return None
        text = str(row.get("text") or "")
        if not text:
            return None
        if sha256_text(text) != str(row.get("source_text_hash") or ""):
            return None
        rights = self._rights_join.get(span_id)
        if not rights or not rights.get("servable"):
            return None
        if str(rights.get("rights_status") or "") not in (
            "confirmed_channel_owner",
            "confirmed_video_owner",
        ):
            return None
        if str(row.get("rights_status") or "") != str(rights.get("rights_status") or ""):
            return None

        start_ms = int(row.get("audio_start_ms") or 0)
        end_ms = int(row.get("audio_end_ms") or 0)
        video_id = str(row.get("video_id") or "")
        return {
            "source_span_id": span_id,
            "video_id": video_id,
            "guru_id": str(row.get("guru_id") or ""),
            "verbatim_text": text,
            "source_text_hash": str(row.get("source_text_hash") or ""),
            "transcript_hash": str(row.get("transcript_hash") or ""),
            "audio_start_ms": start_ms,
            "audio_end_ms": end_ms,
            "audio_sha256": str(row.get("audio_sha256") or ""),
            "playback_start_seconds": round(start_ms / 1000.0, 3),
            "playback_end_seconds": round(end_ms / 1000.0, 3),
            "playback_url": (
                f"https://www.youtube.com/watch?v={video_id}&t={int(start_ms / 1000)}s"
            ),
            "archived_wav": str(row.get("audio_path") or ""),
            "canonical_source_url": str(row.get("canonical_source_url") or ""),
            "speaker_verdict": str(verdict.get("reason_code") or ""),
            "speaker_model": str(verdict.get("speaker_model") or ""),
            "speaker_model_revision": str(verdict.get("speaker_model_revision") or ""),
            "calibration_revision": str(verdict.get("calibration_revision") or ""),
            "cosine": verdict.get("cosine"),
            "cosine_floor": verdict.get("cosine_floor"),
            "margin": verdict.get("margin"),
            "rights_status": str(rights.get("rights_status") or ""),
            "rights_owner_review_status": str(rights.get("owner_review_status") or ""),
            "evidence_policy": self.config.evidence_policy,
            # Every citation carries the owner-only label too: a citation can
            # be copied out of the response and must still say what it is.
            "review_label": self.config.review_label,
            "review_label_lines": list(self.config.review_label_lines),
            "is_verbatim": True,
        }

    # -- query --------------------------------------------------------------
    def query(
        self,
        query: str,
        *,
        teacher_id: str = "both",
        max_clips: int = 3,
        use_cache: bool = True,
    ) -> LocalReviewAnswer:
        """Answer from the candidate tier. Never LLM-authored."""
        if self._index is None:
            raise LocalReviewError("local review service was not started")

        requested = (teacher_id or "both").strip().lower()
        named = self._requested_teacher(query)
        if named and requested not in ("both", "all", "") and named != requested:
            return LocalReviewAnswer(
                answer_text=(
                    "This question names one teacher and requests another. No clip is served."
                ),
                citations=[],
                status="abstained",
                abstain_reason="cross_guru_conflict",
                metadata=self._metadata(
                    {
                        "requested_teacher": requested,
                        "query_teacher": named,
                        "abstain_reason": "cross_guru_conflict",
                    }
                ),
            )
        effective = named or (requested if requested not in ("both", "all", "") else "both")

        guard = self._guard(query)
        if guard is not None:
            status, answer = guard
            reason = "topic_blocked" if status == "abstained" else "crisis_redirect"
            return LocalReviewAnswer(
                answer_text=answer,
                citations=[],
                status=status,
                abstain_reason=reason,
                metadata=self._metadata({"abstain_reason": reason}),
            )

        key = self._cache_key(query, effective)
        if use_cache and key in self._cache:
            cached = self._cache[key]
            return LocalReviewAnswer(
                answer_text=cached.answer_text,
                citations=cached.citations,
                status=cached.status,
                abstain_reason=cached.abstain_reason,
                metadata={**cached.metadata, "cache": "hit"},
                cached=True,
            )

        retrieval_query = query
        if self._translator is not None:
            try:
                translated = self._translator(query)
                if translated and translated.strip():
                    retrieval_query = translated
            except Exception as exc:  # noqa: BLE001
                logger.warning("[LocalReview] query translation failed: %s", exc)

        # Out-of-corpus check FIRST: a question whose vocabulary is mostly
        # absent from the candidate corpus must abstain, not be answered with
        # a coincidental one-word match.
        query_terms = self._index._query_terms(retrieval_query)
        unmatched = self._index.unmatched_terms(retrieval_query)
        latin_only = _is_latin_script(retrieval_query)
        if not query_terms:
            reason = "no_discriminating_query_terms"
            return LocalReviewAnswer(
                answer_text=(
                    "No reviewed candidate span matches this question in the local review "
                    "corpus. Nothing is served."
                ),
                citations=[],
                status="abstained",
                abstain_reason=reason,
                metadata=self._metadata(
                    {
                        "abstain_reason": reason,
                        "query_teacher": effective,
                        "candidate_span_count": len(self._index),
                        "unmatched_query_terms": unmatched,
                    }
                ),
            )
        if latin_only and len(unmatched) * 2 >= len(query_terms):
            # The pinned candidate corpus is English (Latin script). A
            # non-Latin question is judged by the relevance floor instead:
            # term coverage cannot decide it, and the route's translator (not
            # this CLI) is what bridges it.
            return LocalReviewAnswer(
                answer_text=(
                    "No reviewed candidate span matches this question in the local review "
                    "corpus. Nothing is served."
                ),
                citations=[],
                status="abstained",
                abstain_reason="out_of_corpus_query",
                metadata=self._metadata(
                    {
                        "abstain_reason": "out_of_corpus_query",
                        "query_teacher": effective,
                        "candidate_span_count": len(self._index),
                        "unmatched_query_terms": unmatched,
                    }
                ),
            )

        hits = self._index.search(
            retrieval_query,
            teacher_id=effective,
            limit=max(1, min(max_clips, self.config.max_clips)),
        )
        if not hits:
            return LocalReviewAnswer(
                answer_text=(
                    "No reviewed candidate span matches this question in the local review "
                    "corpus. Nothing is served."
                ),
                citations=[],
                status="abstained",
                abstain_reason="no_candidate_match",
                metadata=self._metadata(
                    {
                        "abstain_reason": "no_candidate_match",
                        "query_teacher": effective,
                        "candidate_span_count": len(self._index),
                        "unmatched_query_terms": unmatched,
                    }
                ),
            )

        citations: list[dict[str, Any]] = []
        for row, score in hits:
            citation = self._citation(row)
            if citation is None:
                continue
            citation["match_score"] = round(float(score), 6)
            citations.append(citation)

        if not citations:
            answer = LocalReviewAnswer(
                answer_text=(
                    "No reviewed candidate span matches this question in the local review "
                    "corpus. Nothing is served."
                ),
                citations=[],
                status="abstained",
                abstain_reason="no_candidate_match",
                metadata=self._metadata(
                    {
                        "abstain_reason": "no_candidate_match",
                        "query_teacher": effective,
                        "candidate_span_count": len(self._index),
                    }
                ),
            )
        else:
            body = "\n\n".join(f'"{c["verbatim_text"]}"' for c in citations)
            answer = LocalReviewAnswer(
                answer_text=body,
                citations=citations,
                status="review_candidate",
                abstain_reason="none",
                metadata=self._metadata(
                    {
                        "query_teacher": effective,
                        "candidate_span_count": len(self._index),
                        "answer_source": "verbatim_span_text_only",
                    }
                ),
            )
        if use_cache:
            self._cache[key] = answer
        return answer

    def cache_info(self) -> dict[str, Any]:
        return {
            "entries": len(self._cache),
            "fingerprint_inputs": sorted(self._artifact_hashes),
            "evidence_policy": self.config.evidence_policy,
            "corpus_version": self.config.corpus_version,
            "collection": self.config.collection,
            "review_label": self.config.review_label,
            "review_label_lines": list(self.config.review_label_lines),
            "excluded_speaker_conflicts": len(self._conflicts),
            "excluded_deterministic_id_collisions": len(self._collisions),
        }


__all__ = [
    "COLLECTION_NAME",
    "EVIDENCE_POLICY",
    "LLM_AUTHORED_ANSWER",
    "LocalReviewAnswer",
    "LocalReviewConfig",
    "LocalReviewError",
    "LocalReviewIndex",
    "LocalReviewRefused",
    "LocalReviewService",
    "REVIEW_LABEL",
    "TIER_NAME",
    "load_local_review_config",
    "normalize_text",
    "sha256_file",
    "sha256_text",
    "tokenize",
]
