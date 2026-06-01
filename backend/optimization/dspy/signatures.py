"""DSPy signatures for offline RAG program optimization."""

from __future__ import annotations

try:
    import dspy
except Exception:  # pragma: no cover - optional dependency
    dspy = None


if dspy:

    class QueryRewrite(dspy.Signature):
        """Rewrite a user question into a standalone retrieval query."""

        question = dspy.InputField()
        chat_history = dspy.InputField()
        rewritten_query = dspy.OutputField()

    class CitationSupportedAnswer(dspy.Signature):
        """Answer only from retrieved context and preserve citation support."""

        question = dspy.InputField()
        retrieved_context = dspy.InputField()
        answer = dspy.OutputField()
        citations = dspy.OutputField()

    class FaithfulnessGrade(dspy.Signature):
        """Grade whether the answer is fully supported by retrieved context."""

        question = dspy.InputField()
        retrieved_context = dspy.InputField()
        answer = dspy.InputField()
        faithfulness_score = dspy.OutputField()
        reason = dspy.OutputField()

    class RoutingDecision(dspy.Signature):
        """Choose the lowest-cost model route that can answer safely."""

        question = dspy.InputField()
        context_chars = dspy.InputField()
        query_tier = dspy.OutputField()
        model_route = dspy.OutputField()

else:
    QueryRewrite = CitationSupportedAnswer = FaithfulnessGrade = RoutingDecision = None
