"""Timeout-backed test for in-memory PDF text extraction via pypdf."""

from __future__ import annotations

import signal
from contextlib import contextmanager

import pytest


@contextmanager
def _timeout(seconds: float):
    """Raise TimeoutError if the wrapped block exceeds ``seconds``."""
    if seconds <= 0:
        yield
        return

    def _handler(signum, frame):
        raise TimeoutError(f"PDF extraction did not complete within {seconds}s")

    previous = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _build_in_memory_pdf(text: str) -> bytes:
    """Create a minimal single-page PDF containing ``text``.

    The PDF is handcrafted (valid PDF 1.4 with one content stream using the
    standard Helvetica font) so the test has no dependency on a PDF *writer*
    library and remains hermetic.
    """
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = b"BT /F1 12 Tf 72 72 Td (" + escaped.encode("latin-1") + b") Tj ET"
    stream = (
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        stream,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 6\n0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    return bytes(out)


@pytest.mark.timeout(10)
def test_extract_text_from_in_memory_pdf():
    """Create an in-memory PDF and extract text via pypdf PdfReader."""
    from pypdf import PdfReader

    expected = "Hello from pypdf extraction test."
    pdf_bytes = _build_in_memory_pdf(expected)

    with _timeout(5.0):
        with PdfReader(__import__("io").BytesIO(pdf_bytes)) as doc:
            assert len(doc.pages) == 1, f"expected 1 page, got {len(doc.pages)}"
            extracted = doc.pages[0].extract_text() or ""

    assert expected in extracted, f"expected text not found: {extracted!r}"


if __name__ == "__main__":
    test_extract_text_from_in_memory_pdf()
    print("ok")
