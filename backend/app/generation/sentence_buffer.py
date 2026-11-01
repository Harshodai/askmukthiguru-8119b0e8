# DORMANT (2026-11-01 wiring audit, plan §12): no call site in the request path; not shipped. Only used by speculative_stream.py.
"""Sentence boundary buffering for streaming text generation."""

import re


class SentenceBoundaryBuffer:
    """Buffers streaming token deltas into complete sentences using regex/boundary tokenizer
    while keeping lookahead latency < 35ms. Emits completed sentences as soon as punctuation
    (., ?, !, ।, newline) is detected.
    """

    def __init__(self) -> None:
        self.buffer = ""

    def add_token(self, token: str) -> list[str]:
        """Adds incoming token(s), extracts and returns any completed sentences."""
        self.buffer += token
        completed_sentences = []

        # We scan for sentence delimiters: ., ?, !, ।, or newlines
        while True:
            # Find the earliest occurrence of any punctuation or newline
            match = re.search(r"([.?!।\n])", self.buffer)
            if not match:
                break

            idx = match.end()
            sentence = self.buffer[:idx].strip()
            if sentence:
                completed_sentences.append(sentence)
            self.buffer = self.buffer[idx:].lstrip()

        return completed_sentences

    def flush(self) -> list[str]:
        """Flushes any remaining text in the buffer as a final sentence if non-empty."""
        completed_sentences = []
        stripped = self.buffer.strip()
        if stripped:
            completed_sentences.append(stripped)
            self.buffer = ""
        return completed_sentences

    def reset(self) -> None:
        """Resets the buffer."""
        self.buffer = ""
