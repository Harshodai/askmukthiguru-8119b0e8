"""Test stub — NOT for production use.
Production uses the real langchain_text_splitters package directly.
"""

import os
import warnings

if not os.environ.get("PYTEST_CURRENT_TEST"):
    warnings.warn(
        "langchain_text_splitters stub imported outside test environment",
        RuntimeWarning,
        stacklevel=2,
    )


class RecursiveCharacterTextSplitter:
    def __init__(self, *, chunk_size: int, chunk_overlap: int, separators=None):
        self.chunk_size = chunk_size
        self.chunk_overlap = max(chunk_overlap, 0)
        self.separators = separators or ["\n\n", "\n", ". ", " ", ""]

    def split_text(self, text: str) -> list[str]:
        if not text:
            return []
        words = text.split()
        step = max(self.chunk_size - self.chunk_overlap, 1)
        chunks: list[str] = []
        for i in range(0, len(words), step):
            chunk_words = words[i : i + self.chunk_size]
            if not chunk_words:
                break
            chunks.append(" ".join(chunk_words))
        return chunks
