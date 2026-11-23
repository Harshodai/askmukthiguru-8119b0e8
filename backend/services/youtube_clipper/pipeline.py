"""Core pipeline functions for the YouTube Clipper capability."""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Optional

from services.youtube_clipper.models import (
    Chapter,
    ChapterCoverageValidation,
    ClipperArtifacts,
    ClipperOptions,
)
from services.youtube_transcript.downloader import sanitize_filename

logger = logging.getLogger(__name__)


def seconds_to_srt_time(seconds: float) -> str:
    """Convert float seconds to SRT timecode format: HH:MM:SS,mmm."""
    if seconds < 0:
        seconds = 0.0
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        secs += 1
        millis = 0
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def time_to_seconds(time_str: str) -> float:
    """Parse time string 'HH:MM:SS.mmm' or 'MM:SS.mmm' into float seconds."""
    parts = time_str.replace(",", ".").split(":")
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    return float(parts[0])


def validate_chapter_coverage(
    chapters: list[Chapter],
    total_duration: float,
    tolerance_s: float = 2.0,
) -> ChapterCoverageValidation:
    """Verify semantic chapter set covers the entire video without gaps or overlaps."""
    errors: list[str] = []
    gaps: list[dict] = []
    overlaps: list[dict] = []

    if not chapters:
        return ChapterCoverageValidation(
            is_valid=False,
            total_duration=total_duration,
            covered_duration=0.0,
            coverage_ratio=0.0,
            errors=["Chapter list is empty."],
        )

    # Sort chapters by start time
    sorted_ch = sorted(chapters, key=lambda c: c.start_time)

    # Check start
    if sorted_ch[0].start_time > tolerance_s:
        gaps.append({"start": 0.0, "end": sorted_ch[0].start_time, "duration": sorted_ch[0].start_time})
        errors.append(f"Gap at start of video: 0.0s to {sorted_ch[0].start_time}s")

    # Check contiguous intervals
    covered_duration = 0.0
    for i in range(len(sorted_ch)):
        ch = sorted_ch[i]
        covered_duration += ch.duration

        # Target chapter duration validation (2–5 minutes = 120s – 300s, with boundary tolerance)
        if ch.duration < 15.0:
            errors.append(f"Chapter {ch.index} '{ch.title}' is unusually short ({ch.duration:.1f}s)")

        if i < len(sorted_ch) - 1:
            next_ch = sorted_ch[i + 1]
            diff = next_ch.start_time - ch.end_time
            if diff > tolerance_s:
                gaps.append({"start": ch.end_time, "end": next_ch.start_time, "duration": diff})
                errors.append(f"Gap between chapters {ch.index} and {next_ch.index}: {diff:.1f}s")
            elif diff < -tolerance_s:
                overlaps.append({"start": next_ch.start_time, "end": ch.end_time, "duration": abs(diff)})
                errors.append(f"Overlap between chapters {ch.index} and {next_ch.index}: {abs(diff):.1f}s")

    # Check end
    last_end = sorted_ch[-1].end_time
    if total_duration > 0 and (total_duration - last_end) > tolerance_s:
        gaps.append({"start": last_end, "end": total_duration, "duration": total_duration - last_end})
        errors.append(f"Gap at end of video: {last_end}s to {total_duration}s")

    coverage_ratio = (covered_duration / total_duration) if total_duration > 0 else 1.0
    is_valid = len(errors) == 0

    return ChapterCoverageValidation(
        is_valid=is_valid,
        total_duration=total_duration,
        covered_duration=covered_duration,
        coverage_ratio=coverage_ratio,
        gaps=gaps,
        overlaps=overlaps,
        errors=errors,
    )


def parse_vtt_cues(vtt_text: str) -> list[tuple[float, float, str]]:
    """Parse VTT text into structured list of (start_seconds, end_seconds, cue_text)."""
    cues: list[tuple[float, float, str]] = []
    lines = vtt_text.splitlines()

    timestamp_re = re.compile(
        r"(\d{2}:\d{2}(?::\d{2})?[.,]\d{3})\s*-->\s*(\d{2}:\d{2}(?::\d{2})?[.,]\d{3})"
    )
    tag_re = re.compile(r"<[^>]+>")

    current_start: Optional[float] = None
    current_end: Optional[float] = None
    current_lines: list[str] = []

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            if current_start is not None and current_end is not None and current_lines:
                cues.append((current_start, current_end, " ".join(current_lines)))
                current_start = None
                current_end = None
                current_lines = []
            continue

        ts_match = timestamp_re.search(line_clean)
        if ts_match:
            current_start = time_to_seconds(ts_match.group(1))
            current_end = time_to_seconds(ts_match.group(2))
            current_lines = []
            continue

        if current_start is not None:
            clean_text = tag_re.sub("", line_clean).strip()
            if clean_text:
                current_lines.append(clean_text)

    if current_start is not None and current_end is not None and current_lines:
        cues.append((current_start, current_end, " ".join(current_lines)))

    return cues


def slice_srt_zero_offset(
    cues: list[tuple[float, float, str]],
    start_time: float,
    end_time: float,
) -> str:
    """Slice cues within [start_time, end_time] and shift timestamps to start at 00:00:00,000."""
    offset_cues: list[str] = []
    index = 1

    for c_start, c_end, text in cues:
        # Check overlap with chapter window
        if c_end <= start_time or c_start >= end_time:
            continue

        # Clamp and shift
        shifted_start = max(0.0, c_start - start_time)
        shifted_end = max(shifted_start + 0.1, min(end_time - start_time, c_end - start_time))

        start_str = seconds_to_srt_time(shifted_start)
        end_str = seconds_to_srt_time(shifted_end)

        offset_cues.append(f"{index}\n{start_str} --> {end_str}\n{text}\n")
        index += 1

    return "\n".join(offset_cues)


def batch_translate_cues(
    cues: list[tuple[float, float, str]],
    batch_size: int = 20,
    max_retries: int = 3,
    translator_func: Optional[Callable[[list[str]], list[str]]] = None,
) -> list[tuple[float, float, str, str]]:
    """Translate subtitle cues in batches of up to 20 with bounded retries.

    Returns: List of (shifted_start, shifted_end, original_text, translated_text)
    """
    results: list[tuple[float, float, str, str]] = []

    for i in range(0, len(cues), batch_size):
        batch = cues[i : i + batch_size]
        texts = [c[2] for c in batch]

        translated_texts: list[str] = []
        if translator_func:
            for attempt in range(max_retries):
                try:
                    translated_texts = translator_func(texts)
                    if len(translated_texts) == len(texts):
                        break
                except Exception as e:
                    logger.warning("Subtitle translation batch failed attempt %d: %s", attempt + 1, e)
                    if attempt == max_retries - 1:
                        raise RuntimeError(
                            f"Subtitle translation batch failed after {max_retries} attempts: {e}"
                        ) from e
        else:
            raise RuntimeError(
                "Bilingual subtitles require a configured translation provider; "
                "placeholder translations are not permitted."
            )

        if len(translated_texts) != len(texts):
            raise RuntimeError(
                f"Translation provider returned {len(translated_texts)} items for {len(texts)} cues."
            )

        for (c_start, c_end, orig_text), trans_text in zip(batch, translated_texts):
            results.append((c_start, c_end, orig_text, trans_text))

    return results


def generate_bilingual_srt(bilingual_cues: list[tuple[float, float, str, str]]) -> str:
    """Generate bilingual SRT with English over translated target line."""
    blocks: list[str] = []
    for idx, (c_start, c_end, orig, trans) in enumerate(bilingual_cues, start=1):
        start_str = seconds_to_srt_time(c_start)
        end_str = seconds_to_srt_time(c_end)
        blocks.append(f"{idx}\n{start_str} --> {end_str}\n{orig}\n{trans}\n")
    return "\n".join(blocks)


def cut_mp4_clip(
    input_mp4: Path,
    start_time: float,
    end_time: float,
    output_mp4: Path,
    custom_runner: Optional[Callable] = None,
) -> bool:
    """Execute FFmpeg to cut MP4 between start_time and end_time."""
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    duration = end_time - start_time

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(round(start_time, 3)),
        "-i",
        str(input_mp4),
        "-t",
        str(round(duration, 3)),
        "-c",
        "copy",
        str(output_mp4),
    ]

    if custom_runner:
        res = custom_runner(cmd)
        ok = res.get("returncode", 0) == 0
        return ok and output_mp4.exists() and output_mp4.stat().st_size > 0

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return proc.returncode == 0 and output_mp4.exists() and output_mp4.stat().st_size > 0
    except Exception as e:
        logger.error("FFmpeg clip cutting failed: %s", e)
        return False


def burn_subtitles_libass(
    video_path: Path,
    srt_path: Path,
    output_path: Path,
    custom_runner: Optional[Callable] = None,
) -> bool:
    """Burn subtitles into video using FFmpeg libass filter."""
    if not srt_path.exists() or srt_path.stat().st_size == 0:
        logger.error("Subtitle file missing or empty: %s", srt_path)
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Safe escaping for Windows/Unix path separators in FFmpeg subtitles filter
    escaped_srt = str(srt_path).replace("\\", "/").replace(":", "\\:")
    sub_filter = f"subtitles='{escaped_srt}':force_style='FontSize=16,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1'"

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        sub_filter,
        "-c:a",
        "copy",
        str(output_path),
    ]

    if custom_runner:
        res = custom_runner(cmd)
        ok = res.get("returncode", 0) == 0
        return ok and output_path.exists() and output_path.stat().st_size > 0

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return proc.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0
    except Exception as e:
        logger.error("FFmpeg subtitle burn failed: %s", e)
        return False


def generate_chapter_summary_md(chapter: Chapter, video_title: str) -> str:
    """Generate social media and educational summary Markdown for the chapter."""
    start_str = str(datetime.timedelta(seconds=int(chapter.start_time)))
    end_str = str(datetime.timedelta(seconds=int(chapter.end_time)))
    duration_str = f"{int(chapter.duration // 60)}m {int(chapter.duration % 60)}s"

    tags = " ".join([f"#{re.sub(r'[^a-zA-Z0-9]', '', kw)}" for kw in chapter.keywords])

    return f"""# {chapter.title}

**Source Video:** {video_title}  
**Time Range:** {start_str} – {end_str} ({duration_str})  
**Keywords:** {', '.join(chapter.keywords)}  

---

## Core Summary
{chapter.summary}

---

## Social Caption
{chapter.title} — {chapter.summary}

Watch clip: {start_str} to {end_str}
{tags}
"""


def process_chapter(
    video_path: Path,
    vtt_path: Path,
    chapter: Chapter,
    video_title: str,
    options: ClipperOptions,
    base_output_dir: Path,
    custom_runner: Optional[Callable] = None,
    translator_func: Optional[Callable[[list[str]], list[str]]] = None,
) -> ClipperArtifacts:
    """Orchestrate end-to-end processing of a single chapter into output hierarchy.

    Guarantees fail-closed atomicity: any failure (FFmpeg cut, cue slice, translation,
    subtitle burn, or manifest generation) immediately purges intermediate files
    from the chapter directory and raises an error, ensuring partial corrupt
    artifacts are never emitted.
    """
    clean_title = sanitize_filename(chapter.title, max_length=50).replace(" ", "_")
    ch_dir_name = f"{chapter.index:02d}_{clean_title}"
    chapter_dir = base_output_dir / ch_dir_name
    chapter_dir.mkdir(parents=True, exist_ok=True)

    base_name = f"{clean_title}_clip"
    clip_mp4 = chapter_dir / f"{base_name}.mp4"
    srt_path = chapter_dir / f"{base_name}.en.srt"
    bilingual_srt_path: Optional[Path] = None
    subtitled_mp4: Optional[Path] = None
    summary_md: Optional[Path] = None

    created_artifacts: list[Path] = []

    try:
        # 1. Cut MP4
        if not cut_mp4_clip(
            video_path, chapter.start_time, chapter.end_time, clip_mp4, custom_runner=custom_runner
        ):
            raise RuntimeError(f"FFmpeg failed to cut chapter {chapter.index}: {chapter.title}")
        if not clip_mp4.exists() or clip_mp4.stat().st_size == 0:
            raise RuntimeError(f"Cut MP4 artifact missing or empty for chapter {chapter.index}")
        created_artifacts.append(clip_mp4)

        # 2. Extract and shift SRT
        vtt_text = vtt_path.read_text(encoding="utf-8") if vtt_path.exists() else ""
        cues = parse_vtt_cues(vtt_text)
        shifted_srt = slice_srt_zero_offset(cues, chapter.start_time, chapter.end_time)
        srt_path.write_text(shifted_srt, encoding="utf-8")
        if not srt_path.exists() or srt_path.stat().st_size == 0:
            raise RuntimeError(f"SRT artifact missing or empty for chapter {chapter.index}")
        created_artifacts.append(srt_path)

        # 3. Bilingual SRT if requested
        active_srt = srt_path
        if options.translate_bilingual:
            if not translator_func:
                raise RuntimeError(
                    "Bilingual subtitles require a configured translation provider; "
                    "placeholder translations are not permitted."
                )
            chapter_cues = [
                (max(0.0, c[0] - chapter.start_time), max(0.1, c[1] - chapter.start_time), c[2])
                for c in cues
                if c[1] > chapter.start_time and c[0] < chapter.end_time
            ]
            bilingual_cues = batch_translate_cues(
                chapter_cues,
                batch_size=20,
                translator_func=translator_func,
            )
            bilingual_text = generate_bilingual_srt(bilingual_cues)
            bilingual_srt_path = chapter_dir / f"{base_name}.bilingual.srt"
            bilingual_srt_path.write_text(bilingual_text, encoding="utf-8")
            if not bilingual_srt_path.exists() or bilingual_srt_path.stat().st_size == 0:
                raise RuntimeError(f"Bilingual SRT missing or empty for chapter {chapter.index}")
            created_artifacts.append(bilingual_srt_path)
            active_srt = bilingual_srt_path

        # 4. Burn subtitles if requested
        if options.burn_subtitles:
            if not active_srt.exists() or active_srt.stat().st_size == 0:
                raise RuntimeError(f"Subtitle file missing or empty for chapter {chapter.index}; cannot burn subtitles.")
            subtitled_mp4 = chapter_dir / f"{base_name}_subtitled.mp4"
            if not burn_subtitles_libass(
                clip_mp4, active_srt, subtitled_mp4, custom_runner=custom_runner
            ):
                raise RuntimeError(f"FFmpeg failed to burn subtitles for chapter {chapter.index}")
            if not subtitled_mp4.exists() or subtitled_mp4.stat().st_size == 0:
                raise RuntimeError(f"Subtitled MP4 artifact missing or empty for chapter {chapter.index}")
            created_artifacts.append(subtitled_mp4)

        # 5. Summary Markdown
        if options.generate_summary:
            summary_md = chapter_dir / f"{clean_title}_summary.md"
            summary_text = generate_chapter_summary_md(chapter, video_title)
            summary_md.write_text(summary_text, encoding="utf-8")
            if not summary_md.exists() or summary_md.stat().st_size == 0:
                raise RuntimeError(f"Summary markdown missing or empty for chapter {chapter.index}")
            created_artifacts.append(summary_md)

        # 6. Compute hashes & build manifest
        file_hashes = {}
        for p in created_artifacts:
            h = hashlib.sha256()
            with open(p, "rb") as f:
                while chunk := f.read(65536):
                    h.update(chunk)
            file_hashes[p.name] = h.hexdigest()

        # Compute input video & VTT hashes
        input_video_hash = ""
        if video_path.exists():
            h_in = hashlib.sha256()
            with open(video_path, "rb") as f:
                while chunk := f.read(65536):
                    h_in.update(chunk)
            input_video_hash = h_in.hexdigest()
        vtt_hash = hashlib.sha256(vtt_text.encode("utf-8")).hexdigest()

        is_production_certified = bool(custom_runner is None and clip_mp4.stat().st_size > 1000)

        manifest_path = chapter_dir / "manifest.json"
        manifest_data = {
            "chapter_index": chapter.index,
            "title": chapter.title,
            "video_title": video_title,
            "start_time": chapter.start_time,
            "end_time": chapter.end_time,
            "duration_seconds": chapter.duration,
            "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "inputs": {
                "video_file": video_path.name,
                "video_sha256": input_video_hash,
                "vtt_file": vtt_path.name,
                "vtt_sha256": vtt_hash,
            },
            "files": {
                "clip_mp4": clip_mp4.name,
                "srt": srt_path.name if srt_path.exists() else None,
                "bilingual_srt": bilingual_srt_path.name if bilingual_srt_path and bilingual_srt_path.exists() else None,
                "subtitled_mp4": subtitled_mp4.name if subtitled_mp4 and subtitled_mp4.exists() else None,
                "summary_md": summary_md.name if summary_md and summary_md.exists() else None,
            },
            "artifacts": {
                "clip_mp4": {
                    "file": clip_mp4.name,
                    "sha256": file_hashes[clip_mp4.name],
                    "size_bytes": clip_mp4.stat().st_size,
                },
                "srt": {
                    "file": srt_path.name,
                    "sha256": file_hashes[srt_path.name],
                    "size_bytes": srt_path.stat().st_size,
                },
                "bilingual_srt": {
                    "file": bilingual_srt_path.name,
                    "sha256": file_hashes[bilingual_srt_path.name],
                    "size_bytes": bilingual_srt_path.stat().st_size,
                } if bilingual_srt_path else None,
                "subtitled_mp4": {
                    "file": subtitled_mp4.name,
                    "sha256": file_hashes[subtitled_mp4.name],
                    "size_bytes": subtitled_mp4.stat().st_size,
                } if subtitled_mp4 else None,
                "summary_md": {
                    "file": summary_md.name,
                    "sha256": file_hashes[summary_md.name],
                    "size_bytes": summary_md.stat().st_size,
                } if summary_md else None,
            },
            "environment": {
                "ffmpeg_version": subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.splitlines()[0] if shutil.which("ffmpeg") else "custom_runner",
                "translation_provider": "external_provider" if translator_func else "none",
                "target_language": options.target_lang,
            },
            "production_certified": is_production_certified,
            "certification_status": "CERTIFIED" if is_production_certified else "UNCERTIFIED_OR_TEST",
        }
        manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
        file_hashes[manifest_path.name] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        created_artifacts.append(manifest_path)
    except Exception:
        for p in created_artifacts:
            try:
                if p.is_file():
                    p.unlink()
            except Exception:
                pass
        try:
            if chapter_dir.is_dir() and not any(chapter_dir.iterdir()):
                chapter_dir.rmdir()
        except Exception:
            pass
        raise

    return ClipperArtifacts(
        chapter_index=chapter.index,
        chapter_title=chapter.title,
        chapter_dir=chapter_dir,
        clip_mp4=clip_mp4,
        srt_path=srt_path,
        bilingual_srt_path=bilingual_srt_path,
        subtitled_mp4=subtitled_mp4,
        summary_md=summary_md,
        manifest_path=manifest_path,
        duration_seconds=chapter.duration,
        file_hashes=file_hashes,
        production_certified=is_production_certified,
    )
