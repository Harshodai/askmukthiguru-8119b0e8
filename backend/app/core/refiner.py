import json
import os
import logging
from datetime import datetime, timezone
from typing import Optional
from app.dependencies import get_container
from app.constants import FEEDBACK_LESSONS_FILE_PATH

logger = logging.getLogger(__name__)


async def mine_failed_session(
    query: str,
    retrieved_context: str,
    answer: str,
    comment: Optional[str] = None,
) -> dict:
    """
    Background worker that mines a failed session using the local Ollama LLM
    to classify the error and recommend RAG/prompt improvements.
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

    analysis_json = {
        "category": "other",
        "analysis": "LLM call failed",
        "suggested_correction": "None",
    }

    try:
        container = get_container()
        # Call LLM service
        raw_response = await container.ollama.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        # Clean response and parse JSON
        cleaned = raw_response.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        try:
            analysis_json = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(f"Could not parse clean JSON from refiner response: '{cleaned}'")
            analysis_json = {
                "category": "other",
                "analysis": cleaned[:500],
                "suggested_correction": "N/A",
            }
    except Exception as e:
        logger.error(f"Wisdom Refiner failed to analyze session: {e}")
        analysis_json["analysis"] = f"Refiner error: {str(e)}"

    # Append structured entry to feedback_lessons.jsonl
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "category": analysis_json.get("category", "other"),
        "analysis": analysis_json.get("analysis", ""),
        "suggested_correction": analysis_json.get("suggested_correction", ""),
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
            container = get_container()
            
            # 1. Initialize LettuceDetectService with container's embedding
            from services.lettuce_detect_service import LettuceDetectService
            lettuce = LettuceDetectService(embedder=container.embedding)
            
            # 2. Construct test system prompt incorporating the suggested correction
            from rag.prompts import GURU_SYSTEM_PROMPT
            test_system_prompt = (
                f"{GURU_SYSTEM_PROMPT}\n\n"
                f"CRITICAL RULE FOR THIS SESSION (based on past failure):\n"
                f"{suggested_correction}"
            )
            
            # 3. Call local student model (Ollama)
            student_answer = await container.ollama.generate(
                system_prompt=test_system_prompt,
                user_prompt=f"Question: {query}\n\nCONTEXT (retrieved teachings):\n{retrieved_context}",
            )
            
            # 4. Grade faithfulness
            val_result = lettuce.score_faithfulness(query=query, context=retrieved_context, answer=student_answer)
            is_faithful = val_result.get("is_faithful", False)
            score = val_result.get("score", 0.0)
            
            logger.info(f"Ralph Loop Student output graded: is_faithful={is_faithful}, score={score}")
            
            # 5. If validated successfully, write to validated patches store
            if is_faithful:
                from app.constants import PROMPT_PATCHES_VALIDATED_FILE_PATH
                validated_entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "query": query,
                    "suggested_correction": suggested_correction,
                    "student_answer": student_answer,
                    "score": score,
                    "teacher_analysis": entry["analysis"],
                }
                
                os.makedirs(os.path.dirname(PROMPT_PATCHES_VALIDATED_FILE_PATH), exist_ok=True)
                with open(PROMPT_PATCHES_VALIDATED_FILE_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(validated_entry) + "\n")
                logger.info(f"Ralph Loop: Validated patch recorded in {PROMPT_PATCHES_VALIDATED_FILE_PATH}")
                entry["validated"] = True
                entry["student_score"] = score
                entry["student_answer"] = student_answer
            else:
                entry["validated"] = False
                entry["student_score"] = score
                entry["student_answer"] = student_answer
                logger.info("Ralph Loop: Patch failed student validation run (faithfulness check did not pass).")
                
        except Exception as exc:
            logger.error(f"Ralph Loop: Student validation run failed with error: {exc}")
            entry["validated"] = False
            entry["validation_error"] = str(exc)

    return entry
