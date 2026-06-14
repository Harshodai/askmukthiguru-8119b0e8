"""
Mukthi Guru — Ollama LLM Service

Design Patterns:
  - Facade Pattern: Wraps langchain-ollama behind domain-specific methods
  - Template Method: Each LLM task (classify, grade, generate) has its own
    method with tailored prompts and parsing
  - Single Responsibility: Each method does ONE thing with the LLM
  - Dual-Model Strategy: Uses fast 3B model for classification, full 30B for generation

All LLM calls funnel through this service. No other module talks to Ollama directly.
This makes it trivial to swap the LLM provider (e.g., to a Colab-hosted model).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from rag.prompts import (
    BATCH_GRADE_PROMPT,
    COMBINED_VERIFICATION_PROMPT,
    DECOMPOSE_QUERY_PROMPT,
    FAITHFULNESS_CHECK_PROMPT,
    HINT_EXTRACTION_PROMPT,
    HYDE_PROMPT,
    INTENT_CLASSIFICATION_PROMPT,
    IS_COMPLEX_QUERY_PROMPT,
    QUERY_REWRITE_PROMPT,
    SUMMARIZE_PROMPT,
    VERIFICATION_PROMPT,
)

# Import shared circuit breaker (provider-agnostic)
from services.circuit_breaker import (
    CircuitBreakerConfig,
    DefaultCircuitBreaker,
)
from services.streaming_hardening import StreamInterruptedError, guarded_stream  # Unit 18

logger = logging.getLogger(__name__)


class ModelUnavailableError(Exception):  # Unit 25
    """Raised when the primary Ollama model is unreachable or circuit-open.

    ``is_transient`` hints whether a retry with a different provider might succeed.
    """

    def __init__(self, reason: str, is_transient: bool = True) -> None:
        self.is_transient = is_transient
        super().__init__(reason)


class OllamaService:
    """
    Gateway to all LLM operations.

    Uses a dual-model strategy:
    - _llm (Sarvam 30B): Full generation, verification, summarization
    - _llm_fast (llama3.2:3b): Intent classification, grading, complexity checks

    Classification tasks use the fast model for ~10x speed improvement
    while generation tasks use the full model for quality.
    """

    def __init__(self) -> None:
        """Initialize the Ollama LLM clients (main + fast classifier)."""
        gen_model = settings.model_for_generation
        cls_model = settings.model_for_classification

        # Main model — for generation and verification
        # timeout=settings.llm_timeout enforces per-call HTTP timeout on ChatOllama's
        # internal httpx client, preventing unbounded hangs when Ollama is slow/unresponsive
        self._llm = ChatOllama(
            base_url=settings.ollama_base_url,
            model=gen_model,
            temperature=0.1,  # Low temp for factual accuracy
            num_predict=1024,  # Max output tokens (increased for richer spiritual explanations)
            timeout=settings.llm_timeout,  # CRITICAL: prevents unbounded LLM hangs
        )
        logger.info(
            f"Ollama main model ready: {gen_model} (preset: {settings.model_preset}, timeout={settings.llm_timeout}s)"
        )

        # Fast model — for classification tasks (shorter timeout)
        self._llm_fast = ChatOllama(
            base_url=settings.ollama_base_url,
            model=cls_model,
            temperature=0.0,  # Zero temp for deterministic classification
            num_predict=256,  # Classification outputs are short
            timeout=30,  # Fast model: 30s timeout per call
        )
        logger.info(f"Ollama fast model ready: {cls_model} (timeout=30s)")

        # Connection pooling: Create a singleton httpx.AsyncClient for health checks and direct HTTP calls
        self._http_client = None
        self._http_client_lock = asyncio.Lock()

        # Circuit breaker: fail-fast after consecutive failures to prevent cascading hangs
        # Use provider-agnostic circuit breaker from shared module
        from app.constants import CircuitBreakerProvider
        ollama_config = CircuitBreakerConfig.from_provider(CircuitBreakerProvider.OLLAMA.value)
        self._circuit_breaker = DefaultCircuitBreaker(ollama_config)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Fast heuristic: ~1.3 tokens per word (works for English + Indic)."""
        if not text:
            return 0
        return int(len(text.split()) * 1.3)

    @classmethod
    def _enforce_token_budget(cls, prompt_text: str, budget: int, node: str = "generate") -> None:
        """Soft enforcement: warns if estimated tokens exceed budget; raises only at 2x hard limit."""
        import logging
        estimated = cls._estimate_tokens(prompt_text)
        hard_limit = budget * 2
        if estimated > budget:
            logger = logging.getLogger("TokenBudgetGuard")
            if estimated > hard_limit:
                logger.error(
                    f"TOKEN BUDGET HARD LIMIT EXCEEDED [{node}]: estimated={estimated}, "
                    f"hard_limit={hard_limit}"
                )
                raise Exception(
                    f"TokenBudgetExceeded: [{node}] Estimated {estimated} tokens exceed "
                    f"hard limit {hard_limit}."
                )
            logger.warning(
                f"TOKEN BUDGET SOFT EXCEEDED [{node}]: estimated={estimated} > budget={budget}. "
                f"Continuing (within hard limit {hard_limit})."
            )

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        context: str = "",
        **kwargs,
    ) -> str:
        """
        Core generation method using the main (Sarvam 30B) model.

        Args:
            system_prompt: Role and constraints for the LLM
            user_prompt: User's input with any injected context
            context: Retrieved documents (inserted into the prompt)
            **kwargs: Additional model parameters (temperature, top_k, etc.)
        """
        messages = [SystemMessage(content=system_prompt)]

        if context:
            full_prompt = f"Context:\n{context}\n\nQuestion: {user_prompt}"
        else:
            full_prompt = user_prompt

        messages.append(HumanMessage(content=full_prompt))

        # Hard per-call token budget enforcement (Unit 12)
        full_prompt_text = " ".join([m.content for m in messages])
        max_budget = getattr(settings, "max_tokens_per_request", 12000)
        self._enforce_token_budget(full_prompt_text, max_budget, node="generate")

        # Extract timeout from kwargs (pop so it's not passed to bind())
        timeout = kwargs.pop("timeout", settings.llm_timeout)
        max_retries = kwargs.pop("max_retries", 1)

        # Circuit breaker: fail-fast if too many consecutive failures (Unit 25)
        if not self._circuit_breaker.can_execute():
            raise ModelUnavailableError(
                f"Ollama circuit breaker is OPEN — failing fast. "
                f"Will retry after {self._circuit_breaker.recovery_timeout}s recovery timeout.",
                is_transient=True,
            )

        retryer = AsyncRetrying(
            stop=stop_after_attempt(max_retries),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=5.0),
            retry=retry_if_exception_type((asyncio.TimeoutError, httpx.HTTPError)),
            reraise=True,
        )

        try:
            async for attempt in retryer:
                with attempt:
                    chain = self._llm.bind(**kwargs) if kwargs else self._llm
                    response = await asyncio.wait_for(chain.ainvoke(messages), timeout=timeout)
                    content = response.content.strip()
                    import re

                    think_match = re.search(r"<think>(.*?)</think>", content, flags=re.DOTALL)
                    content_outside_think = re.sub(
                        r"<think>.*?</think>", "", content, flags=re.DOTALL
                    ).strip()

                    if content_outside_think:
                        content = content_outside_think
                    elif think_match:
                        content = think_match.group(1).strip()
                    else:
                        content = content.strip()

                    # Token usage logging (Unit 12)
                    tokens_sent = self._estimate_tokens(system_prompt + user_prompt)
                    tokens_received = self._estimate_tokens(content)
                    logger.info(
                        f"tokens_sent={tokens_sent}, tokens_received={tokens_received}, "
                        f"content_len={len(content)}, model={self._llm.model}"
                    )

                    # Update request-scoped token accumulator
                    try:
                        from services.cost_tracker import token_accumulator_var
                        acc = token_accumulator_var.get()
                        if acc is not None:
                            acc.tokens_in += tokens_sent
                            acc.tokens_out += tokens_received
                            acc.model = self._llm.model
                            acc.provider = "ollama"
                    except Exception as e:
                        logger.warning(f"Failed to record Ollama token usage: {e}")

                    self._circuit_breaker.record_success()
                    return content
        except (asyncio.TimeoutError, httpx.ConnectError, httpx.RemoteProtocolError) as e:
            self._circuit_breaker.record_failure()
            logger.error(f"Ollama generation failed (transient): {type(e).__name__}: {e}")
            raise ModelUnavailableError(str(e), is_transient=True) from e
        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error(f"Ollama generation failed: {e}")
            raise

    async def _generate_fast(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs,
    ) -> str:
        """
        Fast classification using the lightweight model (llama3.2:3b).

        Used for binary/ternary classification tasks where the full 30B
        model is overkill. ~10x faster for intent, grading, complexity checks.
        """
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        _FAST_TIMEOUT = 25
        _FAST_RETRIES = 2
        timeout = kwargs.pop("timeout", _FAST_TIMEOUT)
        max_retries = kwargs.pop("max_retries", _FAST_RETRIES)

        # Circuit breaker: fail-fast if too many consecutive failures (Unit 25)
        if not self._circuit_breaker.can_execute():
            raise ModelUnavailableError(
                f"Ollama circuit breaker is OPEN — failing fast. "
                f"Will retry after {self._circuit_breaker.recovery_timeout}s recovery timeout.",
                is_transient=True,
            )

        retryer = AsyncRetrying(
            stop=stop_after_attempt(max_retries),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=5.0),
            retry=retry_if_exception_type((asyncio.TimeoutError, httpx.HTTPError)),
            reraise=True,
        )

        try:
            async for attempt in retryer:
                with attempt:
                    chain = self._llm_fast.bind(**kwargs) if kwargs else self._llm_fast
                    response = await asyncio.wait_for(chain.ainvoke(messages), timeout=timeout)
                    content = response.content.strip()
                    import re

                    think_match = re.search(r"<think>(.*?)</think>", content, flags=re.DOTALL)
                    content_outside_think = re.sub(
                        r"<think>.*?</think>", "", content, flags=re.DOTALL
                    ).strip()

                    if content_outside_think:
                        content = content_outside_think
                    elif think_match:
                        content = think_match.group(1).strip()
                    else:
                        content = content.strip()

                    tokens_sent = self._estimate_tokens(system_prompt + user_prompt)
                    tokens_received = self._estimate_tokens(content)
                    try:
                        from services.cost_tracker import token_accumulator_var
                        acc = token_accumulator_var.get()
                        if acc is not None:
                            acc.tokens_in += tokens_sent
                            acc.tokens_out += tokens_received
                            acc.model = self._llm_fast.model
                            acc.provider = "ollama"
                    except Exception as e:
                        logger.warning(f"Failed to record Ollama fast token usage: {e}")

                    self._circuit_breaker.record_success()
                    return content
        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.warning(f"Fast model failed: {e}, falling back to main model")
            return await self.generate(system_prompt, user_prompt, **kwargs)

    async def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        context: str = "",
        **kwargs,
    ) -> AsyncIterator[str]:
        """
        Streaming generation using the main model.

        Yields tokens as they are generated for SSE streaming.
        """
        timeout = kwargs.pop("timeout", settings.llm_timeout)
        max_retries = kwargs.pop("max_retries", 1)

        if not self._circuit_breaker.can_execute():
            raise ModelUnavailableError(
                f"Ollama circuit breaker is OPEN — failing fast. "
                f"Will retry after {self._circuit_breaker.recovery_timeout}s recovery timeout.",
                is_transient=True,
            )

        messages = [SystemMessage(content=system_prompt)]
        if context:
            full_prompt = f"Context:\n{context}\n\nQuestion: {user_prompt}"
        else:
            full_prompt = user_prompt
        messages.append(HumanMessage(content=full_prompt))

        retryer = AsyncRetrying(
            stop=stop_after_attempt(max_retries),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=5.0),
            retry=retry_if_exception_type((asyncio.TimeoutError, httpx.HTTPError)),
            reraise=True,
        )

        async def _raw_stream() -> AsyncIterator[str]:
            """Inner generator — yields filtered tokens from the chain."""
            async for attempt in retryer:
                with attempt:
                    chain = self._llm.bind(**kwargs) if kwargs else self._llm
                    in_think_block = False
                    async for chunk in await asyncio.wait_for(
                        chain.astream(messages), timeout=timeout
                    ):
                        if not chunk.content:
                            continue
                        text = chunk.content
                        while text:
                            if in_think_block:
                                end = text.find("</think>")
                                if end == -1:
                                    text = ""
                                else:
                                    text = text[end + 8:]
                                    in_think_block = False
                                continue
                            start = text.find("<think>")
                            if start == -1:
                                yield text
                                text = ""
                            else:
                                if start > 0:
                                    yield text[:start]
                                text = text[start + 7:]
                                in_think_block = True
            self._circuit_breaker.record_success()

        # Unit 18: wrap in guarded_stream to handle mid-stream failures gracefully
        try:
            tokens_sent = self._estimate_tokens(system_prompt + user_prompt)
            accumulated_tokens = ""
            async for token in guarded_stream(_raw_stream()):
                accumulated_tokens += token
                yield token
            
            tokens_received = self._estimate_tokens(accumulated_tokens)
            try:
                from services.cost_tracker import token_accumulator_var
                acc = token_accumulator_var.get()
                if acc is not None:
                    acc.tokens_in += tokens_sent
                    acc.tokens_out += tokens_received
                    acc.model = self._llm.model
                    acc.provider = "ollama"
            except Exception as e:
                logger.warning(f"Failed to record Ollama stream token usage: {e}")
        except StreamInterruptedError:
            self._circuit_breaker.record_failure()
            # StreamInterruptedError already yielded the sentinel; just log
            logger.error("Ollama streaming interrupted mid-stream")
        except (asyncio.TimeoutError, httpx.ConnectError, httpx.RemoteProtocolError) as e:
            self._circuit_breaker.record_failure()
            logger.error(f"Ollama streaming failed (transient): {type(e).__name__}: {e}")
            raise ModelUnavailableError(str(e), is_transient=True) from e
        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error(f"Ollama streaming failed: {e}")
            raise

    async def classify_intent(self, message: str, **kwargs) -> str:
        """
        Classify user message into one of the designated intents.

        OPTIMIZATION (Phase-1 / Truth-3): Routed to the FAST model
        (llama3.2:3b style classifier) instead of the main generation
        model. Classification is a single-label task; it does not
        benefit from deepseek-r1's chain-of-thought traces.
        Empirical impact: ~30s → ~0.5s per intent call.
        """
        # --- LEGACY (preserved per "do not delete, just comment") ---
        # result = await self.generate(INTENT_CLASSIFICATION_PROMPT, message, **kwargs)
        # ------------------------------------------------------------
        result = await self._generate_fast(INTENT_CLASSIFICATION_PROMPT, message, **kwargs)

        # Parse — be lenient with LLM output
        result_upper = result.upper().strip()
        if "DISTRESS" in result_upper:
            return "DISTRESS"
        elif (
            "SAFETY_VIOLATION" in result_upper
            or "SAFETY" in result_upper
            or "VIOLATION" in result_upper
        ):
            return "SAFETY_VIOLATION"
        elif "ADVERSARIAL" in result_upper:
            return "ADVERSARIAL"
        elif "FACTUAL" in result_upper or "QUERY" in result_upper:
            return "FACTUAL"
        elif "RELATIONAL" in result_upper:
            return "RELATIONAL"
        elif "FOLLOW_UP" in result_upper:
            return "FOLLOW_UP"
        elif "MEDITATION" in result_upper:
            return "MEDITATION"
        else:
            return "CASUAL"

    async def classify_intent_and_complexity(self, text: str, **kwargs) -> dict:
        """
        Combined intent + complexity classification in ONE fast-model LLM call.

        OPTIMIZATION (Phase-1 / Truth-3): The previous two-call sequence
        (classify_intent + is_complex_query) is now a single ~0.5s call.
        Used by the intent_router node; falls back to two sequential calls
        if combined parsing fails.

        Returns:
            {"intent": <intent>, "complexity": "simple"|"complex"}
        """
        from rag.prompts import INTENT_AND_COMPLEXITY_PROMPT

        try:
            result = await self._generate_fast(
                INTENT_AND_COMPLEXITY_PROMPT, text, **kwargs
            )
            result_upper = result.upper().strip()

            # Parse intent (first matching label wins; order = priority)
            intent = "CASUAL"
            for label in (
                "DISTRESS", "SAFETY_VIOLATION", "ADVERSARIAL",
                "FACTUAL", "RELATIONAL", "FOLLOW_UP",
                "MEDITATION", "CASUAL",
            ):
                if label in result_upper:
                    intent = label
                    break

            # Parse complexity — must look at the value AFTER "COMPLEXITY:"
            # because the literal token "COMPLEXITY" contains "COMPLEX" and
            # would otherwise force every response to be classified complex.
            complexity = "simple"
            for line in result_upper.splitlines():
                if line.startswith("COMPLEXITY"):
                    # Take the substring after the colon (or after the word)
                    value = line.split(":", 1)[-1] if ":" in line else line.replace("COMPLEXITY", "", 1)
                    if "COMPLEX" in value:
                        complexity = "complex"
                    else:
                        complexity = "simple"
                    break
            else:
                # No COMPLEXITY: line — fall back to substring check, but
                # explicitly subtract the prompt-echo of "COMPLEXITY"
                stripped = result_upper.replace("COMPLEXITY", "")
                complexity = "complex" if "COMPLEX" in stripped else "simple"

            return {"intent": intent, "complexity": complexity}
        except Exception as e:
            logger.warning(
                f"Combined intent+complexity parse failed ({e}); falling back to legacy two-call path."
            )
            intent = await self.classify_intent(text, **kwargs)
            complexity = await self.classify_complexity(text)
            return {"intent": intent, "complexity": complexity}

    async def classify_complexity(self, text: str) -> str:
        """Classify user question complexity into 'simple' or 'complex' using the fast model."""
        is_complex = await self.is_complex_query(text)
        return "complex" if is_complex else "simple"

    async def classify_distress_structured(self, message: str) -> dict:
        """
        Phase 3: Deterministic JSON outputs via Instructor (replacing Guardrails AI).
        Uses Instructor to strictly enforce a Pydantic schema for distress classification.
        """
        import instructor
        from openai import AsyncOpenAI
        from pydantic import BaseModel, Field

        class DistressOutput(BaseModel):
            is_distress: bool = Field(
                description="True if the user is in distress, sad, or asking for help with negative emotions"
            )
            confidence: float = Field(description="Confidence score from 0.0 to 1.0")
            reason: str = Field(description="Brief reason for the assessment")

        client = instructor.from_openai(
            AsyncOpenAI(
                base_url=f"{settings.ollama_base_url}/v1",
                api_key="ollama",  # required, but unused
            ),
            mode=instructor.Mode.JSON,
        )

        prompt = (
            f"Analyze the following message for emotional distress or a cry for help:\n\n{message}"
        )

        try:
            resp: DistressOutput = await client.chat.completions.create(
                model=settings.model_for_classification,
                messages=[
                    {"role": "system", "content": "You are a psychological safety assessor."},
                    {"role": "user", "content": prompt},
                ],
                response_model=DistressOutput,
                max_retries=3,
            )
            return {
                "is_distress": resp.is_distress,
                "confidence": resp.confidence,
                "reason": resp.reason,
            }
        except Exception as e:
            logger.warning(f"Instructor structured output failed: {e}")
            # Fallback to naive parsing if Instructor fails
            intent = await self.classify_intent(message)
            return {
                "is_distress": intent == "DISTRESS",
                "confidence": 0.5,
                "reason": f"Fallback naive classification (intent={intent})",
            }

    async def batch_grade_relevance(self, query: str, documents: list[str], **kwargs) -> list[dict]:
        """
        CRAG: Batch relevance grading of multiple documents in one LLM call.

        Instead of N separate calls (one per document), grades all documents
        at once with a structured prompt. Reduces LLM calls from N to 1.
        Uses the fast model for speed.

        Returns: List of dicts, one per document ({"relevant": bool, "reason": str}).
        """
        if not documents:
            return []

        # Build numbered document list
        numbered_docs = "\n\n".join(
            f"Document {i + 1}:\n{doc[:1500]}"  # Truncate individual docs to fit context
            for i, doc in enumerate(documents)
        )

        prompt = f"Question: {query}\n\n{numbered_docs}"
        result = await self._generate_fast(BATCH_GRADE_PROMPT, prompt, **kwargs)

        # Parse "1: yes - [reason]\n2: no - [reason]" format
        relevance_data = [
            {"relevant": False, "reason": "No reason provided"} for _ in range(len(documents))
        ]
        for line in result.strip().splitlines():
            line = line.strip()
            if ":" in line:
                parts = line.split(":", 1)
                try:
                    idx = int(parts[0].strip()) - 1  # 1-indexed → 0-indexed
                    if 0 <= idx < len(documents):
                        content = parts[1].strip()
                        is_relevant = "yes" in content.lower().split("-")[0]
                        reason = content.split("-", 1)[1].strip() if "-" in content else content
                        relevance_data[idx] = {"relevant": is_relevant, "reason": reason}
                except (ValueError, IndexError):
                    continue

        return relevance_data

    async def check_faithfulness(self, answer: str, context: str, **kwargs) -> bool:
        """
        Self-RAG: Check if the generated answer is faithful to the context.

        Returns True if EVERY claim in the answer is supported by the context.
        Returns False if ANY unsupported claim is detected.

        Uses the fast model for speed.
        """
        prompt = f"Context:\n{context}\n\nAnswer:\n{answer}"
        result = await self._generate_fast(FAITHFULNESS_CHECK_PROMPT, prompt, **kwargs)
        return "faithful" in result.lower()

    async def extract_hints(self, query: str, documents: list[str]) -> list[str]:
        """
        Stimulus RAG: Extract key evidence hints from retrieved documents.

        Instead of dumping raw documents into the generation prompt,
        we first extract the most relevant phrases/sentences. This focuses
        the LLM's attention on precise evidence rather than noisy context.

        Returns: List of 3-5 key hint phrases
        """
        combined_docs = "\n---\n".join(documents)
        system = HINT_EXTRACTION_PROMPT
        prompt = f"Question: {query}\n\nDocuments:\n{combined_docs}"

        result = await self.generate(system, prompt)

        # Parse hints from bullet points
        hints = []
        for line in result.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("• "):
                hints.append(line[2:].strip())
            elif line and not line.startswith("#"):
                hints.append(line)

        return hints[:5]  # Cap at 5 hints

    async def rewrite_query(self, original_query: str, reasons: list[str] = None, **kwargs) -> str:
        """
        CRAG: Rewrite a query to improve retrieval quality.

        Uses the main model for better query expansion with spiritual terminology.
        If reasons for previous retrieval failure are provided, they are incorporated.
        """
        prompt = f"Original query: {original_query}"
        if reasons:
            prompt += "\n\nReasons for previous retrieval failure:\n- " + "\n- ".join(reasons[:5])
            prompt += (
                "\n\nRewrite the query to address these gaps while keeping the spiritual essence."
            )

        return await self.generate(QUERY_REWRITE_PROMPT, prompt, **kwargs)

    async def verify_claims(self, answer: str, context: str) -> dict:
        """
        Chain of Verification (CoVe): Generate verification questions and check.

        This is the FINAL safety net (layer 11). Uses the main model.
        """
        prompt = f"Answer:\n{answer}\n\nContext:\n{context}"
        result = await self.generate(VERIFICATION_PROMPT, prompt)

        # Parse the VERDICT line robustly
        lines = result.upper().strip().splitlines()
        verdict_line = ""
        for line in reversed(lines):
            if "VERDICT" in line:
                verdict_line = line
                break

        if verdict_line:
            after_verdict = verdict_line.split("VERDICT", 1)[-1]
            passed = "PASS" in after_verdict and "FAIL" not in after_verdict
        else:
            logger.warning(
                "CoVe: No VERDICT line found in verification output. "
                f"Raw result (first 200 chars): {result[:200]!r}"
            )
            passed = False

        return {
            "passed": passed,
            "details": result,
        }

    async def combined_verify(self, answer: str, context: str) -> dict:
        """
        Combined Self-RAG + CoVe verification in a single LLM call.

        Merges faithfulness checking (layer 10) and claim verification (layer 11)
        into one structured prompt, reducing 2 LLM calls to 1.
        Also extracts a confidence score (1-10) for graduated response gating.

        Returns:
            Dict with 'is_faithful' (bool), 'passed' (bool),
            'confidence' (float), 'details' (str)
        """
        system = COMBINED_VERIFICATION_PROMPT
        prompt = f"Answer:\n{answer}\n\nContext:\n{context}"

        result = await self.generate(system, prompt, temperature=0.0)

        result_upper = result.upper().strip()
        lines = result_upper.splitlines()

        # Parse FAITHFULNESS line
        is_faithful = False
        for line in lines:
            if "FAITHFULNESS" in line:
                after = line.split("FAITHFULNESS", 1)[-1]
                is_faithful = "FAITHFUL" in after and "HALLUCINATED" not in after
                break

        # Parse VERDICT line
        passed = False
        for line in reversed(lines):
            if "VERDICT" in line:
                after = line.split("VERDICT", 1)[-1]
                passed = "PASS" in after and "FAIL" not in after
                break

        # Parse CONFIDENCE line (1-10)
        confidence = 5.0  # Default mid-range
        for line in lines:
            if "CONFIDENCE" in line:
                after = line.split("CONFIDENCE", 1)[-1]
                # Extract first number from the line
                import re

                nums = re.findall(r"\d+", after)
                if nums:
                    try:
                        confidence = float(min(int(nums[0]), 10))
                    except (ValueError, IndexError):
                        pass
                break

        # Both must pass
        final_passed = is_faithful and passed

        if not final_passed:
            logger.info(
                f"Combined verify: faithful={is_faithful}, verdict_pass={passed}, "
                f"confidence={confidence}"
            )

        return {
            "is_faithful": is_faithful,
            "passed": final_passed,
            "confidence": confidence,
            "details": result,
        }

    async def summarize(self, texts: list[str]) -> str:
        """
        Summarize a cluster of text chunks (used by RAPTOR).

        Creates mid-level tree nodes that capture thematic relationships
        between individual chunks. Uses the main model for quality.
        """
        combined = "\n\n".join(texts)
        return await self.generate(SUMMARIZE_PROMPT, combined)

    async def decompose_query(self, query: str, **kwargs) -> list[str]:
        """
        Query Decomposition: Split complex questions into atomic sub-queries.

        Returns: List of 2-3 simpler sub-queries.
        Uses the fast model since this is a classification/parsing task.
        """
        result = await self._generate_fast(DECOMPOSE_QUERY_PROMPT, query, **kwargs)

        sub_queries = []
        for line in result.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("• "):
                sub_queries.append(line[2:].strip())
            elif line.startswith(("1.", "2.", "3.")):
                sub_queries.append(line[2:].strip())

        return sub_queries if sub_queries else [query]

    async def generate_hypothetical_answer(self, query: str, **kwargs) -> str:
        """
        HyDE (Hypothetical Document Embeddings): Generate a fake answer.

        OPTIMIZATION (Phase-2 / Truth-3): Routed to the FAST model.
        HyDE only needs an approximate, plausible answer to feed retrieval —
        the embedding similarity does not benefit from deepseek-r1's chain-of-thought.
        Empirical impact: HyDE node ~4s → ~1s.
        """
        # --- LEGACY (preserved per "do not delete, just comment") ---
        # return await self.generate(HYDE_PROMPT, query, **kwargs)
        # ------------------------------------------------------------
        return await self._generate_fast(HYDE_PROMPT, query, **kwargs)

    async def is_complex_query(self, query: str, **kwargs) -> bool:
        """
        Determine if a query needs decomposition.

        Uses the fast model since this is a binary classification.
        """
        result = await self._generate_fast(IS_COMPLEX_QUERY_PROMPT, query, **kwargs)
        return "complex" in result.lower()

    async def compress_context(self, question: str, document_text: str, **kwargs) -> str:
        """
        Compress a document chunk using the fast LLM to retain only relevant information.
        If NO_RELEVANT_CONTEXT is returned, it returns an empty string.
        """
        from rag.prompts import COMPRESS_CONTEXT_PROMPT

        prompt = COMPRESS_CONTEXT_PROMPT.format(question=question, document_text=document_text)
        # Always use the fast model for compression to save time
        compressed = await self._generate_fast("", prompt, **kwargs)

        if "NO_RELEVANT_CONTEXT" in compressed:
            return ""

        return compressed.strip()

    async def translate_text(
        self,
        text: str,
        source_language_code: str,
        target_language_code: str,
    ) -> str:
        """
        Translate text using the local LLM if source and target differ.
        """
        if not text.strip():
            return ""

        src_code = source_language_code.lower().split("-")[0]
        tgt_code = target_language_code.lower().split("-")[0]

        if src_code == tgt_code:
            return text

        # Call the fast model to do the translation to reduce lag
        prompt = (
            f"You are a professional translator. Translate the following text from "
            f"language code '{src_code}' to language code '{tgt_code}'. "
            f"Provide ONLY the final translation. Do not include any notes, explanations, or quotes.\n\n"
            f"Text to translate:\n{text}"
        )
        try:
            translated = await self._generate_fast(
                system_prompt="You are a professional translator. Output only the translated text.",
                user_prompt=prompt,
            )
            return translated.strip()
        except Exception as e:
            logger.error(f"Ollama translation failed: {e}")
            return text

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create the singleton HTTP client with connection pooling."""
        async with self._http_client_lock:
            if self._http_client is None:
                # Configure connection pool limits from settings
                limits = httpx.Limits(
                    max_connections=getattr(settings, "http_max_connections", 100),
                    max_keepalive_connections=getattr(
                        settings, "http_max_keepalive_connections", 20
                    ),
                    keepalive_expiry=getattr(settings, "http_keepalive_expiry", 30.0),
                )
                self._http_client = httpx.AsyncClient(
                    timeout=getattr(settings, "llm_timeout", 60), limits=limits
                )
                logger.info(
                    f"Ollama HTTP client initialized with pool limits: "
                    f"max_connections={limits.max_connections}, "
                    f"max_keepalive_connections={limits.max_keepalive_connections}"
                )
            return self._http_client

    @property
    def is_available(self) -> bool:
        """Return True if the Ollama service is available for use."""
        return True

    async def health_check(self) -> bool:
        """Check if Ollama is reachable (async)."""
        try:
            client = await self._get_http_client()
            resp = await client.get(f"{settings.ollama_base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        async with self._http_client_lock:
            if self._http_client is not None:
                await self._http_client.aclose()
                self._http_client = None
                logger.info("Ollama HTTP client closed")
