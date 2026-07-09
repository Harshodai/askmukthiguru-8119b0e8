from __future__ import annotations

import logging
from typing import Any

from guardrails.base import BaseGuardrailHandler

logger = logging.getLogger(__name__)

_LLAMA_GUARD_CATEGORIES = {
    "S1": "violent_crimes",
    "S2": "non_violent_crimes",
    "S3": "sex_related_crimes",
    "S4": "child_sexual_exploitation",
    "S5": "defamation",
    "S6": "specialized_advice",
    "S7": "privacy",
    "S8": "intellectual_property",
    "S9": "indiscriminate_weapons",
    "S10": "hate",
    "S11": "suicide_self_harm",
    "S12": "sexual_content",
    "S13": "elections",
    "S14": "code_interpreter_abuse",
}

_CATEGORY_TO_TOPIC = {
    "suicide_self_harm": "self_harm",
    "specialized_advice": "medical_prescription",
    "sexual_content": "explicit",
    "violent_crimes": "violence",
    "hate": "violence",
    "elections": "politics",
}

_PROMPT_TEMPLATE = """Task: Check if there is unsafe content in 'User' messages according to safety policy.

<BEGIN UNSAFE CONTENT CATEGORIES>
S1: Violent Crimes.
S2: Non-Violent Crimes.
S3: Sex-Related Crimes.
S4: Child Sexual Exploitation.
S5: Defamation.
S6: Specialized Advice (medical, financial, or legal).
S7: Privacy.
S8: Intellectual Property.
S9: Indiscriminate Weapons (including instructions for making them).
S10: Hate.
S11: Suicide & Self-Harm.
S12: Sexual Content.
S13: Elections.
S14: Code Interpreter Abuse.
<END UNSAFE CONTENT CATEGORIES>

<BEGIN CONVERSATION>
User: {message}
<END CONVERSATION>

Provide safety assessment for the User message above:
- First line must read 'safe' or 'unsafe'.
- If unsafe, second line must list violated categories as comma-separated S-codes."""


class LlamaGuardHandler(BaseGuardrailHandler):
    def __init__(self) -> None:
        super().__init__()
        self._model = None
        self._tokenizer = None
        self._available = False
        self._load_model()

    def _load_model(self) -> None:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            model_id = "meta-llama/Llama-Guard-3-1B"
            device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"

            logger.info("Loading Llama Guard 3 1B on %s (this may take a moment)...", device)
            self._tokenizer = AutoTokenizer.from_pretrained(model_id)
            self._model = AutoModelForCausalLM.from_pretrained(
                model_id,
                torch_dtype=torch.float16 if device != "cpu" else torch.float32,
                device_map=device,
            )
            self._available = True
            logger.info("Llama Guard 3 1B loaded successfully on %s", device)
        except ImportError as e:
            logger.warning("transformers/torch not available: %s. Llama Guard will pass through.", e)
        except OSError as e:
            logger.warning(
                "Cannot load Llama Guard model (gated or not found): %s. "
                "Ensure you have accepted the license at hf.co/meta-llama/Llama-Guard-3-1B "
                "and logged in via `huggingface-cli login`. Falling back to pass-through.", e
            )
        except Exception as e:
            logger.warning("Llama Guard model failed to load: %s. Falling back to pass-through.", e)

    async def _classify(self, message: str) -> tuple[bool, list[str]]:
        if not self._available:
            return False, []

        import torch

        prompt = _PROMPT_TEMPLATE.format(message=message)
        inputs = self._tokenizer([prompt], return_tensors="pt").to(self._model.device)

        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=64,
                do_sample=False,
                temperature=None,
                top_p=None,
            )

        response = self._tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
        lines = [l.strip() for l in response.split("\n") if l.strip()]

        if not lines:
            return False, []

        verdict = lines[0].lower()
        if verdict == "safe":
            return False, []

        categories = []
        if len(lines) > 1:
            for code in lines[1].split(","):
                code = code.strip()
                cat = _LLAMA_GUARD_CATEGORIES.get(code, code.lower())
                categories.append(cat)

        return True, categories

    def _map_to_topic(self, categories: list[str]) -> str:
        for cat in categories:
            for guard_cat, topic in _CATEGORY_TO_TOPIC.items():
                if guard_cat in cat:
                    return topic
        return "explicit"

    async def _handle_input(self, text: str, **kwargs: Any) -> dict[str, Any]:
        if not self._available:
            return {"blocked": False, "reason": None, "response": None}

        try:
            unsafe, categories = await self._classify(text)
            if not unsafe:
                return {"blocked": False, "reason": None, "response": None}

            topic = self._map_to_topic(categories)
            logger.info("Llama Guard blocked input: topic=%s categories=%s", topic, categories)

            from guardrails.lightweight_handler import _resolve_block_response, _SERENE_MIND_REDIRECT_TOPICS

            redirect = "serene_mind" if topic in _SERENE_MIND_REDIRECT_TOPICS else None
            return {
                "blocked": True,
                "reason": f"Llama Guard: {topic}",
                "response": _resolve_block_response(topic, "This topic is outside my boundaries of spiritual guidance. 🙏"),
                "redirect_to": redirect,
            }
        except Exception as e:
            logger.error("Llama Guard input check failed: %s", e)
            return {"blocked": False, "reason": None, "response": None}

    async def _handle_output(self, text: str, **kwargs: Any) -> dict[str, Any]:
        if not self._available:
            return {"blocked": False, "reason": None, "moderated_response": None}

        try:
            unsafe, categories = await self._classify(text)
            if not unsafe:
                return {"blocked": False, "reason": None, "moderated_response": None}

            logger.info("Llama Guard moderated output: categories=%s", categories)
            return {
                "blocked": True,
                "reason": f"Output moderated by Llama Guard: {categories}",
                "moderated_response": "I want to keep our conversation focused on spiritual wisdom. Let me share the teachings instead. 🙏",
            }
        except Exception as e:
            logger.error("Llama Guard output check failed: %s", e)
            return {"blocked": False, "reason": None, "moderated_response": None}

    @property
    def is_available(self) -> bool:
        return self._available
