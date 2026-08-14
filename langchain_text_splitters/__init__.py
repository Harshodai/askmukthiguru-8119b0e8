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
        # Keep both the public names and the private names used by the real
        # implementation. Tests and ingestion code may tune either form.
        self.chunk_size = chunk_size
        self.chunk_overlap = max(chunk_overlap, 0)
        self._chunk_size = chunk_size
        self._chunk_overlap = self.chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", " ", ""]

    def split_text(self, text: str) -> list[str]:
        if not text:
            return []
        chunk_size = max(int(self._chunk_size), 1)
        chunk_overlap = min(max(int(self._chunk_overlap), 0), chunk_size - 1)
        step = max(chunk_size - chunk_overlap, 1)
        chunks: list[str] = []
        for start in range(0, len(text), step):
            chunk = text[start : start + chunk_size].strip()
            if chunk:
                chunks.append(chunk)
            if start + chunk_size >= len(text):
                break
        return chunks
