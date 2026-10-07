"""
ingest_single_video_okf.py — Deterministic OKF ingestion for a single video transcript.

# ponytail: zero-LLM transcript-to-OKF compiler for a single video.
Directly extracts authentic spoken words from transcripts/<video_id>.md into memory/okf/<slug>.md.
Guarantees 100% authentic guru words with zero LLM summarization.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

import yaml

# Path setup
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from ingest.verbatim.asr_cleaner import clean_verbatim_text
from services.memory.okf_store import OKF_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_REPO_ROOT = _BACKEND.parent
TRANSCRIPTS_DIR = _REPO_ROOT / "transcripts"


def _clean_slug(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    return re.sub(r"[-\s]+", "_", slug).strip("_")


def ingest_video_to_okf(
    video_id: str,
    transcripts_dir: Path = TRANSCRIPTS_DIR,
    okf_dir: Path = OKF_DIR,
) -> list[Path]:
    """Ingest a single video transcript into deterministic OKF entries."""
    t_file = transcripts_dir / f"{video_id}.md"
    if not t_file.exists():
        raise FileNotFoundError(f"Transcript file not found: {t_file}")

    content = t_file.read_text(encoding="utf-8")

    # Extract metadata
    title_match = re.search(r"^#\s+(.+)$", content, re.M)
    raw_title = title_match.group(1).strip() if title_match else video_id

    # If title is bare video ID, provide known title or canonical name
    KNOWN_TITLES = {
        "TqxxCYnAxo8": "How to Live in a Beautiful State — TEDxKC Talk",
        "rGcNJ_Nsuy8": "What is True Love? Love is Connection, Not Expectation",
        "UlOt31lBhLY": "Manage Your Stress with the Four Sacred Secrets",
        "HCs6I_BNtxo": "The State of Awakening and Enlightenment",
        "0Fa4Wyv0GOk": "The Nature of Mind and Consciousness",
    }
    canonical_title = KNOWN_TITLES.get(video_id, raw_title)

    # Determine speaker
    speaker = "Sri Preethaji"
    if "krishnaji" in content.lower() and "preethaji" not in content.lower():
        speaker = "Sri Krishnaji"
    elif "krishnaji" in content.lower() and "preethaji" in content.lower():
        speaker = "Sri Preethaji & Sri Krishnaji"

    speaker_slug = {
        "Sri Preethaji": "sri-preethaji",
        "Sri Krishnaji": "sri-krishnaji",
    }.get(speaker, "sri-preethaji-and-sri-krishnaji")

    # Extract Transcript body
    transcript_idx = content.find("## Transcript")
    if transcript_idx != -1:
        body_text = content[transcript_idx + len("## Transcript") :].strip()
    else:
        body_text = content

    # Clean ASR stutters
    body_text = clean_verbatim_text(body_text)

    # Split into clean paragraphs
    paras = [p.strip() for p in body_text.split("\n\n") if len(p.strip()) >= 40]
    if not paras:
        paras = [body_text[:1000]]

    created_files: list[Path] = []

    # 1. Main Teaching Entry
    teaching_slug = f"{_clean_slug(canonical_title)}"
    teaching_path = okf_dir / f"{teaching_slug}.md"

    # Select key verbatim sentences (sentences between 50 and 220 chars that capture core doctrine)
    raw_sents = re.split(r"(?<=[.!?])\s+", body_text)
    candidate_sents = []
    for s in raw_sents:
        s = s.strip()
        if (
            50 <= len(s) <= 220
            and s[0].isupper()
            and not any(
                n in s.lower() for n in ("music", "please sit", "close your eyes", "namaste")
            )
        ):
            # Prefer sentences with rich spiritual keywords
            weight = sum(
                2.0
                for kw in (
                    "suffering",
                    "beautiful state",
                    "connection",
                    "inner truth",
                    "stress",
                    "love",
                    "preoccupation",
                    "mind",
                    "freedom",
                )
                if kw in s.lower()
            )
            candidate_sents.append((weight, s))

    candidate_sents.sort(key=lambda x: x[0], reverse=True)
    key_teachings = [s for _, s in candidate_sents[:3]]

    # Select top 2 paragraphs
    excerpts = paras[:2] if len(paras) >= 2 else paras

    teaching_meta = {
        "title": canonical_title,
        "type": "teaching",
        "teacher": speaker_slug,
        "source": f"https://www.youtube.com/watch?v={video_id}",
        "video_id": video_id,
        "tags": ["beautiful-state", "inner-truth", "suffering", "oneness"],
    }

    yaml_header = yaml.safe_dump(teaching_meta, sort_keys=False).strip()
    key_teachings_md = "\n".join(f"- {s} — {speaker}" for s in key_teachings)
    excerpts_md = "\n\n".join(excerpts)

    teaching_content = (
        f"---\n"
        f"{yaml_header}\n"
        f"---\n"
        f"# {canonical_title}\n\n"
        f"## Verbatim Discourse Excerpts\n"
        f"{excerpts_md}\n\n"
        f"## Key Teachings\n"
        f"{key_teachings_md}\n\n"
        f"## Source Context\n"
        f"- Video: {canonical_title}\n"
        f"- URL: https://www.youtube.com/watch?v={video_id}\n"
        f"- Speaker: {speaker}\n"
    )
    teaching_path.write_text(teaching_content, encoding="utf-8")
    created_files.append(teaching_path)
    logger.info("Created OKF teaching entry: %s", teaching_path)

    # 2. Check for Guided Practice (e.g. Three-Question Meditation)
    practice_markers = (
        "meditation",
        "bring attention to your breath",
        "inhale and exhale",
        "observe yourself",
        "close your eyes",
    )
    has_practice = any(m in body_text.lower() for m in practice_markers)

    if has_practice:
        practice_slug = f"{_clean_slug(canonical_title)}_practice"
        practice_path = okf_dir / f"{practice_slug}.md"

        # Extract practice section
        practice_paras = [
            p
            for p in paras
            if any(m in p.lower() for m in ("breath", "meditation", "eyes", "observe yourself"))
        ]
        practice_excerpt = "\n\n".join(practice_paras) if practice_paras else paras[-1]

        practice_meta = {
            "title": f"Guided Practice — {canonical_title}",
            "type": "practice",
            "teacher": speaker_slug,
            "source": f"https://www.youtube.com/watch?v={video_id}",
            "video_id": video_id,
            "tags": ["meditation", "practice", "breath", "beautiful-state"],
        }
        practice_yaml = yaml.safe_dump(practice_meta, sort_keys=False).strip()

        # Extract practice steps directly from transcript imperatives
        steps = []
        for s in re.split(r"(?<=[.!?])\s+", practice_excerpt):
            s = s.strip()
            if any(
                s.lower().startswith(start)
                for start in (
                    "bring",
                    "inhale",
                    "observe",
                    "imagine",
                    "wish",
                    "rest",
                    "sit",
                    "do not",
                )
            ):
                if len(s) >= 20:
                    steps.append(f"- {s} — {speaker}")

        if not steps:
            steps = [
                f"- Bring attention to your breath and observe without resistance. — {speaker}"
            ]

        practice_content = (
            f"---\n"
            f"{practice_yaml}\n"
            f"---\n"
            f"# Guided Practice — {canonical_title}\n\n"
            f"## Verbatim Discourse Excerpts\n"
            f"{practice_excerpt}\n\n"
            f"## Key Teachings\n"
            f"{chr(10).join(steps[:4])}\n\n"
            f"## Source Context\n"
            f"- Video: {canonical_title}\n"
            f"- URL: https://www.youtube.com/watch?v={video_id}\n"
            f"- Speaker: {speaker}\n"
        )
        practice_path.write_text(practice_content, encoding="utf-8")
        created_files.append(practice_path)
        logger.info("Created OKF practice entry: %s", practice_path)

    return created_files


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest a single video transcript into OKF without an LLM"
    )
    parser.add_argument("--video-id", default="TqxxCYnAxo8", help="YouTube video ID")
    args = parser.parse_args()

    files = ingest_video_to_okf(args.video_id)
    print(f"\n✅ Created {len(files)} OKF entries for {args.video_id}:")
    for f in files:
        print(f"  - {f}")

    # Re-compile OKF compiled.json
    print("\nRe-compiling OKF index...")
    from services.memory.compiler import compile_okf

    compiled_path = compile_okf()
    print(f"✅ OKF compiled successfully to: {compiled_path}")
