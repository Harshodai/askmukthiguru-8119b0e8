"""Semantic-First Understanding Engine & Task-Specific Retrieval Planner.

Replaces brittle regex-first intent/emotion routing with a layered architecture:
  1. Deterministic structural & acute safety checks (formats, IDs, acute self-harm).
  2. Embedding prototype similarity with margin-based confidence estimation.
  3. Bounded LLM structured disambiguation on low-margin / ambiguous inputs.
  4. Intent-driven RetrievalPlanner selecting adapters, budgets, and graph depth.
"""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from services.guru_registry import get_gurus

logger = logging.getLogger(__name__)

IntentDomain = Literal[
    "spiritual_teaching",
    "practice_howto",
    "emotional_support",
    "grief_bereavement",
    "comparative_teachers",
    "source_lookup",
    "comprehension_confusion",
    "editorial_research",
    "out_of_scope",
    "crisis",
]

EmotionalSignal = Literal[
    "none",
    "ordinary_sadness",
    "grief_bereavement",
    "persistent_distress",
    "acute_crisis",
]

# Layer 1: Deterministic acute crisis patterns ONLY (never bereavement/ordinary sadness)
_ACUTE_CRISIS_RE = re.compile(
    r"\b(?:kill\s+myself|suicid\w*|end\s+my\s+life|want\s+to\s+die|self[- ]?harm|"
    r"hurt\s+myself|no\s+reason\s+to\s+live|not\s+worth\s+living|wish\s+i\s+(?:was|were)\s+dead)\b",
    re.IGNORECASE,
)

# Deterministic structural extractors (regex belongs on formats/identifiers, not emotions)
_YOUTUBE_ID_RE = re.compile(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})")
_QUOTATION_REQUEST_RE = re.compile(
    r'["\u201c\u201d].{6,}["\u201c\u201d]|\bexact\s+quote\b', re.IGNORECASE
)

# Multilingual & colloquial semantic prototypes (embedding-matched, never exact-keyword gated)
_NAME_A, _NAME_B = ([g.label for g in get_gurus()] + ["the teachers"] * 2)[:2]

DEFAULT_INTENT_PROTOTYPES: dict[IntentDomain, list[str]] = {
    "spiritual_teaching": [
        "What is the beautiful state and how does suffering dissolve?",
        "How do ego and self-centric thinking create inner conflict?",
        "Explain universal intelligence and oneness consciousness.",
        "What do the teachings say about love, fear, and attachment?",
    ],
    "practice_howto": [
        "What are the steps of Soul Sync meditation?",
        "How do I practice Serene Mind breathing observation?",
        "Guide me through the Aham meditation practice.",
    ],
    "emotional_support": [
        "I have been feeling very low for weeks and nothing makes me happy anymore.",
        "I don't feel like doing anything and feel completely disconnected from myself.",
        "I am tired of everything and overwhelmed by anxiety and anger.",
        "Chala kastamga undi, manasu prashantamga ledu.",
        "Bahut akela aur dukhi mehsoos kar raha hoon aaj kal.",
    ],
    "grief_bereavement": [
        "I lost someone I deeply loved and I cannot stop crying.",
        "My mother passed away recently and I am struggling with grief and loss.",
        "How do I cope with mourning the death of a loved one?",
    ],
    "comparative_teachers": [
        f"Compare what {_NAME_A} and {_NAME_B} teach about fear and suffering.",
        f"How do {_NAME_B}'s perspective and {_NAME_A}'s perspective differ on relationships?",
    ],
    "source_lookup": [
        "What does the book The Four Sacred Secrets say about the Warring Self?",
        "Find the passage in Sufkor or the video talk where they explain inner stillness.",
        "Give me the exact quotation and timestamp on spiritual vision.",
    ],
    "comprehension_confusion": [
        "I didn't understand that explanation, can you explain it more simply?",
        "What do you mean by that concept? I'm confused, give me a different example.",
        "That felt too abstract, help me understand what observation without division means.",
    ],
    "editorial_research": [
        "Build an editorial research dossier and video brief on dissolving resentment.",
        "Which spiritual topics are underexplored in our corpus compared to seeker questions?",
        "Fact check this draft script against verified teacher passages.",
    ],
    "out_of_scope": [
        "Write a Python function to sort a dictionary by value.",
        "What is the current stock price of Apple or weather forecast today?",
        "What is the capital city of France and who won the cricket match?",
    ],
}


class SemanticInterpretation(BaseModel):
    """Structured meaning representation produced by the Semantic-First Interpreter."""

    model_config = ConfigDict(extra="forbid")

    intent: IntentDomain
    emotional_signal: EmotionalSignal = "none"
    teacher_scope: str | None = None
    confusion_signal: bool = False
    is_comparative: bool = False
    is_exact_quote_request: bool = False
    referenced_video_id: str | None = None
    target_concepts: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    margin: float = 0.0
    uncertain: bool = False
    method: Literal[
        "acute_safety_rail", "embedding_semantic", "llm_disambiguated", "lexical_fallback"
    ] = "embedding_semantic"
    scores_by_intent: dict[str, float] = Field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalPlan:
    """Task-specific execution plan chosen from SemanticInterpretation."""

    strategy: Literal[
        "narrow_factual",
        "broad_thematic",
        "source_specific",
        "comparative_teachers",
        "comprehension_recovery",
        "editorial_research",
        "safety_redirect",
        "out_of_scope_abstain",
    ]
    budget_mode: Literal["fast", "thinking"]
    adapters: tuple[str, ...]
    top_k: int
    graph_depth: int
    rerank_depth: int
    teacher_scope: str | None = None
    force_equal_teachers: bool = False  # Never force artificial 50/50 symmetry
    require_alternative_sources: bool = False
    notes: list[str] = field(default_factory=list)


def _cosine(a: list[float], b: list[float]) -> float:
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    na = float(np.linalg.norm(va))
    nb = float(np.linalg.norm(vb))
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    val = float(np.dot(va, vb) / (na * nb))
    return val if math.isfinite(val) else 0.0


class SemanticUnderstandingEngine:
    """Layered semantic interpreter combining embedding similarity, ontology concepts, and safety rails."""

    def __init__(
        self,
        embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
        llm_classifier_fn: Callable[[str, dict[str, float]], dict[str, Any] | None] | None = None,
        *,
        ambiguity_margin: float = 0.05,
        low_confidence_threshold: float = 0.42,
    ) -> None:
        self._embed_fn = embed_fn
        self._llm_classifier_fn = llm_classifier_fn
        self._ambiguity_margin = ambiguity_margin
        self._low_confidence_threshold = low_confidence_threshold
        self._prototype_vectors: dict[IntentDomain, list[list[float]]] | None = None

    def _ensure_prototypes(self) -> dict[IntentDomain, list[list[float]]]:
        if self._prototype_vectors is not None:
            return self._prototype_vectors
        if self._embed_fn is None:
            return {}
        flat_texts: list[str] = []
        offsets: list[tuple[IntentDomain, int, int]] = []
        for intent, examples in DEFAULT_INTENT_PROTOTYPES.items():
            start = len(flat_texts)
            flat_texts.extend(examples)
            offsets.append((intent, start, len(flat_texts)))
        vecs = self._embed_fn(flat_texts)
        proto: dict[IntentDomain, list[list[float]]] = {}
        for intent, s, e in offsets:
            proto[intent] = [list(v) for v in vecs[s:e]]
        self._prototype_vectors = proto
        return proto

    @staticmethod
    def _detect_teacher_scope(text: str) -> tuple[str | None, bool]:
        # unbounded alias search (substring, like the original token match)
        low = text or ""
        hits = [g.id for g in get_gurus() if any(re.search(a, low, re.I) for a in g.aliases)]
        if len(hits) > 1:
            return "both", True
        if hits:
            return hits[0], False
        return None, False

    def interpret(
        self,
        query: str,
        *,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> SemanticInterpretation:
        cleaned = (query or "").strip()
        teacher_scope, both_teachers = self._detect_teacher_scope(cleaned)
        vid_match = _YOUTUBE_ID_RE.search(cleaned)
        referenced_vid = vid_match.group(1) if vid_match else None
        is_quote_req = bool(_QUOTATION_REQUEST_RE.search(cleaned))

        # 1. Deterministic acute crisis safety rail (explicit self-harm only; never grief)
        if _ACUTE_CRISIS_RE.search(cleaned):
            return SemanticInterpretation(
                intent="crisis",
                emotional_signal="acute_crisis",
                teacher_scope=teacher_scope,
                confidence=1.0,
                margin=1.0,
                uncertain=False,
                method="acute_safety_rail",
            )

        # 2. Embedding semantic matching (handles indirect expressions, paraphrases, code-switching)
        scores: dict[str, float] = {}
        if self._embed_fn is not None and cleaned:
            protos = self._ensure_prototypes()
            if protos:
                q_vec = self._embed_fn([cleaned])[0]
                for intent, vecs in protos.items():
                    if vecs:
                        scores[intent] = round(max(_cosine(q_vec, pv) for pv in vecs), 4)

        if scores:
            ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            best_intent, best_score = ranked[0]
            second_score = ranked[1][1] if len(ranked) > 1 else 0.0
            margin = round(best_score - second_score, 4)
            uncertain = (
                best_score < self._low_confidence_threshold or margin < self._ambiguity_margin
            )

            # Layer 3: Optional bounded LLM disambiguation when margin is tight
            if uncertain and self._llm_classifier_fn is not None:
                llm_out = self._llm_classifier_fn(cleaned, scores)
                if isinstance(llm_out, dict) and llm_out.get("intent") in DEFAULT_INTENT_PROTOTYPES:
                    chosen = llm_out["intent"]
                    return SemanticInterpretation(
                        intent=chosen,
                        emotional_signal=llm_out.get("emotional_signal")
                        or self._emotion_for(chosen),
                        teacher_scope=llm_out.get("teacher_scope") or teacher_scope,
                        confusion_signal=chosen == "comprehension_confusion",
                        is_comparative=both_teachers or chosen == "comparative_teachers",
                        is_exact_quote_request=is_quote_req,
                        referenced_video_id=referenced_vid,
                        target_concepts=list(llm_out.get("target_concepts") or []),
                        confidence=float(llm_out.get("confidence", best_score)),
                        margin=margin,
                        uncertain=bool(llm_out.get("uncertain", False)),
                        method="llm_disambiguated",
                        scores_by_intent=scores,
                    )

            return SemanticInterpretation(
                intent=best_intent,  # type: ignore[arg-type]
                emotional_signal=self._emotion_for(best_intent),
                teacher_scope=teacher_scope,
                confusion_signal=best_intent == "comprehension_confusion"
                or self._has_followup_confusion(cleaned, conversation_history),
                is_comparative=both_teachers or best_intent == "comparative_teachers",
                is_exact_quote_request=is_quote_req,
                referenced_video_id=referenced_vid,
                confidence=best_score,
                margin=margin,
                uncertain=uncertain,
                method="embedding_semantic",
                scores_by_intent=scores,
            )

        # Fallback if no embedder injected (still avoids giant regex sprawl)
        inferred = self._lightweight_fallback_intent(cleaned, both_teachers=both_teachers)
        return SemanticInterpretation(
            intent=inferred,
            emotional_signal=self._emotion_for(inferred),
            teacher_scope=teacher_scope,
            confusion_signal=inferred == "comprehension_confusion",
            is_comparative=both_teachers or inferred == "comparative_teachers",
            is_exact_quote_request=is_quote_req,
            referenced_video_id=referenced_vid,
            confidence=0.5,
            margin=0.0,
            uncertain=True,
            method="lexical_fallback",
        )

    @staticmethod
    def _emotion_for(intent: str) -> EmotionalSignal:
        if intent == "crisis":
            return "acute_crisis"
        if intent == "grief_bereavement":
            return "grief_bereavement"
        if intent == "emotional_support":
            return "persistent_distress"
        return "none"

    @staticmethod
    def _has_followup_confusion(query: str, history: list[dict[str, str]] | None) -> bool:
        if not history:
            return False
        low = query.lower()
        cues = (
            "didn't understand",
            "did not understand",
            "don't get",
            "explain differently",
            "simpler",
            "confused",
        )
        return any(c in low for c in cues)

    @staticmethod
    def _lightweight_fallback_intent(cleaned: str, *, both_teachers: bool) -> IntentDomain:
        low = cleaned.lower()
        if any(
            p in low
            for p in (
                "didn't understand",
                "did not understand",
                "don't get",
                "confused",
                "explain differently",
                "simpler",
            )
        ):
            return "comprehension_confusion"
        if any(p in low for p in ("lost someone", "passed away", "grief", "mourning")):
            return "grief_bereavement"
        if any(
            p in low
            for p in (
                "feeling very low",
                "nothing makes me happy",
                "disconnected from myself",
                "tired of everything",
            )
        ):
            return "emotional_support"
        if any(
            p in low
            for p in ("dossier", "editorial brief", "underexplored", "fact check", "draft script")
        ):
            return "editorial_research"
        if both_teachers or "compare" in low or "difference between" in low:
            return "comparative_teachers"
        if any(p in low for p in ("sufkor", "sacred secrets", "exact quote", "timestamp")):
            return "source_lookup"
        if any(p in low for p in ("steps of", "how do i practice", "soul sync", "serene mind")):
            return "practice_howto"
        return "spiritual_teaching"


def plan_retrieval(interp: SemanticInterpretation) -> RetrievalPlan:
    """Select retrieval strategy, adapters, and bounded budgets based on query intent."""
    if interp.intent == "crisis":
        return RetrievalPlan(
            strategy="safety_redirect",
            budget_mode="fast",
            adapters=(),
            top_k=0,
            graph_depth=0,
            rerank_depth=0,
            notes=["Acute self-harm rail overrides retrieval."],
        )
    if interp.intent == "out_of_scope" and not interp.uncertain:
        return RetrievalPlan(
            strategy="out_of_scope_abstain",
            budget_mode="fast",
            adapters=(),
            top_k=0,
            graph_depth=0,
            rerank_depth=0,
            notes=["High-confidence out-of-domain query."],
        )
    if interp.intent == "editorial_research":
        return RetrievalPlan(
            strategy="editorial_research",
            budget_mode="thinking",
            adapters=("qdrant", "memgraph", "okf"),
            top_k=50,
            graph_depth=2,
            rerank_depth=20,
            teacher_scope=interp.teacher_scope,
            notes=["Broad corpus exploration + concept discovery for editorial intelligence."],
        )
    if interp.intent == "comprehension_confusion":
        return RetrievalPlan(
            strategy="comprehension_recovery",
            budget_mode="thinking",
            adapters=("qdrant", "memgraph"),
            top_k=25,
            graph_depth=2,
            rerank_depth=15,
            teacher_scope=interp.teacher_scope,
            require_alternative_sources=True,
            notes=["Retrieve distinct verified explanations/parables excluding prior evidence."],
        )
    if interp.is_comparative or interp.intent == "comparative_teachers":
        return RetrievalPlan(
            strategy="comparative_teachers",
            budget_mode="thinking",
            adapters=("qdrant", "memgraph"),
            top_k=30,
            graph_depth=2,
            rerank_depth=15,
            teacher_scope=interp.teacher_scope or "both",
            force_equal_teachers=False,
            notes=["Retrieve per teacher independently without fabricating equal symmetry."],
        )
    if (
        interp.intent == "source_lookup"
        or interp.is_exact_quote_request
        or interp.referenced_video_id
    ):
        return RetrievalPlan(
            strategy="source_specific",
            budget_mode="fast",
            adapters=("qdrant", "okf"),
            top_k=15,
            graph_depth=1,
            rerank_depth=10,
            teacher_scope=interp.teacher_scope,
            notes=["Prioritize exact source/quote lookup and surrounding context."],
        )
    if interp.intent in {"emotional_support", "grief_bereavement"}:
        return RetrievalPlan(
            strategy="broad_thematic",
            budget_mode="thinking",
            adapters=("qdrant", "memgraph"),
            top_k=25,
            graph_depth=1,
            rerank_depth=12,
            teacher_scope=interp.teacher_scope,
            notes=["Compassionate non-clinical grounding across suffering/grief teachings."],
        )
    return RetrievalPlan(
        strategy="narrow_factual" if interp.margin >= 0.08 else "broad_thematic",
        budget_mode="fast" if interp.margin >= 0.08 else "thinking",
        adapters=("qdrant", "memgraph"),
        top_k=15 if interp.margin >= 0.08 else 30,
        graph_depth=1 if interp.margin >= 0.08 else 2,
        rerank_depth=10 if interp.margin >= 0.08 else 15,
        teacher_scope=interp.teacher_scope,
    )
