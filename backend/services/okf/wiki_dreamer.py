"""OKF Knowledge Wiki Dreamer — autonomous triage, deduplication, and graduation.

Consolidates uncurated markdown entries from memory/okf/staging/ into canonical
production teacher subdirectories:
1. Quality Filter: validates frontmatter, minimum body length, citations, and scans
   for LLM CoT leaks, repetition loops, and provider graceful degradation text.
2. Cross-Tree Deduplication: removes entries that duplicate production concepts
   (by filename, exact title, exact content hash, or Jaccard word-set similarity >= 0.9).
3. Intra-Staging Deduplication: collapses near-identical variants within staging,
   retaining the longest, highest-quality survivor.
4. Attribution Resolution: categorizes entries into canonical teacher subdirectories.
5. Bidirectional Wikilinking: adds Obsidian/Anthropic-style [[concept_id]] wikilinks
   across Related Concepts and body prose, linking related concepts bidirectionally.
6. Graduation & Triage Cleanup: writes graduated concepts into canonical subdirectories,
   removes graduated/duplicate files from staging, and generates an audit report.
7. Verification & Compilation: rebuilds memory/okf/compiled.json with dense vector
   embeddings and verifies expanded coverage without duplicates.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
try:
    from datetime import UTC, datetime
except ImportError:
    from datetime import datetime, timezone
    UTC = timezone.utc
from pathlib import Path
from typing import Any, Optional

import yaml

from services.memory.compiler import _body_word_set, _content_hash, compile_okf
from services.memory.okf_store import (
    DOCTRINE_TYPES,
    NON_CONCEPT_FILENAMES,
    OKF_DIR,
    RESERVED_FILENAMES,
    STAGING_DIR,
    _parse_frontmatter,
)
from services.okf_quality_filter import (
    OKFQualityFilter,
    _MIN_COMPLETE_QUOTE_CHARS,
    _QUOTE_TERMINATORS,
)
from services.text_quality_filter import find_artifact

logger = logging.getLogger(__name__)

_DEFAULT_AUDIT_REPORT = (
    OKF_DIR.parent.parent / "audits" / "okf" / "dreaming_report_2026-11-08.json"
)

# Extraction artifacts regex (aligned with test_okf_doctrine_only.py)
_ARTIFACT_RE = re.compile(
    r"RAPTOR Level\s*:|_\(Source:\s*unknown\)_|The user (?:wants me to|has provided)"
    r"|Interpret the Input|Let me analyze|We are given|comma-separated list",
    re.IGNORECASE,
)

from services.guru_registry import get_gurus

_gurus = get_gurus()
_G_P_ID = _gurus[0].id if len(_gurus) > 0 else "teacher_0"
_G_K_ID = _gurus[1].id if len(_gurus) > 1 else "teacher_1"
_G_P_DIR = f"sri-{_G_P_ID}"
_G_K_DIR = f"sri-{_G_K_ID}"

# Common canonical concept mappings for wikilinking
_CANONICAL_WIKI_SEEDS: dict[str, str] = {
    "Beautiful State": f"{_G_P_DIR}/beautiful_state",
    "Serene Mind": f"{_G_K_DIR}/serene_mind_practice",
    "Universal Intelligence": "shared/universal_intelligence",
    "Inner Truth": "shared/inner_truth_and_being",
    "Stillness": "shared/stillness_and_inner_truth",
    "Three-Question Meditation": f"{_G_P_DIR}/three_question_meditation",
    "Oneness": f"{_G_K_DIR}/oneness_the_ultimate_enlightened_state",
    "Truth of Suffering": "shared/the_truth_of_suffering",
    "Soul Sync": f"{_G_P_DIR}/soul_sync_meditation",
    "Deeksha": "shared/become_a_deeksha_giver_for_world_oneness",
    "Observation": f"{_G_P_DIR}/observation_and_self_awareness",
}


@dataclass
class TriageRecord:
    filename: str
    original_path: str
    status: str  # 'graduated', 'dup_of_production', 'dup_in_staging', 'quality_rejected', 'junk_template'
    reason: str
    title: str = ""
    teacher: str = ""
    target_path: Optional[str] = None
    duplicate_match: Optional[str] = None
    wikilinks_added: list[str] = field(default_factory=list)


@dataclass
class DreamingReport:
    timestamp: str
    total_staged: int
    duplicates_production: int
    duplicates_staging: int
    quality_rejected: int
    junk_templates: int
    graduated: int
    graduated_by_teacher: dict[str, int]
    remaining_staged: int
    compiled_entries: int
    graduated_records: list[dict[str, Any]] = field(default_factory=list)
    duplicate_records: list[dict[str, Any]] = field(default_factory=list)
    rejection_records: list[dict[str, Any]] = field(default_factory=list)


class OKFWikiDreamer:
    """Autonomous engine for triaging, wikifying, and graduating staging OKF concepts."""

    def __init__(
        self,
        okf_dir: Optional[Path] = None,
        staging_dir: Optional[Path] = None,
        audit_path: Optional[Path] = None,
    ) -> None:
        self.okf_dir = Path(okf_dir) if okf_dir else OKF_DIR
        self.staging_dir = Path(staging_dir) if staging_dir else STAGING_DIR
        self.audit_path = Path(audit_path) if audit_path else _DEFAULT_AUDIT_REPORT
        self._excluded_dirs = frozenset({"staging", "_scripts"})

    def get_production_files(self) -> list[Path]:
        """List all valid production markdown concept files (excluding staging and _scripts)."""
        return sorted(
            p
            for p in self.okf_dir.glob("**/*.md")
            if p.is_file()
            and p.name not in RESERVED_FILENAMES
            and p.name not in NON_CONCEPT_FILENAMES
            and not any(part in p.parts for part in self._excluded_dirs)
        )

    def load_production_entries(self) -> list[dict[str, Any]]:
        """Load and cache metadata, word sets, and content hashes for production entries."""
        prod_entries = []
        for p in self.get_production_files():
            text = p.read_text(encoding="utf-8")
            if not text.startswith("---"):
                continue
            parts = text.split("---", 2)
            if len(parts) < 3:
                continue
            try:
                meta = yaml.safe_load(parts[1])
            except Exception:
                continue
            if not isinstance(meta, dict):
                continue

            title = str(meta.get("title", "")).strip()
            body = parts[2]
            prod_entries.append(
                {
                    "path": p,
                    "rel_path": str(p.relative_to(self.okf_dir)),
                    "wiki_id": str(p.relative_to(self.okf_dir)).replace(".md", ""),
                    "name": p.name,
                    "title": title,
                    "title_norm": title.lower(),
                    "body": body,
                    "body_words": _body_word_set(body),
                    "hash": _content_hash(body),
                    "meta": meta,
                }
            )
        return prod_entries

    def build_wiki_index(self, prod_entries: list[dict[str, Any]]) -> dict[str, str]:
        """Build mapping of concept title / alias -> wiki_id (relative path without .md)."""
        wiki_index: dict[str, str] = dict(_CANONICAL_WIKI_SEEDS)
        for pe in prod_entries:
            title = pe["title"]
            wiki_id = pe["wiki_id"]
            if title:
                wiki_index[title] = wiki_id
                # Add short title before delimiter
                short_title = re.split(r"\s+[—–:-]\s+", title)[0].strip()
                if short_title and short_title != title and len(short_title) > 3:
                    wiki_index[short_title] = wiki_id

        return wiki_index

    @staticmethod
    def extract_description(meta: dict[str, Any], body: str) -> str:
        """Extract a clean, concise description sentence for frontmatter."""
        explicit = str(meta.get("description", "")).strip()
        if explicit and len(explicit) > 10:
            return explicit

        summary_match = re.search(r"##\s*Summary\s*\n(.*?)(?=\n##|\Z)", body, re.S)
        if summary_match:
            summary_text = summary_match.group(1).strip()
            lines = [
                l.strip()
                for l in summary_text.splitlines()
                if l.strip() and not l.startswith(("#", ">", "-", "*", "`"))
            ]
            if lines:
                sentence = re.split(r"(?<=[.!?])\s", lines[0])[0].strip()
                if len(sentence) > 15:
                    return sentence[:300]

        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", ">", "-", "*", "|", "`")):
                continue
            sentence = re.split(r"(?<=[.!?])\s", line)[0].strip()
            if len(sentence) > 15:
                return sentence[:300]

        return ""

    @staticmethod
    def resolve_teacher(meta: dict[str, Any], body: str) -> tuple[str, Path]:
        """Resolve canonical teacher and destination subdirectory.

        Returns (canonical_teacher, destination_subdir).
        """
        raw = str(meta.get("teacher", "")).strip().lower()
        if not raw or raw in ("none", "null"):
            # Inspect body
            b_lower = body.lower()
            if "preetha" in b_lower and "krishna" not in b_lower:
                return _G_P_DIR, OKF_DIR / _G_P_DIR
            if "krishna" in b_lower and "preetha" not in b_lower:
                return _G_K_DIR, OKF_DIR / _G_K_DIR
            return "both", OKF_DIR / "shared"

        if "preetha" in raw and "krishna" not in raw:
            return _G_P_DIR, OKF_DIR / _G_P_DIR
        if "krishna" in raw and "preetha" not in raw:
            return _G_K_DIR, OKF_DIR / _G_K_DIR
        return "both", OKF_DIR / "shared"

    def wikify_entry(
        self,
        title: str,
        meta: dict[str, Any],
        body: str,
        wiki_index: dict[str, str],
        current_wiki_id: str,
    ) -> tuple[str, list[str]]:
        """Add Obsidian/Anthropic-style [[wiki_id]] links and Related Concepts section."""
        lines = body.split("\n")
        new_lines = []
        bold_re = re.compile(r"\*\*([^*]+?)\*\*")
        rc_line_re = re.compile(r"^(-\s*(?:\*\*)?)(.+?)((?:\*\*)?:.*)$")
        links_added: list[str] = []
        in_rc = False

        for line in lines:
            if re.match(r"^##\s*(Related Concepts|See Also|Cross-References)", line, re.I):
                in_rc = True
            elif line.startswith("## ") and not line.startswith("### "):
                in_rc = False

            if in_rc:
                # Wikify list item in Related Concepts
                m = rc_line_re.match(line)
                if m:
                    concept_name = m.group(2).strip()
                    wiki_id = wiki_index.get(concept_name)
                    if not wiki_id:
                        # Try case-insensitive lookup
                        for k, v in wiki_index.items():
                            if k.lower() == concept_name.lower():
                                wiki_id = v
                                break
                    if wiki_id and wiki_id != current_wiki_id and f"[[{wiki_id}" not in line:
                        prefix = m.group(1).rstrip()
                        if not prefix.endswith("**"):
                            prefix = f"{prefix}**"
                        line = f"{prefix}{concept_name}** ([[{wiki_id}]]): {m.group(3).lstrip(':* ')}"
                        links_added.append(wiki_id)
            else:
                # Wikify bold keywords in body
                def _bold_sub(match: re.Match) -> str:
                    word = match.group(1).strip()
                    wid = wiki_index.get(word)
                    if not wid:
                        for k, v in wiki_index.items():
                            if k.lower() == word.lower():
                                wid = v
                                break
                    if wid and wid != current_wiki_id and f"[[{wid}" not in line:
                        links_added.append(wid)
                        return f"[[{wid}|{word}]]"
                    return match.group(0)

                line = bold_re.sub(_bold_sub, line)

            new_lines.append(line)

        updated_body = "\n".join(new_lines)

        # If no Related Concepts section exists, synthesize one with 2-4 relevant concepts
        if not re.search(r"^##\s*(Related Concepts|See Also|Cross-References)", updated_body, re.M):
            related_candidates = self._find_related_concepts(title, meta, body, wiki_index, current_wiki_id)
            if related_candidates:
                rc_section = ["\n## Related Concepts"]
                for rel_title, rel_id, rel_desc in related_candidates[:4]:
                    rc_section.append(f"- **{rel_title}** ([[{rel_id}]]): {rel_desc}")
                    links_added.append(rel_id)
                updated_body = updated_body.rstrip() + "\n\n" + "\n".join(rc_section) + "\n"

        return updated_body, sorted(set(links_added))

    def _find_related_concepts(
        self,
        title: str,
        meta: dict[str, Any],
        body: str,
        wiki_index: dict[str, str],
        current_wiki_id: str,
    ) -> list[tuple[str, str, str]]:
        """Identify candidate related concepts based on tags, title keywords, and doctrine concepts."""
        tags = set(str(t).lower() for t in meta.get("tags", []))
        body_words = _body_word_set(body)
        candidates = []

        # Check core seed concepts first
        core_seeds = [
            ("Beautiful State", f"{_G_P_DIR}/beautiful_state", "The serene, non-reactive state of inner calm and compassion."),
            ("Serene Mind", f"{_G_K_DIR}/serene_mind_practice", "Quiet observation of thoughts leading to mental clarity."),
            ("Universal Intelligence", "shared/universal_intelligence", "The underlying intelligence connecting all life forms."),
            ("Truth of Suffering", "shared/the_truth_of_suffering", "Understanding how self-centric thinking generates inner suffering."),
            ("Oneness", f"{_G_K_DIR}/oneness_the_ultimate_enlightened_state", "Experiencing interconnectedness and dissolution of division."),
            ("Observation", f"{_G_P_DIR}/observation_and_self_awareness", "Witnessing thoughts and emotional states without reaction."),
        ]
        for c_title, c_id, c_desc in core_seeds:
            if c_id == current_wiki_id:
                continue
            c_words = _body_word_set(c_title + " " + c_desc)
            if (c_words & body_words) or any(w in tags for w in c_words):
                candidates.append((c_title, c_id, c_desc))

        # Check existing wiki_index concepts
        _teachers_label = " and ".join(g.label for g in _gurus if g.label) or "the spiritual teachers"
        for c_title, c_id in wiki_index.items():
            if c_id == current_wiki_id or any(c_id == item[1] for item in candidates):
                continue
            c_words = _body_word_set(c_title)
            if c_words and c_words.issubset(body_words) and len(c_title) > 4:
                candidates.append(
                    (c_title, c_id, f"Core teaching on {c_title.lower()} by {_teachers_label}.")
                )

        return candidates

    def add_bidirectional_backlinks(
        self,
        target_path: Path,
        title: str,
        wiki_id: str,
        description: str,
        referenced_wiki_ids: list[str],
    ) -> int:
        """Add back-links to referenced production concept files that exist on disk."""
        backlinks_added = 0
        backlink_item = f"- **{title}** ([[{wiki_id}]]): {description}"

        for ref_id in referenced_wiki_ids:
            ref_path = self.okf_dir / f"{ref_id}.md"
            if not ref_path.is_file() or ref_path == target_path:
                continue

            try:
                content = ref_path.read_text(encoding="utf-8")
                if f"[[{wiki_id}]]" in content or f"[[{wiki_id}|" in content:
                    continue  # already linked

                if re.search(r"^##\s*(Related Concepts|See Also|Cross-References)", content, re.M):
                    # Append item under existing Related Concepts
                    lines = content.split("\n")
                    new_lines = []
                    inserted = False
                    for line in lines:
                        new_lines.append(line)
                        if (
                            not inserted
                            and re.match(
                                r"^##\s*(Related Concepts|See Also|Cross-References)", line, re.I
                            )
                        ):
                            new_lines.append(backlink_item)
                            inserted = True
                    ref_path.write_text("\n".join(new_lines), encoding="utf-8")
                    backlinks_added += 1
                else:
                    # Append Related Concepts section at end
                    content = content.rstrip() + f"\n\n## Related Concepts\n{backlink_item}\n"
                    ref_path.write_text(content, encoding="utf-8")
                    backlinks_added += 1
            except Exception as e:
                logger.warning("Failed to add backlink in %s: %s", ref_path, e)

        return backlinks_added

    @classmethod
    def repair_truncated_quotes(cls, body: str) -> str:
        """Subtractively repair truncated blockquotes in OKF body.

        Per repository invariants: subtractive repair cuts back to the last
        complete sentence (. ? !) or drops the truncated quote line.
        If ## Quotes has no remaining quotes, removes the section.
        """
        lines = body.split("\n")
        new_lines = []
        in_quotes_section = False

        for line in lines:
            if re.match(r"^##\s*Quotes", line, re.I):
                in_quotes_section = True
                new_lines.append(line)
                continue
            elif line.startswith("## ") and not line.startswith("### "):
                in_quotes_section = False

            m = re.match(r'^>\s*"(.+?)"(?:\s*—\s*(.*))?$', line)
            if m:
                quote_text = m.group(1).strip()
                attrib = (m.group(2) or "").strip()
                if (
                    len(quote_text) > _MIN_COMPLETE_QUOTE_CHARS
                    and quote_text[-1] not in _QUOTE_TERMINATORS
                ):
                    # Subtractive repair: find last sentence terminator . ? !
                    term_matches = [
                        tm.end()
                        for tm in re.finditer(r"[\.\?!](?=\s|\Z)", quote_text)
                    ]
                    if term_matches:
                        last_idx = term_matches[-1]
                        trimmed = quote_text[:last_idx].strip()
                        if len(trimmed) >= 25 and trimmed[-1] in _QUOTE_TERMINATORS:
                            attrib_part = f" — {attrib}" if attrib else ""
                            new_lines.append(f'> "{trimmed}"{attrib_part}')
                            continue
                    # Cannot trim to complete sentence -> drop this quote line
                    continue
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        repaired = "\n".join(new_lines)
        # If a ## Quotes section has no quotes left, remove it
        repaired = re.sub(r"##\s*Quotes\s*\n+(?=\n##|\Z)", "", repaired)
        return repaired

    def triage_and_graduate(
        self, dry_run: bool = False, auto_compile: bool = True
    ) -> DreamingReport:
        """Execute autonomous OKF triage, deduplication, wikification, and graduation."""
        staged_files = sorted(self.staging_dir.glob("*.md"))
        logger.info("Dreamer starting: %d staging files discovered in %s", len(staged_files), self.staging_dir)

        prod_entries = self.load_production_entries()
        logger.info("Loaded %d production entries from %s", len(prod_entries), self.okf_dir)
        wiki_index = self.build_wiki_index(prod_entries)

        records: list[TriageRecord] = []
        candidates: list[dict[str, Any]] = []

        # Step 1: Quality filter and template check
        for sf in staged_files:
            text = sf.read_text(encoding="utf-8")
            if not text.startswith("---"):
                records.append(
                    TriageRecord(
                        filename=sf.name,
                        original_path=str(sf),
                        status="junk_template",
                        reason="Missing YAML frontmatter",
                    )
                )
                continue

            parts = text.split("---", 2)
            if len(parts) < 3:
                records.append(
                    TriageRecord(
                        filename=sf.name,
                        original_path=str(sf),
                        status="junk_template",
                        reason="Malformed YAML frontmatter",
                    )
                )
                continue

            try:
                meta = yaml.safe_load(parts[1])
            except Exception as e:
                records.append(
                    TriageRecord(
                        filename=sf.name,
                        original_path=str(sf),
                        status="junk_template",
                        reason=f"YAML parse error: {e}",
                    )
                )
                continue

            if not isinstance(meta, dict):
                records.append(
                    TriageRecord(
                        filename=sf.name,
                        original_path=str(sf),
                        status="junk_template",
                        reason="Frontmatter is not a mapping",
                    )
                )
                continue

            title = str(meta.get("title", "")).strip()
            body = parts[2]
            source = str(meta.get("source", "")).strip()
            type_ = str(meta.get("type", "")).strip().lower()

            # Template placeholder check
            if (
                title.lower() in ("...", "title", "title here", "insert title")
                or source in ("...", "https://www.youtube.com/watch?v=VIDEO_ID")
                or "video_id" in source.lower()
                or body.strip() in ("...", "")
            ):
                records.append(
                    TriageRecord(
                        filename=sf.name,
                        original_path=str(sf),
                        status="junk_template",
                        reason="Template placeholder content",
                        title=title,
                    )
                )
                continue

            # OKF Quality filter
            entry_dict = {"type": type_, "title": title, "body": body, "source": source}
            ok, reason = OKFQualityFilter.validate_entry(entry_dict)
            if not ok and "Truncated quote" in reason:
                repaired_body = self.repair_truncated_quotes(body)
                rep_entry_dict = {"type": type_, "title": title, "body": repaired_body, "source": source}
                rep_ok, rep_reason = OKFQualityFilter.validate_entry(rep_entry_dict)
                if rep_ok:
                    body = repaired_body
                    ok = True
                else:
                    reason = rep_reason

            if not ok:
                records.append(
                    TriageRecord(
                        filename=sf.name,
                        original_path=str(sf),
                        status="quality_rejected",
                        reason=reason,
                        title=title,
                    )
                )
                continue

            # CoT, degradation, or prompt leakage
            art = find_artifact(text) or find_artifact(body)
            if art:
                records.append(
                    TriageRecord(
                        filename=sf.name,
                        original_path=str(sf),
                        status="quality_rejected",
                        reason=f"Artifact/CoT: {art}",
                        title=title,
                    )
                )
                continue

            leak = _ARTIFACT_RE.search(body)
            if leak:
                records.append(
                    TriageRecord(
                        filename=sf.name,
                        original_path=str(sf),
                        status="quality_rejected",
                        reason=f"Extraction artifact: {leak.group(0)}",
                        title=title,
                    )
                )
                continue

            # Valid clean candidate
            candidates.append(
                {
                    "path": sf,
                    "name": sf.name,
                    "meta": meta,
                    "title": title,
                    "title_norm": title.lower(),
                    "body": body,
                    "body_words": _body_word_set(body),
                    "hash": _content_hash(body),
                    "len": len(body),
                }
            )

        logger.info(
            "Quality filter passed: %d / %d staging candidates clean",
            len(candidates),
            len(staged_files),
        )

        # Step 2: Cross-Tree Deduplication against Production
        surviving_candidates: list[dict[str, Any]] = []
        for cand in candidates:
            sf_name = cand["name"]
            t_norm = cand["title_norm"]
            b_hash = cand["hash"]
            b_words = cand["body_words"]

            matched_prod: Optional[tuple[str, str]] = None
            for pe in prod_entries:
                if sf_name == pe["name"]:
                    matched_prod = (pe["rel_path"], "exact_filename")
                    break
                if t_norm == pe["title_norm"]:
                    matched_prod = (pe["rel_path"], "exact_title")
                    break
                if b_hash == pe["hash"]:
                    matched_prod = (pe["rel_path"], "exact_content_hash")
                    break
                if b_words and pe["body_words"]:
                    inter = len(b_words & pe["body_words"])
                    union = len(b_words | pe["body_words"])
                    if union > 0 and (inter / union) >= 0.9:
                        matched_prod = (pe["rel_path"], f"jaccard_{inter/union:.2f}")
                        break

            if matched_prod:
                records.append(
                    TriageRecord(
                        filename=cand["name"],
                        original_path=str(cand["path"]),
                        status="dup_of_production",
                        reason=f"Redundant with production {matched_prod[0]} ({matched_prod[1]})",
                        title=cand["title"],
                        duplicate_match=matched_prod[0],
                    )
                )
            else:
                surviving_candidates.append(cand)

        logger.info(
            "Cross-tree dedup: %d unique candidates survive against production",
            len(surviving_candidates),
        )

        # Step 3: Intra-Staging Deduplication
        # Sort by body length descending so the longest, most substantive variant survives
        surviving_candidates.sort(key=lambda x: -x["len"])
        graduates: list[dict[str, Any]] = []

        for cand in surviving_candidates:
            matched_survivor: Optional[tuple[dict[str, Any], str]] = None
            for surv in graduates:
                if cand["title_norm"] == surv["title_norm"]:
                    matched_survivor = (surv, "exact_title")
                    break
                base_cand = re.sub(r"__[a-f0-9]{8}\.md$", ".md", cand["name"])
                base_surv = re.sub(r"__[a-f0-9]{8}\.md$", ".md", surv["name"])
                if base_cand == base_surv:
                    matched_survivor = (surv, "filename_variant")
                    break
                if cand["hash"] == surv["hash"]:
                    matched_survivor = (surv, "content_hash")
                    break
                if cand["body_words"] and surv["body_words"]:
                    inter = len(cand["body_words"] & surv["body_words"])
                    union = len(cand["body_words"] | surv["body_words"])
                    if union > 0 and (inter / union) >= 0.9:
                        matched_survivor = (surv, f"jaccard_{inter/union:.2f}")
                        break

            if matched_survivor:
                records.append(
                    TriageRecord(
                        filename=cand["name"],
                        original_path=str(cand["path"]),
                        status="dup_in_staging",
                        reason=f"Redundant with staging survivor {matched_survivor[0]['name']} ({matched_survivor[1]})",
                        title=cand["title"],
                        duplicate_match=matched_survivor[0]["name"],
                    )
                )
            else:
                graduates.append(cand)

        logger.info("Intra-staging dedup: %d canonical concepts to graduate", len(graduates))

        # Step 4: Graduation, Teacher Attribution & Bidirectional Wikilinking
        teacher_counts: dict[str, int] = {}
        for cand in graduates:
            meta = cand["meta"]
            body = cand["body"]
            title = cand["title"]

            # Resolve teacher and destination
            canon_teacher, dest_dir = self.resolve_teacher(meta, body)
            teacher_counts[canon_teacher] = teacher_counts.get(canon_teacher, 0) + 1
            meta["teacher"] = canon_teacher

            # Sanitize source
            raw_source = str(meta.get("source", "")).strip()
            if raw_source.lower().startswith("youtube "):
                raw_source = raw_source[8:].strip()
            meta["source"] = raw_source

            # Clean bold markers from Key Teachings
            def _strip_bold_in_teachings(match: re.Match) -> str:
                kt_body = match.group(2)
                kt_cleaned = kt_body.replace("**", "")
                return f"{match.group(1)}{kt_cleaned}"

            body = re.sub(
                r"(##\s*Key Teachings\s*\n)(.*?)(?=\n##|\Z)",
                _strip_bold_in_teachings,
                body,
                flags=re.DOTALL,
            )

            # Resolve description
            desc = self.extract_description(meta, body)
            if not desc or len(desc) < 10:
                desc = f"Core spiritual teaching on {title}."
            meta["description"] = desc

            # Determine clean target filename
            clean_name = re.sub(r"__[a-f0-9]{8}\.md$", ".md", cand["name"])
            target_path = dest_dir / clean_name
            # If collision in destination with a different file, preserve disambiguated name
            if target_path.exists() and target_path != cand["path"]:
                target_path = dest_dir / cand["name"]

            wiki_id = f"{dest_dir.name}/{target_path.stem}"

            # Wikify body & Related Concepts
            wikified_body, links = self.wikify_entry(
                title=title,
                meta=meta,
                body=body,
                wiki_index=wiki_index,
                current_wiki_id=wiki_id,
            )

            # Update wiki_index so subsequent graduates can link to this concept
            wiki_index[title] = wiki_id

            record = TriageRecord(
                filename=cand["name"],
                original_path=str(cand["path"]),
                status="graduated",
                reason="Passed quality, attribution, dedup, and wikilinking",
                title=title,
                teacher=canon_teacher,
                target_path=str(target_path),
                wikilinks_added=links,
            )
            records.append(record)

            if not dry_run:
                dest_dir.mkdir(parents=True, exist_ok=True)
                # Re-serialize frontmatter and wikified body
                frontmatter_yaml = yaml.dump(
                    meta, sort_keys=False, allow_unicode=True, default_flow_style=False
                ).strip()
                target_path.write_text(f"---\n{frontmatter_yaml}\n---\n\n{wikified_body.lstrip()}", encoding="utf-8")

                # Remove original from staging
                cand["path"].unlink(missing_ok=True)

                # Add bidirectional backlinks to referenced concepts
                self.add_bidirectional_backlinks(
                    target_path=target_path,
                    title=title,
                    wiki_id=wiki_id,
                    description=desc,
                    referenced_wiki_ids=links,
                )

        # Step 5: Clean up duplicates and junk from staging
        if not dry_run:
            for r in records:
                if r.status in ("dup_of_production", "dup_in_staging", "junk_template"):
                    p = Path(r.original_path)
                    p.unlink(missing_ok=True)

        # Remaining in staging are only quality_rejected entries requiring manual curation
        remaining = len(list(self.staging_dir.glob("*.md")))

        # Step 6: Compilation
        compiled_count = 0
        if auto_compile and not dry_run and graduates:
            logger.info("Recompiling production OKF index...")
            comp_path = compile_okf()
            if comp_path.exists():
                comp_data = json.loads(comp_path.read_text(encoding="utf-8"))
                compiled_count = len(comp_data.get("entries", []))

        # Step 7: Write Audit Report
        report = DreamingReport(
            timestamp=datetime.now(UTC).isoformat(),
            total_staged=len(staged_files),
            duplicates_production=sum(1 for r in records if r.status == "dup_of_production"),
            duplicates_staging=sum(1 for r in records if r.status == "dup_in_staging"),
            quality_rejected=sum(1 for r in records if r.status == "quality_rejected"),
            junk_templates=sum(1 for r in records if r.status == "junk_template"),
            graduated=len(graduates),
            graduated_by_teacher=teacher_counts,
            remaining_staged=remaining,
            compiled_entries=compiled_count,
            graduated_records=[asdict(r) for r in records if r.status == "graduated"],
            duplicate_records=[asdict(r) for r in records if "dup" in r.status],
            rejection_records=[asdict(r) for r in records if r.status == "quality_rejected"],
        )

        if not dry_run:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            self.audit_path.write_text(
                json.dumps(asdict(report), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info("Audit report written to %s", self.audit_path)

        return report
