"""Enterprise Offline Memory Dreamer Worker (Sleep-Time Compute) for AskMukthiGuru.

Phase 3 of the Production Agent Memory Plan (incorporating Anthropic's
"The Components of Agent Memory" research).

Offline "Dreaming" (sleep-time compute) rereads session transcripts alongside
notes to:
    1. Pre-dreaming snapshot creation (canonical_memory_compaction_snapshots).
       Abort if snapshot fails.
    2. Transcript Grounding Audit:
       Catch and correct wrong/hallucinated notes against actual transcripts.
       Evict memories with zero transcript grounding or that contradict user messages.
       (status='deleted', reason='dreamer_evicted_no_transcript_grounding', audit event).
    3. Contradiction & Temporal Evolution:
       Resolve contradictions and temporal shifts. Compare transcript timestamps;
       mark older superseded states as status='superseded'.
    4. Mathematical Decay & Pruning:
       decay_score = decay_score * 0.97.
       If decay_score < 0.15 and importance < 0.6 and memory_type != 'USER_EXPLICIT',
       mark status='expired'.
    5. Re-synthesize SeekerCoreDashboard:
       Promote core milestones/facts to top-level Seeker Core Dashboard
       and persist to guru_core_memory.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field

try:
    from datetime import UTC, datetime
except ImportError:
    from datetime import datetime

    UTC = UTC
from typing import Any, Optional

from services.canonical_memory.consolidator import (
    SNAPSHOT_TABLE,
    _decode_snapshot_memories,
)
from services.canonical_memory.models import SeekerCoreDashboard
from services.tenant_context import TenantContext

logger = logging.getLogger(__name__)

# Standard stop words to ignore during keyword extraction for grounding audit
_STOPWORDS = frozenset(
    {
        "a",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "am",
        "an",
        "and",
        "any",
        "are",
        "aren't",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "can",
        "cannot",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "don't",
        "down",
        "during",
        "each",
        "few",
        "for",
        "from",
        "further",
        "had",
        "has",
        "have",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "herself",
        "him",
        "himself",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "isn't",
        "it",
        "its",
        "itself",
        "just",
        "me",
        "more",
        "most",
        "my",
        "myself",
        "no",
        "nor",
        "not",
        "now",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "ought",
        "our",
        "ours",
        "ourselves",
        "out",
        "over",
        "own",
        "same",
        "she",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "very",
        "was",
        "wasn't",
        "we",
        "were",
        "weren't",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "with",
        "would",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
        "user",
        "user's",
        "prefers",
        "likes",
        "really",
    }
)


@dataclass
class DreamingReport:
    """Structured report returned after offline memory dreaming completes."""

    user_id: str
    snapshot_id: Optional[str] = None
    evicted_count: int = 0
    superseded_count: int = 0
    decayed_count: int = 0
    dashboard_updated: bool = False
    active_remaining: int = 0
    dry_run: bool = False
    error: Optional[str] = None
    audit_event_ids: list[str] = field(default_factory=list)


class MemoryDreamer:
    """Enterprise Offline Memory Dreamer Worker (Sleep-Time Compute).

    Executes 5 core stages:
    1. Pre-dreaming snapshot creation (fail-closed rollback contract).
    2. Transcript Grounding Audit (evict hallucinated or contradicted claims).
    3. Contradiction & Temporal Evolution (resolve conflicts; newer transcript wins).
    4. Mathematical Decay & Pruning (score * 0.97; expire < 0.15 unless important/explicit).
    5. Re-synthesize SeekerCoreDashboard (persist to guru_core_memory).
    """

    def __init__(
        self,
        supabase_client: Any,
        llm_service: Optional[Any] = None,
        tenant_id: Optional[str] = None,
    ):
        self._db = supabase_client
        self._llm = llm_service
        self._tenant_id = tenant_id

    def _get_tenant_id(self) -> str:
        return self._tenant_id or TenantContext.get() or "oneness"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def dream(self, user_id: str, dry_run: bool = False) -> DreamingReport:
        """Run the full 5-stage offline dreaming process for a seeker."""
        report = DreamingReport(user_id=user_id, dry_run=dry_run)
        tenant_id = self._get_tenant_id()

        try:
            # 1. Fetch active memories
            memories = await self._fetch_active_memories(user_id)
            if not memories:
                logger.info("No active memories found for user %s during dreaming.", user_id)
                report.active_remaining = 0
                return report

            # Stage 1: Snapshot creation
            snapshot_id: Optional[str] = None
            if not dry_run:
                snapshot_id = await self._create_snapshot(user_id, memories)
                if not snapshot_id:
                    logger.error(
                        "Dreaming aborted for user %s: pre-dreaming snapshot could not be confirmed.",
                        user_id,
                    )
                    report.error = "snapshot_creation_failed"
                    report.active_remaining = len(memories)
                    return report
                report.snapshot_id = snapshot_id
            else:
                report.snapshot_id = "dry-run-snapshot"

            # Stage 2: Transcript Grounding Audit
            transcripts = await self._load_transcripts_for_memories(memories, user_id)
            evicted_ids: set[str] = set()

            for mem in memories:
                conv_id = mem.get("source_conversation_id")
                msg_id = mem.get("source_message_id")
                transcript = transcripts.get(conv_id) or transcripts.get(msg_id) or []

                is_grounded, reason = self._audit_transcript_grounding(mem, transcript)
                if not is_grounded:
                    evicted_ids.add(mem["id"])
                    report.evicted_count += 1
                    if not dry_run:
                        await self._update_memory_status(
                            mem,
                            "deleted",
                            reason=reason,
                        )
                        audit_id = await self._write_audit_event(
                            user_id=user_id,
                            memory_id=mem["id"],
                            event_type="DELETED",
                            reason=reason,
                            old_version=mem.get("version", 1),
                            new_version=mem.get("version", 1) + 1,
                        )
                        if audit_id:
                            report.audit_event_ids.append(audit_id)

            surviving_after_stage2 = [m for m in memories if m["id"] not in evicted_ids]

            # Stage 3: Contradiction & Temporal Evolution
            superseded_ids: set[str] = set()
            conflicts_to_supersede = self._detect_temporal_conflicts(
                surviving_after_stage2, transcripts
            )

            for older_mem, newer_mem in conflicts_to_supersede:
                if older_mem["id"] in superseded_ids:
                    continue
                superseded_ids.add(older_mem["id"])
                report.superseded_count += 1
                reason = f"Superseded by newer memory {newer_mem['id']}"
                if not dry_run:
                    await self._update_memory_status(
                        older_mem,
                        "superseded",
                        reason=reason,
                    )
                    audit_id = await self._write_audit_event(
                        user_id=user_id,
                        memory_id=older_mem["id"],
                        event_type="SUPERSEDED",
                        reason=reason,
                        old_version=older_mem.get("version", 1),
                        new_version=older_mem.get("version", 1) + 1,
                    )
                    if audit_id:
                        report.audit_event_ids.append(audit_id)

            surviving_after_stage3 = [
                m for m in surviving_after_stage2 if m["id"] not in superseded_ids
            ]

            # Stage 4: Mathematical Decay & Pruning
            decayed_ids: set[str] = set()
            for mem in surviving_after_stage3:
                current_decay = self._get_decay_score(mem)
                new_decay = round(current_decay * 0.97, 4)
                importance = float(mem.get("importance", 0.5))
                mem_type = mem.get("memory_type", "")

                if new_decay < 0.15 and importance < 0.6 and mem_type != "USER_EXPLICIT":
                    decayed_ids.add(mem["id"])
                    report.decayed_count += 1
                    reason = f"Decayed below threshold (decay_score={new_decay:.4f}, importance={importance})"
                    if not dry_run:
                        await self._update_memory_status(
                            mem,
                            "expired",
                            reason=reason,
                            new_decay=new_decay,
                        )
                        audit_id = await self._write_audit_event(
                            user_id=user_id,
                            memory_id=mem["id"],
                            event_type="EXPIRED",
                            reason=reason,
                            old_version=mem.get("version", 1),
                            new_version=mem.get("version", 1) + 1,
                        )
                        if audit_id:
                            report.audit_event_ids.append(audit_id)
                else:
                    # Memory stays active, update decayed score
                    if not dry_run:
                        await self._update_decay_score(mem, new_decay)

            surviving_final = [m for m in surviving_after_stage3 if m["id"] not in decayed_ids]
            report.active_remaining = len(surviving_final)

            # Stage 5: Re-synthesize SeekerCoreDashboard
            dashboard = self._synthesize_dashboard(user_id, surviving_final, tenant_id=tenant_id)
            if not dry_run:
                persisted = await self._persist_dashboard(dashboard)
                report.dashboard_updated = persisted
            else:
                report.dashboard_updated = False

            logger.info(
                "Dreaming complete for user %s: %d evicted, %d superseded, %d expired from decay, %d remaining.",
                user_id,
                report.evicted_count,
                report.superseded_count,
                report.decayed_count,
                report.active_remaining,
            )

        except Exception as e:
            logger.error("Dreaming failed for user %s: %s", user_id, e, exc_info=True)
            report.error = str(e)

        return report

    async def dream_all(self, dry_run: bool = False) -> list[DreamingReport]:
        """Run offline dreaming across all users with active memories."""
        tenant_id = self._get_tenant_id()
        try:
            res = await asyncio.to_thread(
                self._db.table("canonical_memories")
                .select("user_id")
                .eq("tenant_id", tenant_id)
                .eq("status", "active")
                .execute
            )
            rows = res.data if res and hasattr(res, "data") else []
            user_ids = sorted(list({r["user_id"] for r in rows if r.get("user_id")}))
        except Exception as e:
            logger.error("Failed to query active users for dreaming: %s", e)
            return []

        reports = []
        for uid in user_ids:
            rep = await self.dream(uid, dry_run=dry_run)
            reports.append(rep)
        return reports

    async def rollback(self, user_id: str, snapshot_id: str) -> bool:
        """Rollback dreaming mutations using the specified compaction snapshot."""
        try:
            tenant_id = self._get_tenant_id()
            snapshot = await self._fetch_snapshot(snapshot_id, user_id=user_id)
            if not snapshot:
                logger.warning("Snapshot %s not found for user %s", snapshot_id, user_id)
                return False

            memories_json = snapshot.get("memories_json", [])
            original_memories = _decode_snapshot_memories(memories_json)

            now = datetime.now(UTC).isoformat()
            for mem in original_memories:
                mem_id = mem.get("id")
                if not mem_id:
                    continue

                res = await asyncio.to_thread(
                    self._db.table("canonical_memories")
                    .update(
                        {
                            "status": mem.get("status", "active"),
                            "valid_to": mem.get("valid_to"),
                            "version": mem.get("version", 1),
                            "metadata": mem.get("metadata", {}),
                            "updated_at": now,
                        }
                    )
                    .eq("id", mem_id)
                    .eq("user_id", user_id)
                    .eq("tenant_id", tenant_id)
                    .execute
                )
                if not getattr(res, "data", None):
                    # In case row was hard-deleted, reinsert
                    mem_copy = dict(mem)
                    mem_copy["user_id"] = user_id
                    mem_copy["tenant_id"] = tenant_id
                    mem_copy["status"] = "active"
                    await asyncio.to_thread(
                        self._db.table("canonical_memories").insert(mem_copy).execute
                    )

            logger.info("Rollback completed for user %s from snapshot %s", user_id, snapshot_id)
            return True

        except Exception as e:
            logger.error("Rollback failed for user %s: %s", user_id, e, exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Stage 1: Snapshot Helpers
    # ------------------------------------------------------------------

    async def _create_snapshot(self, user_id: str, memories: list[dict]) -> Optional[str]:
        try:
            snapshot_data = {
                "user_id": user_id,
                "tenant_id": self._get_tenant_id(),
                "memories_json": json.loads(json.dumps(memories, default=str)),
                "created_at": datetime.now(UTC).isoformat(),
            }
            res = await asyncio.to_thread(
                self._db.table(SNAPSHOT_TABLE).insert(snapshot_data).execute
            )
            if res and hasattr(res, "data") and res.data:
                return res.data[0].get("id")
            return None
        except Exception as e:
            logger.warning("Failed to create snapshot for user %s: %s", user_id, e)
            return None

    async def _fetch_snapshot(self, snapshot_id: str, user_id: str) -> Optional[dict]:
        try:
            res = await asyncio.to_thread(
                self._db.table(SNAPSHOT_TABLE)
                .select("*")
                .eq("id", snapshot_id)
                .eq("user_id", user_id)
                .eq("tenant_id", self._get_tenant_id())
                .single()
                .execute
            )
            return res.data if hasattr(res, "data") else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Stage 2: Transcript Grounding Audit Helpers
    # ------------------------------------------------------------------

    async def _load_transcripts_for_memories(
        self, memories: list[dict], user_id: str
    ) -> dict[str, list[dict]]:
        """Load conversation transcripts for all referenced conversation/message IDs."""
        conversation_ids = {
            m.get("source_conversation_id") for m in memories if m.get("source_conversation_id")
        }
        message_ids = {
            m.get("source_message_id")
            for m in memories
            if m.get("source_message_id") and not m.get("source_conversation_id")
        }

        transcripts: dict[str, list[dict]] = {}

        # 1. Fetch from chat_messages by conversation_id
        for cid in conversation_ids:
            if not cid:
                continue
            msgs: list[dict] = []
            try:
                res = await asyncio.to_thread(
                    self._db.table("chat_messages")
                    .select("id, conversation_id, role, content, created_at")
                    .eq("conversation_id", cid)
                    .order("created_at", desc=False)
                    .execute
                )
                msgs = res.data if res and hasattr(res, "data") else []
            except Exception:
                msgs = []

            # Fallback to messages table if chat_messages returned nothing
            if not msgs:
                try:
                    res_m = await asyncio.to_thread(
                        self._db.table("messages")
                        .select("id, conversation_id, role, content, created_at")
                        .eq("conversation_id", cid)
                        .order("created_at", desc=False)
                        .execute
                    )
                    msgs = res_m.data if res_m and hasattr(res_m, "data") else []
                except Exception:
                    pass

            transcripts[cid] = msgs

        # 2. Fetch standalone message_ids
        for mid in message_ids:
            if not mid:
                continue
            msgs = []
            try:
                res = await asyncio.to_thread(
                    self._db.table("chat_messages")
                    .select("id, conversation_id, role, content, created_at")
                    .eq("id", mid)
                    .limit(1)
                    .execute
                )
                msgs = res.data if res and hasattr(res, "data") else []
            except Exception:
                msgs = []
            if not msgs:
                try:
                    res_m = await asyncio.to_thread(
                        self._db.table("messages")
                        .select("id, conversation_id, role, content, created_at")
                        .eq("id", mid)
                        .limit(1)
                        .execute
                    )
                    msgs = res_m.data if res_m and hasattr(res_m, "data") else []
                except Exception:
                    pass
            transcripts[mid] = msgs

        return transcripts

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract meaningful content keywords for transcript grounding verification."""
        clean_words = re.findall(r"\b[a-zA-Z0-9']+\b", text.lower())
        return [w for w in clean_words if len(w) >= 3 and w not in _STOPWORDS]

    def _audit_transcript_grounding(
        self, memory: dict, transcript_messages: list[dict]
    ) -> tuple[bool, str]:
        """Audit whether memory is grounded in transcripts or contradicts user utterances."""
        # USER_EXPLICIT without transcript source is user-supplied directly via profile/settings
        if (
            memory.get("memory_type") == "USER_EXPLICIT"
            and not memory.get("source_conversation_id")
            and not memory.get("source_message_id")
        ):
            return True, ""

        # If source conversation or message was specified, but transcripts are entirely empty
        if (
            memory.get("source_conversation_id") or memory.get("source_message_id")
        ) and not transcript_messages:
            return False, "dreamer_evicted_no_transcript_grounding"

        user_utterances = [
            m.get("content", "") for m in transcript_messages if m.get("role") in ("user", "seeker")
        ]
        all_utterances = [m.get("content", "") for m in transcript_messages]
        user_text = " ".join(user_utterances).lower()
        all_text = " ".join(all_utterances).lower()

        stmt = memory.get("statement", "")
        norm_stmt = memory.get("normalized_statement") or stmt
        keywords = self._extract_keywords(norm_stmt)
        if not keywords:
            keywords = self._extract_keywords(stmt)

        # 1. Contradiction Detection against user messages:
        # Check for explicit negation of the stated claim in user utterances
        for kw in keywords:
            neg_pattern = rf"\b(not|never|no|don't|dont|do not|stopped|quit|cannot|can't)\s+(?:[\w']+\s+){{0,3}}\b{re.escape(kw)}\b"
            if re.search(neg_pattern, user_text):
                return False, "dreamer_evicted_no_transcript_grounding"

        # 2. Zero Grounding Check:
        # At least one meaningful keyword from the claim must appear in the transcript
        if keywords:
            grounded = [kw for kw in keywords if kw in all_text]
            if len(grounded) == 0:
                return False, "dreamer_evicted_no_transcript_grounding"

        return True, ""

    # ------------------------------------------------------------------
    # Stage 3: Contradiction & Temporal Evolution Helpers
    # ------------------------------------------------------------------

    def _detect_temporal_conflicts(
        self, memories: list[dict], transcripts: dict[str, list[dict]]
    ) -> list[tuple[dict, dict]]:
        """Identify pairs of conflicting memories where older should be superseded by newer.

        Returns list of (older_memory, newer_memory).
        """
        conflicts: list[tuple[dict, dict]] = []
        handled_pairs: set[tuple[str, str]] = set()

        # 1. Conflicts by fact_key
        fact_key_groups: dict[str, list[dict]] = {}
        for m in memories:
            fk = m.get("fact_key")
            if fk:
                fact_key_groups.setdefault(fk, []).append(m)

        for group in fact_key_groups.values():
            if len(group) > 1:
                # Sort by timestamp ascending
                sorted_group = sorted(
                    group,
                    key=lambda x: self._get_memory_timestamp(x, transcripts),
                )
                newest = sorted_group[-1]
                for older in sorted_group[:-1]:
                    pair_key = (older["id"], newest["id"])
                    if pair_key not in handled_pairs:
                        handled_pairs.add(pair_key)
                        conflicts.append((older, newest))

        # 2. Semantic/lexical conflicts without shared fact_key
        n = len(memories)
        for i in range(n):
            m1 = memories[i]
            if m1.get("fact_key"):
                continue
            s1 = (m1.get("normalized_statement") or m1.get("statement", "")).lower()
            ts1 = self._get_memory_timestamp(m1, transcripts)

            for j in range(i + 1, n):
                m2 = memories[j]
                if m2.get("fact_key"):
                    continue
                s2 = (m2.get("normalized_statement") or m2.get("statement", "")).lower()
                ts2 = self._get_memory_timestamp(m2, transcripts)

                ratio = difflib.SequenceMatcher(None, s1, s2).ratio()
                if 0.75 <= ratio < 1.0:
                    # Conflicting claims on the same topic
                    older, newer = (m1, m2) if ts1 <= ts2 else (m2, m1)
                    pair_key = (older["id"], newer["id"])
                    if pair_key not in handled_pairs:
                        handled_pairs.add(pair_key)
                        conflicts.append((older, newer))

        return conflicts

    def _get_memory_timestamp(self, mem: dict, transcripts: dict[str, list[dict]]) -> float:
        """Derive the chronological timestamp of a memory from transcript or timestamps."""
        conv_id = mem.get("source_conversation_id")
        msg_id = mem.get("source_message_id")

        if conv_id and conv_id in transcripts:
            msgs = transcripts[conv_id]
            if msg_id:
                for m in msgs:
                    if str(m.get("id")) == str(msg_id) and m.get("created_at"):
                        ts = self._parse_iso_to_ts(m["created_at"])
                        if ts > 0:
                            return ts
            if msgs:
                msg_ts = [
                    self._parse_iso_to_ts(m.get("created_at")) for m in msgs if m.get("created_at")
                ]
                if msg_ts:
                    return max(msg_ts)

        for key in ("valid_from", "created_at", "last_confirmed_at", "updated_at"):
            val = mem.get(key)
            if val:
                ts = self._parse_iso_to_ts(val)
                if ts > 0:
                    return ts

        return 0.0

    def _parse_iso_to_ts(self, val: Any) -> float:
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, datetime):
            return val.timestamp()
        if isinstance(val, str) and val.strip():
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                return dt.timestamp()
            except Exception:
                pass
        return 0.0

    # ------------------------------------------------------------------
    # Stage 4: Mathematical Decay Helpers
    # ------------------------------------------------------------------

    def _get_decay_score(self, mem: dict) -> float:
        if mem.get("decay_score") is not None:
            try:
                return float(mem["decay_score"])
            except (ValueError, TypeError):
                pass
        meta = mem.get("metadata") or {}
        if meta.get("decay_score") is not None:
            try:
                return float(meta["decay_score"])
            except (ValueError, TypeError):
                pass
        return 1.0

    async def _update_decay_score(self, mem: dict, new_decay: float) -> bool:
        meta = dict(mem.get("metadata") or {})
        meta["decay_score"] = new_decay
        now = datetime.now(UTC).isoformat()
        payload: dict[str, Any] = {
            "metadata": meta,
            "updated_at": now,
        }
        if "decay_score" in mem:
            payload["decay_score"] = new_decay

        try:
            await asyncio.to_thread(
                self._db.table("canonical_memories")
                .update(payload)
                .eq("id", mem["id"])
                .eq("user_id", mem["user_id"])
                .eq("tenant_id", self._get_tenant_id())
                .execute
            )
            return True
        except Exception as e:
            logger.warning("Failed to update decay score for %s: %s", mem.get("id"), e)
            return False

    # ------------------------------------------------------------------
    # Stage 5: SeekerCoreDashboard Synthesis Helpers
    # ------------------------------------------------------------------

    def _synthesize_dashboard(
        self, user_id: str, active_memories: list[dict], tenant_id: str = "oneness"
    ) -> SeekerCoreDashboard:
        """Compile top surviving memories into a SeekerCoreDashboard."""
        sorted_mems = sorted(
            active_memories,
            key=lambda m: (
                float(m.get("importance", 0.5)),
                float(m.get("confidence", 0.75)),
                self._get_decay_score(m),
            ),
            reverse=True,
        )

        goals = [
            m["statement"]
            for m in sorted_mems
            if m.get("memory_type") == "GOAL" or "goal" in (m.get("fact_key") or "")
        ]
        practices = [
            m["statement"]
            for m in sorted_mems
            if any(
                w in (m.get("statement") or "").lower()
                for w in ("meditat", "breath", "sadhana", "practice", "yoga")
            )
        ]
        preferences = [
            m["statement"]
            for m in sorted_mems
            if m.get("memory_type") == "PREFERENCE" or "prefer" in (m.get("fact_key") or "")
        ]

        themes = []
        for m in sorted_mems:
            fk = m.get("fact_key")
            if fk and ":" in fk:
                theme = fk.split(":", 1)[1].replace("_", " ")
                if theme not in themes:
                    themes.append(theme)

        summary_parts = []
        if goals:
            summary_parts.append(f"Focus: {goals[0]}")
        if practices:
            summary_parts.append(f"Practice: {practices[0]}")
        summary = (
            "; ".join(summary_parts) if summary_parts else "Active seeker on the spiritual path."
        )

        return SeekerCoreDashboard(
            user_id=user_id,
            tenant_id=tenant_id,
            dominant_themes=themes[:5],
            key_goals=goals[:5],
            core_practices=practices[:5],
            preferences=preferences[:5],
            top_memories=[m["statement"] for m in sorted_mems[:7]],
            summary=summary,
        )

    async def _persist_dashboard(self, dashboard: SeekerCoreDashboard) -> bool:
        """Upsert SeekerCoreDashboard content into guru_core_memory."""
        content = dashboard.to_core_content()
        payload = {
            "user_id": dashboard.user_id,
            "tenant_id": dashboard.tenant_id,
            "content": content[:2048],
            "updated_at": datetime.now(UTC).isoformat(),
        }
        try:
            await asyncio.to_thread(
                self._db.table("guru_core_memory")
                .upsert(payload, on_conflict="user_id,tenant_id")
                .execute
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to persist SeekerCoreDashboard for user %s: %s",
                dashboard.user_id,
                e,
            )
            return False

    # ------------------------------------------------------------------
    # Common DB Helpers
    # ------------------------------------------------------------------

    async def _fetch_active_memories(self, user_id: str) -> list[dict]:
        res = await asyncio.to_thread(
            self._db.table("canonical_memories")
            .select("*")
            .eq("user_id", user_id)
            .eq("tenant_id", self._get_tenant_id())
            .eq("status", "active")
            .order("importance", desc=True)
            .execute
        )
        return res.data if res and hasattr(res, "data") else []

    async def _update_memory_status(
        self,
        mem: dict,
        new_status: str,
        reason: str,
        new_decay: Optional[float] = None,
    ) -> bool:
        now = datetime.now(UTC).isoformat()
        old_version = mem.get("version", 1)
        meta = dict(mem.get("metadata") or {})
        if new_decay is not None:
            meta["decay_score"] = new_decay

        payload: dict[str, Any] = {
            "status": new_status,
            "valid_to": now,
            "updated_at": now,
            "version": old_version + 1,
            "metadata": meta,
        }
        if new_decay is not None and "decay_score" in mem:
            payload["decay_score"] = new_decay

        try:
            await asyncio.to_thread(
                self._db.table("canonical_memories")
                .update(payload)
                .eq("id", mem["id"])
                .eq("user_id", mem["user_id"])
                .eq("tenant_id", self._get_tenant_id())
                .execute
            )
            return True
        except Exception as e:
            logger.error("Failed to update status for memory %s: %s", mem.get("id"), e)
            return False

    async def _write_audit_event(
        self,
        user_id: str,
        memory_id: str,
        event_type: str,
        reason: str,
        actor: str = "dreamer",
        old_version: Optional[int] = None,
        new_version: Optional[int] = None,
    ) -> Optional[str]:
        event_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        try:
            await asyncio.to_thread(
                self._db.table("canonical_memory_events")
                .insert(
                    {
                        "id": event_id,
                        "user_id": user_id,
                        "tenant_id": self._get_tenant_id(),
                        "memory_id": memory_id,
                        "event_type": event_type,
                        "actor": actor,
                        "old_version": old_version,
                        "new_version": new_version,
                        "reason": reason,
                        "created_at": now,
                    }
                )
                .execute
            )
            return event_id
        except Exception as e:
            logger.warning("Failed to write audit event for memory %s: %s", memory_id, e)
            return None


def create_dreamer(
    supabase_client: Any,
    llm_service: Optional[Any] = None,
    tenant_id: Optional[str] = None,
) -> MemoryDreamer:
    """Factory function to instantiate MemoryDreamer."""
    return MemoryDreamer(
        supabase_client=supabase_client,
        llm_service=llm_service,
        tenant_id=tenant_id,
    )
