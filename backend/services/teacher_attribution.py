"""Teacher Attribution Resolver.

Single source of truth for resolving spiritual teacher attribution across
the AskMukthiGuru ingestion and retrieval pipelines.

Invariants & Doctrinal Architecture:
------------------------------------
1. Lineage & Co-Creation:
   Sri Preethaji and Sri Krishnaji are the founders and spiritual guides of Ekam
   (O&O Academy) and co-authors of 'The Four Sacred Secrets'. All discourses across
   this corpus belong to their shared spiritual body of teachings.
   Therefore, `attributed_teacher_ids` retains both gurus (["preethaji", "krishnaji"])
   so that seeker queries addressed to Mukthi Guru draw freely upon all teachings,
   while `primary_teacher_id` records the specific discourse speaker.

2. Prevention of Misattribution:
   - Substring matches (e.g. "amma" in "inflammation", "krishna" in "krishnaji",
     or "oneness"/"deeksha" mapped to external lineages) are strictly prohibited.
   - Strict regex word boundaries (`\\b`) ensure only genuine, explicit teacher mentions
     trigger attribution.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def resolve_teacher_attribution(
    source_url: str,
    title: str = "",
    speaker: str = "",
    chunks: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
) -> Tuple[List[str], str, List[str]]:
    """Deterministically resolves the primary and attributed teacher IDs.

    Uses strict word boundaries and context hierarchy:
    1. Direct whole-word title/speaker references.
    2. Explicit non-ambiguous tags.
    3. Ekam / O&O Academy shared corpus defaults.

    Parameters:
        title (str): The discourse or video title.
        source_url (str): Source URL (e.g., YouTube video link).
        speaker (str): Speaker or channel metadata.
        chunks (List[str]): Initial transcript chunks (for context inspection).
        tags (Optional[List[str]]): Source metadata tags or category tags.

    Returns:
        Tuple[List[str], str, List[str]]:
            - teacher_tags (list[str]): Clean tags for indexing.
            - primary_teacher_id (str): Primary keyword identifier for strict indexing.
            - attributed_teacher_ids (list[str]): Comprehensive list of attributed teachers.
    """
    clean_title = (title or "").strip()
    clean_speaker = (speaker or "").strip()
    clean_url = (source_url or "").strip()
    clean_tags = [t.lower().strip() for t in (tags or [])]

    combined_parts = [clean_title, clean_url, clean_speaker]
    if chunks:
        combined_parts.extend(chunks[:3])
    combined_context = " ".join(combined_parts).lower()

    teacher_tags: List[str] = []
    primary_teacher_id = "ekam"
    attributed_teacher_ids: List[str] = ["preethaji", "krishnaji"]

    # Strict whole-word regex checks for external teachers
    has_sadhguru = bool(re.search(r"\b(?:sadhguru|jaggi|vasudev|isha)\b", combined_context, re.IGNORECASE))
    has_amma_bhagavan = bool(
        re.search(
            r"\b(?:sri\s+amma\s+bhagavan|amma\s+bhagavan|kalki\s+bhagavan|kalki)\b",
            combined_context,
            re.IGNORECASE,
        )
    )
    has_iskcon = bool(
        re.search(r"\b(?:iskcon|prabhupada|krishna\s+consciousness)\b", combined_context, re.IGNORECASE)
    )

    if has_sadhguru:
        teacher_tags.append("teacher:sadhguru")
        primary_teacher_id = "sadhguru"
        attributed_teacher_ids = ["sadhguru"]
    elif has_amma_bhagavan:
        teacher_tags.append("teacher:amma_bhagavan")
        primary_teacher_id = "amma_bhagavan"
        attributed_teacher_ids = ["amma_bhagavan"]
    elif has_iskcon:
        teacher_tags.append("teacher:iskcon")
        primary_teacher_id = "iskcon"
        attributed_teacher_ids = ["iskcon"]
    else:
        # Core Ekam lineage checks
        has_preethaji = bool(
            re.search(r"\b(?:preethaji|prithaji|sri\s+preetha|preetha\s*ji)\b", combined_context, re.IGNORECASE)
        )
        has_krishnaji = bool(
            re.search(r"\b(?:krishnaji|sri\s+krishna|krishna\s*ji|srikrishnaji)\b", combined_context, re.IGNORECASE)
        )

        if has_preethaji and has_krishnaji:
            teacher_tags.extend(["teacher:sri_preethaji", "teacher:sri_krishnaji"])
            primary_teacher_id = "preethaji_krishnaji"
            attributed_teacher_ids = ["preethaji", "krishnaji"]
        elif has_preethaji:
            teacher_tags.append("teacher:sri_preethaji")
            primary_teacher_id = "preethaji"
            attributed_teacher_ids = ["preethaji", "krishnaji"]
        elif has_krishnaji:
            teacher_tags.append("teacher:sri_krishnaji")
            primary_teacher_id = "krishnaji"
            attributed_teacher_ids = ["krishnaji", "preethaji"]
        else:
            # Fallback to category / tag checks
            tag_preethaji = any(
                t in ("category:sri_preethaji", "sri preethaji", "teacher:sri_preethaji", "teacher:preethaji")
                for t in clean_tags
            )
            tag_krishnaji = any(
                t in ("category:sri_krishnaji", "sri krishnaji", "teacher:sri_krishnaji", "teacher:krishnaji")
                for t in clean_tags
            )

            if tag_preethaji and tag_krishnaji:
                teacher_tags.extend(["teacher:sri_preethaji", "teacher:sri_krishnaji"])
                primary_teacher_id = "preethaji_krishnaji"
            elif tag_preethaji:
                teacher_tags.append("teacher:sri_preethaji")
                primary_teacher_id = "preethaji"
            elif tag_krishnaji:
                teacher_tags.append("teacher:sri_krishnaji")
                primary_teacher_id = "krishnaji"
            else:
                teacher_tags.append("teacher:ekam")
                primary_teacher_id = "ekam"

            attributed_teacher_ids = ["preethaji", "krishnaji"]

    return teacher_tags, primary_teacher_id, attributed_teacher_ids
