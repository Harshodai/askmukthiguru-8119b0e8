"""Minimal stub for langchain_text_splitters used in tests.
Implements RecursiveCharacterTextSplitter with a simple word‑window splitter.
"""

class RecursiveCharacterTextSplitter:
    """Very small subset of the original class.

    Parameters
    ----------
    chunk_size: int
        Desired number of tokens/words per chunk.
    chunk_overlap: int
        Number of tokens/words to overlap between consecutive chunks.
    separators: list[str] | None
        Ignored in this stub – kept for signature compatibility.
    """

    def __init__(self, *, chunk_size: int, chunk_overlap: int, separators=None):
        self.chunk_size = chunk_size
        self.chunk_overlap = max(chunk_overlap, 0)
        # separators kept for API compatibility but not used in this simple implementation
        self.separators = separators or ["\n\n", "\n", ". ", " ", ""]

    def split_text(self, text: str) -> list[str]:
        """Split *text* into chunks of ``chunk_size`` words with ``chunk_overlap``.

        This naive implementation does not respect separators – it merely
        tokenises on whitespace and yields overlapping windows. It is sufficient
        for the unit‑tests that only verify that a list of strings is returned.
        """
        if not text:
            return []
        words = text.split()
        # Step size ensures overlap
        step = max(self.chunk_size - self.chunk_overlap, 1)
        chunks: list[str] = []
        for i in range(0, len(words), step):
            chunk_words = words[i : i + self.chunk_size]
            if not chunk_words:
                break
            chunks.append(" ".join(chunk_words))
        return chunks
