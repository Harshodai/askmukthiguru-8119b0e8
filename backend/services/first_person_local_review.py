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
* Not a release sign-off. X40's canonical ``domain_rights_status="licensed"``
  stamp/filter/revalidation contract is still open, B5 rights sign-off and B7
  human speaker certification remain open, and the separate oversize-parent
  hydration cap remains an open P2. This file validates immutable local
  artifacts only; it does not close or weaken those blockers.
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
from collections import Counter, OrderedDict
from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

SCHEMA = "fp-local-review-contract-v1"
TIER_SCHEMA = "first-person-corpus-tier-v2"
TIERS_MANIFEST_SCHEMA = "first-person-corpus-tiers-manifest-v2"
RIGHTS_JOIN_SCHEMA = "first-person-rights-join-v1"
RIGHTS_MANIFEST_SCHEMA = "first-person-rights-register-v1"
VERDICT_INDEX_SCHEMA = "first-person-v10-ecapa-verdict-index-v1"
# This is the row schema in the shipped verdict index.  It is intentionally
# distinct from VERDICT_INDEX_SCHEMA: the index root and each verdict row have
# different contracts.
VERDICT_ROW_SCHEMA = "first-person-v10-ecapa-span-verdict-v1"
SPEAKER_CONFLICT_SCHEMA = "first-person-speaker-conflict-v2"
DETERMINISTIC_COLLISION_SCHEMA = "first-person-deterministic-id-collision-v1"
COLLISION_TIER_NAME = "deterministic_id_collision_quarantine"
SPEAKER_CONFLICT_COUNT = 45
DETERMINISTIC_COLLISION_COUNT = 1
_RIGHTS_EVIDENCE_FIELDS = (
    ("rights_evidence_document", "evidence_document"),
    ("rights_evidence_sha256", "evidence_sha256"),
    ("rights_review_date", "review_date"),
)
_SPEAKER_CONFLICT_REQUIRED_FIELDS = (
    "schema",
    "source_span_id",
    "source_asset_id",
    "video_id",
    "text",
    "source_text_hash",
    "transcript_hash",
    "audio_sha256",
    "audio_file_duration_ms",
    "audio_slice_duration_ms",
    "audio_start_ms",
    "audio_end_ms",
    "word_start",
    "word_end",
    "quarantined",
    "review_decision",
    "reviewer",
    "reviewed_at_utc",
)
_COLLISION_MEMBER_REQUIRED_FIELDS = (
    "source_span_id",
    "live_source_span_id",
    "video_id",
    "guru_id",
    "live_word_start",
    "live_word_end",
    "rebuilt_word_start",
    "rebuilt_word_end",
    "source_text_hash",
    "transcript_hash",
    "input_record_sha256",
    "quarantine_record_id",
)
_RIGHTS_JOIN_REQUIRED_FIELDS = (
    "schema",
    "source_span_id",
    "video_id",
    "guru_id",
    "rights_status",
    "owner_review_status",
    "servable",
    "speaker_verdict",
    "rights_evidence_document",
    "rights_evidence_sha256",
    "rights_review_date",
)
_VERDICT_ROW_REQUIRED_FIELDS = (
    "schema",
    "source_span_id",
    "video_id",
    "guru_id",
    "expected_guru",
    "predicted_guru",
    "reason_code",
    "verdict",
    "source_text_hash",
    "transcript_hash",
    "audio_sha256",
    "audio_start_ms",
    "audio_end_ms",
    "audio_slice_duration_ms",
    "audio_window_ordered",
    "audio_path",
    "speaker_model",
    "speaker_model_revision",
    "calibration_revision",
)
_TIER_REQUIRED_FIELDS = (
    "schema",
    "tier",
    "serve_by_default",
    "source_span_id",
    "source_asset_id",
    "video_id",
    "guru_id",
    "text",
    "source_text_hash",
    "transcript_hash",
    "audio_start_ms",
    "audio_end_ms",
    "audio_file_duration_ms",
    "audio_slice_duration_ms",
    "audio_sha256",
    "audio_path",
    "canonical_source_url",
    "corpus_version",
    "evidence_policy",
    "rights_status",
    "rights_owner_review_status",
    "rights_evidence_document",
    "rights_evidence_sha256",
    "rights_review_date",
    "speaker_verdict",
    "speaker_model",
    "speaker_model_revision",
    "calibration_revision",
    "expected_guru",
    "predicted_guru",
)

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
CACHE_MAX_ENTRIES = 256
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
APPROVED_LOCAL_OWNER_CONFIRMED_STATUSES = frozenset(
    {"confirmed_channel_owner", "confirmed_video_owner"}
)

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
    deterministic_id_collisions: ArtifactPin
    corpus_version: str
    review_label: str
    review_label_lines: tuple[str, ...]
    evidence_policy: str
    max_clips: int = 3
    enabled: bool = False
    allow_in_production: bool = False

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

    raw_statuses = raw.get("servable_statuses")
    if raw_statuses is not None:
        if (
            not isinstance(raw_statuses, list)
            or len(raw_statuses) != 2
            or not all(isinstance(status, str) and status.strip() for status in raw_statuses)
            or set(raw_statuses) != APPROVED_LOCAL_OWNER_CONFIRMED_STATUSES
        ):
            raise LocalReviewError(
                "local-review contract servable_statuses must be exactly the two "
                "approved local owner-confirmed statuses"
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
        deterministic_id_collisions=_pin("deterministic_id_collisions"),
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
        if limit <= 0:
            return []
        wanted = (teacher_id or "both").strip().lower()
        terms = self._query_terms(query)
        if not terms or not self._docs:
            return []
        total_idf = sum(self._idf(term) for term in terms)
        if total_idf <= 0:
            return []
        scored: list[tuple[dict[str, Any], float]] = []
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
            scored.append((doc.row, score))
        scored.sort(key=lambda item: (-item[1], str(item[0].get("source_span_id"))))

        # At most one span per video (same rule as the production path):
        # score every eligible row first so file order cannot hide a stronger
        # fragment of the same talk.
        selected: list[tuple[dict[str, Any], float]] = []
        seen_videos: set[str] = set()
        for row, score in scored:
            video_id = str(row.get("video_id") or "")
            if video_id and video_id in seen_videos:
                continue
            if video_id:
                seen_videos.add(video_id)
            selected.append((row, score))
            if len(selected) >= max(0, limit):
                break
        return selected

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
        self._rights_assets: dict[str, dict[str, Any]] = {}
        self._servable_rights_statuses: frozenset[str] = frozenset()
        self._rights_join: dict[str, Any] = {}
        self._conflicts: set[str] = set()
        self._collisions: set[str] = set()
        self._collided_rebuilt_ids: set[str] = set()
        self._artifact_file_pins: dict[str, tuple[Path, str]] = {}
        self._artifact_integrity_failed = False
        self._cache: OrderedDict[str, LocalReviewAnswer] = OrderedDict()

    # -- lifecycle ----------------------------------------------------------
    @staticmethod
    def _validate_speaker_conflicts(conflict_rows: list[dict[str, Any]]) -> None:
        if len(conflict_rows) != SPEAKER_CONFLICT_COUNT:
            raise LocalReviewError(
                f"speaker-conflict artifact must contain {SPEAKER_CONFLICT_COUNT} rows; "
                f"got {len(conflict_rows)}"
            )
        seen: set[str] = set()
        for row in conflict_rows:
            missing = [field for field in _SPEAKER_CONFLICT_REQUIRED_FIELDS if field not in row]
            if missing:
                raise LocalReviewError(
                    f"speaker-conflict row is missing required fields: {missing}"
                )
            if row.get("schema") != SPEAKER_CONFLICT_SCHEMA:
                raise LocalReviewError(
                    f"speaker-conflict row schema must be {SPEAKER_CONFLICT_SCHEMA!r}"
                )
            span_id = str(row.get("source_span_id") or "").strip()
            if not span_id or span_id in seen:
                raise LocalReviewError(
                    "speaker-conflict rows require unique non-empty source_span_id values"
                )
            seen.add(span_id)
            source_asset_id = str(row.get("source_asset_id") or "").strip()
            video_id = str(row.get("video_id") or "").strip()
            if not source_asset_id or source_asset_id != video_id:
                raise LocalReviewError(
                    "speaker-conflict row source_asset_id and video_id must be non-empty and agree"
                )
            text = str(row.get("text") or "")
            if not text or sha256_text(text) != str(row.get("source_text_hash") or ""):
                raise LocalReviewError("speaker-conflict row has an invalid text hash")
            for field_name in ("source_text_hash", "transcript_hash", "audio_sha256"):
                if not _SHA256_RE.fullmatch(str(row.get(field_name) or "")):
                    raise LocalReviewError(f"speaker-conflict row has an invalid {field_name}")
            numeric_fields = (
                "audio_file_duration_ms",
                "audio_slice_duration_ms",
                "audio_start_ms",
                "audio_end_ms",
                "word_start",
                "word_end",
            )
            if any(
                not isinstance(row.get(field), int) or isinstance(row.get(field), bool)
                for field in numeric_fields
            ):
                raise LocalReviewError("speaker-conflict coordinates must be integer values")
            if (
                row["audio_file_duration_ms"] <= 0
                or row["audio_slice_duration_ms"] <= 0
                or row["audio_start_ms"] < 0
                or row["audio_end_ms"] <= row["audio_start_ms"]
                or row["audio_end_ms"] > row["audio_file_duration_ms"]
                or row["audio_slice_duration_ms"] != row["audio_end_ms"] - row["audio_start_ms"]
                or row["word_start"] < 0
                or row["word_end"] <= row["word_start"]
            ):
                raise LocalReviewError("speaker-conflict coordinates are invalid")
            if row.get("quarantined") is not True:
                raise LocalReviewError("speaker-conflict row must have quarantined=true")
            if any(
                row.get(field) != "" for field in ("review_decision", "reviewer", "reviewed_at_utc")
            ):
                raise LocalReviewError(
                    "speaker-conflict review_decision, reviewer, and reviewed_at_utc must remain empty"
                )
            if "audio_duration_ms" in row:
                raise LocalReviewError(
                    "speaker-conflict row must not contain the removed audio_duration_ms field"
                )
            playback = row.get("playback")
            if not isinstance(playback, dict):
                raise LocalReviewError("speaker-conflict row must contain playback identity")
            if str(playback.get("archived_wav_sha256") or "") != str(row["audio_sha256"]):
                raise LocalReviewError("speaker-conflict playback audio hash does not match row")
            if (
                playback.get("file_duration_ms") != row["audio_file_duration_ms"]
                or playback.get("slice_duration_ms") != row["audio_slice_duration_ms"]
                or playback.get("start_ms") != row["audio_start_ms"]
                or playback.get("end_ms") != row["audio_end_ms"]
                or str(playback.get("youtube_url") or "").find(video_id) < 0
            ):
                raise LocalReviewError("speaker-conflict playback identity does not match row")

    @staticmethod
    def _validate_collision_rows(collision_rows: list[dict[str, Any]]) -> None:
        if len(collision_rows) != DETERMINISTIC_COLLISION_COUNT:
            raise LocalReviewError(
                f"deterministic-collision artifact must contain {DETERMINISTIC_COLLISION_COUNT} row; "
                f"got {len(collision_rows)}"
            )
        row = collision_rows[0]
        if row.get("schema") != DETERMINISTIC_COLLISION_SCHEMA:
            raise LocalReviewError(
                f"deterministic-collision row schema must be {DETERMINISTIC_COLLISION_SCHEMA!r}"
            )
        if row.get("member_count") != 2 or row.get("distinct_source_span_count") != 2:
            raise LocalReviewError(
                "deterministic-collision row must have member_count=2 and "
                "distinct_source_span_count=2"
            )
        if (
            row.get("quarantined") is not True
            or row.get("resolution_status") != "unresolved"
            or row.get("namespace_fix_applied") is not False
            or row.get("serve_by_default") is not False
        ):
            raise LocalReviewError(
                "deterministic-collision row has an invalid quarantine or resolution status"
            )
        collided = str(row.get("collided_source_span_id") or "").strip()
        members = row.get("members")
        live_ids = row.get("distinct_live_span_ids")
        if not collided or not isinstance(members, list) or len(members) != 2:
            raise LocalReviewError("deterministic-collision row must contain two logical members")
        if (
            not isinstance(live_ids, list)
            or len(live_ids) != 2
            or len(set(live_ids)) != 2
            or not all(isinstance(live_id, str) and live_id.strip() for live_id in live_ids)
        ):
            raise LocalReviewError(
                "deterministic-collision row must identify two distinct live source spans"
            )
        member_live_ids: list[str] = []
        logical_ranges: set[tuple[str, int, int]] = set()
        for member in members:
            if not isinstance(member, dict):
                raise LocalReviewError("deterministic-collision members must be objects")
            missing = [field for field in _COLLISION_MEMBER_REQUIRED_FIELDS if field not in member]
            if missing:
                raise LocalReviewError(
                    f"deterministic-collision member is missing required fields: {missing}"
                )
            if str(member.get("source_span_id") or "").strip() != collided:
                raise LocalReviewError(
                    "deterministic-collision member source_span_id must match collided_source_span_id"
                )
            live_id = str(member.get("live_source_span_id") or "").strip()
            member_live_ids.append(live_id)
            if not live_id or live_id in member_live_ids[:-1]:
                raise LocalReviewError("deterministic-collision live source IDs must be unique")
            for field_name in ("input_record_sha256", "source_text_hash", "transcript_hash"):
                if not _SHA256_RE.fullmatch(str(member.get(field_name) or "")):
                    raise LocalReviewError(
                        f"deterministic-collision member has invalid {field_name}"
                    )
            for field_name in (
                "live_word_start",
                "live_word_end",
                "rebuilt_word_start",
                "rebuilt_word_end",
            ):
                if not isinstance(member.get(field_name), int) or isinstance(
                    member.get(field_name), bool
                ):
                    raise LocalReviewError(
                        "deterministic-collision word coordinates must be integers"
                    )
            if (
                member["live_word_start"] < 0
                or member["live_word_end"] <= member["live_word_start"]
                or member["rebuilt_word_start"] < 0
                or member["rebuilt_word_end"] <= member["rebuilt_word_start"]
            ):
                raise LocalReviewError("deterministic-collision word coordinates are invalid")
            logical_ranges.add((live_id, member["live_word_start"], member["live_word_end"]))
        if member_live_ids != list(live_ids) and set(member_live_ids) != set(live_ids):
            raise LocalReviewError("deterministic-collision live member IDs do not match the row")
        if len(logical_ranges) != 2:
            raise LocalReviewError("deterministic-collision members are not logically distinct")
        evidence = row.get("collision_cause_evidence")
        if not isinstance(evidence, dict):
            raise LocalReviewError(
                "deterministic-collision row must contain collision_cause_evidence"
            )
        evidence_ids = evidence.get("distinct_live_source_span_ids")
        if (
            not isinstance(evidence_ids, list)
            or set(evidence_ids) != set(live_ids)
            or evidence.get("member_count") != 2
        ):
            raise LocalReviewError(
                "deterministic-collision evidence does not match the two members"
            )

    @staticmethod
    def _validate_collision_tier_rows(
        tier_rows: list[dict[str, Any]], collision_row: Mapping[str, Any]
    ) -> None:
        """Require the quarantine tier to be an exact projection of both members."""
        members = collision_row.get("members")
        if not isinstance(members, list) or len(members) != 2:
            raise LocalReviewError(
                "collision quarantine tier requires the pinned two-member artifact"
            )
        if len(tier_rows) != 2:
            raise LocalReviewError(
                "collision quarantine tier must contain exactly the two pinned collision members"
            )
        expected: set[tuple[Any, ...]] = set()
        for member in members:
            expected.add(
                (
                    str(member["source_span_id"]),
                    str(member["live_source_span_id"]),
                    str(member["video_id"]),
                    str(member["guru_id"]),
                    member["live_word_start"],
                    member["live_word_end"],
                    member["rebuilt_word_start"],
                    member["rebuilt_word_end"],
                    str(member["source_text_hash"]),
                    str(member["transcript_hash"]),
                    str(member["input_record_sha256"]),
                    str(member["quarantine_record_id"]),
                )
            )
        actual: set[tuple[Any, ...]] = set()
        collided_id = str(collision_row["collided_source_span_id"])
        for row in tier_rows:
            if row.get("schema") != TIER_SCHEMA or row.get("tier") != COLLISION_TIER_NAME:
                raise LocalReviewError("collision quarantine row has an invalid tier identity")
            if row.get("serve_by_default") is not False:
                raise LocalReviewError("collision quarantine rows must have serve_by_default=false")
            if str(row.get("source_span_id") or "") != collided_id:
                raise LocalReviewError(
                    "collision quarantine row rebuilt ID does not match the pinned artifact"
                )
            actual.add(
                (
                    str(row.get("source_span_id") or ""),
                    str(row.get("live_source_span_id") or ""),
                    str(row.get("video_id") or ""),
                    str(row.get("guru_id") or ""),
                    row.get("live_word_start"),
                    row.get("live_word_end"),
                    row.get("word_start"),
                    row.get("word_end"),
                    str(row.get("source_text_hash") or ""),
                    str(row.get("transcript_hash") or ""),
                    str(row.get("input_record_sha256") or ""),
                    str(row.get("quarantine_record_id") or ""),
                )
            )
        if actual != expected:
            raise LocalReviewError(
                "collision quarantine tier rows do not exactly match the pinned two-member artifact"
            )

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
        artifact_file_pins: dict[str, tuple[Path, str]] = {}
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
            artifact_file_pins[name] = (path, pin.sha256)

        tiers_path = _resolve(self.config.repo_root, self.config.tiers_manifest.path)
        try:
            tiers = json.loads(tiers_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LocalReviewError(f"tiers manifest is unreadable: {exc}") from exc
        if not isinstance(tiers, dict):
            raise LocalReviewError("tiers manifest must contain a JSON object")
        if tiers.get("schema") != TIERS_MANIFEST_SCHEMA:
            raise LocalReviewError(
                f"tiers manifest schema must be {TIERS_MANIFEST_SCHEMA!r}; "
                f"got {tiers.get('schema')!r}"
            )
        if tiers.get("release_blocking") is not True:
            raise LocalReviewError("tiers manifest release_blocking must be true")
        tier_counts = tiers.get("tier_counts")
        tier_entries = tiers.get("tiers")
        if not isinstance(tier_counts, dict) or not isinstance(tier_entries, dict):
            raise LocalReviewError(
                "tiers manifest must contain object-valued tier_counts and tiers"
            )
        if set(tier_counts) != set(tier_entries):
            raise LocalReviewError("tiers manifest tier_counts and tiers declarations do not agree")
        for field_name, expected in (
            ("corpus_version", self.config.corpus_version),
            ("evidence_policy", self.config.evidence_policy),
        ):
            if tiers.get(field_name) != expected:
                raise LocalReviewError(
                    f"tiers manifest {field_name} must be {expected!r}; "
                    f"got {tiers.get(field_name)!r}"
                )
        tier_entry = tier_entries.get(self.config.tier)
        if not isinstance(tier_entry, dict):
            raise LocalReviewError(f"tiers manifest does not declare the {self.config.tier!r} tier")
        rows: list[dict[str, Any]] = []
        all_tier_rows: list[tuple[str, dict[str, Any]]] = []
        for tier_name, entry in tier_entries.items():
            if not isinstance(entry, dict):
                raise LocalReviewError(f"tiers manifest entry for {tier_name!r} must be an object")
            row_count = entry.get("row_count")
            declared_root_count = tier_counts.get(tier_name)
            for label, value in (("row_count", row_count), ("tier_counts", declared_root_count)):
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise LocalReviewError(
                        f"tiers manifest {label} for {tier_name!r} must be a non-negative integer"
                    )
            if row_count != declared_root_count:
                raise LocalReviewError(
                    f"tiers manifest count declarations disagree for {tier_name!r}"
                )
            tier_path = _resolve(self.config.repo_root, str(entry.get("path") or ""))
            if not tier_path.is_file():
                raise LocalReviewError(f"tier manifest is missing: {tier_path}")
            tier_hash = sha256_file(tier_path)
            if str(entry.get("sha256") or "") != tier_hash:
                raise LocalReviewError(
                    f"tier manifest is stale or modified: expected "
                    f"{str(entry.get('sha256'))[:16]}…, got {tier_hash[:16]}…"
                )
            if tier_name == self.config.tier:
                hashes["tier_manifest"] = tier_hash
            artifact_file_pins[f"tier:{tier_name}"] = (
                tier_path,
                str(entry.get("sha256") or ""),
            )
            tier_rows = self._read_jsonl(tier_path)
            if len(tier_rows) != row_count:
                raise LocalReviewError(
                    f"tiers manifest row_count for {tier_name!r} is {row_count}; "
                    f"tier contains {len(tier_rows)} rows"
                )
            for row in tier_rows:
                if row.get("schema") != TIER_SCHEMA:
                    raise LocalReviewError(
                        f"tier manifest row schema must be {TIER_SCHEMA!r}; got {row.get('schema')!r}"
                    )
                if not str(row.get("source_span_id") or "").strip():
                    raise LocalReviewError(
                        f"tier {tier_name!r} contains a row with no source_span_id"
                    )
                if row.get("tier") != tier_name:
                    raise LocalReviewError(
                        f"tier manifest row has tier={row.get('tier')!r}; expected {tier_name!r}"
                    )
                all_tier_rows.append((tier_name, row))
            if tier_name == self.config.tier:
                rows = tier_rows

        # Rebuilt IDs must be globally unique for ordinary tiers.  The
        # collision quarantine is the one deliberate exception: both rows
        # retain the same rebuilt source_span_id, so their live source span ID
        # and live word range are the logical identity checked below.
        seen_tier_ids: dict[str, str] = {}
        collision_live_ids: set[str] = set()
        for tier_name, row in all_tier_rows:
            source_span_id = str(row.get("source_span_id") or "").strip()
            if tier_name == COLLISION_TIER_NAME:
                live_source_span_id = str(row.get("live_source_span_id") or "").strip()
                if not live_source_span_id or live_source_span_id in collision_live_ids:
                    raise LocalReviewError(
                        "collision quarantine tier must have unique non-empty live_source_span_id values"
                    )
                collision_live_ids.add(live_source_span_id)
                continue
            previous_tier = seen_tier_ids.get(source_span_id)
            if previous_tier is not None:
                raise LocalReviewError(
                    "source_span_id is duplicated across tiers: "
                    f"{source_span_id!r} ({previous_tier!r}, {tier_name!r})"
                )
            seen_tier_ids[source_span_id] = tier_name

        selected_ids = [str(row.get("source_span_id") or "").strip() for row in rows]
        if len(selected_ids) != len(set(selected_ids)):
            raise LocalReviewError("selected tier contains duplicate source_span_id values")
        for row in rows:
            missing = [field_name for field_name in _TIER_REQUIRED_FIELDS if field_name not in row]
            if missing:
                raise LocalReviewError(f"selected tier row is missing required fields: {missing}")
            if row.get("corpus_version") != self.config.corpus_version:
                raise LocalReviewError(
                    "selected tier row corpus_version does not match the contract"
                )
            if row.get("evidence_policy") != self.config.evidence_policy:
                raise LocalReviewError(
                    "selected tier row evidence_policy does not match the contract"
                )
            if row.get("serve_by_default") is not True:
                raise LocalReviewError("selected tier row must have serve_by_default=true")
            if str(row.get("source_asset_id") or "") != str(row.get("video_id") or ""):
                raise LocalReviewError("selected tier row source_asset_id and video_id must agree")
            for field_name in (
                "text",
                "source_span_id",
                "source_asset_id",
                "video_id",
                "canonical_source_url",
            ):
                if not str(row.get(field_name) or "").strip():
                    raise LocalReviewError(f"selected tier row has an empty {field_name}")
            for field_name in (
                "source_text_hash",
                "transcript_hash",
                "audio_sha256",
                "rights_evidence_sha256",
            ):
                if not _SHA256_RE.fullmatch(str(row.get(field_name) or "")):
                    raise LocalReviewError(f"selected tier row has an invalid {field_name}")
            numeric_fields = (
                "audio_start_ms",
                "audio_end_ms",
                "audio_file_duration_ms",
                "audio_slice_duration_ms",
            )
            if any(
                not isinstance(row.get(field_name), int) or isinstance(row.get(field_name), bool)
                for field_name in numeric_fields
            ):
                raise LocalReviewError(
                    "selected tier row audio fields must be integer milliseconds"
                )
            if (
                row["audio_start_ms"] < 0
                or row["audio_end_ms"] <= row["audio_start_ms"]
                or row["audio_end_ms"] > row["audio_file_duration_ms"]
                or row["audio_slice_duration_ms"] != row["audio_end_ms"] - row["audio_start_ms"]
            ):
                raise LocalReviewError(
                    "selected tier row audio bounds or slice duration are invalid"
                )
        self._index = LocalReviewIndex(rows)

        verdict_doc = self._read_json(_resolve(self.config.repo_root, self.config.verdicts.path))
        if not isinstance(verdict_doc, dict) or verdict_doc.get("schema") != VERDICT_INDEX_SCHEMA:
            raise LocalReviewError(
                f"verdict index schema must be {VERDICT_INDEX_SCHEMA!r}; "
                f"got {verdict_doc.get('schema') if isinstance(verdict_doc, dict) else None!r}"
            )
        if verdict_doc.get("key_field") != "source_span_id":
            raise LocalReviewError("verdict index key_field must be 'source_span_id'")
        verdicts = verdict_doc.get("verdicts")
        if not isinstance(verdicts, dict):
            raise LocalReviewError("verdict manifest has no 'verdicts' object")
        verdict_count = verdict_doc.get("verdict_count")
        if (
            not isinstance(verdict_count, int)
            or isinstance(verdict_count, bool)
            or verdict_count < 0
        ):
            raise LocalReviewError("verdict index verdict_count must be a non-negative integer")
        if len(verdicts) != verdict_count:
            raise LocalReviewError(
                f"verdict index verdict_count is {verdict_count}; index contains {len(verdicts)} rows"
            )
        for key, verdict in verdicts.items():
            if not isinstance(key, str) or not key.strip() or not isinstance(verdict, dict):
                raise LocalReviewError("verdict index contains a missing ID or non-object row")
            missing = [
                field_name
                for field_name in _VERDICT_ROW_REQUIRED_FIELDS
                if field_name not in verdict
            ]
            if missing:
                raise LocalReviewError(f"verdict row is missing required fields: {missing}")
            if verdict.get("schema") != VERDICT_ROW_SCHEMA:
                raise LocalReviewError(
                    f"verdict row schema must be {VERDICT_ROW_SCHEMA!r}; "
                    f"got {verdict.get('schema')!r}"
                )
            if str(verdict.get("source_span_id") or "").strip() != key.strip():
                raise LocalReviewError("verdict index key and row source_span_id do not agree")
        self._verdicts = verdicts

        rights_doc = self._read_json(
            _resolve(self.config.repo_root, self.config.rights_manifest.path)
        )
        if not isinstance(rights_doc, dict) or rights_doc.get("schema") != RIGHTS_MANIFEST_SCHEMA:
            raise LocalReviewError(
                f"rights manifest schema must be {RIGHTS_MANIFEST_SCHEMA!r}; "
                f"got {rights_doc.get('schema') if isinstance(rights_doc, dict) else None!r}"
            )
        asset_count = rights_doc.get("asset_count")
        if not isinstance(asset_count, int) or isinstance(asset_count, bool) or asset_count < 0:
            raise LocalReviewError("rights manifest asset_count must be a non-negative integer")
        self._rights = rights_doc
        assets = self._rights.get("assets")
        policy = self._rights.get("policy")
        statuses = policy.get("servable_statuses") if isinstance(policy, dict) else None
        if not isinstance(assets, list) or not assets:
            raise LocalReviewError("rights manifest must contain a non-empty 'assets' list")
        if len(assets) != asset_count:
            raise LocalReviewError(
                f"rights manifest asset_count is {asset_count}; manifest contains {len(assets)} assets"
            )
        if (
            not isinstance(statuses, list)
            or not statuses
            or not all(isinstance(status, str) and status.strip() for status in statuses)
        ):
            raise LocalReviewError(
                "rights manifest must declare non-empty policy.servable_statuses"
            )
        if set(statuses) != APPROVED_LOCAL_OWNER_CONFIRMED_STATUSES or len(statuses) != 2:
            raise LocalReviewError(
                "rights manifest policy.servable_statuses must be exactly the two "
                "approved local owner-confirmed statuses"
            )
        indexed_assets: dict[str, dict[str, Any]] = {}
        for asset in assets:
            if not isinstance(asset, dict):
                raise LocalReviewError("rights manifest contains a non-object asset")
            asset_id = str(asset.get("source_asset_id") or "").strip()
            video_id = str(asset.get("video_id") or "").strip()
            if not asset_id or not video_id:
                raise LocalReviewError(
                    "rights manifest asset is missing source_asset_id or video_id"
                )
            if asset_id != video_id:
                raise LocalReviewError(
                    f"rights manifest asset identity mismatch: source_asset_id={asset_id!r} "
                    f"video_id={video_id!r}"
                )
            if asset_id in indexed_assets:
                raise LocalReviewError(
                    f"rights manifest contains duplicate source_asset_id: {asset_id!r}"
                )
            for _, asset_field in _RIGHTS_EVIDENCE_FIELDS:
                value = asset.get(asset_field)
                if asset_field == "review_date":
                    continue
                if not isinstance(value, str) or not value.strip():
                    raise LocalReviewError(
                        f"rights manifest asset {asset_id!r} has empty {asset_field}"
                    )
            if not _SHA256_RE.fullmatch(str(asset.get("evidence_sha256") or "")):
                raise LocalReviewError(
                    f"rights manifest asset {asset_id!r} has invalid evidence_sha256"
                )
            in_candidate = asset.get("in_candidate")
            status = str(asset.get("rights_status") or "")
            review_date = asset.get("review_date")
            if not isinstance(in_candidate, bool):
                raise LocalReviewError(
                    f"rights manifest asset {asset_id!r} must declare boolean in_candidate"
                )
            date_is_empty = review_date == ""
            date_is_valid = isinstance(review_date, str) and bool(
                _ISO_DATE_RE.fullmatch(review_date)
            )
            if date_is_valid:
                try:
                    date.fromisoformat(review_date)
                except ValueError:
                    date_is_valid = False
            if in_candidate or status in APPROVED_LOCAL_OWNER_CONFIRMED_STATUSES:
                if not date_is_valid:
                    raise LocalReviewError(
                        f"rights manifest candidate/servable asset {asset_id!r} must have a valid ISO review_date"
                    )
            elif not date_is_empty and not date_is_valid:
                raise LocalReviewError(
                    f"rights manifest non-servable asset {asset_id!r} has an invalid review_date"
                )
            indexed_assets[asset_id] = asset
        candidate_asset_count = self._rights.get("candidate_asset_count")
        if candidate_asset_count is not None and (
            not isinstance(candidate_asset_count, int)
            or isinstance(candidate_asset_count, bool)
            or candidate_asset_count != sum(asset.get("in_candidate") is True for asset in assets)
        ):
            raise LocalReviewError("rights manifest candidate_asset_count does not match assets")
        self._rights_assets = indexed_assets
        self._servable_rights_statuses = frozenset(str(status) for status in statuses)

        self._rights_join = {}
        rights_join_rows = self._read_jsonl(
            _resolve(self.config.repo_root, self.config.rights_join.path)
        )
        for row in rights_join_rows:
            missing = [
                field_name for field_name in _RIGHTS_JOIN_REQUIRED_FIELDS if field_name not in row
            ]
            if missing:
                raise LocalReviewError(
                    f"rights join row is missing required rights-owned fields: {missing}"
                )
            if row.get("schema") != RIGHTS_JOIN_SCHEMA:
                raise LocalReviewError(
                    f"rights join row schema must be {RIGHTS_JOIN_SCHEMA!r}; "
                    f"got {row.get('schema')!r}"
                )
            span_id = str(row.get("source_span_id") or "").strip()
            if not span_id:
                raise LocalReviewError("rights join row has an empty source_span_id")
            video_id = str(row.get("video_id") or "").strip()
            asset = self._rights_assets.get(video_id)
            if asset is None:
                raise LocalReviewError(
                    f"rights join row has no matching rights asset for video_id {video_id!r}"
                )
            for row_field, asset_field in _RIGHTS_EVIDENCE_FIELDS:
                if str(row.get(row_field) or "") != str(asset.get(asset_field) or ""):
                    raise LocalReviewError(
                        f"rights join evidence does not match rights manifest: {row_field}"
                    )
            if not isinstance(row.get("servable"), bool):
                raise LocalReviewError("rights join servable must be boolean")
            if span_id in self._rights_join:
                raise LocalReviewError(
                    f"rights join contains duplicate source_span_id: {span_id!r}"
                )
            self._rights_join[span_id] = row
        if len(rights_join_rows) != verdict_count:
            raise LocalReviewError(
                f"rights join contains {len(rights_join_rows)} rows; verdict index declares "
                f"{verdict_count}"
            )
        if set(self._rights_join) != set(self._verdicts):
            raise LocalReviewError("rights join and verdict index source_span_id sets do not agree")
        declared_span_count = self._rights.get("span_count")
        if declared_span_count is not None and declared_span_count != len(self._rights_join):
            raise LocalReviewError(
                f"rights manifest span_count is {declared_span_count}; rights join contains "
                f"{len(self._rights_join)} rows"
            )

        # Every candidate-tier row must have an independent manifest asset. Do
        # not silently fall back to the per-span rights join when this fails.
        for row in rows:
            span_id = str(row.get("source_span_id") or "").strip()
            if span_id not in self._verdicts or span_id not in self._rights_join:
                raise LocalReviewError(
                    "selected tier row has no matching verdict and rights-join row"
                )
            source_asset_id = str(row.get("source_asset_id") or "").strip()
            video_id = str(row.get("video_id") or "").strip()
            if not source_asset_id or not video_id:
                raise LocalReviewError("candidate tier row is missing source_asset_id or video_id")
            if source_asset_id != video_id:
                raise LocalReviewError(
                    f"candidate tier identity mismatch: source_asset_id={source_asset_id!r} "
                    f"video_id={video_id!r}"
                )
            asset = self._rights_assets.get(source_asset_id)
            if asset is None:
                raise LocalReviewError(
                    f"rights manifest has no asset for candidate video {source_asset_id!r}"
                )
            if str(asset.get("rights_status") or "") not in APPROVED_LOCAL_OWNER_CONFIRMED_STATUSES:
                raise LocalReviewError(
                    f"candidate rights status is outside the approved local owner-confirmed set for {source_asset_id!r}"
                )
            if (
                asset.get("in_candidate") is not True
                or asset.get("engineering_allowlist_only") is True
            ):
                raise LocalReviewError(
                    f"candidate tier is not backed by a servable rights asset for {source_asset_id!r}"
                )
            for row_field, asset_field in (
                ("canonical_source_url", "canonical_source_url"),
                ("rights_status", "rights_status"),
                ("rights_owner_review_status", "owner_review_status"),
            ):
                if str(row.get(row_field) or "") != str(asset.get(asset_field) or ""):
                    raise LocalReviewError(
                        f"rights manifest disagrees with candidate tier for {source_asset_id!r}: "
                        f"{row_field}"
                    )
            rights_join = self._rights_join[span_id]
            verdict = self._verdicts[span_id]
            if str(rights_join.get("source_span_id") or "") != span_id:
                raise LocalReviewError(
                    f"rights join source_span_id does not match candidate tier for {span_id!r}"
                )
            # Rights-register assets are video-level ownership records and do
            # not own speaker attribution. Keep guru binding independent:
            # tier -> rights join -> verdict below. Only fields actually owned
            # by the rights manifest may be compared to this asset.
            for field_name in ("video_id", "rights_status", "owner_review_status"):
                tier_value = row.get(
                    "rights_owner_review_status"
                    if field_name == "owner_review_status"
                    else field_name
                )
                manifest_value = asset.get(
                    "owner_review_status" if field_name == "owner_review_status" else field_name
                )
                join_value = rights_join.get(field_name)
                if str(tier_value or "") != str(manifest_value or "") or str(
                    join_value or ""
                ) != str(tier_value or ""):
                    raise LocalReviewError(
                        f"rights join ownership mismatch for candidate {span_id!r}: {field_name}"
                    )
            if rights_join.get("servable") is not True:
                raise LocalReviewError(f"candidate rights join row is not servable for {span_id!r}")
            if str(rights_join.get("speaker_verdict") or "") != str(
                row.get("speaker_verdict") or ""
            ):
                raise LocalReviewError(
                    f"rights join speaker_verdict does not match candidate tier for {span_id!r}"
                )
            # guru_id is span/speaker attribution owned by the candidate tier
            # and the per-span rights join. The video-level rights manifest
            # has no guru_id and must never participate in this comparison.
            if str(rights_join.get("guru_id") or "") != str(row.get("guru_id") or ""):
                raise LocalReviewError(
                    f"rights join guru_id does not match candidate tier for {span_id!r}"
                )
            for field_name in ("video_id", "guru_id", "expected_guru", "predicted_guru"):
                if str(verdict.get(field_name) or "") != str(row.get(field_name) or ""):
                    raise LocalReviewError(
                        f"verdict ownership mismatch for candidate {span_id!r}: {field_name}"
                    )
            if str(verdict.get("speaker_verdict") or verdict.get("reason_code") or "") != str(
                row.get("speaker_verdict") or ""
            ):
                raise LocalReviewError(
                    f"verdict speaker_verdict does not match candidate tier for {span_id!r}"
                )
            for row_field, asset_field in _RIGHTS_EVIDENCE_FIELDS:
                expected = str(asset.get(asset_field) or "")
                if str(row.get(row_field) or "") != expected:
                    raise LocalReviewError(
                        f"rights manifest disagrees with candidate tier for {source_asset_id!r}: "
                        f"{row_field}"
                    )
                if str(rights_join.get(row_field) or "") != expected:
                    raise LocalReviewError(
                        f"rights join disagrees with candidate tier for {span_id!r}: {row_field}"
                    )

        conflict_rows = self._read_jsonl(
            _resolve(self.config.repo_root, self.config.speaker_conflicts.path)
        )
        self._validate_speaker_conflicts(conflict_rows)
        self._conflicts = {str(row["source_span_id"]).strip() for row in conflict_rows}

        # Deterministic-id collisions: two distinct source spans can share one
        # rebuilt id. The preview must not serve either of them, and the
        # pinned tier must not contain one.
        self._collisions: set[str] = set()
        collision_pin = self.config.deterministic_id_collisions
        collision_path = _resolve(self.config.repo_root, collision_pin.path)
        if not collision_path.is_file():
            raise LocalReviewError(
                f"pinned artifact is missing: deterministic_id_collisions ({collision_path})"
            )
        collision_hash = sha256_file(collision_path)
        if collision_hash != collision_pin.sha256:
            raise LocalReviewError(
                "pinned artifact deterministic_id_collisions is stale or modified: "
                f"expected {collision_pin.sha256[:16]}…, got {collision_hash[:16]}… "
                f"({collision_path})"
            )
        hashes["deterministic_id_collisions"] = collision_hash
        artifact_file_pins["deterministic_id_collisions"] = (collision_path, collision_pin.sha256)
        collision_rows = self._read_jsonl(collision_path)
        self._validate_collision_rows(collision_rows)
        collision_row = collision_rows[0]
        self._collisions = {
            str(member["live_source_span_id"]).strip() for member in collision_row["members"]
        }
        collided_ids = {str(collision_row["collided_source_span_id"]).strip()}
        self._collided_rebuilt_ids = set(collided_ids)
        collision_tier_rows = [
            row for tier_name, row in all_tier_rows if tier_name == COLLISION_TIER_NAME
        ]
        if not collision_tier_rows:
            raise LocalReviewError("tiers manifest must declare the collision quarantine tier")
        self._validate_collision_tier_rows(collision_tier_rows, collision_row)
        ordinary_ids = {
            str(row.get("source_span_id") or "").strip()
            for tier_name, row in all_tier_rows
            if tier_name != COLLISION_TIER_NAME
        }
        leaked = sorted(collided_ids & ordinary_ids)
        if leaked:
            raise LocalReviewError(
                "an ordinary tier contains a deterministic-id collision member: "
                f"{leaked}; the preview refuses to serve an id that identifies two spans"
            )

        self._artifact_hashes = hashes
        self._artifact_file_pins = artifact_file_pins
        self._artifact_integrity_failed = False
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

    def _effective_max_clips(self, max_clips: int) -> int:
        """Normalize a request limit to the pinned local contract bound."""
        return max(1, min(int(max_clips), max(1, int(self.config.max_clips))))

    def _cache_key(self, query: str, teacher_id: str, max_clips: int | None = None) -> str:
        """The exact-cache key. Every serving-policy input rides in it."""
        norm = unicodedata.normalize("NFKC", query).strip().lower()
        effective_max_clips = self._effective_max_clips(
            self.config.max_clips if max_clips is None else max_clips
        )
        digest = hashlib.sha256(
            "|".join(
                [
                    norm,
                    (teacher_id or "both").strip().lower(),
                    f"max_clips={effective_max_clips}",
                    self.config.tier,
                    self.config.evidence_policy,
                    self.config.corpus_version,
                    self.config.collection,
                    *(f"{key}={value}" for key, value in sorted(self._artifact_hashes.items())),
                ]
            ).encode("utf-8")
        ).hexdigest()
        return f"local_review_exact:{digest}"

    def _verify_pinned_artifacts_current(self) -> None:
        """Recheck immutable evidence before touching the index or cache."""
        if self._artifact_integrity_failed:
            self._cache.clear()
            raise LocalReviewError("pinned local-review artifacts are no longer valid")
        for path, expected in self._artifact_file_pins.values():
            try:
                actual = sha256_file(path)
            except OSError as exc:
                self._cache.clear()
                self._artifact_integrity_failed = True
                raise LocalReviewError("pinned local-review artifacts are no longer valid") from exc
            if actual != expected:
                self._cache.clear()
                self._artifact_integrity_failed = True
                raise LocalReviewError("pinned local-review artifacts are no longer valid")

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

                    return ("crisis_redirect", format_helplines_block(verified_only=True))
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
        if span_id in self._collisions or span_id in self._collided_rebuilt_ids:
            # A rebuilt id that identifies two source spans is not citable.
            return None
        verdict = self._verdicts.get(span_id)
        rights = self._rights_join.get(span_id)
        if not isinstance(verdict, dict) or not isinstance(rights, dict):
            return None

        source_asset_id = str(row.get("source_asset_id") or "").strip()
        video_id = str(row.get("video_id") or "").strip()
        if not source_asset_id or not video_id or source_asset_id != video_id:
            return None
        asset = self._rights_assets.get(source_asset_id)
        if not isinstance(asset, dict):
            return None
        if asset.get("in_candidate") is not True or asset.get("engineering_allowlist_only") is True:
            return None
        manifest_status = str(asset.get("rights_status") or "")
        if manifest_status not in APPROVED_LOCAL_OWNER_CONFIRMED_STATUSES:
            return None
        if str(asset.get("source_asset_id") or "") != source_asset_id:
            return None
        for row_field, asset_field in (
            ("canonical_source_url", "canonical_source_url"),
            ("rights_status", "rights_status"),
            ("rights_owner_review_status", "owner_review_status"),
        ):
            if str(asset.get(asset_field) or "") != str(row.get(row_field) or ""):
                return None
        for row_field, asset_field in _RIGHTS_EVIDENCE_FIELDS:
            expected = str(asset.get(asset_field) or "")
            if str(row.get(row_field) or "") != expected:
                return None
            if str(rights.get(row_field) or "") != expected:
                return None

        text = str(row.get("text") or "")
        source_text_hash = str(row.get("source_text_hash") or "")
        transcript_hash = str(row.get("transcript_hash") or "")
        audio_sha256 = str(row.get("audio_sha256") or "")
        if (
            not text
            or not _SHA256_RE.fullmatch(source_text_hash)
            or not _SHA256_RE.fullmatch(transcript_hash)
            or not _SHA256_RE.fullmatch(audio_sha256)
            or sha256_text(text) != source_text_hash
        ):
            return None
        try:
            start_ms = int(row["audio_start_ms"])
            end_ms = int(row["audio_end_ms"])
            file_duration_ms = int(row["audio_file_duration_ms"])
            slice_duration_ms = int(row["audio_slice_duration_ms"])
        except (KeyError, TypeError, ValueError):
            return None
        if (
            start_ms < 0
            or end_ms <= start_ms
            or end_ms > file_duration_ms
            or slice_duration_ms != end_ms - start_ms
        ):
            return None

        identity_fields = (
            "source_span_id",
            "video_id",
            "guru_id",
            "expected_guru",
            "predicted_guru",
            "source_text_hash",
            "transcript_hash",
            "audio_sha256",
            "audio_start_ms",
            "audio_end_ms",
            "audio_slice_duration_ms",
        )
        for identity_field in identity_fields:
            expected = row.get(identity_field)
            if expected is None or str(verdict.get(identity_field)) != str(expected):
                return None
            if identity_field in {"source_span_id", "video_id", "guru_id"} and str(
                rights.get(identity_field)
            ) != str(expected):
                return None
        for identity_field in ("speaker_model", "speaker_model_revision", "calibration_revision"):
            expected = row.get(identity_field)
            if expected is None or str(verdict.get(identity_field)) != str(expected):
                return None
        # ``audio_duration_ms`` in the old verdict artifact is legacy input. It
        # was historically ambiguous (file duration versus quoted slice) and
        # is deliberately ignored, never repurposed. The tier's authoritative
        # audio_file_duration_ms/audio_slice_duration_ms plus start/end fields
        # above define the citable window.
        if str(verdict.get("reason_code") or "") != "verified":
            return None
        if "verdict" in verdict and str(verdict.get("verdict") or "") != "verified":
            return None
        if str(row.get("speaker_verdict") or "") != "verified":
            return None
        if not rights.get("servable"):
            return None
        if str(rights.get("source_span_id") or "") != span_id:
            return None
        if str(rights.get("video_id") or "") != video_id:
            return None
        if str(rights.get("guru_id") or "") != str(row.get("guru_id") or ""):
            return None
        if str(rights.get("speaker_verdict") or "") != str(row.get("speaker_verdict") or ""):
            return None
        if str(rights.get("rights_status") or "") not in APPROVED_LOCAL_OWNER_CONFIRMED_STATUSES:
            return None
        if str(rights.get("rights_status") or "") != manifest_status:
            return None
        if str(rights.get("owner_review_status") or "") != str(
            asset.get("owner_review_status") or ""
        ):
            return None
        if str(row.get("rights_owner_review_status") or "") != str(
            asset.get("owner_review_status") or ""
        ):
            return None

        return {
            "source_span_id": span_id,
            "source_asset_id": source_asset_id,
            "video_id": video_id,
            "guru_id": str(row.get("guru_id") or ""),
            "verbatim_text": text,
            "source_text_hash": source_text_hash,
            "transcript_hash": transcript_hash,
            "audio_start_ms": start_ms,
            "audio_end_ms": end_ms,
            "audio_sha256": audio_sha256,
            "playback_start_seconds": round(start_ms / 1000.0, 3),
            "playback_end_seconds": round(end_ms / 1000.0, 3),
            "playback_url": (
                f"https://www.youtube.com/watch?v={video_id}&t={int(start_ms / 1000)}s"
            ),
            "canonical_source_url": str(row.get("canonical_source_url") or ""),
            "speaker_verdict": str(verdict.get("reason_code") or ""),
            "speaker_model": str(verdict.get("speaker_model") or ""),
            "speaker_model_revision": str(verdict.get("speaker_model_revision") or ""),
            "calibration_revision": str(verdict.get("calibration_revision") or ""),
            "cosine": verdict.get("cosine"),
            "cosine_floor": verdict.get("cosine_floor"),
            "margin": verdict.get("margin"),
            "rights_status": manifest_status,
            "rights_owner_review_status": str(asset.get("owner_review_status") or ""),
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
        self._verify_pinned_artifacts_current()

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

        effective_max_clips = self._effective_max_clips(max_clips)
        key = self._cache_key(query, effective, effective_max_clips)
        if use_cache and key in self._cache:
            cached = deepcopy(self._cache[key])
            self._cache.move_to_end(key)
            cached.metadata["cache"] = "hit"
            cached.cached = True
            return cached

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
            limit=effective_max_clips,
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
            self._cache[key] = deepcopy(answer)
            self._cache.move_to_end(key)
            while len(self._cache) > CACHE_MAX_ENTRIES:
                self._cache.popitem(last=False)
        return answer

    def cache_info(self) -> dict[str, Any]:
        return {
            "entries": len(self._cache),
            "max_entries": CACHE_MAX_ENTRIES,
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
    "APPROVED_LOCAL_OWNER_CONFIRMED_STATUSES",
    "CACHE_MAX_ENTRIES",
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
