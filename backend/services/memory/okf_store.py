"""OKF (Open Knowledge Format) store — read, validate, and query markdown entries.

Implements Google Cloud's Open Knowledge Format v0.1 (June 2026), which formalizes
Karpathy's LLM-wiki pattern: a bundle is a directory of markdown files, each carrying
YAML frontmatter with exactly one required field, ``type``. ``index.md`` and ``log.md``
are reserved filenames and carry no frontmatter.
  spec: https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md

This bundle is a *doctrine* bundle: it holds only Sri Preethaji & Sri Krishnaji's
teachings. OKF lets a producer define its own types; ours are ``DOCTRINE_TYPES``.
Anything else — engineering runbooks, RAG notes, config lessons — must live outside
``memory/okf/`` (see ``docs/engineering-notes/``), because every entry here is
embedded and injected verbatim into answers by ``rag/nodes/retrieval.py:_okf_match``.

The store reads from disk; the compiler (compiler.py) builds a compiled index.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

try:
    import frontmatter  # type: ignore
except ImportError:  # pragma: no cover
    frontmatter = None  # type: ignore

from app.config import settings
from services.okf_quality_filter import OKFQualityFilter
from services.transcript_verbatim import CORPUS_ROOT as _DEFAULT_CORPUS_ROOT
from services.transcript_verbatim import strip_fabricated_quotes

logger = logging.getLogger(__name__)

_VIDEO_ID_RE = re.compile(r"[?&]v=([A-Za-z0-9_-]{6,})")


def _video_id_from_source(source: str) -> Optional[str]:
    """Parse a YouTube ``v=<id>`` query param out of an entry's ``source`` field."""
    match = _VIDEO_ID_RE.search(source or "")
    return match.group(1) if match else None


_base_path = Path(__file__).resolve().parent
while _base_path.name and _base_path.name != "backend":
    _base_path = _base_path.parent
_OKF_DIR = (_base_path.parent / "memory" / "okf") if _base_path.name else Path("/app/memory/okf")

# The one correct resolver. compiler.py and scripts/extract_okf_from_stores.py each
# hand-rolled their own and both broke inside the image (backend/ IS /app there, so
# `.parent` lands on `/`). Import these instead of deriving them again.
OKF_DIR = _OKF_DIR
STAGING_DIR = _OKF_DIR / "staging"

# OKF v0.1 reserved filenames — no frontmatter, not concept documents.
RESERVED_FILENAMES = frozenset({"index.md", "log.md"})

# The producer-defined type vocabulary for this bundle. OKF says consumers must
# tolerate unknown types "gracefully"; for a zero-hallucination doctrine layer,
# graceful means *excluded from the answer path*, not silently injected.
DOCTRINE_TYPES = frozenset({"teaching", "practice", "glossary", "qa", "reflection"})


@dataclass(frozen=True)
class OKFEntry:
    path: Path
    meta: dict[str, Any]
    body: str

    @property
    def type(self) -> str:
        return self.meta.get("type", "unknown")

    @property
    def title(self) -> str:
        return self.meta.get("title", self.path.stem.replace("_", " ").title())

    @property
    def tags(self) -> list[str]:
        t = self.meta.get("tags", [])
        return t if isinstance(t, list) else [t] if t else []

    @property
    def source(self) -> str:
        return self.meta.get("source", "")

    @property
    def resource(self) -> str:
        """OKF v0.2 canonical resource; falls back to v0.1 source."""
        return self.meta.get("resource", "") or self.source

    @property
    def status(self) -> str:
        return self.meta.get("status", "stable")

    @property
    def generated(self) -> Optional[dict]:
        return self.meta.get("generated")

    @property
    def verified(self) -> Optional[Any]:
        return self.meta.get("verified")

    @property
    def sources(self) -> list[dict]:
        s = self.meta.get("sources", [])
        return s if isinstance(s, list) else [s] if s else []

    @property
    def teacher(self) -> str:
        return self.meta.get("teacher", "both")

    @property
    def description(self) -> str:
        """OKF-recommended one-sentence summary; derived from the body when absent.

        The compiler embeds ``title + description``. Embedding the bare title meant
        a seeker's question was matched against strings like "The Beautiful State".
        """
        explicit = str(self.meta.get("description", "")).strip()
        if explicit:
            return explicit
        for line in self.body.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", ">", "-", "*", "|", "`")):
                continue
            sentence = re.split(r"(?<=[.!?])\s", line)[0].strip()
            return sentence[:300]
        return ""

    @property
    def embed_text(self) -> str:
        """What the compiler embeds for semantic match."""
        desc = self.description
        return f"{self.title}. {desc}" if desc else self.title


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Minimal YAML frontmatter parser (no external dep)."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            raw_yaml = parts[1].strip()
            body = parts[2].strip()
            import yaml

            try:
                meta = yaml.safe_load(raw_yaml) or {}
            except Exception:
                meta = {}
            return meta, body
    return {}, text


class OKFStore:
    """Read and validate OKF markdown entries from disk."""

    def __init__(
        self, directory: Optional[Path] = None, corpus_root: Optional[Path] = None
    ) -> None:
        self.dir = directory or _OKF_DIR
        # Only consulted when settings.okf_verbatim_quote_gate is on; tests pass
        # a tmp corpus here instead of the real scripts/ingestion/corpus tree.
        self.corpus_root = corpus_root or _DEFAULT_CORPUS_ROOT

    def list_entries(self) -> list[OKFEntry]:
        """Return all valid OKF entries in the directory."""
        entries: list[OKFEntry] = []
        if not self.dir.exists():
            logger.warning("OKF directory not found: %s", self.dir)
            return entries
        # **/*.md recurses into sri-preethaji/, sri-krishnaji/, shared/.
        # Exclude staging/ (unreviewed LLM output) and _scripts/ (tooling).
        _excluded_parts = frozenset({"staging", "_scripts"})
        for p in sorted(self.dir.rglob("*.md")):
            if any(part in p.parts for part in _excluded_parts):
                continue
            if p.name in RESERVED_FILENAMES:
                continue  # OKF v0.1: index.md / log.md are not concept documents
            try:
                text = p.read_text(encoding="utf-8")
                meta, body = _parse_frontmatter(text)
                if "type" not in meta:
                    logger.warning("Skipping OKF entry without 'type': %s", p)
                    continue

                entry_type = str(meta.get("type", "")).strip().lower()
                if entry_type not in DOCTRINE_TYPES:
                    # Everything in this bundle is embedded and injected verbatim into
                    # answers. A runbook or engineering note reaching _okf_match would
                    # be cited to the seeker as a teaching of the gurus.
                    logger.warning(
                        "Skipping non-doctrine OKF entry (type=%r, allowed=%s): %s",
                        entry_type,
                        sorted(DOCTRINE_TYPES),
                        p,
                    )
                    continue

                ok, reason = OKFQualityFilter.validate_entry(
                    {
                        "type": entry_type,
                        "title": str(meta.get("title", "")),
                        "body": body,
                        "source": meta.get("source", ""),
                    }
                )
                if not ok:
                    logger.warning("Skipping malformed OKF entry (%s): %s", reason, p)
                    continue

                if settings.okf_verbatim_quote_gate:
                    _fm_vid = str(meta.get("video_id", "")).strip()
                    video_id = (
                        _fm_vid if _fm_vid else _video_id_from_source(str(meta.get("source", "")))
                    )
                    if video_id:
                        gated_body, removed = strip_fabricated_quotes(
                            body, video_id, corpus_root=self.corpus_root
                        )
                        if removed:
                            logger.warning(
                                "OKF load-time quote gate: removed %d non-verbatim quote(s) "
                                "from %s (video_id=%s)",
                                removed,
                                p,
                                video_id,
                            )
                        body = gated_body

                entries.append(OKFEntry(path=p, meta=meta, body=body))
            except Exception as e:
                logger.warning("Failed to read OKF entry %s: %s", p, e)
        return entries

    def by_type(self, type_name: str) -> list[OKFEntry]:
        return [e for e in self.list_entries() if e.type == type_name]

    def search(self, term: str, limit: int = 20) -> list[OKFEntry]:
        """Case-insensitive substring search across titles and bodies."""
        term_lower = term.lower()
        results: list[OKFEntry] = []
        for e in self.list_entries():
            if term_lower in e.title.lower() or term_lower in e.body.lower():
                results.append(e)
                if len(results) >= limit:
                    break
        return results

    def match_okf_entries(
        self,
        query_dense_vector: list[float],
        top_k: int = 3,
        min_similarity: float = 0.45,
        teacher: Optional[str] = None,
        preferred_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """In-memory vector matching against compiled.json using numpy dot product (<1ms)."""
        return match_okf_entries(
            query_dense_vector=query_dense_vector,
            top_k=top_k,
            min_similarity=min_similarity,
            teacher=teacher,
            preferred_type=preferred_type,
            compiled_path=self.dir / "compiled.json",
        )

    def match_verbatim_clusters(
        self,
        query_dense_vector: list[float],
        top_k: int = 2,
        min_similarity: float = 0.35,
    ) -> list[dict[str, Any]]:
        """In-memory vector matching against verbatim_clusters.json using numpy dot product (<0.1ms)."""
        return match_verbatim_clusters(
            query_dense_vector=query_dense_vector,
            top_k=top_k,
            min_similarity=min_similarity,
            clusters_path=self.dir / "verbatim_clusters.json",
        )


_COMPILED_INDEX_CACHE: dict[str, Any] = {
    "mtime": None,
    "path": None,
    "entries": [],
    "matrix": None,
}


def _extract_summary(entry: dict[str, Any]) -> str:
    """Extract or derive a concise summary from an OKF entry dict."""
    if entry.get("summary"):
        return str(entry["summary"]).strip()
    body = str(entry.get("body", ""))
    match = re.search(
        r"(?:##\s*Summary|\*\*Summary:\*\*|Summary:)\s*\n(.*?)(?=\n\s*(?:##|\*\*|---)|\Z)",
        body,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        s = match.group(1).strip()
        if s:
            return s
    return str(entry.get("description", "")).strip()


_TRAILING_ATTR_RE = re.compile(
    r"(?:"
    r"\s*\(\s*\"[^\"]*\"\s*\)\s*(?:[—–-][^.\n]*)?[.\s]*$"
    r"|\s*\((?:[^)]*?(?:speaker|channel|says|implies|source|preetha|krishna|ekam|o&o|academy|guru|knowledge\s+graph)[^)]*)\)\s*(?:[—–-][^.\n]*)?[.\s]*$"
    r"|\s*[—–-]\s*(?:(?:Sri\s+)?(?:Preethaji|Krishnaji)|Ekam\s*/\s*O&O\s*Academy|Unknown\s+(?:Channel|Speaker)|Speaker\s+Unknown)[^.\n]*[.\s]*$"
    r")",
    re.IGNORECASE,
)

_LEADING_BOILERPLATE_RE = re.compile(
    r"^(?:"
    r"(?:Teaching\s+Point\s+\d+|Key\s+Teaching)(?:\*\*)?:\s*"
    r"|(?:\*\*)?%\s+of\s+[^:*]+(?:\*\*)?:\s*"
    r"|(?:\*\*)?(?:(?:Sri\s+)?(?:Sri\s+)?(?:Preethaji|Krishnaji)|(?:The\s+)?(?:speaker|teacher|guru|Guruji)|Ekam\s*/\s*O&O\s*Academy)"
    r"(?:\s+(?:and|&)\s+(?:(?:Sri\s+)?(?:Sri\s+)?(?:Preethaji|Krishnaji)|(?:The\s+)?(?:speaker|teacher|guru)))?"
    r"(?:\*\*)?"
    r"\s*(?:"
    r"says|say|emphasizes|emphasize|encourages|encourage|suggests|suggest|explains|explain"
    r"|teaches|teach|instructs|instruct|observes|observe|notes|note|states|state"
    r"|reminds|remind|highlights|highlight|warns|warn|shares|share|advises|advise"
    r"|points\s+out|point\s+out|describes|describe|urges|urge|mentions|mention"
    r"|recommends|recommend|guides|guide|asks|ask|defines|define|argues|argue"
    r"|challenges|challenge|calls\s+for|call\s+for|envisions|envision|addresses|address|questions|question"
    r")"
    r"(?:\s+(?:the\s+importance\s+of|the\s+significance\s+of|the\s+listener|listeners|participants|individuals|seekers|viewers|us|reflection\s+on|the\s+notion\s+that|the\s+fear\s+of|the\s+necessity\s+of|a\s+shift\s+in|the\s+creation\s+of))?"
    r"(?:\s*:\s*\*\*|\s*:\s*\"|\s*:\s*|\s*\*\*:\s*|\s*\*\*|\s*\.\.\.\s*|\s+that\s+|\s+to\s+|\s+)?"
    r")",
    re.IGNORECASE,
)

_DANGLING_END_WORDS = frozenset({"and", "or", "but", "because", "the", "a", "an", "as"})
_TRUNCATED_QUOTE_END_RE = re.compile(r"\b(?:sp|comfo|expre|me|e|t)\"\s*[.)]?$", re.IGNORECASE)


def clean_teaching_sentence(text: str) -> Optional[str]:
    """Clean a single key teaching sentence by stripping extraction boilerplate.

    - Strips leading boilerplate prefixes (e.g., 'Sri Preethaji says:', 'The speaker encourages:').
    - Strips trailing parenthetical attributions (e.g., '(Sri Preethaji says)', '(Unknown speaker)').
    - Strips wrapping quotes and dangling connectors ('that', 'to').
    - Capitalizes the first letter if a prefix was stripped.
    - Drops malformed or truncated quote fragments (e.g., cut-off words, unmatched quotes, length < 20).
    - Returns clean teaching sentence (length >= 20) or None if invalid.
    """
    s = text.strip()
    if not s:
        return None

    # Strip trailing parenthetical / citation / dash attributions repeatedly
    while True:
        m_trail = _TRAILING_ATTR_RE.search(s)
        if m_trail:
            s = s[: m_trail.start()].strip()
        else:
            break

    # Strip leading extraction boilerplate prefixes repeatedly
    while True:
        m_lead = _LEADING_BOILERPLATE_RE.match(s)
        if m_lead:
            s = s[m_lead.end() :].strip()
        else:
            break

    # Strip surrounding quotes if wrapped
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("“") and s.endswith("”")):
        s = s[1:-1].strip()

    # Strip leftover connective leading words
    if s.lower().startswith("that "):
        s = s[5:].strip()
    elif s.lower().startswith("to "):
        s = s[3:].strip()

    # Capitalize first letter
    if s and s[0].islower():
        s = s[0].upper() + s[1:]

    # Fix unbalanced trailing or leading single quote mark
    if s.count('"') % 2 != 0:
        if s.endswith('"'):
            s = s[:-1].strip()
        elif s.startswith('"'):
            s = s[1:].strip()

    # Ensure terminal punctuation if ending with alphanumeric character
    if s and s[-1].isalnum():
        s = s + "."

    # Quality and integrity filters: drop malformed/truncated fragments
    if len(s) < 20:
        return None
    if s.count('"') % 2 != 0:
        return None
    if re.match(r"^%\s+of\b", s, re.IGNORECASE):
        return None
    if _TRUNCATED_QUOTE_END_RE.search(s):
        return None
    if re.search(r"\b\w+\[", s):
        return None
    clean_no_punct = re.sub(r"[\s.,;:!?\"\'”]+$", "", s).strip()
    words = clean_no_punct.split()
    if words and words[-1].lower() in _DANGLING_END_WORDS:
        return None

    return s


_clean_teaching_sentence = clean_teaching_sentence


def _extract_key_teachings(entry: dict[str, Any]) -> list[str]:
    """Extract structured bullet points of key teachings from an OKF entry dict,
    stripping extraction boilerplate and dropping malformed/truncated fragments."""
    points: list[str] = []
    if entry.get("key_teachings"):
        kt = entry["key_teachings"]
        raw_list = list(kt) if isinstance(kt, list) else [str(kt)]
        for item in raw_list:
            cleaned = clean_teaching_sentence(str(item))
            if cleaned:
                points.append(cleaned)
        return points

    body = str(entry.get("body", ""))
    match = re.search(
        r"(?:##\s*Key Teachings|\*\*Key Teachings:\*\*|Key Teachings:)\s*\n(.*?)(?=\n\s*(?:##|\*\*|---)|\Z)",
        body,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        section = match.group(1)
        for line in section.strip().splitlines():
            line = line.strip()
            if line.startswith(("-", "*", "•")) or (
                len(line) > 2 and line[0].isdigit() and line[1] in (".", ")")
            ):
                raw = re.sub(r"^[-*•\d.)\s]+", "", line).strip()
                if raw:
                    cleaned = clean_teaching_sentence(raw)
                    if cleaned:
                        points.append(cleaned)
    return points


def _extract_related_concepts(entry: dict[str, Any]) -> list[str]:
    """Extract related doctrine concepts from OKF entry (Karpathy LLM-Wiki pattern)."""
    if entry.get("related_concepts"):
        rc = entry["related_concepts"]
        return list(rc) if isinstance(rc, list) else [str(rc)]
    body = str(entry.get("body", ""))
    match = re.search(
        r"(?:##\s*Related Concepts|\*\*Related Concepts:\*\*|Related Concepts:)\s*\n(.*?)(?=\n\s*(?:##|\*\*|---)|\Z)",
        body,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        section = match.group(1)
        points = []
        for line in section.strip().splitlines():
            line = line.strip()
            if line.startswith(("-", "*", "•")):
                clean = re.sub(r"^[-*•\s]+", "", line).strip()
                if clean:
                    points.append(clean)
        if points:
            return points
    return []


def _matches_teacher(entry_teacher: str, requested_teacher: Optional[str]) -> bool:
    """Check if entry's teacher matches requested teacher filter."""
    if not requested_teacher:
        return True
    req = requested_teacher.strip().lower()
    if req in ("both", "all", ""):
        return True
    entry_t = (entry_teacher or "both").strip().lower()
    if entry_t == "both":
        return True
    if "preetha" in req and "preetha" in entry_t:
        return True
    if "krishna" in req and "krishna" in entry_t:
        return True
    return req == entry_t


def _load_compiled_matrix(compiled_path: Path) -> tuple[list[dict[str, Any]], Optional[np.ndarray]]:
    """Load pre-computed 1024-dim BGE-M3 embeddings and entries from compiled.json, cached by mtime."""
    global _COMPILED_INDEX_CACHE
    if not compiled_path.exists():
        return [], None
    try:
        mtime = compiled_path.stat().st_mtime
    except OSError:
        return [], None

    if (
        _COMPILED_INDEX_CACHE["mtime"] == mtime
        and _COMPILED_INDEX_CACHE["path"] == str(compiled_path)
        and _COMPILED_INDEX_CACHE["matrix"] is not None
    ):
        return _COMPILED_INDEX_CACHE["entries"], _COMPILED_INDEX_CACHE["matrix"]

    try:
        with open(compiled_path, encoding="utf-8") as f:
            data = json.load(f)
        raw_entries = data.get("entries", [])
    except Exception as e:
        logger.warning("Failed to load compiled OKF index from %s: %s", compiled_path, e)
        return [], None

    valid_entries = []
    emb_list = []
    for e in raw_entries:
        emb = e.get("embedding")
        if emb and len(emb) == 1024:
            valid_entries.append(e)
            emb_list.append(emb)

    if not emb_list:
        return [], None

    matrix = np.array(emb_list, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    norm_matrix = matrix / norms

    _COMPILED_INDEX_CACHE["mtime"] = mtime
    _COMPILED_INDEX_CACHE["path"] = str(compiled_path)
    _COMPILED_INDEX_CACHE["entries"] = valid_entries
    _COMPILED_INDEX_CACHE["matrix"] = norm_matrix

    return valid_entries, norm_matrix


def match_okf_entries(
    query_dense_vector: list[float],
    top_k: int = 3,
    min_similarity: float = 0.45,
    teacher: Optional[str] = None,
    preferred_type: Optional[str] = None,
    compiled_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """In-memory vector matching against compiled.json using numpy dot product (<1ms).

    Args:
        query_dense_vector: 1024-dim BGE-M3 query vector.
        top_k: Maximum number of entries to return.
        min_similarity: Cosine similarity threshold (default 0.45).
        teacher: Optional filter ('sri-preethaji', 'sri-krishnaji', or 'both').
        preferred_type: Optional entry type to boost (e.g. 'practice').
        compiled_path: Optional override path to compiled.json.

    Returns:
        List of matched entry dicts with:
        `title`, `type`, `teacher`, `source`, `summary`, `key_teachings`, `score`.
    """
    if not query_dense_vector or len(query_dense_vector) != 1024:
        return []

    c_path = compiled_path or (OKF_DIR / "compiled.json")
    entries, matrix = _load_compiled_matrix(c_path)
    if matrix is None or not entries:
        return []

    q = np.asarray(query_dense_vector, dtype=np.float32)
    q_norm = float(np.linalg.norm(q))
    if q_norm == 0.0:
        return []
    q_unit = q / q_norm

    # Ultra-fast numpy matrix dot product (<0.1ms for 715 entries)
    similarities = np.dot(matrix, q_unit)

    candidates: list[tuple[float, float, dict[str, Any]]] = []
    pref_type_lower = preferred_type.strip().lower() if preferred_type else None

    for i, base_sim in enumerate(similarities):
        e = entries[i]
        sim = float(base_sim)
        e_type = str(e.get("type", "")).strip().lower()

        # Teacher filter
        if teacher and not _matches_teacher(e.get("teacher", ""), teacher):
            continue

        # Type boost
        boosted_score = sim
        if pref_type_lower and e_type == pref_type_lower:
            # 20% boost to prioritize preferred type while capping at 1.0
            boosted_score = min(1.0, sim * 1.20)

        # Minimum similarity threshold
        if boosted_score < min_similarity:
            continue

        candidates.append((boosted_score, sim, e))

    if not candidates:
        return []

    # Sort descending by boosted score, breaking ties with base similarity
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)

    results: list[dict[str, Any]] = []
    for score, _base_sim, e in candidates[:top_k]:
        results.append(
            {
                "title": e.get("title", ""),
                "type": e.get("type", "teaching"),
                "teacher": e.get("teacher", "both"),
                "source": e.get("source", "") or e.get("resource", ""),
                "summary": _extract_summary(e),
                "key_teachings": _extract_key_teachings(e),
                "score": round(float(score), 4),
                "tags": e.get("tags", []),
                "related_concepts": _extract_related_concepts(e),
                "body": e.get("body", ""),
                "description": e.get("description", ""),
            }
        )

    return results


_VERBATIM_CLUSTERS_CACHE: dict[str, Any] = {
    "mtime": None,
    "path": None,
    "clusters": [],
    "matrix": None,
}


def _load_verbatim_clusters_matrix(
    clusters_path: Path,
) -> tuple[list[dict[str, Any]], Optional[np.ndarray]]:
    """Load pre-computed 1024-dim cluster centroid embeddings, cached by mtime."""
    global _VERBATIM_CLUSTERS_CACHE
    if not clusters_path.exists():
        return [], None
    try:
        mtime = clusters_path.stat().st_mtime
    except OSError:
        return [], None

    if (
        _VERBATIM_CLUSTERS_CACHE["mtime"] == mtime
        and _VERBATIM_CLUSTERS_CACHE["path"] == str(clusters_path)
        and _VERBATIM_CLUSTERS_CACHE["matrix"] is not None
    ):
        return _VERBATIM_CLUSTERS_CACHE["clusters"], _VERBATIM_CLUSTERS_CACHE["matrix"]

    try:
        with open(clusters_path, encoding="utf-8") as f:
            data = json.load(f)
        raw_clusters = data.get("clusters", [])
    except Exception as e:
        logger.warning("Failed to load verbatim clusters from %s: %s", clusters_path, e)
        return [], None

    valid_clusters = []
    emb_list = []
    for c in raw_clusters:
        emb = c.get("embedding")
        if emb and len(emb) == 1024:
            valid_clusters.append(c)
            emb_list.append(emb)

    if not emb_list:
        return [], None

    matrix = np.array(emb_list, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    norm_matrix = matrix / norms

    _VERBATIM_CLUSTERS_CACHE["mtime"] = mtime
    _VERBATIM_CLUSTERS_CACHE["path"] = str(clusters_path)
    _VERBATIM_CLUSTERS_CACHE["clusters"] = valid_clusters
    _VERBATIM_CLUSTERS_CACHE["matrix"] = norm_matrix

    return valid_clusters, norm_matrix


def match_verbatim_clusters(
    query_dense_vector: list[float],
    top_k: int = 2,
    min_similarity: float = 0.35,
    clusters_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """In-memory cosine search over canonical verbatim OKF clusters (<0.1ms).

    Args:
        query_dense_vector: 1024-dim query vector.
        top_k: Maximum number of clusters to return.
        min_similarity: Cosine similarity threshold.
        clusters_path: Optional path override to verbatim_clusters.json.

    Returns:
        List of cluster dicts with:
        `cluster_id`, `title`, `description`, `teacher`, `clip_count`,
        `clip_ids`, `key_verbatim_quotes`, `quotes_with_provenance`,
        `reflection_questions`, `score`.
    """
    if not query_dense_vector or len(query_dense_vector) != 1024:
        return []

    c_path = clusters_path or (OKF_DIR / "verbatim_clusters.json")
    clusters, matrix = _load_verbatim_clusters_matrix(c_path)
    if matrix is None or not clusters:
        return []

    q = np.asarray(query_dense_vector, dtype=np.float32)
    q_norm = float(np.linalg.norm(q))
    if q_norm == 0.0:
        return []
    q_unit = q / q_norm

    similarities = np.dot(matrix, q_unit)
    candidates: list[tuple[float, dict[str, Any]]] = []
    for i, sim in enumerate(similarities):
        score = float(sim)
        if score >= min_similarity:
            candidates.append((score, clusters[i]))

    candidates.sort(key=lambda x: x[0], reverse=True)

    results: list[dict[str, Any]] = []
    for score, c in candidates[:top_k]:
        results.append(
            {
                "cluster_id": c.get("cluster_id", ""),
                "title": c.get("title", ""),
                "description": c.get("description", ""),
                "teacher": c.get("teacher", "both"),
                "clip_count": c.get("clip_count", 0),
                "clip_ids": c.get("clip_ids", []),
                "key_verbatim_quotes": c.get("key_verbatim_quotes", []),
                "quotes_with_provenance": c.get("quotes_with_provenance", []),
                "reflection_questions": c.get("reflection_questions", []),
                "score": round(score, 4),
            }
        )
    return results


if __name__ == "__main__":  # ponytail: runnable self-check
    store = OKFStore()
    entries = store.list_entries()
    print(f"OKF entries: {len(entries)}")
    for e in entries:
        print(f"  {e.type}: {e.title}")
    assert len(entries) >= 1
    teaching = store.by_type("teaching")
    print(f"  teaching count: {len(teaching)}")
    results = store.search("beautiful")
    print(f"  search 'beautiful': {len(results)} results")
    print("okf_store OK")
