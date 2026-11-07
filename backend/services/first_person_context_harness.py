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
import re
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
    ValidatedCrossParentEdge,
    clip_text_hash,
)
from domain.speaker_provenance import speaker_write_violations
from services.first_person_evidence_policy import first_person_evidence_policy
from services.first_person_rights import source_is_authoritatively_licensed
from services.injection_screen import screen as screen_injection

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
        "asr_script_garbage",
        "fragment_without_antecedent",
        "antecedent_missing",
        "boundary_uncertain",
        "answerability_no",
        "citation_alignment_failed",
        "reconstruction_failed",
        "question_only_clip",
        "retrieved_hit_trimmed",
        "context_span_limit",
        "not_standalone",
        "violent_relationship_context",
        "unsolicited_self_harm_reference",
        "injection_screen",  # NEW-AI-5 drop mode (default off, D-PG16)
    }
)
_SHADOW_OUTCOMES = frozenset({"evaluated", "no_candidate", "not_configured", "timeout", "error"})
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


_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]*")

# This detector can only request the bounded immediate predecessor after the
# store issues a validated edge capability; it never performs timestamp search.
# The configured context-span cap remains strict after that one-span recovery.
_ANTECEDENT_CONNECTIVE_RE = re.compile(
    r"^(?:"
    r"imagine\s+what\s+will\s+be\s+the\s+outcome\s+of\s+(?:it|this|that)\b|"
    r"(?:because|as\s+a\s+result)\s+of\s+(?:it|this|that)\b|"
    r"in\s+response\s+to\s+(?:it|this|that)\b"
    r")",
    re.IGNORECASE,
)


def _span_starts_with_antecedent(span: SourceSpan) -> bool:
    """Return true only for explicit connective/coreference or fragment evidence."""
    if span.completeness_status is CompletenessStatus.FRAGMENT:
        return bool(span.previous_span_id)
    if span.coreference_chain_ids:
        return bool(span.previous_span_id)
    return bool(_ANTECEDENT_CONNECTIVE_RE.match(span.verbatim_text.strip()))


def _injection_screen_refuses(spans: tuple[SourceSpan, ...]) -> bool:
    """Count spans the injection screen matches; True only in drop mode."""
    from services.first_person_pipeline import (
        injection_screen_drop_enabled,
        record_injection_screen,
    )

    flagged = [s.source_span_id for s in spans if screen_injection(s.verbatim_text)]
    if not flagged:
        return False
    drop = injection_screen_drop_enabled()
    action = "dropped" if drop else "flagged"
    for span_id in flagged:
        record_injection_screen("harness", action)
        logger.warning("[FPHarness] injection screen %s span %s", action, span_id)
    return drop


def _is_question_only(text: str) -> bool:
    """True when the text asks questions and states nothing.

    Interviewer prompts and rhetorical set-ups ("How do we find a balance...?")
    are not teaching. Text without any ``?`` is never judged here (unpunctuated
    ASR must not be rejected on a guess), and a trailing unterminated fragment
    counts as a statement.
    """
    if "?" not in text:
        return False
    sentences = [m.group(0).strip() for m in _SENTENCE_RE.finditer(text)]
    sentences = [x for x in sentences if any(ch.isalnum() for ch in x)]
    return bool(sentences) and all(x.endswith("?") for x in sentences)


def _norm_text(text: str) -> str:
    return " ".join(text.lower().split())


def _drop_redundant_spans(spans: tuple[SourceSpan, ...]) -> tuple[SourceSpan, ...]:
    """Drop spans whose time range or text is already carried by another span.

    Overlapping spans are concatenated into one answer, so a contained span
    would be read out twice. The kept span's text is untouched (verbatim and
    hash-checked); only the redundant span leaves the served set.
    """
    kept: list[SourceSpan] = []
    for span in spans:
        text = _norm_text(span.verbatim_text)
        redundant = False
        for other in spans:
            if other is span:
                continue
            other_text = _norm_text(other.verbatim_text)
            time_inside = other.start_ms <= span.start_ms and span.end_ms <= other.end_ms
            text_inside = bool(text) and text in other_text
            if not (time_inside or text_inside):
                continue
            # Identical ranges/texts: keep the earlier span only.
            identical = (other.start_ms, other.end_ms) == (span.start_ms, span.end_ms) or (
                text == other_text
            )
            if identical and spans.index(other) > spans.index(span):
                continue
            redundant = True
            break
        if not redundant:
            kept.append(span)
    return tuple(kept)


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
    # Word budget for one assembled answer (plan T2c 2026-10-27). Span count
    # alone does not bound length: three long turns are still a wall of text.
    # Trimming never edits text and never removes the hit while a legal
    # alternative exists (see _apply_word_budget).
    max_context_words: int = 600
    require_speaker_verified: bool = True
    # Also require a recorded voice_verification_method (see settings).
    require_voice_method: bool = False
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

    return HarnessPolicy(
        max_context_spans=max(1, int(settings.first_person_context_max_spans)),
        require_voice_method=getattr(settings, "first_person_require_voice_method", False) is True,
    )


def _not_standalone(spans: tuple[SourceSpan, ...]) -> bool:
    from app.config import settings
    from services.first_person_evidence_policy import first_person_evidence_policy

    if not getattr(settings, "first_person_standalone_gate_enabled", True) or not spans:
        return False
    decision = first_person_evidence_policy.assess_context_standalone(
        span.verbatim_text for span in spans
    )
    return not decision.may_serve


class FirstPersonContextHarness:
    def __init__(self, policy: HarnessPolicy | None = None) -> None:
        self._policy = policy or HarnessPolicy()

    # ------------------------------------------------------------------ gates
    @staticmethod
    def _speaker_gate(spans: tuple[SourceSpan, ...], policy: HarnessPolicy) -> bool:
        for span in spans:
            if span.speaker_role is not SpeakerRole.GURU:
                return False
            # A label and a boolean are not speaker evidence.  The context
            # harness is a release-quality serving gate, so unlike legacy
            # retrieval it refuses missing, failed, or unknown provenance even
            # when the compatibility setting is left at its old value.
            if not span.speaker_verified:
                return False
            if speaker_write_violations(
                span.to_payload(),
                allow_legacy_centroid=not policy.require_voice_method,
            ):
                return False
        return True

    @staticmethod
    def _rights_gate(spans: tuple[SourceSpan, ...]) -> bool:
        return all(
            span.rights_cleared is True
            and source_is_authoritatively_licensed(
                source_url=span.source_url,
                video_id=span.video_id,
                domain_rights_status=span.domain_rights_status,
            )
            for span in spans
        )

    @staticmethod
    def _hash_gate(spans: tuple[SourceSpan, ...]) -> bool:
        return all(clip_text_hash(span.verbatim_text) == span.source_text_hash for span in spans)

    @staticmethod
    def _text_sanity_gate(spans: tuple[SourceSpan, ...]) -> bool:
        from ingest.verbatim.gates import expected_script_for, script_and_loop_problem

        # The expected script comes from the span's DECLARED language (language ID, audit
        # D10). An undeclared span belongs to the English corpus and must be Latin: the
        # ASR stage cannot transcribe Indic speech, so non-Latin text there is decoder
        # garbage (all 9 such spans in the 2,737-span v10 export were). A span that
        # declares another language is held to that language's script, and a loop or a
        # foreign letter inside it is still refused.
        return all(
            script_and_loop_problem(
                span.verbatim_text, expected_script=expected_script_for(span.language)
            )
            is None
            for span in spans
        )

    @staticmethod
    def _completeness_gate(
        spans: tuple[SourceSpan, ...],
        policy: HarnessPolicy,
        *,
        parent_status: CompletenessStatus | None = None,
    ) -> bool:
        # UNCERTAIN is never made safe by an antecedent.  A fragment may be completed by
        # an explicitly present predecessor; an uncertain child or parent cannot.
        if parent_status is CompletenessStatus.UNCERTAIN or any(
            s.completeness_status is CompletenessStatus.UNCERTAIN for s in spans
        ):
            return False
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

    def _window(
        self, context: ParentContext, *, span_limit: int | None = None
    ) -> tuple[SourceSpan, ...]:
        """Bounded chronological window around the first hit span.

        Spans are always returned in ``start_ms`` order so the concatenated
        answer reads chronologically.  The window is centered on the first
        matching ``hit_span_ids`` entry (one preceding span when the policy
        allows it).  Only when the parent has no hit do we fall back to its
        head.  The ``max_context_spans`` bound always applies.

        The span bound is strict: no antecedent heuristic may return more spans
        than the configured limit. Recovery, when enabled by the pipeline, must
        happen before this decision using a store-issued validated edge.
        """
        # The validated parent record, not timestamps or child pointers, is the
        # adjacency authority.  Store hydration verifies that every ordered id
        # exists and belongs to this parent before a context reaches serving.
        by_id = {span.source_span_id: span for span in context.spans}
        ordered_ids = tuple(context.parent.ordered_source_span_ids)
        ordered = tuple(by_id[span_id] for span_id in ordered_ids if span_id in by_id)
        # Preserve unexpected children so the explicit same-parent gate below
        # rejects a corrupted/deserialised context rather than silently hiding
        # a candidate behind the max-span bound.
        extras = tuple(
            span for span in context.spans if span.source_span_id not in set(ordered_ids)
        )
        if extras:
            ordered += extras
        if not ordered:
            return ()
        limit = max(1, span_limit if span_limit is not None else self._policy.max_context_spans)
        hit_ids = set(context.hit_span_ids or ())
        hit_index = next(
            (index for index, span in enumerate(ordered) if span.source_span_id in hit_ids),
            None,
        )
        if hit_index is None:
            return self._apply_word_budget(ordered[:limit], hit_ids)

        # Include one preceding span whenever the bound allows it, even for an
        # even-sized window where exact centering would drop it.
        offset = 0 if limit == 1 else max(1, (limit - 1) // 2)
        start = max(0, hit_index - offset)
        end = min(len(ordered), start + limit)
        start = max(0, end - limit)
        return self._apply_word_budget(ordered[start:end], hit_ids)

    def _apply_word_budget(
        self, spans: tuple[SourceSpan, ...], hit_ids: set[str]
    ) -> tuple[SourceSpan, ...]:
        """Trim a window that is over the policy word budget.

        ``max_context_spans`` bounds *how many* spans a parent contributes, not
        how long they are: three 400-word turns are a wall of text even though
        the count is legal. Trimming always removes the span furthest from the
        hit, so the hit itself and the predecessor that carries its antecedent
        survive as long as the budget allows them. Text is never edited.
        """
        budget = max(1, int(getattr(self._policy, "max_context_words", 600)))
        window = list(spans)
        while len(window) > 1:
            total = sum(len(span.verbatim_text.split()) for span in window)
            if total <= budget:
                break
            if window[-1].source_span_id in hit_ids:
                window.pop(0)
            else:
                window.pop()
        return tuple(window)

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
        query: str = "",
        requested_teacher: str | None = None,
        answerability: str = "indeterminate",
        selected_span_ids: tuple[str, ...] | None = None,
        retrieval_query: str | None = None,
        validated_predecessor: ValidatedCrossParentEdge | None = None,
    ) -> RetrievalDecision:
        """Run the gate chain and record one metric + one structured trace line.

        ``selected_span_ids`` is the optional Phase-D8 structured selector
        output: span IDs only. Unknown IDs are ignored (deterministic order is
        kept) and no selector prose can ever reach the answer text.
        """
        decision = self._decide(
            context,
            query=query,
            requested_teacher=requested_teacher,
            answerability=answerability,
            selected_span_ids=selected_span_ids,
            retrieval_query=retrieval_query,
            validated_predecessor=validated_predecessor,
        )
        _record_metrics(decision)
        return decision

    def _decide(
        self,
        context: ParentContext,
        *,
        query: str = "",
        requested_teacher: str | None = None,
        answerability: str = "indeterminate",
        selected_span_ids: tuple[str, ...] | None = None,
        retrieval_query: str | None = None,
        validated_predecessor: ValidatedCrossParentEdge | None = None,
    ) -> RetrievalDecision:
        # Check the complete retrieved set before applying the bounded window.
        # Otherwise a malformed extra child could be trimmed away and evade the
        # cross-parent contract gate.
        if self._policy.require_same_parent and any(
            span.parent_unit_id != context.parent.parent_unit_id for span in context.spans
        ):
            return self._abstain(
                context,
                "cross_parent_contamination",
                gates={},
                state_path=(),
            )
        predecessor_edge = validated_predecessor
        predecessor: SourceSpan | None = None
        validated_opener_id: str | None = None
        validated_hit_id: str | None = None
        window_limit: int | None = None
        if predecessor_edge is not None:
            if self._policy.max_context_spans < 2:
                return self._abstain(
                    context,
                    "context_span_limit",
                    gates={"context_span_limit": False},
                    state_path=(),
                )
            ordered_ids = tuple(context.parent.ordered_source_span_ids)
            current_opener = (
                next(
                    (span for span in context.spans if span.source_span_id == ordered_ids[0]),
                    None,
                )
                if ordered_ids
                else None
            )
            if current_opener is None or current_opener.source_span_id not in set(
                context.hit_span_ids or ()
            ):
                return self._abstain(
                    context,
                    "antecedent_missing",
                    gates={"antecedent_edge": False},
                    state_path=(),
                )
            # Preserve the exact hit identity before windowing, redundancy removal,
            # selector output, and trailing-question trimming.
            validated_opener_id = current_opener.source_span_id
            validated_hit_id = current_opener.source_span_id
            if not isinstance(
                predecessor_edge, ValidatedCrossParentEdge
            ) or not predecessor_edge.matches(current_opener, context.parent):
                return self._abstain(
                    context,
                    "antecedent_missing",
                    gates={"antecedent_edge": False},
                    state_path=(),
                )
            predecessor = predecessor_edge.predecessor
            if (
                not _span_starts_with_antecedent(current_opener)
                or predecessor.parent_unit_id == current_opener.parent_unit_id
                or predecessor.next_span_id != current_opener.source_span_id
                or current_opener.previous_span_id != predecessor.source_span_id
                or predecessor.video_id != current_opener.video_id
                or predecessor.guru_id != current_opener.guru_id
                or predecessor.corpus_version != current_opener.corpus_version
                or predecessor.speaker_id != current_opener.speaker_id
                or predecessor.end_ms > current_opener.start_ms
                or predecessor.word_end > current_opener.word_start
            ):
                return self._abstain(
                    context,
                    "antecedent_missing",
                    gates={"antecedent_edge": False},
                    state_path=(),
                )
            window_limit = self._policy.max_context_spans - 1

        def _validated_opener_present(candidate_spans: tuple[SourceSpan, ...]) -> bool:
            if validated_opener_id is None or validated_hit_id is None:
                return True
            present_ids = {span.source_span_id for span in candidate_spans}
            return validated_opener_id in present_ids and validated_hit_id in present_ids

        spans = _drop_redundant_spans(self._window(context, span_limit=window_limit))
        if not spans:
            return self._abstain(context, "no_spans", gates={}, state_path=())
        if not _validated_opener_present(spans):
            return self._abstain(
                context,
                "antecedent_missing",
                gates={"antecedent_edge": False},
                state_path=(),
            )

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

        if selected_span_ids and predecessor is not None:
            opener_id = context.parent.ordered_source_span_ids[0]
            # A predecessor is meaningful only with this exact opener. Ignore
            # selector output that omits or moves it; never attach the edge to
            # whichever span the selector happened to retain.
            if selected_span_ids[0] != opener_id:
                gates["selector_honored"] = False
                selected_span_ids = None

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

        if not _validated_opener_present(spans):
            return self._abstain(
                context,
                "antecedent_missing",
                gates={**gates, "antecedent_edge": False},
                state=state,
                state_path=tuple(states),
            )

        if predecessor is not None:
            # The store-issued capability has validated both complete parent/
            # child sets. This is the sole authorized cross-parent composition
            # and it happens before any gate or decision.
            if len(spans) + 1 > self._policy.max_context_spans:
                return self._abstain(
                    context,
                    "context_span_limit",
                    gates={"context_span_limit": False},
                    state=state,
                    state_path=tuple(states),
                )
            spans = (predecessor,) + spans

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

        gates["text_sanity"] = self._text_sanity_gate(spans)
        if not gates["text_sanity"]:
            return self._abstain(
                context,
                "asr_script_garbage",
                gates=gates,
                state=state,
                state_path=tuple(states),
            )

        # NEW-AI-5 (AI-010): text addressed to a model is flagged for review;
        # it refuses the answer only when the drop flag is on (D-PG16 open).
        if _injection_screen_refuses(spans):
            return self._abstain(
                context,
                "injection_screen",
                gates={**gates, "injection_screen": False},
                state=state,
                state_path=tuple(states),
            )

        # An answer must not end on a host/rhetorical question: drop whole trailing
        # question-only spans (text untouched). If every span is question-only,
        # keep them so the question_only_clip gate below abstains.
        # Runs after the speaker/rights/hash gates so host turns are still refused.
        hit_ids = set(context.hit_span_ids or ())
        hits_before = any(s.source_span_id in hit_ids for s in spans) if hit_ids else False
        trimmed = list(spans)
        while len(trimmed) > 1 and _is_question_only(trimmed[-1].verbatim_text):
            trimmed.pop()
        spans = tuple(trimmed)

        if not _validated_opener_present(spans):
            return self._abstain(
                context,
                "antecedent_missing",
                gates={**gates, "antecedent_edge": False},
                state=state,
                state_path=tuple(states),
            )

        if hits_before and not any(s.source_span_id in hit_ids for s in spans):
            return self._abstain(
                context,
                "retrieved_hit_trimmed",
                gates=gates,
                state=state,
                state_path=tuple(states),
            )

        gates["completeness"] = self._completeness_gate(
            spans,
            self._policy,
            parent_status=context.parent.completeness_status,
        )
        state = enter(HarnessState.COMPLETENESS_GATE)
        if not gates["completeness"]:
            return self._abstain(
                context,
                "fragment_without_antecedent",
                gates=gates,
                state=state,
                state_path=tuple(states),
            )

        # Same deterministic standalone checks as the legacy path (whole-clip rejection, text
        # untouched): a one-off event marker anywhere, an orphan opener on the first span only
        # (later spans may lean on an earlier included span).
        if _not_standalone(spans):
            return self._abstain(
                context,
                "not_standalone",
                gates=gates,
                state=state,
                state_path=tuple(states),
            )

        safety_decision = first_person_evidence_policy.assess_contextual_safety(
            query,
            " ".join(span.verbatim_text.strip() for span in spans),
            retrieval_query=retrieval_query or "",
        )
        state = enter(HarnessState.CONTEXTUAL_SAFETY_GATE)
        gates["contextual_safety"] = safety_decision.may_serve
        if not safety_decision.may_serve:
            reason = safety_decision.reason_codes[0] if safety_decision.reason_codes else "other"
            return self._abstain(
                context,
                reason,
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
                context,
                "antecedent_missing",
                gates,
                chains,
                spans=spans,
                state=state,
                state_path=tuple(states),
            )

        if not self._boundary_gate(spans):
            return self._related(
                context,
                "boundary_uncertain",
                gates,
                chains,
                spans=spans,
                state=state,
                state_path=tuple(states),
            )

        gates["not_question_only"] = not _is_question_only(
            " ".join(span.verbatim_text.strip() for span in spans)
        )
        if not gates["not_question_only"]:
            return self._abstain(
                context,
                "question_only_clip",
                gates=gates,
                state=state,
                state_path=tuple(states),
            )

        # Keep the parent record's validated adjacency/order through citation
        # construction and verbatim reconstruction. Do not re-derive order from
        # timestamps or child pointers here.
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
                    CONTEXT_LABEL_LATER if span.start_ms > primary_start else CONTEXT_LABEL_EARLIER
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
                    domain_rights_status=span.domain_rights_status,
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
            if (
                cite.domain_rights_status != "licensed"
                or cite.domain_rights_status != span.domain_rights_status
            ):
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
    assert _decision.decision == HarnessDecision.SERVE_SINGLE_SPAN, (
        f"Unexpected decision {_decision.decision}"
    )
    assert _decision.answer_text == _text, f"Expected {_text!r}, got {_decision.answer_text!r}"
    assert _decision.answer_text_reconstructed is True
    print("first_person_context_harness self-check passed")
