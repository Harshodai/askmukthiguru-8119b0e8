from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

try:
    import dspy
except ImportError:  # prod without DSPy installed — callers degrade gracefully
    dspy = None  # type: ignore[assignment]

from app.config import settings

logger = logging.getLogger(__name__)

COMPILED_PROGRAM_PATH = Path(__file__).resolve().parent / "compiled" / "dspy_optimized_program.json"

_MISSING_DEPS_MSG = "dspy package not installed — DSPy module unavailable"


if dspy is not None:

    class MukthiGuruSignature(dspy.Signature):
        """Answer a seeker question grounded ONLY in retrieved context."""

        context = dspy.InputField(
            desc="Retrieved spiritual teachings and background context — the ONLY source of truth"
        )
        question = dspy.InputField(
            desc="The seeker's spiritual question or distress input, verbatim"
        )
        tone = dspy.InputField(
            desc="Requested answer voice: gentle (default), direct, or poetic — style hint only, never changes citations"
        )
        answer = dspy.OutputField(
            desc="A compassionate, accurate answer grounded ONLY in the context, with inline [n] citations"
        )

    class MukthiGuruModule(dspy.Module):
        def __init__(self):
            super().__init__()
            self.generate_answer = dspy.ChainOfThought(MukthiGuruSignature)

        def forward(self, question: str, context: str, tone: str = "gentle") -> dspy.Prediction:
            prediction = self.generate_answer(context=context, question=question, tone=tone)
            return dspy.Prediction(answer=prediction.answer, rationale=prediction.rationale)

else:

    class MukthiGuruSignature:  # type: ignore[no-redef]
        """Stub when dspy is not installed."""

    class MukthiGuruModule:  # type: ignore[no-redef]
        """Stub when dspy is not installed."""


def setup_dspy_lm() -> bool:
    """
    Configure DSPy to use the production LLM provider.

    Priority: openrouter (live default) -> nim -> ollama local-only.
    Returns False when dspy is not installed or no provider is configured.
    """
    if dspy is None:
        logger.warning(_MISSING_DEPS_MSG)
        return False
    try:
        provider = settings.llm_provider.lower()
        model = settings.model_for_generation
        max_tokens = getattr(settings, "max_tokens_per_request", 2000)

        if provider == "openrouter":
            api_key = getattr(settings, "openrouter_api_key", "")
            api_base = getattr(settings, "openrouter_base_url", "https://openrouter.ai/api/v1")
            if api_key:
                lm = dspy.LM(
                    model=f"openrouter/{model}",
                    api_key=api_key,
                    api_base=api_base,
                    max_tokens=max_tokens,
                    cache=False,
                    num_retries=2,
                )
                dspy.settings.configure(lm=lm)
                logger.info(f"DSPy configured to use OpenRouter model: {model}")
                return True
            logger.warning("OpenRouter provider selected but no API key — trying NIM")

        if provider == "nim" or provider == "openrouter":
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

        # Fallback: Ollama (local dev only)
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
    if dspy is None:
        logger.warning(_MISSING_DEPS_MSG)
        return None
    if not getattr(settings, "use_dspy", False):
        return None
    ok = setup_dspy_lm()
    if not ok:
        logger.warning("DSPy LM setup failed — DSPy module will not be available")
        return None
    try:
        module = MukthiGuruModule()
        loaded = load_compiled_module(module)
        if loaded is not None:
            return loaded
        return module
    except Exception as e:
        logger.error(f"Failed to instantiate MukthiGuruModule: {e}")
        return None


def dspy_generate(
    question: str,
    context: str,
    module: Optional[MukthiGuruModule] = None,
    tone: str = "gentle",
) -> Optional[str]:
    """Generate an answer using the DSPy module. Returns None on failure."""
    if module is None or dspy is None:
        return None
    try:
        prediction = module.forward(question=question, context=context, tone=tone)
        return prediction.answer
    except Exception as e:
        logger.warning(f"DSPy generation failed, caller should fall back: {e}")
        return None


def save_compiled_module(module: Any, path: Path = COMPILED_PROGRAM_PATH) -> Path:
    """Persist an optimized DSPy program to compiled/dspy_optimized_program.json.

    Only approved (metric-gated) programs should be saved — the harness
    enforces thresholds before calling this.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if dspy is None:
        raise RuntimeError(_MISSING_DEPS_MSG)
    module.save(str(path))
    logger.info(f"Saved compiled DSPy program to {path}")
    return path


def load_compiled_module(module: Any, path: Path = COMPILED_PROGRAM_PATH) -> Optional[Any]:
    """Load a previously optimized program over the base module, if present."""
    if dspy is None:
        return None
    if not path.exists():
        return None
    try:
        module.load(str(path))
        logger.info(f"Loaded compiled DSPy program from {path}")
        return module
    except Exception as e:
        logger.warning(f"Could not load compiled DSPy program from {path}: {e}")
        return None


def compiled_program_info(path: Path = COMPILED_PROGRAM_PATH) -> dict[str, Any]:
    """Read-only metadata probe for the compiled artifact (no dspy import)."""
    if not path.exists():
        return {"present": False, "path": str(path)}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {
            "present": True,
            "path": str(path),
            "bytes": path.stat().st_size,
            "top_level_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
        }
    except Exception as e:
        return {"present": True, "path": str(path), "error": str(e)}


if __name__ == "__main__":
    print(compiled_program_info())
    if dspy is None:
        print(_MISSING_DEPS_MSG)
    else:
        settings.use_dspy = True
        mod = make_module()
        if mod:
            ans = dspy_generate(
                "What is the Four Sacred Secrets?",
                "The four sacred secrets are spiritual vision, inner truth, universal intelligence, and spiritual right action.",
            )
            print(f"DSPy answer: {ans}")
        else:
            print("DSPy module not available")
