"""Deterministic first-person context harness (decision layer, no generation).

Sits between retrieval and answer rendering. It never writes teaching text: the
served answer is a deterministic concatenation of immutable source spans whose
hashes and speaker/rights gates passed. An LLM, when enabled, may only *select*
from the candidate IDs passed in; its prose is discarded.

``FIRST_PERSON_CONTEXT_HARNESS_ENABLED`` defaults to false, so wiring this into
serving is an explicit, reversible opt-in.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from domain.first_person_context import (
    AnswerRole,
    BoundaryStatus,
    CitationSpan,
    CompletenessStatus,
    HarnessDecision,
    HarnessState,
    ParentContext,
    RetrievalDecision,
    SourceSpan,
    SpeakerRole,
    clip_text_hash,
)

logger = logging.getLogger(__name__)

# Phase F5: bounded in-process counters keyed by
# ``decision|state|abstain_reason``. Prometheus scrape of /metrics is a
# separate surface; these counters are the harness-local source of truth and are
# safe to read at any time (no I/O, no locks, no user data).
_HARNESS_METRICS: dict[str, int] = {}
_HARNESS_METRICS_MAX_KEYS = 256

# Prometheus labels and local counters use only these fixed vocabularies.
_ALLOWED_ABSTAIN_REASONS = frozenset(
    {
        "no_spans",
        "cross_parent_contamination",
        "cross_guru_contamination",
        "speaker_unverified_or_not_guru",
        "rights_not_cleared",
        "source_text_hash_mismatch",
        "fragment_without_antecedent",
        "antecedent_missing",
        "boundary_uncertain",
        "answerability_no",
        "citation_alignment_failed",
        "reconstruction_failed",
    }
)
_SHADOW_OUTCOMES = frozenset(
    {"evaluated", "no_candidate", "not_configured", "timeout", "error"}
)
_SHADOW_METRICS: dict[str, int] = {}
# Prometheus series for the Grafana surface (scraped from /internal/metrics once
# Phase-D wiring lands). Optional: a missing prometheus_client is a no-op, never
# an import error on the serving path.
try:  # pragma: no cover - exercised only when prometheus_client is installed
    from prometheus_client import Counter as _Counter

    _FP_CONTEXT_DECISIONS = _Counter(
        "fp_context_harness_decisions_total",
        "First-person context harness decisions by decision, state and abstain reason",
        ["decision", "state", "abstain_reason"],
    )
    _FP_CONTEXT_SHADOW = _Counter(
        "fp_context_harness_shadow_total",
        "First-person context shadow evaluation outcomes",
        ["outcome"],
    )
except Exception:  # noqa: BLE001 - metrics are optional
    _FP_CONTEXT_DECISIONS = None  # type: ignore[assignment]
    _FP_CONTEXT_SHADOW = None  # type: ignore[assignment]


def reset_harness_metrics() -> None:
    """Clear the counters (tests, and operator use after a soak run)."""
    _HARNESS_METRICS.clear()
    _SHADOW_METRICS.clear()


def harness_metrics_snapshot() -> dict[str, int]:
    """Copy of the counters so a caller cannot mutate the registry."""
    return dict(_HARNESS_METRICS)


def shadow_metrics_snapshot() -> dict[str, int]:
    """Copy bounded shadow outcomes; never includes query or source text."""
    return dict(_SHADOW_METRICS)


def record_shadow_outcome(outcome: str) -> None:
    """Record one fixed-vocabulary shadow outcome without request-derived labels."""
    safe_outcome = outcome if outcome in _SHADOW_OUTCOMES else "error"
    _SHADOW_METRICS[safe_outcome] = _SHADOW_METRICS.get(safe_outcome, 0) + 1
    if _FP_CONTEXT_SHADOW is not None:  # pragma: no branch - optional dep
        try:
            _FP_CONTEXT_SHADOW.labels(outcome=safe_outcome).inc()
        except Exception as exc:  # noqa: BLE001 - metrics must never break serving
            logger.debug("[FPContextHarness] shadow metric increment failed: %s", exc)
    logger.info("[FPContextShadow] outcome=%s", safe_outcome)


def _bounded_abstain_reason(reason: str | None) -> str:
    if reason is None:
        return "none"
    return reason if reason in _ALLOWED_ABSTAIN_REASONS else "other"


def _record_metrics(decision: RetrievalDecision) -> None:
    reason = _bounded_abstain_reason(decision.abstain_reason)
    key = f"{decision.decision.value}|{decision.state.value}|{reason}"
    if key in _HARNESS_METRICS:
        _HARNESS_METRICS[key] += 1
    elif len(_HARNESS_METRICS) < _HARNESS_METRICS_MAX_KEYS:
        _HARNESS_METRICS[key] = 1
    if _FP_CONTEXT_DECISIONS is not None:  # pragma: no branch - optional dep
        try:
            _FP_CONTEXT_DECISIONS.labels(
                decision=decision.decision.value,
                state=decision.state.value,
                abstain_reason=reason,
            ).inc()
        except Exception as exc:  # noqa: BLE001 - metrics must never break serving
            logger.debug("[FPContextHarness] metric increment failed: %s", exc)
    logger.info(
        "[FPContextHarness] decision=%s state=%s abstain_reason=%s abstain_stage=%s "
        "state_path=%s gates=%s",
        decision.decision.value,
        decision.state.value,
        reason,
        decision.abstain_stage.value if decision.abstain_stage else None,
        ",".join(state.value for state in decision.state_path),
        ",".join(sorted(f"{k}={v}" for k, v in decision.gates.items())),
    )


CONTEXT_LABEL_EARLIER = "Earlier in this discourse"
CONTEXT_LABEL_LATER = "Later in this discourse"


@dataclass(frozen=True)
class HarnessPolicy:
    """Thresholds live here so a policy change is a reviewed diff, not a magic word."""

    max_context_spans: int = 3
    require_speaker_verified: bool = True
    require_same_parent: bool = True
    allow_fragment_with_antecedent: bool = True
    min_context_sufficiency: str = "sufficient"
    labels_enabled: bool = True
    extra: dict[str, str] = field(default_factory=dict)


def harness_enabled() -> bool:
    """Whether a wired serving path should run the context harness.

    Imported lazily so this module stays importable without app settings; the
    flag defaults to false until the fp-context collection exists.
    """
    from app.config import settings

    return bool(settings.first_person_context_harness_enabled)


def policy_from_settings() -> HarnessPolicy:
    """Policy a wired serving path must use (settings are the single source)."""
    from app.config import settings

    return HarnessPolicy(max_context_spans=max(1, int(settings.first_person_context_max_spans)))


class FirstPersonContextHarness:
    def __init__(self, policy: HarnessPolicy | None = None) -> None:
        self._policy = policy or HarnessPolicy()

    # ------------------------------------------------------------------ gates
    @staticmethod
    def _speaker_gate(spans: tuple[SourceSpan, ...], policy: HarnessPolicy) -> bool:
        for span in spans:
            if span.speaker_role is not SpeakerRole.GURU:
                return False
            if policy.require_speaker_verified and not span.speaker_verified:
                return False
        return True

    @staticmethod
    def _rights_gate(spans: tuple[SourceSpan, ...]) -> bool:
        return all(span.rights_cleared for span in spans)

    @staticmethod
    def _hash_gate(spans: tuple[SourceSpan, ...]) -> bool:
        return all(clip_text_hash(span.verbatim_text) == span.source_text_hash for span in spans)

    @staticmethod
    def _completeness_gate(spans: tuple[SourceSpan, ...], policy: HarnessPolicy) -> bool:
        if all(s.completeness_status is CompletenessStatus.COMPLETE for s in spans):
            return True
        if not policy.allow_fragment_with_antecedent:
            return False
        # A fragment is only usable when the context set also carries its antecedent.
        present_ids = {s.source_span_id for s in spans}
        fragments = [s for s in spans if s.completeness_status is CompletenessStatus.FRAGMENT]
        return all(
            s.previous_span_id is not None and s.previous_span_id in present_ids for s in fragments
        )

    @staticmethod
    def _boundary_gate(spans: tuple[SourceSpan, ...]) -> bool:
        # "uncertain" boundaries may still be served as related, never as direct.
        return all(s.boundary_status is not BoundaryStatus.UNCERTAIN for s in spans)

    def _window(self, context: ParentContext) -> tuple[SourceSpan, ...]:
        """Bounded chronological window around the first hit span.

        Centered on the first matching ``hit_span_ids`` entry (one preceding span
        when the policy allows it). Only when the parent has no hit do we fall
        back to its head. The ``max_context_spans`` bound always applies.
        """
        ordered = tuple(context.spans)
        if not ordered:
            return ()
        limit = max(1, self._policy.max_context_spans)
        hit_ids = set(context.hit_span_ids or ())
        hit_index = next(
            (index for index, span in enumerate(ordered) if span.source_span_id in hit_ids),
            None,
        )
        if hit_index is None:
            return ordered[:limit]
        # Include one preceding span whenever the bound allows it, even for an
        # even-sized window where exact centering would drop it.
        offset = 0 if limit == 1 else max(1, (limit - 1) // 2)
        start = max(0, hit_index - offset)
        end = min(len(ordered), start + limit)
        start = max(0, end - limit)
        return ordered[start:end]

    @staticmethod
    def _coreference_gate(spans: tuple[SourceSpan, ...]) -> tuple[bool, tuple[str, ...]]:
        """A pronoun-bearing span needs its antecedent inside the served set."""
        present_ids = {s.source_span_id for s in spans}
        chains: set[str] = set()
        ok = True
        for span in spans:
            if not span.coreference_chain_ids:
                continue
            chains.update(span.coreference_chain_ids)
            if span.answer_role is AnswerRole.ANTECEDENT:
                continue
            antecedent_present = any(
                other.source_span_id != span.source_span_id
                and other.answer_role is AnswerRole.ANTECEDENT
                and set(other.coreference_chain_ids) & set(span.coreference_chain_ids)
                for other in spans
            )
            if not antecedent_present:
                # Adjacent-span expansion is legitimate evidence too: a previous span
                # that is present in the set and shares the chain counts.
                previous_present = span.previous_span_id in present_ids
                if not previous_present:
                    ok = False
        return ok, tuple(sorted(chains))

    # --------------------------------------------------------------- decision
    def decide(
        self,
        context: ParentContext,
        *,
        requested_teacher: str | None = None,
        answerability: str = "indeterminate",
        selected_span_ids: tuple[str, ...] | None = None,
    ) -> RetrievalDecision:
        """Run the gate chain and record one metric + one structured trace line.

        ``selected_span_ids`` is the optional Phase-D8 structured selector
        output: span IDs only. Unknown IDs are ignored (deterministic order is
        kept) and no selector prose can ever reach the answer text.
        """
        decision = self._decide(
            context,
            requested_teacher=requested_teacher,
            answerability=answerability,
            selected_span_ids=selected_span_ids,
        )
        _record_metrics(decision)
        return decision

    def _decide(
        self,
        context: ParentContext,
        *,
        requested_teacher: str | None = None,
        answerability: str = "indeterminate",
        selected_span_ids: tuple[str, ...] | None = None,
    ) -> RetrievalDecision:
        spans = self._window(context)
        if not spans:
            return self._abstain(context, "no_spans", gates={}, state_path=())

        states: list[HarnessState] = []

        def enter(next_state: HarnessState) -> HarnessState:
            states.append(next_state)
            return next_state

        gates: dict[str, bool] = {}
        state = enter(HarnessState.GROUPED_BY_PARENT)

        if self._policy.require_same_parent and len({s.parent_unit_id for s in spans}) != 1:
            return self._abstain(
                context,
                "cross_parent_contamination",
                gates=gates,
                state=state,
                state_path=tuple(states),
            )
        state = enter(HarnessState.CONTEXT_EXPANDED)

        if selected_span_ids:
            by_id = {span.source_span_id: span for span in spans}
            if all(span_id in by_id for span_id in selected_span_ids):
                # Reading order stays chronological even when a selector returns
                # IDs out of order; duplicates collapse.
                ordered = sorted(
                    (by_id[span_id] for span_id in dict.fromkeys(selected_span_ids)),
                    key=lambda span: span.start_ms,
                )
                if ordered:
                    spans = tuple(ordered)
                gates["selector_honored"] = True
            else:
                # Fail open to the deterministic retrieval order, and say so.
                gates["selector_honored"] = False

        if len({span.guru_id for span in spans}) != 1:
            return self._abstain(
                context,
                "cross_guru_contamination",
                gates={"guru_isolation": False},
                state=state,
                state_path=tuple(states),
            )
        if spans[0].guru_id != context.parent.guru_id:
            return self._abstain(
                context,
                "cross_guru_contamination",
                gates={"guru_isolation": False},
                state=state,
                state_path=tuple(states),
            )

        teacher = (requested_teacher or context.parent.guru_id).lower()
        if teacher not in ("", "both", "all"):
            if any(s.guru_id.lower() != teacher for s in spans):
                return self._abstain(
                    context,
                    "cross_guru_contamination",
                    gates={"guru_isolation": False},
                    state=state,
                    state_path=tuple(states),
                )
        gates["guru_isolation"] = True

        gates["speaker"] = self._speaker_gate(spans, self._policy)
        state = enter(HarnessState.SPEAKER_GATE)
        if not gates["speaker"]:
            return self._abstain(
                context,
                "speaker_unverified_or_not_guru",
                gates=gates,
                state=state,
                state_path=tuple(states),
            )

        gates["rights"] = self._rights_gate(spans)
        state = enter(HarnessState.RIGHTS_GATE)
        if not gates["rights"]:
            return self._abstain(
                context,
                "rights_not_cleared",
                gates=gates,
                state=state,
                state_path=tuple(states),
            )

        gates["hash"] = self._hash_gate(spans)
        state = enter(HarnessState.HASH_GATE)
        if not gates["hash"]:
            return self._abstain(
                context,
                "source_text_hash_mismatch",
                gates=gates,
                state=state,
                state_path=tuple(states),
            )

        gates["completeness"] = self._completeness_gate(spans, self._policy)
        state = enter(HarnessState.COMPLETENESS_GATE)
        if not gates["completeness"]:
            return self._abstain(
                context,
                "fragment_without_antecedent",
                gates=gates,
                state=state,
                state_path=tuple(states),
            )

        # A firm negative verdict comes before coreference/boundary: those gates
        # only relax a candidate to "related", so checking them first could serve
        # text the answerability layer already rejected.
        gates["answerability_yes"] = answerability == "yes"
        state = enter(HarnessState.ANSWERABILITY_GATE)
        if answerability == "no":
            return self._abstain(
                context, "answerability_no", gates=gates, state=state, state_path=tuple(states)
            )

        gates["coreference"], chains = self._coreference_gate(spans)
        state = enter(HarnessState.COREFERENCE_GATE)
        if not gates["coreference"]:
            return self._related(
                context, "antecedent_missing", gates, chains, spans=spans, state=state, state_path=tuple(states)
            )

        if not self._boundary_gate(spans):
            return self._related(
                context, "boundary_uncertain", gates, chains, spans=spans, state=state, state_path=tuple(states)
            )

        cites = self._citations(spans)
        gates["citations_verified"] = self._citations_verified(spans, cites)
        state = enter(HarnessState.CITATION_AND_AUDIO_GATE)
        if not gates["citations_verified"]:
            return self._abstain(
                context,
                "citation_alignment_failed",
                gates=gates,
                state=state,
                state_path=tuple(states),
            )

        answer_text = " ".join(span.verbatim_text.strip() for span in spans)
        if not self._reconstructs_from_spans(answer_text, spans):
            return self._abstain(
                context,
                "reconstruction_failed",
                gates=gates,
                state=state,
                state_path=tuple(states),
            )

        decision = (
            HarnessDecision.SERVE_SINGLE_SPAN
            if len(spans) == 1
            else HarnessDecision.SERVE_PARENT_CONTEXT
        )
        if answerability == "indeterminate":
            decision = HarnessDecision.SERVE_RELATED_NOT_DIRECT

        return RetrievalDecision(
            decision=decision,
            state=enter(HarnessState.SERVE),
            guru_id=spans[0].guru_id,
            parent_unit_id=context.parent.parent_unit_id,
            source_span_ids=tuple(s.source_span_id for s in spans),
            context_edges_used=chains,
            speaker_boundary_passed=True,
            context_sufficiency="sufficient",
            llm_used=False,
            llm_role="none",
            answer_text_reconstructed=True,
            citations_verified=True,
            answer_text=answer_text,
            citations=cites,
            gates=gates,
            state_path=tuple(states),
        )

    # --------------------------------------------------------------- helpers
    def _citations(self, spans: tuple[SourceSpan, ...]) -> tuple[CitationSpan, ...]:
        out: list[CitationSpan] = []
        primary_start = spans[0].start_ms if spans else 0
        for index, span in enumerate(spans):
            label = None
            if self._policy.labels_enabled and index > 0:
                label = (
                    CONTEXT_LABEL_LATER
                    if span.start_ms > primary_start
                    else CONTEXT_LABEL_EARLIER
                )
            out.append(
                CitationSpan(
                    source_span_id=span.source_span_id,
                    video_id=span.video_id,
                    guru_id=span.guru_id,
                    text=span.verbatim_text,
                    start_ms=span.start_ms,
                    end_ms=span.end_ms,
                    source_url=span.source_url,
                    label=label,
                )
            )
        return tuple(out)

    @staticmethod
    def _citations_verified(spans: tuple[SourceSpan, ...], cites: tuple[CitationSpan, ...]) -> bool:
        if len(spans) != len(cites):
            return False
        for span, cite in zip(spans, cites, strict=True):
            if cite.text != span.verbatim_text:
                return False
            if (cite.start_ms, cite.end_ms) != (span.start_ms, span.end_ms):
                return False
            if cite.source_span_id != span.source_span_id:
                return False
        return True

    @staticmethod
    def _reconstructs_from_spans(answer_text: str, spans: tuple[SourceSpan, ...]) -> bool:
        """Proof obligation: the answer is exactly the stored span text, in order."""
        return answer_text == " ".join(s.verbatim_text.strip() for s in spans)

    def _related(
        self,
        context: ParentContext,
        reason: str,
        gates: dict[str, bool],
        chains: tuple[str, ...],
        *,
        spans: tuple[SourceSpan, ...] | None = None,
        state: HarnessState = HarnessState.ANSWERABILITY_GATE,
        state_path: tuple[HarnessState, ...] = (),
    ) -> RetrievalDecision:
        if spans is None:
            spans = self._window(context)
        cites = self._citations(spans)
        gates["citations_verified"] = self._citations_verified(spans, cites)
        if not gates["citations_verified"]:
            # Related text is still cited text: unverifiable citations abstain.
            return self._abstain(
                context,
                "citation_alignment_failed",
                gates=gates,
                state=state,
                state_path=state_path,
            )
        return RetrievalDecision(
            decision=HarnessDecision.SERVE_RELATED_NOT_DIRECT,
            state=state,
            guru_id=spans[0].guru_id if spans else context.parent.guru_id,
            parent_unit_id=context.parent.parent_unit_id,
            source_span_ids=tuple(s.source_span_id for s in spans),
            context_edges_used=chains,
            speaker_boundary_passed=bool(gates.get("speaker", False)),
            context_sufficiency="insufficient",
            answer_text_reconstructed=True,
            citations_verified=True,
            answer_text=" ".join(s.verbatim_text.strip() for s in spans) or None,
            citations=cites,
            gates={**gates, "context_sufficiency": False},
            abstain_reason=reason,
            abstain_stage=state,
            state_path=state_path,
        )

    def _abstain(
        self,
        context: ParentContext,
        reason: str,
        *,
        gates: dict[str, bool],
        state: HarnessState = HarnessState.ANSWERABILITY_GATE,
        state_path: tuple[HarnessState, ...] = (),
    ) -> RetrievalDecision:
        logger.info(
            "[ContextHarness] abstain reason=%s",
            _bounded_abstain_reason(reason),
        )
        return RetrievalDecision(
            decision=HarnessDecision.ABSTAIN,
            state=state,
            guru_id=context.parent.guru_id,
            parent_unit_id=context.parent.parent_unit_id,
            speaker_boundary_passed=bool(gates.get("speaker", False)),
            context_sufficiency="insufficient",
            gates=gates,
            abstain_reason=reason,
            abstain_stage=state,
            state_path=state_path,
        )


if __name__ == "__main__":
    from domain.first_person_context import (
        AnswerRole,
        BoundaryStatus,
        CompletenessStatus,
        ParentContext,
        ParentUnit,
        ProvenanceKind,
        SourceSpan,
        SpeakerRole,
        clip_text_hash,
        make_parent_unit_id,
        make_source_span_id,
    )

    _text = "Meditation brings deep silence to the mind."
    _hash = clip_text_hash(_text)
    _parent_id = make_parent_unit_id(
        guru_id="krishnaji",
        video_id="test_vid_01",
        corpus_version="fp-context-v1",
        first_word_index=0,
        last_word_index=7,
    )
    _span_id = make_source_span_id(
        guru_id="krishnaji",
        video_id="test_vid_01",
        corpus_version="fp-context-v1",
        word_start=0,
        word_end=7,
        transcript_hash=_hash,
    )
    _span = SourceSpan(
        corpus_version="fp-context-v1",
        guru_id="krishnaji",
        video_id="test_vid_01",
        source_asset_id="asset_01",
        source_span_id=_span_id,
        parent_unit_id=_parent_id,
        turn_id="turn_01",
        turn_index=0,
        source_span_index=0,
        speaker_id="krishnaji",
        speaker_role=SpeakerRole.GURU,
        speaker_verified=True,
        rights_cleared=True,
        caption_status="auto",
        provenance_kind=ProvenanceKind.SPEECH_TURN_SPAN,
        answer_role=AnswerRole.DIRECT,
        word_start=0,
        word_end=7,
        start_ms=1000,
        end_ms=5000,
        source_transcript_text=_text,
        verbatim_text=_text,
        transcript_hash=_hash,
        source_text_hash=_hash,
        source_url="https://youtube.com/watch?v=test_vid_01",
        boundary_status=BoundaryStatus.VERIFIED,
        completeness_status=CompletenessStatus.COMPLETE,
    )
    _parent = ParentUnit(
        corpus_version="fp-context-v1",
        guru_id="krishnaji",
        video_id="test_vid_01",
        parent_unit_id=_parent_id,
        ordered_source_span_ids=(_span_id,),
        start_ms=1000,
        end_ms=5000,
        parent_text_hash=_hash,
        speaker_ids=("krishnaji",),
        speaker_continuity=True,
        boundary_status=BoundaryStatus.VERIFIED,
        completeness_status=CompletenessStatus.COMPLETE,
    )
    _ctx = ParentContext(
        parent=_parent,
        spans=(_span,),
        hit_span_ids=(_span_id,),
        score=0.95,
    )
    _harness = FirstPersonContextHarness()
    _decision = _harness.decide(_ctx, answerability="yes")
    assert _decision.decision == HarnessDecision.SERVE_SINGLE_SPAN, f"Unexpected decision {_decision.decision}"
    assert _decision.answer_text == _text, f"Expected {_text!r}, got {_decision.answer_text!r}"
    assert _decision.answer_text_reconstructed is True
    print("first_person_context_harness self-check passed")
