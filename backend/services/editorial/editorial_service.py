"""Editorial Intelligence Service — Research Dossiers, Content Gap Discovery, Claim-Mapped Scripts & Approvals.

Treats Editorial Intelligence as a first-class governed workflow:
  Idea -> Research -> Evidence Collection -> Brief -> Outline -> Script -> Review -> Approved -> Published

Invariants:
  - Every attributed quote or paraphrase is verified against canonical evidence via ClaimVerificationService.
  - Strictly separates exact_quote, faithful_paraphrase, editorial_narration, ai_explanation, proposed_connection.
  - Content gap discovery explicitly accounts for corpus ingestion completeness (never mistakes uningested
    books/videos for "teachers never spoke about this").
  - Human editorial approval is mandatory before transition to ``approved`` or ``published``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from domain.evidence_contract import (
    ClaimEvidenceMapping,
    ClaimVerificationReport,
    EpistemicCategory,
    EvidenceCandidate,
)
from services.editorial.editorial_store import EditorialStore, InMemoryEditorialStore
from services.evidence_adapters.claim_verifier import ClaimVerificationService
from services.guru_registry import default_founders_label

EditorialStage = Literal[
    "idea",
    "research",
    "evidence_collection",
    "brief",
    "outline",
    "script",
    "review",
    "approved",
    "published",
    "archived",
]

ScriptBlockType = Literal[
    "exact_quote",
    "faithful_paraphrase",
    "editorial_narration",
    "ai_explanation",
    "proposed_connection",
]

_BLOCK_TO_EPISTEMIC: dict[ScriptBlockType, EpistemicCategory] = {
    "exact_quote": EpistemicCategory.VERBATIM_EVIDENCE,
    "faithful_paraphrase": EpistemicCategory.PARAPHRASE,
    "editorial_narration": EpistemicCategory.EDITORIAL_NARRATION,
    "ai_explanation": EpistemicCategory.INTERPRETATION,
    "proposed_connection": EpistemicCategory.SYNTHESIS,
}


class ClipRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source_title: str
    source_url: str
    source_type: str
    teacher_id: str | None = None
    start_time: float | None = None
    end_time: float | None = None
    page_number: int | None = None
    excerpt: str
    corroborating_sources: list[str] = Field(default_factory=list)


class LaneResults(list):  # type: ignore[type-arg]
    """Search result list that also carries per-lane failure messages."""

    lane_errors: list[str]

    def __init__(self, items: Any = (), lane_errors: list[str] | None = None) -> None:
        super().__init__(items)
        self.lane_errors = list(lane_errors or [])


class EditorialDossier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dossier_id: str
    topic: str
    objective: str = ""
    evidence_items: list[EvidenceCandidate]
    clip_recommendations: list[ClipRecommendation]
    concept_connections: list[dict[str, Any]] = Field(default_factory=list)
    existing_coverage_count: int = 0
    teacher_coverage: dict[str, int] = Field(default_factory=dict)
    source_type_coverage: dict[str, int] = Field(default_factory=dict)
    underexplored_angles: list[str] = Field(default_factory=list)
    provenance_versions: dict[str, str] = Field(default_factory=dict)
    lane_errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ContentOpportunity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    opportunity_type: Literal[
        "high_demand_low_coverage", "cross_source_synthesis", "missing_source_ingestion"
    ]
    seeker_query_count: int = 0
    abstain_rate: float = 0.0
    indexed_evidence_count: int = 0
    ingestion_completeness_note: str
    rationale: str
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    proposed_angle: str


class ScriptBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_id: str
    block_type: ScriptBlockType
    text: str
    teacher_attributed: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    timestamp_ref: str | None = None


class EditorialScript(BaseModel):
    model_config = ConfigDict(extra="forbid")

    script_id: str
    title: str
    topic: str
    blocks: list[ScriptBlock]
    verification: ClaimVerificationReport


class EditorialBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brief_id: str
    topic: str
    target_format: str = "youtube_video"
    core_thesis: str
    audience_need: str
    primary_evidence_ids: list[str] = Field(default_factory=list)
    differentiating_angle: str
    guardrails: list[str] = Field(
        default_factory=lambda: [
            f"Keep exact quotations verbatim and properly attributed to {default_founders_label(' or ')}.",
            "Label editorial narration and proposed synthesis distinctly from original teacher statements.",
        ]
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OutlineSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int
    heading: str
    epistemic_role: ScriptBlockType
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    notes: str = ""


class EditorialOutline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outline_id: str
    title: str
    topic: str
    sections: list[OutlineSection]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EditorialProject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    title: str
    topic: str
    objective: str = ""
    target_format: str = "youtube_video"
    status: EditorialStage = "idea"
    dossier: EditorialDossier | None = None
    brief: EditorialBrief | None = None
    outline: EditorialOutline | None = None
    script: EditorialScript | None = None
    author_id: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    approval_notes: str = ""
    published_at: datetime | None = None
    audit_log: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def _norm(user_id: str | None) -> str:
    return (user_id or "").strip().casefold()


class EditorialApprovalError(ValueError):
    """Raised when an approval violates human-review or claim-verification invariants."""


class EditorialIntelligenceService:
    """Orchestrates editorial research, content discovery, script verification, and approvals."""

    def __init__(
        self,
        *,
        search_fn: Callable[[str, str | None, int], list[EvidenceCandidate]],
        concept_graph_fn: Callable[[list[str]], list[dict[str, Any]]] | None = None,
        seeker_demand_fn: Callable[[], list[dict[str, Any]]] | None = None,
        ingestion_status_fn: Callable[[], dict[str, Any]] | None = None,
        verifier: ClaimVerificationService | None = None,
        provenance_versions: dict[str, str] | None = None,
        store: EditorialStore | None = None,
    ) -> None:
        self._search_fn = search_fn
        self._concept_graph_fn = concept_graph_fn
        self._seeker_demand_fn = seeker_demand_fn
        self._ingestion_status_fn = ingestion_status_fn
        self._verifier = verifier or ClaimVerificationService()
        self._provenance = provenance_versions or {}
        self._store: EditorialStore = store or InMemoryEditorialStore()

    def generate_dossier(
        self,
        *,
        topic: str,
        objective: str = "",
        teacher_scope: str | None = None,
        max_evidence: int = 20,
    ) -> EditorialDossier:
        evidence = self._search_fn(topic, teacher_scope, max_evidence)
        lane_errors = list(getattr(evidence, "lane_errors", []))
        clips: list[ClipRecommendation] = []
        teacher_counts: dict[str, int] = {}
        type_counts: dict[str, int] = {}
        concepts: list[str] = []

        for ev in evidence:
            tid = ev.teacher_id or "unattributed"
            teacher_counts[tid] = teacher_counts.get(tid, 0) + 1
            type_counts[ev.source_type] = type_counts.get(ev.source_type, 0) + 1
            for c in ev.concepts:
                if c not in concepts:
                    concepts.append(c)
            clips.append(
                ClipRecommendation(
                    evidence_id=ev.evidence_id,
                    source_title=ev.source_title or ev.source_url,
                    source_url=ev.source_url,
                    source_type=ev.source_type,
                    teacher_id=ev.teacher_id,
                    start_time=ev.start_time,
                    end_time=ev.end_time,
                    page_number=ev.page_number,
                    excerpt=ev.text[:400],
                    corroborating_sources=ev.corroborating_sources,
                )
            )

        graph_edges = (
            self._concept_graph_fn(concepts[:6] or [topic]) if self._concept_graph_fn else []
        )
        angles: list[str] = []
        if "book" not in type_counts:
            angles.append(
                "Cross-reference relevant chapters from The Four Sacred Secrets / Sufkor (books not yet in active first-person index)."
            )
        if len(teacher_counts) > 1:
            angles.append(
                f"Highlight complementary perspectives across {default_founders_label(' and ')} with explicit source citations."
            )
        if graph_edges:
            angles.append(
                f"Explore {len(graph_edges)} connected ontology relationships across related concepts."
            )

        return EditorialDossier(
            dossier_id=str(uuid.uuid4()),
            topic=topic,
            objective=objective,
            evidence_items=evidence,
            clip_recommendations=clips,
            concept_connections=graph_edges,
            existing_coverage_count=len({ev.source_id for ev in evidence}),
            teacher_coverage=teacher_counts,
            source_type_coverage=type_counts,
            underexplored_angles=angles,
            provenance_versions=dict(self._provenance),
            lane_errors=lane_errors,
        )

    def discover_opportunities(self, *, limit: int = 10) -> list[ContentOpportunity]:
        demand_rows = self._seeker_demand_fn() if self._seeker_demand_fn else []
        ingest_meta = self._ingestion_status_fn() if self._ingestion_status_fn else {}
        books_indexed = bool(ingest_meta.get("books_indexed", False))
        completeness_note = (
            "All registered source formats (videos + books) indexed."
            if books_indexed
            else "Ingestion incomplete: books/websites not yet fully indexed in first-person store; absence may reflect indexing gaps rather than lack of teachings."
        )

        opportunities: list[ContentOpportunity] = []
        for row in demand_rows[:limit]:
            topic = str(row.get("topic") or "").strip()
            if not topic:
                continue
            evidence = self._search_fn(topic, None, 8)
            q_cnt = int(row.get("query_count", 0))
            abstain_rate = float(row.get("abstain_rate", 0.0))
            ev_cnt = len(evidence)

            if ev_cnt == 0 and not books_indexed:
                opp_type = "missing_source_ingestion"
                rationale = f"{q_cnt} seeker queries with 0 indexed first-person hits; verify uningested books/talks before concluding a teaching gap."
            elif abstain_rate >= 0.4 or ev_cnt <= 2:
                opp_type = "high_demand_low_coverage"
                rationale = f"{q_cnt} seeker queries (abstain rate {abstain_rate:.0%}) backed by only {ev_cnt} indexed evidence passages."
            else:
                opp_type = "cross_source_synthesis"
                rationale = f"{q_cnt} seeker queries with {ev_cnt} verified passages across {len({e.source_id for e in evidence})} sources."

            opportunities.append(
                ContentOpportunity(
                    topic=topic,
                    opportunity_type=opp_type,
                    seeker_query_count=q_cnt,
                    abstain_rate=abstain_rate,
                    indexed_evidence_count=ev_cnt,
                    ingestion_completeness_note=completeness_note,
                    rationale=rationale,
                    supporting_evidence_ids=[e.evidence_id for e in evidence[:5]],
                    proposed_angle=f"Grounded teaching deep-dive on '{topic}' bridging verified talks and seeker questions.",
                )
            )
        return opportunities

    def fact_check_blocks(
        self,
        blocks: list[ScriptBlock],
        evidence_pool: list[EvidenceCandidate],
        *,
        expected_source_versions: dict[str, str] | None = None,
    ) -> ClaimVerificationReport:
        claims = [
            ClaimEvidenceMapping(
                claim_id=b.block_id,
                claim_text=b.text,
                epistemic_category=_BLOCK_TO_EPISTEMIC[b.block_type],
                teacher_attributed=b.teacher_attributed,
                evidence_ids=b.evidence_ids,
            )
            for b in blocks
        ]
        return self._verifier.verify_claims(
            claims,
            evidence_pool,
            expected_source_versions=expected_source_versions,
        )

    def build_verified_script(
        self,
        *,
        title: str,
        topic: str,
        blocks: list[ScriptBlock],
        evidence_pool: list[EvidenceCandidate],
    ) -> EditorialScript:
        report = self.fact_check_blocks(blocks, evidence_pool)
        return EditorialScript(
            script_id=str(uuid.uuid4()),
            title=title,
            topic=topic,
            blocks=blocks,
            verification=report,
        )

    # --- Project Workflow State Machine ---

    def create_project(
        self,
        *,
        title: str,
        topic: str,
        objective: str = "",
        target_format: str = "youtube_video",
        author_id: str | None = None,
    ) -> EditorialProject:
        author = author_id.strip() if author_id and author_id.strip() else None
        proj = EditorialProject(
            project_id=str(uuid.uuid4()),
            title=title,
            topic=topic,
            objective=objective,
            target_format=target_format,
            status="idea",
            author_id=author,
        )
        entry = self._audit_entry("project_created", author, None, "idea", proj.created_at)
        proj = proj.model_copy(update={"audit_log": [entry]})
        self._store.save(proj)
        self._store.append_audit(proj.project_id, entry)
        return proj

    def get_project(self, project_id: str) -> EditorialProject | None:
        return self._store.get(project_id)

    def list_projects(self) -> list[EditorialProject]:
        return self._store.list()

    @staticmethod
    def _audit_entry(
        event: str,
        actor_id: str | None,
        from_state: str | None,
        to_state: str,
        at: datetime,
        **detail: Any,
    ) -> dict[str, Any]:
        return {
            "event": event,
            "at": at.isoformat(),
            "actor_id": actor_id,
            "from_state": from_state,
            "to_state": to_state,
            **detail,
        }

    def _commit(
        self,
        proj: EditorialProject,
        event: str,
        actor_id: str | None,
        updates: dict[str, Any],
        **detail: Any,
    ) -> EditorialProject:
        """Apply a state transition, append an audit entry, persist. Store errors propagate."""
        now = datetime.now(UTC)
        to_state = updates.get("status", proj.status)
        entry = self._audit_entry(event, actor_id, proj.status, to_state, now, **detail)
        updated = proj.model_copy(
            update={**updates, "audit_log": [*proj.audit_log, entry], "updated_at": now}
        )
        self._store.save(updated)
        self._store.append_audit(proj.project_id, entry)
        return updated

    def generate_brief(
        self,
        *,
        dossier: EditorialDossier,
        target_format: str = "youtube_video",
        audience_need: str = "",
    ) -> EditorialBrief:
        """Synthesize a sourced editorial brief grounded strictly in dossier evidence."""
        angle = (
            dossier.underexplored_angles[0]
            if dossier.underexplored_angles
            else f"Examine '{dossier.topic}' through verbatim source citations."
        )
        return EditorialBrief(
            brief_id=str(uuid.uuid4()),
            topic=dossier.topic,
            target_format=target_format,
            core_thesis=dossier.objective
            or f"Explore '{dossier.topic}' grounded in verified Ekam teachings.",
            audience_need=audience_need
            or "Seekers asking practical and existential questions on this theme.",
            primary_evidence_ids=[ev.evidence_id for ev in dossier.evidence_items[:6]],
            differentiating_angle=angle,
        )

    def generate_outline(
        self,
        *,
        title: str,
        dossier: EditorialDossier,
        brief: EditorialBrief | None = None,
    ) -> EditorialOutline:
        """Generate a structured, evidence-linked editorial outline before script drafting."""
        ev_ids = [ev.evidence_id for ev in dossier.evidence_items]
        sections = [
            OutlineSection(
                order=1,
                heading="Opening Framing (Editorial Narration)",
                epistemic_role="editorial_narration",
                supporting_evidence_ids=[],
                notes=brief.audience_need
                if brief
                else f"Frame why '{dossier.topic}' matters to seekers.",
            ),
            OutlineSection(
                order=2,
                heading="Primary Teacher Quotations",
                epistemic_role="exact_quote",
                supporting_evidence_ids=ev_ids[:3],
                notes="Present exact teacher words with timestamp/page citations.",
            ),
            OutlineSection(
                order=3,
                heading="Cross-Source Synthesis & Context",
                epistemic_role="proposed_connection",
                supporting_evidence_ids=ev_ids[3:6] or ev_ids[:2],
                notes="Clearly label cross-talk or book-to-video synthesis as editorial interpretation.",
            ),
        ]
        return EditorialOutline(
            outline_id=str(uuid.uuid4()),
            title=title,
            topic=dossier.topic,
            sections=sections,
        )

    def attach_dossier(
        self, project_id: str, dossier: EditorialDossier, *, actor_id: str | None = None
    ) -> EditorialProject:
        return self._commit(
            self._require_project(project_id),
            "dossier_attached",
            actor_id,
            {"dossier": dossier, "status": "research"},
            evidence_count=len(dossier.evidence_items),
        )

    def attach_brief(
        self, project_id: str, brief: EditorialBrief, *, actor_id: str | None = None
    ) -> EditorialProject:
        return self._commit(
            self._require_project(project_id),
            "brief_attached",
            actor_id,
            {"brief": brief, "status": "brief"},
            brief_id=brief.brief_id,
        )

    def attach_outline(
        self, project_id: str, outline: EditorialOutline, *, actor_id: str | None = None
    ) -> EditorialProject:
        return self._commit(
            self._require_project(project_id),
            "outline_attached",
            actor_id,
            {"outline": outline, "status": "outline"},
            outline_id=outline.outline_id,
        )

    def attach_script(
        self, project_id: str, script: EditorialScript, *, actor_id: str | None = None
    ) -> EditorialProject:
        return self._commit(
            self._require_project(project_id),
            "script_attached",
            actor_id,
            {"script": script, "status": "review"},
            passed=script.verification.passed,
        )

    def approve_project(
        self, project_id: str, *, reviewer_id: str, notes: str = ""
    ) -> EditorialProject:
        """Mandatory human approval gate — refuses if script or claim verification failed."""
        proj = self._require_project(project_id)
        if not reviewer_id or not reviewer_id.strip():
            raise EditorialApprovalError("Human reviewer_id is mandatory for approval.")
        if reviewer_id.strip().lower() in {"ai", "llm", "system", "auto"}:
            raise EditorialApprovalError(
                "Autonomous AI approval is forbidden; human reviewer required."
            )
        if proj.script is None:
            raise EditorialApprovalError("Cannot approve project without a claim-mapped script.")
        if not proj.script.verification.passed:
            raise EditorialApprovalError(
                f"Cannot approve project with failing claim verification: {proj.script.verification.summary}"
            )
        reviewer = reviewer_id.strip()
        author = _norm(proj.author_id)
        if not author:
            raise EditorialApprovalError(
                "Cannot approve a project with no recorded author; author/approver separation "
                "cannot be verified."
            )
        contributors = {author} | {
            _norm(e.get("actor_id"))
            for e in proj.audit_log
            if str(e.get("event", "")).endswith("_attached")
        }
        if _norm(reviewer) in contributors:
            raise EditorialApprovalError(
                "Approver must differ from the project's author and from anyone who attached "
                "content to it; ask another reviewer to approve."
            )
        now = datetime.now(UTC)
        return self._commit(
            proj,
            "human_approved",
            reviewer,
            {
                "status": "approved",
                "approved_by": reviewer,
                "approved_at": now,
                "approval_notes": notes,
            },
            reviewer_id=reviewer,
        )

    def publish_project(self, project_id: str, *, publisher_id: str) -> EditorialProject:
        """Refuse publication unless a human has approved a passing claim-verified script."""
        proj = self._require_project(project_id)
        if proj.status != "approved" or not proj.approved_by:
            raise EditorialApprovalError(
                "Publication blocked: human editorial approval is mandatory before publishing."
            )
        return self._commit(
            proj,
            "published",
            publisher_id,
            {"status": "published", "published_at": datetime.now(UTC)},
            publisher_id=publisher_id,
        )

    def _require_project(self, project_id: str) -> EditorialProject:
        proj = self._store.get(project_id)
        if proj is None:
            raise KeyError(f"Editorial project not found: {project_id}")
        return proj
