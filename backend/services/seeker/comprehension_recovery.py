"""Seeker Comprehension Recovery Workflow & Version-Isolated Cache Keys.

Implements the 10-step comprehension recovery workflow (Part 8):
  1. Detect explicit confusion / clarification request.
  2. Identify the target concept that was not understood.
  3. Retrieve the prior answer and its supporting evidence IDs.
  4. Retrieve seeker preferences and prior comprehension signals (consent-gated).
  5. Search for alternative verified explanations (excluding prior evidence IDs).
  6. Select a distinct pedagogical strategy (simpler framing / teacher parable / step-by-step).
  7. Strictly separate teacher examples/quotes from AI-created analogies.
  8. Validate the new explanation against canonical evidence via ClaimVerificationService.
  9. Include a gentle comprehension feedback prompt.
  10. Record the learning/comprehension signal under user_id + tenant_id isolation.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from domain.evidence_contract import (
    ClaimEvidenceMapping,
    ClaimVerificationReport,
    EpistemicCategory,
    EvidenceCandidate,
)
from services.evidence_adapters.claim_verifier import ClaimVerificationService

logger = logging.getLogger(__name__)

ExplanationStrategy = Literal["simpler_language", "teacher_parable", "step_by_step", "contrastive"]


class ExplanationSegment(BaseModel):
    """Typed response unit enforcing strict separation of teacher evidence vs AI analogy."""

    model_config = ConfigDict(extra="forbid")

    category: EpistemicCategory
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    teacher_attributed: str | None = None
    source_reference: str | None = None


class ComprehensionRecoveryResult(BaseModel):
    """Structured output from the Seeker Comprehension Recovery workflow."""

    model_config = ConfigDict(extra="forbid")

    concept: str
    strategy_used: ExplanationStrategy
    segments: list[ExplanationSegment]
    evidence_used: list[EvidenceCandidate]
    verification: ClaimVerificationReport
    feedback_prompt: str
    learning_signal_recorded: bool = False


def build_isolated_cache_key(
    *,
    query: str,
    corpus_version: str,
    embedding_version: str,
    retrieval_config_hash: str,
    ontology_version: str,
    model_version: str,
    prompt_version: str,
    user_id: str | None = None,
    tenant_id: str | None = None,
    personal_memory_version: str | None = None,
    incognito: bool = False,
) -> str | None:
    """Build strictly isolated cache keys separating shared teaching vs personalized caches.

    Returns ``None`` for incognito or unversioned personal sessions so private turns
    never pollute shared caches or leak across tenants/seekers.
    """
    if incognito:
        return None
    q_hash = hashlib.sha256(" ".join((query or "").lower().split()).encode("utf-8")).hexdigest()[
        :24
    ]
    base_dims = (
        f"c={corpus_version}|e={embedding_version}|r={retrieval_config_hash}|"
        f"o={ontology_version}|m={model_version}|p={prompt_version}"
    )
    if user_id and user_id not in {"anonymous", "anon"}:
        if not tenant_id or not personal_memory_version:
            # Fail closed on missing tenant or memory version: bypass cache rather than risk leakage
            return None
        scope = hashlib.sha256(
            f"{tenant_id}:{user_id}:{personal_memory_version}".encode()
        ).hexdigest()[:16]
        return f"cache:seeker:v2:{scope}:{base_dims}:{q_hash}"
    return f"cache:teaching:v2:{base_dims}:{q_hash}"


class ComprehensionRecoveryService:
    """Orchestrates alternative evidence-grounded explanation when a seeker expresses confusion."""

    def __init__(
        self,
        *,
        retrieve_fn: Callable[[str, list[str]], list[EvidenceCandidate]],
        verifier: ClaimVerificationService | None = None,
        signal_sink: Callable[[dict[str, Any]], bool] | None = None,
        ai_analogy_fn: Callable[[str, list[EvidenceCandidate], ExplanationStrategy], str]
        | None = None,
    ) -> None:
        self._retrieve_fn = retrieve_fn
        self._verifier = verifier or ClaimVerificationService()
        self._signal_sink = signal_sink
        self._ai_analogy_fn = ai_analogy_fn

    def recover(
        self,
        *,
        concept: str,
        user_query: str,
        prior_evidence_ids: list[str],
        prior_strategies: list[str] | None = None,
        user_id: str | None = None,
        tenant_id: str = "oneness",
        consent_granted: bool = False,
        familiarity_level: str = "beginner",
    ) -> ComprehensionRecoveryResult:
        strategy = self._pick_strategy(prior_strategies or [], familiarity_level=familiarity_level)

        # Retrieve alternative verified explanations excluding prior evidence IDs
        candidates = self._retrieve_fn(concept or user_query, prior_evidence_ids)
        alt_candidates = [c for c in candidates if c.evidence_id not in set(prior_evidence_ids)]
        chosen_evidence = (alt_candidates or candidates)[:3]

        segments: list[ExplanationSegment] = []
        claim_mappings: list[ClaimEvidenceMapping] = []

        for idx, ev in enumerate(chosen_evidence):
            loc = (
                f"{ev.source_title or ev.source_url} ({int(ev.start_time)}s)"
                if ev.start_time is not None
                else f"{ev.source_title or ev.source_url}"
                + (f", p.{ev.page_number}" if ev.page_number is not None else "")
            )
            segments.append(
                ExplanationSegment(
                    category=EpistemicCategory.VERBATIM_EVIDENCE,
                    text=ev.text,
                    evidence_ids=[ev.evidence_id],
                    teacher_attributed=ev.teacher_id,
                    source_reference=loc.strip(),
                )
            )
            claim_mappings.append(
                ClaimEvidenceMapping(
                    claim_id=f"ev_{idx}",
                    claim_text=ev.text,
                    epistemic_category=EpistemicCategory.VERBATIM_EVIDENCE,
                    teacher_attributed=ev.teacher_id,
                    evidence_ids=[ev.evidence_id],
                )
            )

        # Optional AI-created illustrative analogy (strictly labeled as APPLICATION, never teacher quote)
        if self._ai_analogy_fn and chosen_evidence:
            analogy_text = self._ai_analogy_fn(concept, chosen_evidence, strategy).strip()
            if analogy_text:
                labeled = f"[AI Illustrative Analogy — not a teacher quote] {analogy_text}"
                segments.append(
                    ExplanationSegment(
                        category=EpistemicCategory.APPLICATION,
                        text=labeled,
                        evidence_ids=[c.evidence_id for c in chosen_evidence],
                        teacher_attributed=None,
                    )
                )
                claim_mappings.append(
                    ClaimEvidenceMapping(
                        claim_id="ai_analogy",
                        claim_text=labeled,
                        epistemic_category=EpistemicCategory.APPLICATION,
                        teacher_attributed=None,
                        evidence_ids=[c.evidence_id for c in chosen_evidence],
                    )
                )

        verification = self._verifier.verify_claims(claim_mappings, chosen_evidence)

        recorded = False
        if consent_granted and user_id and self._signal_sink is not None:
            try:
                recorded = bool(
                    self._signal_sink(
                        {
                            "user_id": user_id,
                            "tenant_id": tenant_id,
                            "concept_name": concept,
                            "evidence_id": chosen_evidence[0].evidence_id
                            if chosen_evidence
                            else None,
                            "signal_type": "confused",
                            "strategy_used": strategy,
                            "confidence": 0.75,
                        }
                    )
                )
            except Exception as exc:
                logger.debug("[ComprehensionRecovery] signal sink error: %s", exc)

        return ComprehensionRecoveryResult(
            concept=concept,
            strategy_used=strategy,
            segments=segments,
            evidence_used=chosen_evidence,
            verification=verification,
            feedback_prompt="Did this alternative perspective make the idea clearer, or would another example help?",
            learning_signal_recorded=recorded,
        )

    @staticmethod
    def _pick_strategy(
        prior_strategies: list[str], *, familiarity_level: str
    ) -> ExplanationStrategy:
        order: list[ExplanationStrategy] = (
            ["teacher_parable", "simpler_language", "step_by_step", "contrastive"]
            if familiarity_level == "beginner"
            else ["contrastive", "step_by_step", "teacher_parable", "simpler_language"]
        )
        for s in order:
            if s not in prior_strategies:
                return s
        return order[0]
