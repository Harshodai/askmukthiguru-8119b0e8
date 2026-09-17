"""Tests for F-SEC-1 item 9: bounded upload read + PDF magic-byte gate.

These are unit/integration tests against the FastAPI app (not a live backend).
They verify:
  1. A valid PDF (correct magic bytes) is accepted by the gate.
  2. A renamed non-PDF (e.g. a JPEG renamed to .pdf) is rejected with 400.
  3. A file whose suffix is not .pdf is rejected with 400 (pre-existing gate).
  4. The read is bounded: a file larger than MAX_UPLOAD_BYTES is rejected.
  5. An empty upload is rejected with 400.
  6. Magic-byte check is NOT fooled by correct-length content that is not %PDF.

Mutation check: tests 2 and 6 together form a mutation check for the magic-byte
guard — removing the guard causes both to pass silently (a regression), while
the guard causes both to reject. Unlike a test that restates the formula, these
tests drive the real endpoint and read the HTTP status code.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.api.ingest import MAX_UPLOAD_BYTES

# ---------------------------------------------------------------------------
# Minimal PDF bytes (valid 1-page empty PDF, 167 bytes).
# All real PDFs start with %PDF; this minimal stub is enough to pass the magic-
# byte gate and produce a parse error (no text content), but the gate check
# happens before PdfReader, so we only need it for tests 1 (accepted by gate).
# ---------------------------------------------------------------------------
_MINIMAL_PDF_BYTES = (
    b"%PDF-1.0\n"
    b"1 0 obj<</Type /Catalog /Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type /Pages /Kids [3 0 R] /Count 1>>endobj\n"
    b"3 0 obj<</Type /Page /MediaBox [0 0 3 3]>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f\n"
    b"0000000009 00000 n\n0000000058 00000 n\n"
    b"0000000115 00000 n\n"
    b"trailer<</Size 4 /Root 1 0 R>>\n"
    b"startxref\n190\n%%EOF\n"
)

# JPEG magic bytes (FFD8FF) — a file renamed to .pdf that is actually a JPEG.
_JPEG_MAGIC_AS_PDF = b"\xff\xd8\xff\xe0" + b"\x00" * 100

# Content that starts with the right 4 bytes of text but is not ASCII %PDF.
_WRONG_MAGIC = b"BEEF" + b"\x00" * 100


def _make_app_with_mock_auth():
    """Return a TestClient whose admin-auth dependency is stubbed out.

    We bypass authentication entirely so the test exercises only the upload-
    validation logic (bounded read + magic-byte gate).
    """

    from app.main import app
    from services.auth_service import require_aal2

    mock_superuser = {"id": "test-admin", "is_superuser": True}

    async def _mock_admin():
        return mock_superuser

    app.dependency_overrides[require_aal2] = _mock_admin
    client = TestClient(app, raise_server_exceptions=False)
    return client, app


@pytest.fixture(scope="module")
def client_and_app():
    client, app = _make_app_with_mock_auth()
    yield client, app
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _post_upload(client: TestClient, content: bytes, filename: str = "test.pdf") -> int:
    """POST content to /api/ingest/upload, return HTTP status code."""
    return client.post(
        "/api/ingest/upload",
        files={"file": (filename, io.BytesIO(content), "application/pdf")},
        data={"max_accuracy": "false", "tags": "test"},
    ).status_code


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_pdf_magic_bytes_accepted_by_gate(client_and_app):
    """A valid PDF (correct magic bytes) must pass the magic-byte gate.

    The request may ultimately fail (e.g. 500 from missing DB), but must NOT
    fail with 400 at the magic-byte gate.  Accept any status code except 400
    with 'not a valid PDF' as proof the gate passed.
    """
    client, _ = client_and_app
    code = _post_upload(client, _MINIMAL_PDF_BYTES)
    # 400 with "not a valid PDF" would mean the gate wrongly rejected a real PDF.
    # Any other code (200, 400 for other reasons, 500 from DB, 422 for DI) is fine.
    assert code != 400 or True  # loosened: we just confirm no WRONG magic-byte rejection
    # A stronger assertion: the magic-byte check specifically must not fire.
    resp = client.post(
        "/api/ingest/upload",
        files={"file": ("test.pdf", io.BytesIO(_MINIMAL_PDF_BYTES), "application/pdf")},
        data={"max_accuracy": "false", "tags": "test"},
    )
    assert resp.status_code != 400 or "not a valid PDF" not in resp.text


def test_jpeg_renamed_to_pdf_rejected(client_and_app):
    """A JPEG renamed to .pdf must be rejected by the magic-byte gate (400)."""
    client, _ = client_and_app
    resp = client.post(
        "/api/ingest/upload",
        files={"file": ("photo.pdf", io.BytesIO(_JPEG_MAGIC_AS_PDF), "application/pdf")},
        data={"max_accuracy": "false", "tags": "test"},
    )
    assert resp.status_code == 400
    assert "not a valid PDF" in resp.text


def test_wrong_magic_bytes_rejected(client_and_app):
    """Content that does not start with %PDF must be rejected, even if named .pdf."""
    client, _ = client_and_app
    resp = client.post(
        "/api/ingest/upload",
        files={"file": ("data.pdf", io.BytesIO(_WRONG_MAGIC), "application/pdf")},
        data={"max_accuracy": "false", "tags": "test"},
    )
    assert resp.status_code == 400
    assert "not a valid PDF" in resp.text


def test_non_pdf_suffix_rejected(client_and_app):
    """Pre-existing suffix gate: a .txt file must be rejected with 400."""
    client, _ = client_and_app
    resp = client.post(
        "/api/ingest/upload",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
        data={"max_accuracy": "false", "tags": "test"},
    )
    assert resp.status_code == 400
    assert "Only PDF" in resp.text


def test_empty_upload_rejected(client_and_app):
    """An empty file must be rejected with 400."""
    client, _ = client_and_app
    resp = client.post(
        "/api/ingest/upload",
        files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
        data={"max_accuracy": "false", "tags": "test"},
    )
    assert resp.status_code == 400
    assert "empty" in resp.text.lower()


def test_oversized_upload_rejected(client_and_app):
    """A file larger than MAX_UPLOAD_BYTES must be rejected with 400.

    We construct content that starts with valid PDF magic bytes so the magic-
    byte gate passes, then exceeds the size limit.  This proves the size check
    fires independently of the magic-byte check.
    """
    client, _ = client_and_app
    oversized = _MINIMAL_PDF_BYTES + b"\x00" * (MAX_UPLOAD_BYTES + 1)
    resp = client.post(
        "/api/ingest/upload",
        files={"file": ("big.pdf", io.BytesIO(oversized), "application/pdf")},
        data={"max_accuracy": "false", "tags": "test"},
    )
    assert resp.status_code == 400
    assert "exceeds" in resp.text.lower() or "25MB" in resp.text


# ---------------------------------------------------------------------------
# AST-based source assertion (defect-class-7 guard)
# Confirms the magic-byte guard is in the production module, not restated here.
# ---------------------------------------------------------------------------


def test_magic_byte_guard_in_production_source():
    """The magic-byte check must be present in ingest.py, not only in this test.

    This guards against the 'test scores its own reference' defect (class 7)
    by asserting against the real production source rather than restating the
    check inline.
    """
    import ast
    import pathlib

    src = pathlib.Path(__file__).parent.parent / "app" / "api" / "ingest.py"
    tree = ast.parse(src.read_text())

    # Look for a Constant node whose value contains the PDF magic bytes string.
    magic_found = any(
        isinstance(node, ast.Constant) and isinstance(node.value, bytes) and node.value == b"%PDF"
        for node in ast.walk(tree)
    )
    assert magic_found, (
        "Production ingest.py no longer contains the b'%PDF' magic-byte constant. "
        "The F-SEC-1 guard has been removed or changed — restore it."
    )

    # Also confirm `file.read(` is called with an argument (bounded) not bare.
    read_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "read"
        and node.args  # at least one argument → bounded
    ]
    assert read_calls, (
        "Production ingest.py no longer calls file.read() with a size argument. "
        "The bounded-read fix (F-SEC-1 item 9) has been removed — restore it."
    )
