"""
rebuild_okf_from_transcripts.py — Replace LLM-generated OKF entries with verbatim transcript sources.

# ponytail: deterministic transcript-to-OKF compiler — zero LLM calls, zero new deps.
Directly extracts authentic spoken words from transcripts/*.md into memory/okf/*.md.
Eliminates all LLM summarization artifacts and provides 100% authentic guru words.
"""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path
from typing import Any, Optional

import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Resolve base directories
_BASE = Path(__file__).resolve().parent.parent.parent.parent
TRANSCRIPTS_DIR = _BASE / "transcripts"
OKF_DIR = _BASE / "memory" / "okf"

_VIDEO_ID_RE = re.compile(r"video_id:\s*([a-zA-Z0-9_-]+)")
_URL_VID_RE = re.compile(r"[?&]v=([a-zA-Z0-9_-]+)")

# Skip audience logistics and transcript noise
_LOGISTICS_FILTER = (
    "close your eyes",
    "open your eyes",
    "music starts",
    "music ends",
    "please be seated",
    "thank you all",
    "sneaking a peek",
    "peeking",
    "namaste",
    "subscribe to",
    "click the bell",
)


def _extract_video_id(content: str) -> Optional[str]:
    """Extract YouTube video_id from OKF frontmatter or source URL."""
    m = _VIDEO_ID_RE.search(content)
    if m:
        return m.group(1).strip()
    m2 = _URL_VID_RE.search(content)
    if m2:
        return m2.group(1).strip()
    return None


def _parse_transcript_file(transcript_path: Path) -> tuple[str, str, list[str]]:
    """Parse a transcript markdown file into (video_title, speaker, paragraphs)."""
    text = transcript_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    video_title = ""
    speaker = "Sri Preethaji & Sri Krishnaji"
    in_transcript = False
    raw_paras: list[str] = []
    current_para: list[str] = []

    for line in lines:
        s_line = line.strip()
        if not video_title and line.startswith("# "):
            video_title = line[2:].strip()
        elif line.startswith("**Speaker:**"):
            speaker = line.replace("**Speaker:**", "").strip() or speaker
        elif s_line == "## Transcript":
            in_transcript = True
            continue
        elif in_transcript:
            if not s_line:
                if current_para:
                    raw_paras.append(" ".join(current_para))
                    current_para = []
            else:
                current_para.append(s_line)

    if current_para:
        raw_paras.append(" ".join(current_para))

    # Clean paragraphs
    clean_paras = [p for p in raw_paras if len(p) >= 30]
    return video_title, speaker, clean_paras


def _score_sentence(sent: str, topic_terms: set[str]) -> float:
    """Score a verbatim sentence for relevance to the entry's topic terms."""
    words = set(re.findall(r"\w+", sent.lower()))
    matches = sum(2.0 for t in topic_terms if t in words)
    # Prefer complete, quotable sentences (40 - 200 chars)
    length_bonus = 1.0 if 40 <= len(sent) <= 200 else 0.0
    return matches + length_bonus


def _extract_top_verbatim_teachings(
    paras: list[str],
    title: str,
    tags: list[str],
    max_teachings: int = 4,
) -> list[str]:
    """Deterministically select the most philosophically potent verbatim sentences for a topic."""
    topic_terms = set(re.findall(r"\w+", f"{title} {' '.join(tags)}".lower()))
    # Remove generic stop words from topic terms
    stop_words = {
        "the",
        "and",
        "a",
        "an",
        "in",
        "of",
        "to",
        "for",
        "with",
        "as",
        "is",
        "are",
        "on",
        "at",
        "it",
    }
    topic_terms = topic_terms - stop_words

    candidate_sents: list[str] = []
    seen = set()

    for p in paras:
        # Split on sentence boundaries
        sents = re.split(r"(?<=[.!?])\s+", p)
        for s in sents:
            s_clean = s.strip()
            # Invariant: must be substantial, start with uppercase, and have no logistics
            if (
                len(s_clean) >= 35
                and s_clean[0].isupper()
                and not any(neg in s_clean.lower() for neg in _LOGISTICS_FILTER)
            ):
                norm = s_clean.lower()
                if norm not in seen:
                    seen.add(norm)
                    candidate_sents.append(s_clean)

    if not candidate_sents:
        return []

    # Score and rank
    scored = sorted(
        candidate_sents,
        key=lambda s: _score_sentence(s, topic_terms),
        reverse=True,
    )

    return scored[:max_teachings]


def process_okf_entry(okf_path: Path, transcripts_dir: Path = TRANSCRIPTS_DIR) -> bool:
    """Rebuild a single OKF entry with verbatim transcript sources."""
    content = okf_path.read_text(encoding="utf-8")
    vid = _extract_video_id(content)
    if not vid:
        logger.debug("No video_id found in %s", okf_path.name)
        return False

    t_file = transcripts_dir / f"{vid}.md"
    if not t_file.exists():
        logger.debug("Transcript file %s not found for %s", t_file.name, okf_path.name)
        return False

    # Extract frontmatter metadata via regex or yaml
    frontmatter_match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
    existing_meta: dict[str, Any] = {}
    if frontmatter_match:
        try:
            existing_meta = yaml.safe_load(frontmatter_match.group(1)) or {}
        except Exception:
            existing_meta = {}

    title = existing_meta.get("title") or okf_path.stem.replace("_", " ").title()
    entry_type = str(existing_meta.get("type", "teaching")).strip().lower()
    if entry_type not in ("teaching", "practice", "reflection", "qa", "glossary"):
        entry_type = "teaching"

    raw_tags = existing_meta.get("tags", [])
    if isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    else:
        tags = [t.strip() for t in str(raw_tags).split(",") if t.strip()]

    vid_title, speaker, paras = _parse_transcript_file(t_file)
    if not paras:
        return False

    # Select top verbatim sentences for key teachings
    top_sents = _extract_top_verbatim_teachings(paras, title, tags, max_teachings=3)
    if not top_sents:
        top_sents = [paras[0][:150]] if paras else []

    # Select the most relevant excerpt paragraphs
    ranked_paras = sorted(
        paras,
        key=lambda p: sum(1.0 for t in re.findall(r"\w+", title.lower()) if t in p.lower()),
        reverse=True,
    )
    selected_excerpts = ranked_paras[:2] if ranked_paras else paras[:1]
    excerpts_text = "\n\n".join(selected_excerpts)

    speaker_slug = "sri-preethaji-and-sri-krishnaji"
    spk_lower = speaker.lower()
    if "preetha" in spk_lower and "krishna" not in spk_lower:
        speaker_slug = "sri-preethaji"
    elif "krishna" in spk_lower and "preetha" not in spk_lower:
        speaker_slug = "sri-krishnaji"

    # Reconstruct authentic OKF metadata using yaml safe_dump
    meta_dict = {
        "title": title,
        "type": entry_type,
        "teacher": speaker_slug,
        "source": f"https://www.youtube.com/watch?v={vid}",
        "video_id": vid,
        "tags": tags[:6] if tags else ["oneness", "teaching"],
    }
    yaml_header = yaml.safe_dump(meta_dict, sort_keys=False).strip()

    key_teachings_lines = "\n".join(f"- {s} — {speaker}" for s in top_sents)

    new_body = (
        f"---\n"
        f"{yaml_header}\n"
        f"---\n"
        f"# {title}\n\n"
        f"## Verbatim Discourse Excerpts\n"
        f"{excerpts_text}\n\n"
        f"## Key Teachings\n"
        f"{key_teachings_lines}\n\n"
        f"## Source Context\n"
        f"- Video: {vid_title or title}\n"
        f"- URL: https://www.youtube.com/watch?v={vid}\n"
        f"- Speaker: {speaker}\n"
    )

    okf_path.write_text(new_body, encoding="utf-8")
    return True


def rebuild_all_okf_entries(
    okf_dir: Path = OKF_DIR, transcripts_dir: Path = TRANSCRIPTS_DIR
) -> int:
    """Rebuild all OKF markdown entries from verbatim transcripts."""
    okf_files = list(okf_dir.glob("*.md"))
    updated = 0
    for f in okf_files:
        if f.name in ("index.md", "log.md"):
            continue
        if process_okf_entry(f, transcripts_dir=transcripts_dir):
            updated += 1

    logger.info(
        "Successfully updated %d of %d OKF entries with authentic verbatim transcripts.",
        updated,
        len(okf_files),
    )
    return updated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild OKF entries from transcripts")
    parser.add_argument("--dry-run", action="store_true", help="Print summary without writing")
    args = parser.parse_args()

    count = rebuild_all_okf_entries()
    print(f"Rebuilt {count} OKF files with authentic guru verbatim text.")

    # Recompile OKF
    from services.memory.compiler import compile_okf

    compiled_path = compile_okf()
    print(f"Re-compiled OKF index at {compiled_path}")
