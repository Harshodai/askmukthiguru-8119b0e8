"""Chunk provenance classification — what kind of text a retrieved chunk actually is.

The problem this exists for: retrieval treats an LLM-written RAPTOR summary
paragraph ("The transition from 'I-consciousness' to 'One Consciousness'
reveals...") as equivalent evidence to the guru's own transcribed words. It
isn't — one is doctrine, the other is a machine's book report on doctrine.
This module gives every chunk a deterministic origin label so retrieval (and
anything else) can tell them apart, without re-embedding or re-chunking the
corpus (see backend/CLAUDE.md — no re-ingestion in scope).

ponytail: classification is payload-only (raptor_level, content_type,
source_type, speaker/channel_name) plus one cheap regex over already-fetched
text. No LLM call, no new ingest pass — reuses fields teacher_attribution.py
already established as the per-chunk metadata surface.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ChunkProvenance(str, Enum):
    """Where a chunk's text actually came from."""

    VERBATIM_SPEECH = "verbatim_speech"  # transcribed guru discourse (the default for the corpus)
    POLISHED_SPEECH = "polished_speech"  # guru-authored/edited published prose (e.g. the book)
    THIRD_PARTY_PROSE = "third_party_prose"  # coverage/commentary ABOUT the gurus, not BY them
    MACHINE_SUMMARY = "machine_summary"  # LLM-written RAPTOR summary paragraph
    JUNK = (
        "junk"  # extraction artifact / off-topic scrape noise that should never have been indexed
    )


# Channels whose content is commentary/coverage of the gurus, not the gurus'
# own words. Extend this set if another non-doctrine channel turns up in a
# future (non-re-ingested) source — see backend/ingest/quality_gate.py, which
# uses the same set to reject this class of content at ingest time.
THIRD_PARTY_CHANNELS: frozenset[str] = frozenset({"times now"})

# Deterministic patterns for artifacts that leaked into the index instead of
# being filtered at ingest time: LLM refusals, meta-commentary about the
# extraction task itself, and other tells that the "content" is actually
# machine chatter about failing to produce content.
_JUNK_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"cannot be situated within the document", re.IGNORECASE),
    re.compile(r"the user wants me to analyze", re.IGNORECASE),
    re.compile(r"as an ai language model", re.IGNORECASE),
    re.compile(r"i cannot provide (?:that|this) (?:information|content)", re.IGNORECASE),
    re.compile(r"i'm sorry,? but i can'?t", re.IGNORECASE),
)


def is_junk_text(text: str) -> bool:
    """Cheap regex check for known ingestion artifacts (LLM refusals, meta-commentary)."""
    if not text:
        return False
    return any(pattern.search(text) for pattern in _JUNK_PATTERNS)


def is_third_party_channel(speaker: str = "", channel_name: str = "") -> bool:
    """True when the attributed channel is known commentary/coverage, not the gurus."""
    channel = (channel_name or speaker or "").strip().casefold()
    return channel in THIRD_PARTY_CHANNELS


class ProvenanceResult(BaseModel):
    """Classification result for a single chunk, plus the signal it fired on."""

    provenance: ChunkProvenance
    rationale: str = Field(description="Which payload signal decided the classification")


def classify_chunk_provenance(
    *,
    raptor_level: Optional[int] = None,
    content_type: str = "",
    source_type: str = "",
    speaker: str = "",
    channel_name: str = "",
    text: str = "",
) -> ProvenanceResult:
    """Deterministically classify a chunk's origin from already-stored payload fields.

    Order matters: junk and machine-summary are unambiguous and checked
    first; third-party channel is checked before defaulting to guru speech;
    everything else defaults to verbatim speech, because the corpus is
    verified 100% Sri Preethaji & Sri Krishnaji teachings (backend/CLAUDE.md's
    2026-09-13 teacher_id backfill note) — most chunks simply lack an
    explicit `speaker`/`channel_name` and that is a missing-attribution gap,
    not evidence the content isn't theirs.
    """
    if is_junk_text(text):
        return ProvenanceResult(provenance=ChunkProvenance.JUNK, rationale="junk_text_pattern")

    if raptor_level == 1 or content_type == "summary":
        return ProvenanceResult(
            provenance=ChunkProvenance.MACHINE_SUMMARY,
            rationale="raptor_level_1_or_content_type_summary",
        )

    if is_third_party_channel(speaker, channel_name):
        channel = (channel_name or speaker or "").strip().casefold()
        return ProvenanceResult(
            provenance=ChunkProvenance.THIRD_PARTY_PROSE, rationale=f"third_party_channel:{channel}"
        )

    if source_type == "book":
        return ProvenanceResult(
            provenance=ChunkProvenance.POLISHED_SPEECH, rationale="source_type_book"
        )

    return ProvenanceResult(
        provenance=ChunkProvenance.VERBATIM_SPEECH, rationale="default_guru_transcript"
    )


if __name__ == "__main__":
    # ponytail: a runnable self-check instead of a separate pytest fixture file.
    r = classify_chunk_provenance(raptor_level=1, content_type="summary")
    assert r.provenance == ChunkProvenance.MACHINE_SUMMARY, r

    r = classify_chunk_provenance(raptor_level=0, source_type="video", channel_name="Times Now")
    assert r.provenance == ChunkProvenance.THIRD_PARTY_PROSE, r

    r = classify_chunk_provenance(raptor_level=0, source_type="book")
    assert r.provenance == ChunkProvenance.POLISHED_SPEECH, r

    r = classify_chunk_provenance(
        raptor_level=0, text="As an AI language model, I cannot provide this information."
    )
    assert r.provenance == ChunkProvenance.JUNK, r

    r = classify_chunk_provenance(
        raptor_level=0, source_type="video", channel_name="Unknown Channel"
    )
    assert r.provenance == ChunkProvenance.VERBATIM_SPEECH, r

    assert is_junk_text("The Magnificent black bird will do this for the entire summer.") is False
    assert is_junk_text("Therefore, it cannot be situated within the document's context.") is True

    print("OK: provenance classification self-check passed")
