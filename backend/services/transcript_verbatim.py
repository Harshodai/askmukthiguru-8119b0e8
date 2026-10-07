"""Shared verbatim-transcript lookup — the data-quality gate's single source
of truth for "is this quote the teacher's actual recorded words?".

Resolves a video's transcript from the same place the rest of the ingestion
pipeline does: ``scripts/ingestion/corpus/<video_id>/canonical_segments.json``
(see ``scripts/ingestion/corpus_engine.py``, and ``backend/ingest/
youtube_loader.py``'s ``candidate_md_paths`` for the other code path that
already reads this directory). Normalisation matches the 2026-09-24
data-quality audit exactly: lowercase, alnum tokens only, apostrophes
dropped rather than treated as word breaks.

Callers:
  * ``backend/scripts/ops/data_quality_audit.py`` — read-only nightly audit
    (OKF fabricated-quote check, transcript structural checks).
  * ``scripts/ingestion/corpus_engine.py`` — per-video ingestion gate,
    quarantining a new video before it reaches Qdrant.
  * ``backend/scripts/extract_okf_from_stores.py`` (both tracked copies) —
    strips fabricated quotes before a staged OKF entry is written.
  * ``backend/services/memory/okf_store.py`` — optional load-time gate
    (``settings.okf_verbatim_quote_gate``, default off) re-checking quotes in
    already-staged/live entries before they reach the compiled index.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional, TypedDict

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
# Callers that need another corpus location pass `corpus_root` explicitly
# (e.g. data_quality_audit.py --corpus-root); no direct env reads here.
CORPUS_ROOT = REPO_ROOT / "scripts" / "ingestion" / "corpus"
# Flat caption projections (2026-10-03): fallback verbatim source for videos
# that only have transcripts/<video_id>.md and no word-timestamp corpus dir
# (older talks, TEDx). Same caption text the pipeline serves from — WITHOUT
# timestamps, so fallback matches return start=end=None, never a guessed t=.
TRANSCRIPTS_ROOT = REPO_ROOT / "transcripts"

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_APOSTROPHE_RE = re.compile(r"[‘’']")
_PARTIAL_MATCH_THRESHOLD = 0.70
_QUOTED_STRING_RE = re.compile(r'["\u201c]([^"\u201c\u201d\n]{20,400})["\u201d]')
MIN_QUOTE_WORDS = 8

MatchStatus = Literal["verbatim", "partial", "not_found"]
Severity = Literal["hard", "soft"]


class VerbatimResult(TypedDict):
    status: MatchStatus
    video_id: Optional[str]
    start: Optional[float]
    end: Optional[float]
    score: float


@dataclass(frozen=True)
class Finding:
    """One structural defect (or informational gap) found in a video's
    transcript. `severity="hard"` should block indexing; `"soft"` is
    surfaced in the audit but does not quarantine the video."""

    check: str
    severity: Severity
    detail: str


def normalise(text: str) -> str:
    """lowercase, apostrophes removed, alnum tokens only, space-joined.

    Matches the audit's method exactly: "don't" -> "dont" (one token, not
    two), punctuation dropped entirely.
    """
    if not text:
        return ""
    text = _APOSTROPHE_RE.sub("", text.lower())
    return " ".join(_TOKEN_RE.findall(text))


def _video_dir(video_id: str, corpus_root: Path) -> Path:
    return corpus_root / video_id


@lru_cache(maxsize=8)
def _log_missing_corpus_root(corpus_root: Path) -> None:
    # Once per root: without the corpus every quote check reports not_found, so
    # OKF extraction strips every quote. Fail-closed, but it must be visible.
    logger.error(
        "transcript_verbatim: corpus root missing: %s -- every quote check will "
        "report not_found (is scripts/ingestion/corpus available here?)",
        corpus_root,
    )


def load_segments(video_id: str, corpus_root: Path = CORPUS_ROOT) -> Optional[list[dict]]:
    """Load a video's canonical_segments.json segment list. None if missing/unreadable."""
    if not corpus_root.is_dir():
        _log_missing_corpus_root(corpus_root)
        return None
    seg_file = _video_dir(video_id, corpus_root) / "canonical_segments.json"
    if not seg_file.is_file():
        return None
    try:
        data = json.loads(seg_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("transcript_verbatim: could not read %s: %s", seg_file, exc)
        return None
    return data.get("segments", []) if isinstance(data, dict) else data


@lru_cache(maxsize=128)
def _token_index_keyed(video_id: str, corpus_root_str: str, _mtime_ns: int) -> Optional[tuple]:
    """Inner cache keyed by (video_id, corpus_root, file mtime_ns) so stale
    indexes are never served after the segment file changes. maxsize=128
    bounds memory for corpus-wide lookups."""
    segments = load_segments(video_id, Path(corpus_root_str))
    if not segments:
        return None
    index: list[tuple[str, float, float]] = []
    for seg in segments:
        text = seg.get("text") or ""
        start = seg.get("start", 0.0) or 0.0
        end = seg.get("end", start) or start
        for tok in normalise(text).split():
            index.append((tok, start, end))
    return tuple(index) if index else None


def _token_index(video_id: str, corpus_root_str: str) -> Optional[tuple]:
    """Cached (token, seg_start, seg_end) triples across every segment's
    display text, in transcript order. This is what find_verbatim slides a
    window over.

    Delegates to _token_index_keyed with the segment file's mtime_ns so
    the cache is invalidated when the file changes, and missing transcripts
    are never cached (they return None and are not stored)."""
    seg_file = Path(corpus_root_str) / video_id / "canonical_segments.json"
    try:
        mtime_ns = seg_file.stat().st_mtime_ns
    except OSError:
        # File absent — do not cache. A missing corpus ROOT must still be loud:
        # load_segments (which logs it) is never reached on this early return.
        root = Path(corpus_root_str)
        if not root.is_dir():
            _log_missing_corpus_root(root)
        return None
    return _token_index_keyed(video_id, corpus_root_str, mtime_ns)


@lru_cache(maxsize=128)
def _transcript_token_index_keyed(video_id: str, _mtime_ns: int) -> Optional[tuple]:
    """Token index over the flat transcripts/<video_id>.md projection.

    Fallback for find_verbatim when the corpus has no word-timestamp dir for
    this video: the caption text still IS the teacher's recorded words, so a
    quote absent from the corpus but present here is genuine. Timestamps are
    unknown (flat markdown), so entries are (token, None, None) — exact
    matches come back with start=end=None and callers must treat that as
    "no t= available", never as time zero."""
    try:
        text = (TRANSCRIPTS_ROOT / f"{video_id}.md").read_text(encoding="utf-8")
    except OSError:
        return None
    tokens = normalise(text).split()
    return tuple((tok, None, None) for tok in tokens) or None


def _transcript_token_index(video_id: str) -> Optional[tuple]:
    """Cached transcript-projection index, invalidated by file mtime like the
    corpus index. Missing transcripts are not cached (never pin a gap)."""
    try:
        mtime_ns = (TRANSCRIPTS_ROOT / f"{video_id}.md").stat().st_mtime_ns
    except OSError:
        return None
    return _transcript_token_index_keyed(video_id, mtime_ns)


def _all_video_ids(corpus_root: Path) -> list[str]:
    if not corpus_root.is_dir():
        return []
    return [p.name for p in corpus_root.iterdir() if p.is_dir()]


def _exact_match(index: tuple, quote_tokens: list[str]) -> Optional[tuple[float, float]]:
    tokens = [t for t, _, _ in index]
    n = len(quote_tokens)
    for i in range(len(tokens) - n + 1):
        if tokens[i : i + n] == quote_tokens:
            return index[i][1], index[i + n - 1][2]
    return None


def _best_partial_match(
    index: tuple, quote_tokens: list[str]
) -> tuple[float, Optional[float], Optional[float]]:
    tokens = [t for t, _, _ in index]
    span = max(len(quote_tokens), 1)
    qset = set(quote_tokens)
    best_score, best_start, best_end = 0.0, None, None
    for i in range(max(1, len(tokens) - span + 1)):
        window = tokens[i : i + span]
        if not window:
            continue
        overlap = len(qset & set(window)) / len(qset)
        if overlap > best_score:
            best_score = overlap
            best_start, best_end = index[i][1], index[min(i + span, len(index)) - 1][2]
    return best_score, best_start, best_end


def find_verbatim(
    quote: str, video_id: Optional[str] = None, corpus_root: Path = CORPUS_ROOT
) -> VerbatimResult:
    """Is `quote` the teacher's actual recorded words?

    "verbatim": the normalised quote is an exact token-sequence match
    somewhere in the video's transcript. "partial": no exact match, but the
    best sliding-window token overlap is >= 0.70. "not_found": neither.

    Source order (2026-10-03): the word-timestamp corpus is authoritative
    when present; videos WITHOUT a corpus dir fall back to the flat
    ``transcripts/<video_id>.md`` caption projection (fallback matches carry
    start=end=None). Without this fallback, every quote from a non-corpus
    video (e.g. TqxxCYnAxo8 TEDxKC) reported not_found and would have been
    stripped as fabricated even though it is genuinely in the transcript.

    With video_id=None, scans every video in the corpus and returns the best
    match found anywhere — correct but O(corpus size), so callers who know
    the video_id (OKF frontmatter always has one) should pass it.
    """
    quote_tokens = normalise(quote).split()
    result: VerbatimResult = {
        "status": "not_found",
        "video_id": video_id,
        "start": None,
        "end": None,
        "score": 0.0,
    }
    if not quote_tokens:
        return result

    candidates = [video_id] if video_id else _all_video_ids(corpus_root)
    for vid in candidates:
        index = _token_index(vid, str(corpus_root))
        if not index:
            index = _transcript_token_index(vid)
        if not index:
            continue
        exact = _exact_match(index, quote_tokens)
        if exact:
            return {
                "status": "verbatim",
                "video_id": vid,
                "start": exact[0],
                "end": exact[1],
                "score": 1.0,
            }
        score, start, end = _best_partial_match(index, quote_tokens)
        if score > result["score"]:
            result = {
                "status": "partial" if score >= _PARTIAL_MATCH_THRESHOLD else "not_found",
                "video_id": vid,
                "start": start,
                "end": end,
                "score": score,
            }
    return result


def strip_fabricated_quotes(
    body: str,
    video_id: Optional[str],
    corpus_root: Path = CORPUS_ROOT,
    find_verbatim_fn=None,
) -> tuple[str, int]:
    """Remove any quoted string (>= MIN_QUOTE_WORDS words) that find_verbatim
    says is not verbatim in this video's transcript.

    Single shared implementation for both OKF write paths: the extractor
    (``backend/scripts/extract_okf_from_stores.py``, both tracked copies —
    kept as thin wrappers calling this) and the ``OKFStore.list_entries()``
    load-time gate (``okf_verbatim_quote_gate``). Do not fork this logic.

    Line-scoped: if removing the quote leaves nothing but blockquote/dash
    punctuation on that line, drops the whole line rather than leaving a
    bare "> " behind.

    ``find_verbatim_fn`` lets a caller inject a stand-in (the extractor
    wrappers pass their own module's ``find_verbatim`` so tests can
    monkeypatch it); defaults to this module's real ``find_verbatim``.
    """
    if not video_id:
        return body, 0
    _find = find_verbatim_fn or find_verbatim
    removed = 0

    def _check(match: re.Match[str]) -> str:
        nonlocal removed
        quote = match.group(1)
        if len(quote.split()) < MIN_QUOTE_WORDS:
            return match.group(0)
        result = _find(quote, video_id=video_id, corpus_root=corpus_root)
        # Only an exact transcript match may stand as the teacher's words; a
        # "partial" (~70% token overlap) is a paraphrase and is dropped too.
        if result["status"] != "verbatim":
            removed += 1
            logger.warning(
                "OKF: dropping non-verbatim quote (video_id=%s, status=%s, %d words): %s",
                video_id,
                result["status"],
                len(quote.split()),
                quote[:80],
            )
            return ""
        return match.group(0)

    kept_lines = []
    for line in body.splitlines():
        new_line = _QUOTED_STRING_RE.sub(_check, line)
        if new_line != line and not re.sub(r"[>\-—\s]", "", new_line):
            continue  # nothing left but blockquote/dash punctuation
        kept_lines.append(new_line)
    return "\n".join(kept_lines), removed


_REPETITION_MIN_WORDS = 20
_REPETITION_GRAM_LEN = 5
_REPETITION_MIN_COUNT = 4
_LOW_PUNCTUATION_THRESHOLD = 0.5


def per_video_checks(video_dir: Path) -> list[Finding]:
    """Structural checks over one video's canonical_segments.json.

    A "hard" finding means the transcript is unsafe to serve verbatim
    quotes from (empty, malformed timing, or a hallucination-shaped
    repetition loop) and should quarantine the video. "soft" findings are
    coverage gaps (missing verbatim/timestamp/confidence layers) that are
    worth tracking but don't block indexing on their own.
    """
    video_dir = Path(video_dir)
    seg_file = video_dir / "canonical_segments.json"
    if not seg_file.is_file():
        return [Finding("missing_segments_file", "hard", str(seg_file))]

    try:
        data = json.loads(seg_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [Finding("unreadable_segments_file", "hard", str(exc))]

    segments = data.get("segments", []) if isinstance(data, dict) else data
    if not segments:
        return [Finding("empty_segments", "hard", "canonical_segments.json has zero segments")]

    findings: list[Finding] = []

    recorded_hash = data.get("transcript_hash") if isinstance(data, dict) else None
    if recorded_hash:
        actual_hash = compute_verbatim_hash(segments)
        if actual_hash != recorded_hash:
            findings.append(
                Finding(
                    "transcript_hash_mismatch",
                    "hard",
                    f"recorded={recorded_hash} actual={actual_hash}",
                )
            )
    else:
        findings.append(
            Finding(
                "missing_transcript_hash", "soft", "canonical_segments.json has no transcript_hash"
            )
        )

    # Merkle Integrity Check: verify artifact_manifest.json if present
    manifest_file = video_dir / "artifact_manifest.json"
    if manifest_file.exists():
        try:
            m_data = json.loads(manifest_file.read_text(encoding="utf-8"))
            artifacts = m_data.get("artifacts") or {}
            for rel_path, art_info in artifacts.items():
                target_f = video_dir / rel_path
                if not target_f.exists():
                    findings.append(
                        Finding(
                            "missing_manifest_artifact",
                            "hard",
                            f"Manifest references missing {rel_path}",
                        )
                    )
                else:
                    expected_sha = art_info.get("sha256")
                    if expected_sha:
                        actual_sha = hashlib.sha256(target_f.read_bytes()).hexdigest()
                        if actual_sha != expected_sha:
                            findings.append(
                                Finding(
                                    "artifact_manifest_hash_mismatch",
                                    "hard",
                                    f"{rel_path}: expected={expected_sha[:16]} actual={actual_sha[:16]}",
                                )
                            )
        except Exception as exc:
            findings.append(Finding("unreadable_manifest", "soft", str(exc)))

    prev_end: Optional[float] = None
    text_parts: list[str] = []
    ended_properly = 0
    missing_verbatim = 0
    missing_word_ts = 0
    missing_confidence = 0

    for seg in segments:
        sid = seg.get("segment_id", "?")
        start, end = seg.get("start"), seg.get("end")
        if start is None or end is None or end < start:
            findings.append(Finding("negative_span", "hard", f"{sid}: start={start} end={end}"))
        elif prev_end is not None and start < prev_end:
            findings.append(
                Finding(
                    "unsorted_or_overlapping", "hard", f"{sid}: start={start} < prev_end={prev_end}"
                )
            )
        if end is not None:
            prev_end = end

        text = (seg.get("text") or "").strip()
        text_parts.append(text)
        if text.endswith((".", "!", "?")):
            ended_properly += 1
        if not seg.get("verbatim_text"):
            missing_verbatim += 1
        if not seg.get("word_timestamps") and not seg.get("words"):
            missing_word_ts += 1
        if seg.get("confidence") is None:
            missing_confidence += 1

    full_text = " ".join(text_parts)
    words = full_text.split()
    if len(words) >= _REPETITION_MIN_WORDS:
        # Detect only CONSECUTIVE back-to-back repeats of the same n-gram.
        # A single linear pass: compare each block to the immediately preceding one.
        for n in range(len(words) - _REPETITION_GRAM_LEN * _REPETITION_MIN_COUNT + 1):
            gram = tuple(w.lower() for w in words[n : n + _REPETITION_GRAM_LEN])
            consec = 1
            pos = n + _REPETITION_GRAM_LEN
            while pos + _REPETITION_GRAM_LEN <= len(words):
                if tuple(w.lower() for w in words[pos : pos + _REPETITION_GRAM_LEN]) == gram:
                    consec += 1
                    pos += _REPETITION_GRAM_LEN
                else:
                    break
            if consec >= _REPETITION_MIN_COUNT:
                gram_str = " ".join(gram)
                findings.append(
                    Finding(
                        "repetition_loop", "hard", f"'{gram_str}' repeats {consec}x consecutively"
                    )
                )
                break

    n_segs = len(segments)
    punctuation_rate = ended_properly / n_segs if n_segs else 1.0
    if punctuation_rate < _LOW_PUNCTUATION_THRESHOLD:
        findings.append(
            Finding(
                "low_punctuation_rate",
                "soft",
                f"only {punctuation_rate:.2f} of segments end with terminal punctuation",
            )
        )
    if missing_verbatim:
        findings.append(
            Finding(
                "missing_verbatim_layer",
                "soft",
                f"{missing_verbatim}/{n_segs} segments have no verbatim_text",
            )
        )
    if missing_word_ts == n_segs:
        findings.append(
            Finding("missing_word_timestamps", "soft", "no segment carries word-level timestamps")
        )
    if missing_confidence:
        findings.append(
            Finding(
                "missing_confidence",
                "soft",
                f"{missing_confidence}/{n_segs} segments have null confidence",
            )
        )

    return findings


def has_hard_failure(findings: list[Finding]) -> bool:
    return any(f.severity == "hard" for f in findings)


def compute_verbatim_hash(segments: list[dict]) -> str:
    """Deterministic sha256 over every segment's verbatim layer, in transcript
    order. Falls back to the display `text` for older corpora that predate
    the verbatim layer, so the hash is always computable, never a KeyError.
    """
    parts = [(seg.get("verbatim_text") or seg.get("text") or "") for seg in segments]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


if __name__ == "__main__":
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="transcript_verbatim_selfcheck_"))
    try:
        # ── find_verbatim: verbatim / partial / fabricated ──────────────
        good_video = tmp / "vidGOOD01"
        good_video.mkdir()
        (good_video / "canonical_segments.json").write_text(
            json.dumps(
                {
                    "video_id": "vidGOOD01",
                    "segments": [
                        {
                            "segment_id": "seg_0000",
                            "start": 0.0,
                            "end": 5.0,
                            "text": "Individual transformation is at the crux of our work.",
                            "verbatim_text": "Individual transformation is at the crux of our work.",
                            "confidence": None,
                        },
                        {
                            "segment_id": "seg_0001",
                            "start": 5.0,
                            "end": 9.0,
                            "text": "Don't wait for the world to change.",
                            "verbatim_text": "Don't wait for the world to change.",
                            "confidence": None,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        exact = find_verbatim(
            "Individual transformation is at the crux of our work.", "vidGOOD01", corpus_root=tmp
        )
        assert exact["status"] == "verbatim" and exact["score"] == 1.0, exact
        print(f"PASS verbatim match: {exact}")

        apostrophe = find_verbatim(
            "Dont wait for the world to change", "vidGOOD01", corpus_root=tmp
        )
        assert apostrophe["status"] == "verbatim", apostrophe
        print("PASS apostrophe-insensitive verbatim match")

        partial = find_verbatim(
            "Individual transformation is truly at the very crux of everyone's work.",
            "vidGOOD01",
            corpus_root=tmp,
        )
        assert partial["status"] == "partial", partial
        print(f"PASS partial match: score={partial['score']:.2f}")

        fabricated = find_verbatim(
            "The secret to eternal happiness is found only in silence and gold.",
            "vidGOOD01",
            corpus_root=tmp,
        )
        assert fabricated["status"] == "not_found", fabricated
        print("PASS fabricated quote not found")

        missing = find_verbatim("anything at all here", "NONEXISTENT", corpus_root=tmp)
        assert missing["status"] == "not_found" and missing["score"] == 0.0
        print("PASS missing video fails closed")

        # ── transcript-projection fallback (2026-10-03) ────────────────
        # video with NO corpus dir but a flat transcripts/<id>.md: genuine
        # quote must verify as verbatim (start=None, no guessed t=), while a
        # fabricated one must still fail closed.
        fake_tr = tmp / "transcripts"
        fake_tr.mkdir()
        (fake_tr / "vidTRANSCRIPT01.md").write_text(
            "The most important choice is from which state do we live our life.",
            encoding="utf-8",
        )
        _orig_tr_root = TRANSCRIPTS_ROOT
        TRANSCRIPTS_ROOT = fake_tr
        try:
            fb = find_verbatim(
                "the most important choice is from which state do we live our life",
                "vidTRANSCRIPT01",
                corpus_root=tmp,
            )
            assert fb["status"] == "verbatim" and fb["start"] is None, fb
            print(f"PASS transcript fallback verbatim with start=None: {fb}")
            fb_bad = find_verbatim(
                "This sentence was never spoken anywhere in any recording ever.",
                "vidTRANSCRIPT01",
                corpus_root=tmp,
            )
            assert fb_bad["status"] == "not_found", fb_bad
            print("PASS transcript fallback still fails fabricated quotes")
        finally:
            TRANSCRIPTS_ROOT = _orig_tr_root

        # ── per_video_checks: each defect class + a clean fixture ───────
        clean = tmp / "vidCLEAN"
        clean.mkdir()
        (clean / "canonical_segments.json").write_text(
            json.dumps(
                {
                    "segments": [
                        {
                            "segment_id": "seg_0000",
                            "start": 0.0,
                            "end": 4.0,
                            "text": "Welcome to Ekam.",
                            "verbatim_text": "Welcome to Ekam.",
                            "word_timestamps": [{"word": "Welcome", "start": 0.0, "end": 0.5}],
                            "confidence": -0.2,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        clean_findings = per_video_checks(clean)
        assert not has_hard_failure(clean_findings), clean_findings
        print(f"PASS clean fixture has no hard findings: {clean_findings}")

        empty = tmp / "vidEMPTY"
        empty.mkdir()
        (empty / "canonical_segments.json").write_text(
            json.dumps({"segments": []}), encoding="utf-8"
        )
        assert has_hard_failure(per_video_checks(empty))
        print("PASS empty_segments is a hard failure")

        negative = tmp / "vidNEG"
        negative.mkdir()
        (negative / "canonical_segments.json").write_text(
            json.dumps({"segments": [{"segment_id": "s0", "start": 5.0, "end": 2.0, "text": "x"}]}),
            encoding="utf-8",
        )
        neg_findings = per_video_checks(negative)
        assert any(f.check == "negative_span" for f in neg_findings)
        assert has_hard_failure(neg_findings)
        print("PASS negative_span is a hard failure")

        overlap = tmp / "vidOVERLAP"
        overlap.mkdir()
        (overlap / "canonical_segments.json").write_text(
            json.dumps(
                {
                    "segments": [
                        {"segment_id": "s0", "start": 0.0, "end": 10.0, "text": "First."},
                        {"segment_id": "s1", "start": 3.0, "end": 12.0, "text": "Second."},
                    ]
                }
            ),
            encoding="utf-8",
        )
        assert any(f.check == "unsorted_or_overlapping" for f in per_video_checks(overlap))
        print("PASS unsorted_or_overlapping detected")

        loop_text = "the beautiful state is here " * 5
        looped = tmp / "vidLOOP"
        looped.mkdir()
        (looped / "canonical_segments.json").write_text(
            json.dumps(
                {"segments": [{"segment_id": "s0", "start": 0.0, "end": 5.0, "text": loop_text}]}
            ),
            encoding="utf-8",
        )
        loop_findings = per_video_checks(looped)
        assert any(f.check == "repetition_loop" for f in loop_findings)
        assert has_hard_failure(loop_findings)
        print("PASS repetition_loop is a hard failure")

        soft_gaps = tmp / "vidSOFT"
        soft_gaps.mkdir()
        (soft_gaps / "canonical_segments.json").write_text(
            json.dumps(
                {
                    "segments": [
                        {
                            "segment_id": "s0",
                            "start": 0.0,
                            "end": 5.0,
                            "text": "no ending punctuation here",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        soft_findings = per_video_checks(soft_gaps)
        assert not has_hard_failure(soft_findings), soft_findings
        soft_checks = {f.check for f in soft_findings}
        assert {
            "low_punctuation_rate",
            "missing_verbatim_layer",
            "missing_word_timestamps",
            "missing_confidence",
        } <= soft_checks
        print(f"PASS soft-only findings: {sorted(soft_checks)}")

        missing_file = tmp / "vidNOFILE"
        missing_file.mkdir()
        assert has_hard_failure(per_video_checks(missing_file))
        print("PASS missing segments file fails closed (hard)")

        # ── transcript_hash: matching / missing / mismatched ─────────────
        hash_segs = [
            {
                "segment_id": "s0",
                "start": 0.0,
                "end": 4.0,
                "text": "Welcome to Ekam.",
                "verbatim_text": "Welcome to Ekam.",
            }
        ]
        good_hash = compute_verbatim_hash(hash_segs)

        hashed = tmp / "vidHASHOK"
        hashed.mkdir()
        (hashed / "canonical_segments.json").write_text(
            json.dumps({"transcript_hash": good_hash, "segments": hash_segs}), encoding="utf-8"
        )
        assert not has_hard_failure(per_video_checks(hashed))
        print("PASS matching transcript_hash has no hard findings")

        mismatched = tmp / "vidHASHBAD"
        mismatched.mkdir()
        (mismatched / "canonical_segments.json").write_text(
            json.dumps({"transcript_hash": "deadbeef", "segments": hash_segs}), encoding="utf-8"
        )
        mismatch_findings = per_video_checks(mismatched)
        assert any(f.check == "transcript_hash_mismatch" for f in mismatch_findings)
        assert has_hard_failure(mismatch_findings)
        print("PASS transcript_hash_mismatch is a hard failure")

        print("\nAll backend/services/transcript_verbatim.py self-checks passed.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
