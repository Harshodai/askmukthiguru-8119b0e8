"""
Mukthi Guru — Chain-of-Thought Verifier (Chain-of-Thought Pattern)

Extracts reusable CoT logic from verify_answer and reflect_on_answer nodes.
Produces sub-questions, retrieves evidence, and aggregates a confidence score.

Design Patterns:
  - Strategy: Pluggable evidence-retrieval and scoring strategies
  - Template Method: SubQuestion → Retrieve → Score → Aggregate
"""

from __future__ import annotations

import logging
from typing import List

logger = logging.getLogger(__name__)


class CoTSubQuestion:
    """A single sub-question generated to verify a claim."""

    def __init__(self, question: str, claim: str) -> None:
        self.question = question
        self.claim = claim
        self.evidence: str = ""
        self.score: float = 0.0

    def __repr__(self) -> str:
        return f"CoTSubQuestion(q={self.question!r}, score={self.score:.2f})"


class CoTVerifier:
    """
    Generic CoT verifier that can be used by any pipeline node.

    Usage:
        verifier = CoTVerifier()
        result = await verifier.verify(answer="...", context="...", llm_service=...)
    """

    MAX_SUBQUESTIONS = 5

    async def generate_sub_questions(self, answer: str, context: str, llm_service) -> List[CoTSubQuestion]:
        """Ask the LLM to generate sub-questions based on claims in the answer."""
        prompt = (
            "Analyze the following answer and its supporting context. "
            "Generate up to 3 focused sub-questions that, if answered, "
            "would verify whether the answer is faithful to the context.\n\n"
            f"Answer:\n{answer}\n\nContext:\n{context}"
        )
        raw = await llm_service.generate("", prompt)
        questions = [q.strip() for q in raw.split("\n") if q.strip() and "?" in q]
        return [CoTSubQuestion(q, claim=q) for q in questions[: self.MAX_SUBQUESTIONS]]

    async def retrieve_evidence(self, sub_question: CoTSubQuestion, context: str) -> str:
        """Find the most relevant context snippet for a sub-question."""
        # Simple implementation: grab the paragraph with the most keyword overlap
        # Override with embedding/retrieval if needed
        snippets = context.split("\n\n")
        best = max(snippets, key=lambda s: sum(1 for w in sub_question.question.split() if w in s), default="")
        return best

    async def score_sub_question(self, sub_question: CoTSubQuestion, llm_service) -> float:
        """Score how well the evidence supports the claim."""
        prompt = (
            f"Question: {sub_question.question}\n"
            f"Claim: {sub_question.claim}\n"
            f"Evidence: {sub_question.evidence}\n\n"
            "Rate the evidence-to-claim support on a scale of 0.0 to 1.0. "
            "Respond ONLY with the numeric score."
        )
        raw = await llm_service.generate("", prompt)
        try:
            return float(raw.strip())
        except ValueError:
            return 0.0

    async def verify(self, answer: str, context: str, llm_service) -> dict:
        """
        Run the full CoT verification pipeline.

        Returns a dict with:
          - sub_questions: list of CoTSubQuestion objects
          - average_score: float (0.0 – 1.0)
          - verdict: "supported" | "partial" | "unsupported"
        """
        sub_questions = await self.generate_sub_questions(answer, context, llm_service)

        total = 0.0
        for sq in sub_questions:
            sq.evidence = await self.retrieve_evidence(sq, context)
            sq.score = await self.score_sub_question(sq, llm_service)
            total += sq.score

        avg = total / len(sub_questions) if sub_questions else 0.0
        verdict = "supported" if avg >= 0.8 else "partial" if avg >= 0.5 else "unsupported"

        return {
            "sub_questions": sub_questions,
            "average_score": avg,
            "verdict": verdict,
        }
