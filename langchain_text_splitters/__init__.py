"""Test stub — NOT for production use.
Production uses the real langchain_text_splitters package directly.
"""
import os
import warnings

if not os.environ.get("PYTEST_CURRENT_TEST"):
    # Fail closed, not loudly-but-onward. This package sits at the REPO ROOT, so
    # it precedes site-packages on sys.path for any process whose cwd is the repo
    # root. That includes `python3 -m pytest backend/tests/` (the command the root
    # CLAUDE.md documents) and, critically, the bulk corpus-ingestion scripts:
    #   scripts/ingestion/ingest_four_sacred_secrets.py:21
    #   scripts/ingestion/bulk_ingest_whisper.py:245
    #   scripts/ingestion/bulk_ingest_async.py:381
    # plus backend/ingest/{pipeline,adaptive_chunking,video_pipeline}.py.
    #
    # A corpus ingested from the repo root was therefore split by THIS simplified
    # stub, while one ingested from backend/ used the real library — silently,
    # with nothing in the Qdrant payload to tell the two apart. A RuntimeWarning
    # let that proceed and write differently-chunked vectors; an ImportError
    # stops it at the boundary.
    #
    # The real package is installed in backend/.venv. Run ingestion from
    # backend/, or `pip install langchain-text-splitters` into the env you use.
    raise ImportError(
        "langchain_text_splitters resolved to the TEST STUB at the repo root, "
        "shadowing the real package. Run from backend/ so site-packages wins. "
        "Importing this stub outside pytest would chunk the corpus with a "
        "different splitter than production uses."
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
