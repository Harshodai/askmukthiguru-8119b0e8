from __future__ import annotations

import logging
from typing import Optional

import dspy

from app.config import settings

logger = logging.getLogger(__name__)


class MukthiGuruSignature(dspy.Signature):
    context = dspy.InputField(desc="Retrieved spiritual teachings and background context")
    question = dspy.InputField(desc="The seeker's spiritual question or distress input")
    answer = dspy.OutputField(desc="A compassionate, accurate answer grounded ONLY in the context")


class MukthiGuruModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.generate_answer = dspy.ChainOfThought(MukthiGuruSignature)

    def forward(self, question: str, context: str) -> dspy.Prediction:
        prediction = self.generate_answer(context=context, question=question)
        return dspy.Prediction(answer=prediction.answer, rationale=prediction.rationale)


def setup_dspy_lm() -> bool:
    """
    Configure DSPy to use the production LLM provider (NIM).
    Falls back to Ollama if NIM is not configured.
    """
    try:
        provider = settings.llm_provider.lower()
        model = settings.model_for_generation
        max_tokens = getattr(settings, "max_tokens_per_request", 2000)

        if provider == "nim":
            api_key = getattr(settings, "nim_api_key", "")
            api_base = getattr(settings, "nim_base_url", "https://integrate.api.nvidia.com/v1")
            if api_key:
                lm = dspy.LM(
                    model=f"openai/{model}",
                    api_key=api_key,
                    api_base=api_base,
                    max_tokens=max_tokens,
                    cache=False,
                    num_retries=2,
                )
                dspy.settings.configure(lm=lm)
                logger.info(f"DSPy configured to use NIM model: {model}")
                return True

        # Fallback: Ollama (local dev)
        ollama_base = getattr(settings, "ollama_base_url", "http://localhost:11434")
        lm = dspy.LM(
            model=f"openai/{model}",
            api_base=ollama_base,
            max_tokens=max_tokens,
            cache=False,
        )
        dspy.settings.configure(lm=lm)
        logger.info(f"DSPy configured to use Ollama at {ollama_base} with model: {model}")
        return True
    except Exception as e:
        logger.error(f"Failed to configure DSPy LM: {e}")
        return False


def make_module() -> Optional[MukthiGuruModule]:
    """Create a DSPy module if DSPy is enabled and configured."""
    if not getattr(settings, "use_dspy", False):
        return None
    ok = setup_dspy_lm()
    if not ok:
        logger.warning("DSPy LM setup failed — DSPy module will not be available")
        return None
    try:
        return MukthiGuruModule()
    except Exception as e:
        logger.error(f"Failed to instantiate MukthiGuruModule: {e}")
        return None


def dspy_generate(question: str, context: str, module: Optional[MukthiGuruModule] = None) -> Optional[str]:
    """Generate an answer using the DSPy module. Returns None on failure."""
    if module is None:
        return None
    try:
        prediction = module.forward(question=question, context=context)
        return prediction.answer
    except Exception as e:
        logger.warning(f"DSPy generation failed, caller should fall back: {e}")
        return None


if __name__ == "__main__":
    settings.use_dspy = True
    mod = make_module()
    if mod:
        ans = dspy_generate("What is the Four Sacred Secrets?", "The four sacred secrets are spiritual vision, inner truth, universal intelligence, and spiritual right action.")
        print(f"DSPy answer: {ans}")
    else:
        print("DSPy module not available")
