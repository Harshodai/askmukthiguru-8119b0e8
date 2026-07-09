from __future__ import annotations

import asyncio
import logging
from typing import Any

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.tracing import rag_span
from guardrails.base import BaseGuardrailHandler

logger = logging.getLogger(__name__)

REJECTION_THRESHOLD = 0.85


class RejectionClassifierHandler(BaseGuardrailHandler):
    def __init__(self) -> None:
        super().__init__()
        self._model = None
        self._tokenizer = None
        self._device = None
        self._available = False
        self._load_model()

    def _load_model(self) -> None:
        try:
            model_id = "protectai/distilroberta-base-rejection-v1"
            self._device = (
                "cuda" if torch.cuda.is_available()
                else "mps" if torch.backends.mps.is_available()
                else "cpu"
            )
            logger.info(
                "Loading Rejection Classifier on %s (this may take a moment)...",
                self._device,
            )
            self._tokenizer = AutoTokenizer.from_pretrained(model_id)
            self._model = AutoModelForSequenceClassification.from_pretrained(model_id).to(
                self._device
            )
            self._model.eval()
            label2id = getattr(self._model.config, "label2id", None) or {}
            self._rejection_idx = int(label2id.get("REJECTION", 1))
            self._available = True
            logger.info(
                "Rejection Classifier loaded successfully on %s (rejection_idx=%d)",
                self._device, self._rejection_idx,
            )
        except ImportError as e:
            logger.warning("transformers/torch not available: %s. Rejection classifier disabled.", e)
        except OSError as e:
            logger.warning(
                "Cannot load Rejection Classifier model: %s. Ensure the model identifier "
                "'protectai/distilroberta-base-rejection-v1' is correct and accessible.",
                e,
            )
        except Exception as e:
            logger.warning("Rejection Classifier model failed to load: %s. Disabled.", e)

    async def _classify(self, text: str) -> tuple[bool, float]:
        if not self._available:
            return False, 0.0

        def _infer(t: str) -> tuple[bool, float]:
            inputs = self._tokenizer(
                [t],
                return_tensors="pt",
                truncation=True,
                max_length=512,
            ).to(self._device)
            with torch.no_grad():
                outputs = self._model(**inputs)
                probs = torch.softmax(outputs.logits, dim=-1)
                score = probs[0][self._rejection_idx].item()
            return score >= REJECTION_THRESHOLD, score

        return await asyncio.to_thread(_infer, text)

    async def _handle_input(self, text: str, **kwargs: Any) -> dict[str, Any]:
        if not self._available:
            return {"blocked": False, "reason": None, "response": None}

        try:
            async with rag_span("rejection_classifier_input", input_len=len(text)) as span:
                rejected, score = await self._classify(text)
                if rejected:
                    span.set_attribute("rejection.score", score)
                    span.set_attribute("rejection.blocked", True)

            if not rejected:
                return {"blocked": False, "reason": None, "response": None}

            logger.info("Rejection Classifier blocked input: score=%.4f", score)
            return {
                "blocked": True,
                "reason": f"Rejection Classifier: score={score:.4f}",
                "response": (
                    "I'm here to share spiritual wisdom from the teachings of "
                    "Sri Preethaji and Sri Krishnaji. "
                    "How may I guide you on your path? 🙏"
                ),
            }
        except Exception as e:
            logger.error("Rejection Classifier input check failed: %s", e)
            return {"blocked": False, "reason": None, "response": None}

    async def _handle_output(self, text: str, **kwargs: Any) -> dict[str, Any]:
        if not self._available:
            return {"blocked": False, "reason": None, "moderated_response": None}

        try:
            async with rag_span("rejection_classifier_output", output_len=len(text)) as span:
                rejected, score = await self._classify(text)
                if rejected:
                    span.set_attribute("rejection.score", score)
                    span.set_attribute("rejection.blocked", True)

            if not rejected:
                return {"blocked": False, "reason": None, "moderated_response": None}

            logger.info("Rejection Classifier moderated output: score=%.4f", score)
            return {
                "blocked": True,
                "reason": f"Output contains rejection pattern: score={score:.4f}",
                "moderated_response": (
                    "I want to keep our conversation focused on spiritual wisdom. "
                    "Let me share the teachings instead. 🙏"
                ),
            }
        except Exception as e:
            logger.error("Rejection Classifier output check failed: %s", e)
            return {"blocked": False, "reason": None, "moderated_response": None}

    @property
    def is_available(self) -> bool:
        return self._available
