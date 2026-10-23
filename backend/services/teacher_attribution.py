"""Teacher Attribution Resolver.

Single source of truth for resolving spiritual teacher attribution across
the AskMukthiGuru ingestion and retrieval pipelines.

Root-cause fix (2026-09-24): the corpus is Sri Preethaji & Sri Krishnaji
(Ekam / O&O Academy) ONLY. No Sadhguru, ISKCON, or Amma Bhagavan talks exist
in it. Prior versions of this function (and its origin, commit 56c31438)
let a text MENTION of another teacher's name inside a transcript override the
SPEAKER, which mis-tagged 3,121 points as belonging to external teachers
(triggered by "digital"/"Krishnaji" containing "gita"/"krishna", "Mahishasura"
containing "isha", and "oneness"/"amma"(-in-"grammar")/"deeksha" mapped to
Amma Bhagavan).

Invariants & Doctrinal Architecture
------------------------------------
1. Identity comes from the SOURCE, never from the transcript body:
   title, speaker/channel metadata, source_url, and an explicit allowlist
   (`EXTERNAL_TEACHER_SOURCE_REGISTRY`). A word appearing in what someone
   said is not evidence of who is speaking.
2. Lineage & Co-Creation: Sri Preethaji and Sri Krishnaji are the founders
   of Ekam (O&O Academy) and co-authors of 'The Four Sacred Secrets'.
   `attributed_teacher_ids` retains both gurus so seeker queries draw on the
   full shared body of teachings, while `primary_teacher_id` records the
   specific discourse speaker when the source clearly names one.
3. An external teacher (sadhguru / amma_bhagavan / iskcon) can be the
   PRIMARY attribution only for a source explicitly registered as theirs in
   `EXTERNAL_TEACHER_SOURCE_REGISTRY` (empty by default -- nothing in this
   corpus is registered). A mention of their name anywhere -- title, speaker,
   URL, or transcript -- produces only a `mentions:<teacher>` tag: it is
   never a `teacher:` tag, never sets `teacher_id`, and never filters.
4. Matching is whole-word with tight boundaries on the teacher's own name.
   "isha", "amma", "oneness", "deeksha", "gita", and bare "krishna" are
   dropped entirely -- they are the teachers' own vocabulary or substrings
   of it, and even as whole words they are common enough (a person named
   Isha, "Kalki" as a title, "Krishna" as the Gita's speaker) to misfire.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from services.guru_registry import (
    attribution_tag_for,
    get_gurus,
    match_organization,
    requested_gurus,
    shared_attribution,
)

logger = logging.getLogger(__name__)

# Sources explicitly verified to be an external teacher's own content.
# Empty by default: no source in this corpus is registered here. Add an
# entry only after confirming the SOURCE (not a text mention) is genuinely
# that teacher's own channel/video -- key is the lowercased, stripped
# source_url, value is the teacher id ("sadhguru" | "amma_bhagavan" | "iskcon").
EXTERNAL_TEACHER_SOURCE_REGISTRY: dict[str, str] = {}

# Identity aliases and organization names are sourced only from gurus.yaml.
# They match source metadata (title/speaker/source_url), never transcript text.

# Mention signals: matched against title/speaker/source_url/transcript, and
# only ever produce a `mentions:<teacher>` tag -- never identity.
_MENTION_PATTERNS: dict[str, re.Pattern] = {
    "sadhguru": re.compile(r"\b(?:sadhguru|jaggi\s+vasudev)\b", re.IGNORECASE),
    "amma_bhagavan": re.compile(
        r"\b(?:sri\s+amma\s+bhagavan|amma\s+bhagavan|kalki\s+bhagavan)\b", re.IGNORECASE
    ),
    "iskcon": re.compile(r"\b(?:iskcon|prabhupada|krishna\s+consciousness)\b", re.IGNORECASE),
}


def resolve_teacher_attribution(
    source_url: str,
    title: str = "",
    speaker: str = "",
    chunks: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
) -> tuple[list[str], str, list[str]]:
    """Deterministically resolves the primary and attributed teacher IDs.

    Identity is source-based only (title/speaker/source_url + the explicit
    external-teacher registry). Transcript content (`chunks`) is scanned only
    for `mentions:<teacher>` bookkeeping tags and never affects identity.

    Parameters:
        title (str): The discourse or video title.
        source_url (str): Source URL (e.g., YouTube video link).
        speaker (str): Speaker or channel metadata.
        chunks (List[str]): Initial transcript chunks (mention-scan only).
        tags (Optional[List[str]]): Unused for identity; accepted for call
            signature compatibility with existing callers.

    Returns:
        Tuple[List[str], str, List[str]]:
            - teacher_tags (list[str]): Clean `teacher:`/`mentions:` tags.
            - primary_teacher_id (str): Primary keyword identifier for strict indexing.
            - attributed_teacher_ids (list[str]): Comprehensive list of attributed teachers.
    """
    del tags  # not an identity signal -- see module docstring, invariant 1

    clean_url = (source_url or "").strip()
    source_context = " ".join([title or "", speaker or "", clean_url])
    mention_context = " ".join([source_context] + list((chunks or [])[:3]))

    teacher_tags: list[str] = [
        f"mentions:{t}" for t, p in _MENTION_PATTERNS.items() if p.search(mention_context)
    ]

    registered = EXTERNAL_TEACHER_SOURCE_REGISTRY.get(clean_url.lower())
    if registered:
        return [f"teacher:{registered}"] + teacher_tags, registered, [registered]

    shared_primary, shared_ids = shared_attribution()
    matched_ids = requested_gurus(source_context)

    if matched_ids:
        # Preserve configured shared-lineage behavior. A teacher outside the
        # shared set remains independently attributable by its canonical ID.
        if shared_primary and shared_ids and set(matched_ids).issubset(set(shared_ids)):
            primary_id = shared_primary if len(matched_ids) > 1 else matched_ids[0]
            attributed_ids = shared_ids
        else:
            primary_id = matched_ids[0]
            attributed_ids = matched_ids
        tags = [tag for guru_id in matched_ids if (tag := attribution_tag_for(guru_id))]
        return tags + teacher_tags, primary_id, attributed_ids

    organization = match_organization(source_context)
    if organization:
        org_id = str(organization.get("id") or "").strip().lower()
        org_primary = str(organization.get("primary_teacher_id") or org_id).strip().lower()
        org_tag = str(organization.get("attribution_tag") or f"teacher:{org_id}")
        org_attributed = organization.get("attributed_teacher_ids") or shared_ids
        known_ids = {guru.id for guru in get_gurus()}
        if (
            org_id
            and org_primary
            and isinstance(org_attributed, list)
            and all(str(value).lower() in known_ids for value in org_attributed)
        ):
            return (
                [org_tag] + teacher_tags,
                org_primary,
                [str(value).lower() for value in org_attributed],
            )

    # The shared-corpus defaults are configuration, not a hardcoded teacher list.
    # If the registry is unavailable, return no identity rather than invent one.
    if shared_primary and shared_ids:
        return teacher_tags, shared_primary, shared_ids
    logger.error("Teacher attribution skipped because shared registry config is incomplete")
    return teacher_tags, "", []


if __name__ == "__main__":
    # ponytail: smallest runnable self-check, not a full suite (see
    # tests/test_teacher_attribution.py for the real coverage)
    assert resolve_teacher_attribution("u1", title="digital platforms")[1] == "preethaji_krishnaji"
    assert (
        "teacher:sadhguru"
        not in resolve_teacher_attribution("u2", title="the demon Mahishasura")[0]
    )
    tags, tid, ids = resolve_teacher_attribution("u3", title="Talk", speaker="Sri Krishnaji")
    assert tid == "krishnaji" and "preethaji" in ids
    tags, tid, ids = resolve_teacher_attribution(
        "u4", title="Preethaji on Suffering", chunks=["Sadhguru once said something similar."]
    )
    assert tid == "preethaji" and "mentions:sadhguru" in tags
    EXTERNAL_TEACHER_SOURCE_REGISTRY["https://example.com/sadhguru-talk"] = "sadhguru"
    tags, tid, ids = resolve_teacher_attribution("https://example.com/sadhguru-talk")
    assert tid == "sadhguru"
    del EXTERNAL_TEACHER_SOURCE_REGISTRY["https://example.com/sadhguru-talk"]
    print("teacher_attribution self-check OK")
