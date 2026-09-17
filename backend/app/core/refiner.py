import json
import logging
import os
from datetime import UTC, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.constants import FEEDBACK_LESSONS_FILE_PATH
from app.dependencies import get_container

logger = logging.getLogger(__name__)


class RefinerAnalysisResult(BaseModel):
    """Typed refiner LLM output — replaces split("```json")/json.loads."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    category: Literal[
        "hallucination",
        "missing_context",
        "incorrect_intent",
        "poor_formatting",
        "other",
    ] = Field(default="other", description="Failure category")
    analysis: str = Field(default="", max_length=2000, description="Brief analysis")
    suggested_correction: str = Field(
        default="N/A", max_length=2000, description="Concrete RAG/prompt correction"
    )


def parse_refiner_result(raw_response: str) -> RefinerAnalysisResult:
    """Parse raw LLM text into RefinerAnalysisResult via model_validate_json().

    Strips optional markdown fences, then takes the single-pass native JSON
    path. Falls back to a bounded 'other' record when the model emits
    non-JSON text (never raises to the caller).
    """
    cleaned = (raw_response or "").strip()
    if cleaned.startswith("```"):
        # Strip one optional ```json ... ``` fence without fragile split chains.
        lines = cleaned.splitlines()
        lines = lines[1:]  # drop opening fence (``` or ```json)
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        return RefinerAnalysisResult.model_validate_json(cleaned)
    except (ValidationError, ValueError) as e:
        logger.warning(f"Could not parse refiner JSON, using fallback: {e}")
        return RefinerAnalysisResult(
            category="other",
            analysis=cleaned[:500],
            suggested_correction="N/A",
        )


async def _generate_via_gateway(
    system_prompt: str,
    user_prompt: str,
) -> str:
    """Generate via container.llm_gateway with provider fallback.

    The gateway itself routes primary -> secondary when cross-provider
    fallback is enabled. Ollama local-only is the last-resort fallback here
    (never a cloud call), used only when the gateway raises.
    """
    container = get_container()
    try:
        gateway = getattr(container, "llm_gateway", None)
        if gateway is not None:
            return await gateway.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        logger.warning("llm_gateway missing on container — using local Ollama fallback")
    except Exception as e:
        logger.warning(f"llm_gateway.generate failed, trying local Ollama fallback: {e}")
    # Local-only fallback: loopback Ollama, no cloud provider involved.
    ollama = getattr(container, "ollama", None)
    if ollama is None:
        raise RuntimeError("No LLM backend available (gateway failed, no Ollama fallback)")
    return await ollama.generate(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )


async def mine_failed_session(
    query: str,
    retrieved_context: str,
    answer: str,
    comment: Optional[str] = None,
) -> dict:
    """
    Background worker that mines a failed session using the LLM gateway
    (provider fallback: openrouter/nim per container wiring) to classify the
    error and recommend RAG/prompt improvements. Ollama local-only fallback.
    """
    logger.info(f"Refining failed session for query: '{query}'")

    system_prompt = (
        "You are the Wisdom Refiner. Your job is to analyze failed AI spiritual guide interactions "
        "and determine why the response failed based on the user's query, the retrieved teachings (context), "
        "and the generated response.\n"
        "Categorize the failure into one of: 'hallucination', 'missing_context', 'incorrect_intent', 'poor_formatting', 'other'.\n"
        "Provide a brief analysis and propose a concrete correction or RAG rule to fix this issue in the future.\n"
        "Return your answer as a JSON object with the following fields: 'category', 'analysis', 'suggested_correction'. "
        "Do NOT output any markdown blocks or conversational text, only the raw JSON string."
    )

    user_prompt = (
        f"Query: {query}\n\n"
        f"Retrieved Context: {retrieved_context}\n\n"
        f"Generated Answer: {answer}\n\n"
        f"User Feedback/Comment: {comment or 'None provided'}"
    )

    analysis: RefinerAnalysisResult = RefinerAnalysisResult(
        category="other",
        analysis="LLM call failed",
        suggested_correction="None",
    )

    try:
        raw_response = await _generate_via_gateway(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        analysis = parse_refiner_result(raw_response)
    except Exception as e:
        logger.error(f"Wisdom Refiner failed to analyze session: {e}")
        analysis = RefinerAnalysisResult(
            category="other",
            analysis=f"Refiner error: {str(e)}"[:2000],
            suggested_correction="None",
        )

    # Append structured entry to feedback_lessons.jsonl
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "query": query,
        "category": analysis.category,
        "analysis": analysis.analysis,
        "suggested_correction": analysis.suggested_correction,
        "comment": comment,
    }

    try:
        os.makedirs(os.path.dirname(FEEDBACK_LESSONS_FILE_PATH), exist_ok=True)
        with open(FEEDBACK_LESSONS_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        logger.info(f"Recorded failure lesson in {FEEDBACK_LESSONS_FILE_PATH}")
    except Exception as e:
        logger.error(f"Failed to write to {FEEDBACK_LESSONS_FILE_PATH}: {e}")

    # ---- Ralph Loop Student Validation Stage ----
    suggested_correction = entry["suggested_correction"]
    if suggested_correction and suggested_correction not in ("None", "N/A") and retrieved_context:
        try:
            logger.info("Ralph Loop: Initiating Student validation run...")

            # 1. Initialize LettuceDetectService with container's embedding
            from services.lettuce_detect_service import LettuceDetectService

            container = get_container()
            lettuce = LettuceDetectService(embedder=container.embedding)

            # 2. Construct test system prompt incorporating the suggested correction
            from rag.prompts import GURU_SYSTEM_PROMPT

            test_system_prompt = (
                f"{GURU_SYSTEM_PROMPT}\n\n"
                f"CRITICAL RULE FOR THIS SESSION (based on past failure):\n"
                f"{suggested_correction}"
            )

            # 3. Call student model via gateway (gateway fallback, Ollama local-only last resort)
            student_answer = await _generate_via_gateway(
                system_prompt=test_system_prompt,
                user_prompt=f"Question: {query}\n\nCONTEXT (retrieved teachings):\n{retrieved_context}",
            )

            # 4. Grade faithfulness
            val_result = lettuce.score_faithfulness(
                query=query, context=retrieved_context, answer=student_answer
            )
            is_faithful = val_result.get("is_faithful", False)
            score = val_result.get("score", 0.0)

            logger.info(
                f"Ralph Loop Student output graded: is_faithful={is_faithful}, score={score}"
            )

            # 5. If validated successfully, write to validated patches store
            if is_faithful:
                from app.constants import PROMPT_PATCHES_VALIDATED_FILE_PATH

                validated_entry = {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "query": query,
                    "suggested_correction": suggested_correction,
                    "student_answer": student_answer,
                    "score": score,
                    "teacher_analysis": entry["analysis"],
                }

                os.makedirs(os.path.dirname(PROMPT_PATCHES_VALIDATED_FILE_PATH), exist_ok=True)
                with open(PROMPT_PATCHES_VALIDATED_FILE_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(validated_entry) + "\n")
                logger.info(
                    f"Ralph Loop: Validated patch recorded in {PROMPT_PATCHES_VALIDATED_FILE_PATH}"
                )
                entry["validated"] = True
                entry["student_score"] = score
                entry["student_answer"] = student_answer
            else:
                entry["validated"] = False
                entry["student_score"] = score
                entry["student_answer"] = student_answer
                logger.info(
                    "Ralph Loop: Patch failed student validation run (faithfulness check did not pass)."
                )

        except Exception as exc:
            logger.error(f"Ralph Loop: Student validation run failed with error: {exc}")
            entry["validated"] = False
            entry["validation_error"] = str(exc)

    return entry


if __name__ == "__main__":
    r = parse_refiner_result(
        '```json\n{"category": "hallucination", "analysis": "a", "suggested_correction": "c"}\n```'
    )
    assert r.category == "hallucination", r
    r2 = parse_refiner_result("not json at all")
    assert r2.category == "other", r2
    print("refiner parse OK")
