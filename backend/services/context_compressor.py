import logging

logger = logging.getLogger(__name__)


class ContextCompressor:
    """
    Context compression using Microsoft LLMLingua-2.
    Falls back to no-op if the library is unavailable or initialization fails.
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._compressor = None
        if enabled:
            try:
                from llmlingua import PromptCompressor

                self._compressor = PromptCompressor(
                    model_name="microsoft/llmlingua-2-bert-base-multilingual-cased-meeting",
                    use_llmlingua2=True,
                )
            except Exception as e:
                logger.error(f"Failed to initialize LLMLingua: {e}")
                self.enabled = False

    def compress(self, context: str, target_ratio: float = 0.5) -> str:
        """Compress context text, preserving key spiritual terminology."""
        if not self.enabled or not self._compressor or not context.strip():
            return context

        try:
            res = self._compressor.compress_prompt(
                [context],
                rate=target_ratio,
                force_tokens=["Sri Krishnaji", "Preethaji", "Mukthi Guru"],
                drop_consecutive=True,
            )
            compressed = res.get("compressed_prompt", [context])
            if isinstance(compressed, list):
                return " ".join(compressed)
            return compressed if compressed else context
        except Exception as e:
            logger.warning(f"Compression failed, using raw context: {e}")
            return context