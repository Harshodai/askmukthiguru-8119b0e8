"""
GuruToneAdapter Node — Fused GraphRAG + Qdrant Dual-Stream Final Guardrail Voice Transformer.

Acts as the mandatory FINAL GUARDRAIL in the retrieval pipeline (ChatEngine), incorporating:
- Neo4j Knowledge Graph Traversal (OKF Ontology Engine): Traverses spiritual state transformations.
- Qdrant Vector DB (guru_tone_podcast): Retrieves live direct seeker interaction exemplars from YouTube playlists.
- PersonaDiscriminator (2026): Automated 1-pass Reflexion self-correction loop when authenticity score < 9.0/10.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from rag.prompts import (
    GURU_TONE_ADAPTER_SYSTEM_PROMPT,
    GURU_TONE_ADAPTER_USER_PROMPT,
    GURU_TONE_REFLEXION_CORRECTION_PROMPT,
)
from rag.states import GraphState
from services.guru_brain.guru_brain_service import GuruBrainService
from services.guru_brain.guru_kg_service import GuruKGService
from services.guru_brain.persona_discriminator import PersonaDiscriminator

logger = logging.getLogger(__name__)


class GuruToneAdapterNode:
    """Pass 2 Final Guardrail Guru Voice Transformation Node with Reflexion Self-Correction."""

    def __init__(
        self,
        guru_brain_service: Optional[GuruBrainService] = None,
        guru_kg_service: Optional[GuruKGService] = None,
        persona_discriminator: Optional[PersonaDiscriminator] = None,
        llm_service: Any = None,
    ) -> None:
        if guru_brain_service is None or guru_kg_service is None:
            try:
                from app.dependencies import get_container
                container = get_container()
                if guru_brain_service is None:
                    guru_brain_service = getattr(container, "guru_brain_service", None)
                if guru_kg_service is None:
                    guru_kg_service = getattr(container, "guru_kg_service", None)
            except Exception:
                logger.warning(
                    "GuruToneAdapterNode: container unavailable — services initialized "
                    "without Qdrant/Neo4j. Tone adaptation will run on static prompts only."
                )

        if guru_brain_service is None:
            guru_brain_service = GuruBrainService()
        if guru_kg_service is None:
            guru_kg_service = GuruKGService()

        self.guru_brain_service = guru_brain_service
        self.guru_kg_service = guru_kg_service
        self.llm_service = llm_service
        self.persona_discriminator = persona_discriminator or PersonaDiscriminator(llm_service=llm_service)

    async def transform_tone(
        self,
        state: GraphState | dict | None = None,
        user_query: Optional[str] = None,
        factual_draft: Optional[str] = None,
        guru_name: Optional[str] = None,
        teacher_id: Optional[str] = None,
    ) -> GraphState | dict:
        """Transform factual_draft into Sri Preethaji & Sri Krishnaji's authentic voice using fused GraphRAG + Qdrant persona retrieval + Reflexion guardrail."""
        if state is None:
            state = {}
        elif not isinstance(state, dict):
            state = dict(state)

        req_id = state.get("request_id") or "no-req-id"
        query = user_query or state.get("question") or state.get("user_query") or ""
        draft = factual_draft or state.get("final_answer") or state.get("answer") or state.get("factual_draft") or ""
        target_guru = guru_name or teacher_id or state.get("guru_name") or state.get("teacher_id") or state.get("assistant_slug") or "combined"

        out_state = dict(state)
        out_state["request_id"] = req_id

        if not draft or not draft.strip():
            logger.warning(f"[{req_id}] GuruToneAdapter: empty draft received, skipping transformation.")
            out_state["final_answer"] = draft
            return out_state

        # Stream 1: Vector Persona Search from Qdrant `guru_tone_podcast` (157 playlist exemplars)
        exemplars = await self.guru_brain_service.search_tone_exemplars(
            query=query,
            guru_name=target_guru,
            limit=3,
        )
        vector_persona_context = self.guru_brain_service.format_persona_context(exemplars)

        # Stream 2: Knowledge Graph & OKF Ontology Traversal from Neo4j
        kg_paths = await asyncio.to_thread(self.guru_kg_service.traverse_guru_ontology, query=query, limit=3)
        kg_context = self.guru_kg_service.format_kg_ontology_context(kg_paths)

        # Build Fused System and User Prompts using rag/prompts constants
        system_prompt = GURU_TONE_ADAPTER_SYSTEM_PROMPT.format(
            kg_context=kg_context,
            vector_persona_context=vector_persona_context,
        )

        user_prompt = GURU_TONE_ADAPTER_USER_PROMPT.format(
            user_query=query,
            factual_draft=draft,
        )

        if not self.llm_service:
            logger.info(f"[{req_id}] GuruToneAdapterNode: LLM service unavailable, returning factual draft.")
            out_state["final_answer"] = draft
            return out_state

        try:
            # First Pass Transformation with explicit timeout
            transformed = await asyncio.wait_for(
                self.llm_service.generate(system_prompt, user_prompt, temperature=0.25),
                timeout=12.0,
            )
            if not transformed or len(transformed.strip()) <= 20:
                out_state["final_answer"] = draft
                return out_state

            transformed_text = transformed.strip()

            # Reflexion Evaluation Step
            eval_res = await self.persona_discriminator.evaluate_persona(user_query=query, response_text=transformed_text)
            logger.info(f"[{req_id}] GuruToneAdapter Discriminator Score: {eval_res.overall_score:.1f}/10.0 (Needs Correction: {eval_res.needs_correction})")

            # Execute 1-Pass Self-Correction Loop if Score < 9.0
            if eval_res.needs_correction and eval_res.correction_directive:
                logger.info(f"[{req_id}] Executing Reflexion Self-Correction Loop: {eval_res.correction_directive}")
                correction_prompt = GURU_TONE_REFLEXION_CORRECTION_PROMPT.format(
                    user_prompt=user_prompt,
                    overall_score=eval_res.overall_score,
                    correction_directive=eval_res.correction_directive,
                )
                try:
                    corrected = await asyncio.wait_for(
                        self.llm_service.generate(system_prompt, correction_prompt, temperature=0.2),
                        timeout=10.0,
                    )
                    if corrected and len(corrected.strip()) > 20:
                        out_state["final_answer"] = corrected.strip()
                        return out_state
                except (asyncio.TimeoutError, Exception) as corr_exc:
                    logger.warning(f"[{req_id}] GuruToneAdapter self-correction LLM generate timed out/failed ({corr_exc}).")

            out_state["final_answer"] = transformed_text
            return out_state

        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning(f"[{req_id}] GuruToneAdapterNode: Voice transformation failed ({exc}), keeping factual draft.")

        out_state["final_answer"] = draft
        return out_state

