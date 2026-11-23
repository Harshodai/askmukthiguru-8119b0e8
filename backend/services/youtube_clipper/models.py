"""Data models for the standalone YouTube Clipper pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Chapter:
    """Represents a semantic video chapter."""
    index: int
    title: str
    start_time: float  # in seconds
    end_time: float    # in seconds
    summary: str
    keywords: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)


@dataclass
class ChapterCoverageValidation:
    """Result of chapter coverage verification."""
    is_valid: bool
    total_duration: float
    covered_duration: float
    coverage_ratio: float
    gaps: list[dict] = field(default_factory=list)
    overlaps: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class ClipperOptions:
    """Options for processing selected chapters."""
    burn_subtitles: bool = True
    translate_bilingual: bool = True
    target_lang: str = "zh"
    generate_summary: bool = True


@dataclass
class ClipperArtifacts:
    """Output deliverables generated for a chapter."""
    chapter_index: int
    chapter_title: str
    chapter_dir: Path
    clip_mp4: Path
    srt_path: Optional[Path] = None
    bilingual_srt_path: Optional[Path] = None
    subtitled_mp4: Optional[Path] = None
    summary_md: Optional[Path] = None
    manifest_path: Optional[Path] = None
    duration_seconds: float = 0.0
    file_hashes: dict = field(default_factory=dict)
    production_certified: bool = False
