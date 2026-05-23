import logging

import dspy

logger = logging.getLogger(__name__)


class MukthiGuruSignature(dspy.Signature):
    """
    DSPy Signature for the Mukthi Guru RAG answering process.
    Given context and a question, generate a compassionate and factual spiritual answer.
    """

    context = dspy.InputField(desc="Retrieved spiritual teachings and background context")
    question = dspy.InputField(desc="The seeker's spiritual question or distress input")
    answer = dspy.OutputField(desc="A compassionate, accurate answer grounded ONLY in the context")


class MukthiGuruModule(dspy.Module):
    def __init__(self):
        super().__init__()
        # Use ChainOfThought to encourage reasoning before answering
        self.generate_answer = dspy.ChainOfThought(MukthiGuruSignature)

    def forward(self, question, context):
        prediction = self.generate_answer(context=context, question=question)
        return dspy.Prediction(answer=prediction.answer, rationale=prediction.rationale)


def setup_dspy_lm(model_name="llama3.1"):
    """
    Configure DSPy to use the local Ollama instance as the language model.
    """
    try:
        # Assuming Ollama is running locally on default port
        ollama_lm = dspy.OllamaLocal(
            model=model_name, url="http://localhost:11434", max_tokens=1000
        )
        dspy.settings.configure(lm=ollama_lm)
        logger.info(f"DSPy configured to use Ollama model: {model_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to configure DSPy LM: {e}")
        return False
