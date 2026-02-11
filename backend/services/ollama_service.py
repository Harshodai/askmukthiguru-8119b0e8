"""
Mukthi Guru — Ollama LLM Service

Design Patterns:
  - Facade Pattern: Wraps langchain-ollama behind domain-specific methods
  - Template Method: Each LLM task (classify, grade, generate) has its own
    method with tailored prompts and parsing
  - Single Responsibility: Each method does ONE thing with the LLM

All LLM calls funnel through this service. No other module talks to Ollama directly.
This makes it trivial to swap the LLM provider (e.g., to a Colab-hosted model).
"""

import logging
from typing import Optional

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings

logger = logging.getLogger(__name__)


class OllamaService:
    """
    Gateway to all LLM operations.
    
    Every method is a specific "capability" of the LLM:
    - generate(): Free-form generation with context
    - classify_intent(): DISTRESS / QUERY / CASUAL routing
    - grade_relevance(): Binary doc relevance check (CRAG)
    - check_faithfulness(): Is the answer grounded? (Self-RAG)
    - extract_hints(): Pull key phrases from docs (Stimulus RAG)
    - rewrite_query(): Expand/rephrase for better retrieval
    - verify_claims(): Generate verification sub-questions (CoVe)
    - summarize(): Condensed summary for RAPTOR tree nodes
    """

    def __init__(self) -> None:
        """Initialize the Ollama LLM client."""
        self._llm = ChatOllama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            temperature=0.1,  # Low temp for factual accuracy
            num_predict=512,  # Limit output length
        )
        logger.info(f"Ollama service ready: {settings.ollama_model}")

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        context: str = "",
    ) -> str:
        """
        Core generation method. All other methods build on top of this.
        
        Args:
            system_prompt: Role and constraints for the LLM
            user_prompt: User's input with any injected context
            context: Retrieved documents (inserted into the prompt)
            
        Returns:
            LLM response text
        """
        messages = [SystemMessage(content=system_prompt)]

        if context:
            full_prompt = f"Context:\n{context}\n\nQuestion: {user_prompt}"
        else:
            full_prompt = user_prompt

        messages.append(HumanMessage(content=full_prompt))

        try:
            response = await self._llm.ainvoke(messages)
            return response.content.strip()
        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            raise

    async def classify_intent(self, message: str) -> str:
        """
        Classify user message into one of three intents.
        
        Returns: 'DISTRESS' | 'QUERY' | 'CASUAL'
        
        This is the first decision point in the pipeline:
        - DISTRESS → triggers Serene Mind meditation
        - QUERY → enters the 11-layer RAG pipeline
        - CASUAL → warm, brief conversational reply
        """
        system = (
            "You are an intent classifier for a spiritual guidance app. "
            "Classify the user's message into exactly one category:\n\n"
            "DISTRESS - The user is expressing emotional pain, stress, anxiety, "
            "sadness, anger, fear, loneliness, hopelessness, or seeks comfort. "
            "Examples: 'I'm so stressed', 'Life feels meaningless', 'I can't sleep'\n\n"
            "QUERY - The user is asking a question about spiritual teachings, "
            "meditation, consciousness, or seeking knowledge. "
            "Examples: 'What is the Beautiful State?', 'How do I meditate?'\n\n"
            "CASUAL - The user is making small talk, greeting, or a general comment. "
            "Examples: 'Hello', 'Thank you', 'How are you?'\n\n"
            "Respond with ONLY the category name: DISTRESS, QUERY, or CASUAL"
        )

        result = await self.generate(system, message)
        
        # Parse — be lenient with LLM output
        result_upper = result.upper().strip()
        if "DISTRESS" in result_upper:
            return "DISTRESS"
        elif "QUERY" in result_upper:
            return "QUERY"
        else:
            return "CASUAL"

    async def grade_relevance(self, query: str, document: str) -> bool:
        """
        CRAG: Binary relevance grading of a retrieved document.
        
        Returns True if the document is relevant to the query.
        
        This is layer 6 in the anti-hallucination pipeline.
        If no documents pass this gate, the query gets rewritten (up to 3x).
        """
        system = (
            "You are a relevance grader for a spiritual guidance system. "
            "Given a user question and a retrieved document, determine if the "
            "document contains information relevant to answering the question.\n\n"
            "Respond with ONLY 'yes' or 'no'."
        )
        prompt = f"Question: {query}\n\nDocument: {document}"
        
        result = await self.generate(system, prompt)
        return "yes" in result.lower()

    async def check_faithfulness(self, answer: str, context: str) -> bool:
        """
        Self-RAG: Check if the generated answer is faithful to the context.
        
        Returns True if EVERY claim in the answer is supported by the context.
        Returns False if ANY unsupported claim is detected.
        
        This is layer 10 — the post-generation safety net.
        If this fails, the entire answer is discarded.
        """
        system = (
            "You are a faithfulness checker for a spiritual guidance system. "
            "Your job is to verify that EVERY claim in the Answer is directly "
            "supported by the Context. \n\n"
            "If ANY sentence in the Answer contains information NOT found in "
            "the Context, respond 'hallucinated'.\n"
            "If ALL sentences are fully supported by the Context, respond 'faithful'.\n\n"
            "Respond with ONLY 'faithful' or 'hallucinated'."
        )
        prompt = f"Context:\n{context}\n\nAnswer:\n{answer}"
        
        result = await self.generate(system, prompt)
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
        system = (
            "You are a hint extractor for a spiritual guidance system. "
            "Given a question and retrieved teaching documents, extract "
            "the 3-5 most relevant key phrases, sentences, or concepts "
            "that directly answer the question.\n\n"
            "Format: Return each hint on a new line, prefixed with '- '.\n"
            "Be precise. Use exact quotes from the documents when possible."
        )
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

    async def rewrite_query(self, original_query: str) -> str:
        """
        CRAG: Rewrite a query to improve retrieval quality.
        
        When retrieved documents aren't relevant (CRAG grading fails),
        this rewrites the query with:
        - Expanded spiritual terminology
        - Synonym injection
        - Rephrased structure
        
        Part of the self-correcting retrieval loop (max 3 attempts).
        """
        system = (
            "You are a query rewriter for a spiritual teachings search system. "
            "The original query didn't retrieve good results. Rewrite it to:\n"
            "1. Add synonyms for spiritual terms (e.g., 'suffering' → 'dukkha, pain, anguish')\n"
            "2. Expand abbreviations or shorthand\n"
            "3. Rephrase for clarity\n"
            "4. Add related concepts from Sri Krishnaji and Sri Preethaji's teachings\n\n"
            "Return ONLY the rewritten query, nothing else."
        )
        
        return await self.generate(system, f"Original query: {original_query}")

    async def verify_claims(self, answer: str, context: str) -> dict:
        """
        Chain of Verification (CoVe): Generate verification questions and check.
        
        This is the FINAL safety net (layer 11). It:
        1. Generates 2-3 verification questions from the answer
        2. Checks if the context can answer them
        3. Returns pass/fail with details
        
        If ANY verification question cannot be answered from context,
        the answer is rejected.
        """
        system = (
            "You are a fact-checker for a spiritual guidance system. "
            "Given an answer and its source context, do the following:\n\n"
            "1. Generate 2-3 specific verification questions based on claims in the Answer\n"
            "2. Check if the Context can answer each question\n"
            "3. Respond in this exact format:\n"
            "Q1: [question]\n"
            "A1: [VERIFIED or UNVERIFIED] - [brief reason]\n"
            "Q2: [question]\n"
            "A2: [VERIFIED or UNVERIFIED] - [brief reason]\n"
            "VERDICT: [PASS or FAIL]"
        )
        prompt = f"Answer:\n{answer}\n\nContext:\n{context}"
        
        result = await self.generate(system, prompt)
        
        # Parse the VERDICT line robustly
        lines = result.upper().strip().splitlines()
        verdict_line = ""
        for line in reversed(lines):
            if "VERDICT" in line:
                verdict_line = line
                break
        
        if verdict_line:
            # Check the text AFTER "VERDICT" on that line
            after_verdict = verdict_line.split("VERDICT", 1)[-1]
            passed = "PASS" in after_verdict and "FAIL" not in after_verdict
        else:
            # No VERDICT line found — treat as verification failure.
            # Absence of a clear safe verdict must be treated as rejection
            # to prevent unverified answers from reaching the user.
            logger.warning(
                "CoVe: No VERDICT line found in verification output. "
                f"Raw result (first 200 chars): {result[:200]!r}"
            )
            passed = False
        
        return {
            "passed": passed,
            "details": result,
        }

    async def summarize(self, texts: list[str]) -> str:
        """
        Summarize a cluster of text chunks (used by RAPTOR).
        
        Creates mid-level tree nodes that capture thematic relationships
        between individual chunks.
        """
        combined = "\n\n".join(texts)
        system = (
            "You are a spiritual teachings summarizer. "
            "Summarize the following related text passages into a single, "
            "cohesive paragraph that captures the key teachings, concepts, "
            "and wisdom. Preserve important spiritual terminology. "
            "Keep the summary under 200 words."
        )
        
        return await self.generate(system, combined)

    async def decompose_query(self, query: str) -> list[str]:
        """
        Query Decomposition: Split complex questions into atomic sub-queries.
        
        Only triggered for complex queries (e.g., "Compare X and Y",
        "What are the differences between...").
        
        Returns: List of 2-3 simpler sub-queries
        """
        system = (
            "You are a query decomposer for a spiritual teachings search. "
            "The user asked a complex question. Break it into 2-3 simpler, "
            "independent sub-questions that together answer the original.\n\n"
            "Format: Return each sub-question on a new line, prefixed with '- '.\n"
            "If the question is already simple, return it unchanged as a single item."
        )
        
        result = await self.generate(system, query)
        
        sub_queries = []
        for line in result.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("• "):
                sub_queries.append(line[2:].strip())
            elif line.startswith(("1.", "2.", "3.")):
                sub_queries.append(line[2:].strip())
        
        return sub_queries if sub_queries else [query]

    async def is_complex_query(self, query: str) -> bool:
        """
        Determine if a query needs decomposition.
        
        Returns True for queries that contain comparisons, multiple concepts,
        or multi-part questions.
        """
        system = (
            "Determine if this question is complex (needs to be broken into parts) "
            "or simple (can be answered directly). A question is complex if it:\n"
            "- Compares two or more concepts\n"
            "- Asks about multiple unrelated things\n"
            "- Contains 'and', 'vs', 'compare', 'difference between'\n\n"
            "Respond with ONLY 'complex' or 'simple'."
        )
        
        result = await self.generate(system, query)
        return "complex" in result.lower()

    async def health_check(self) -> bool:
        """Check if Ollama is reachable (async)."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{settings.ollama_base_url}/api/tags", timeout=5
                )
            return resp.status_code == 200
        except Exception:
            return False
