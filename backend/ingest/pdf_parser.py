"""PDF parser helper module using pypdf and non-blocking HTTP fetching."""

from __future__ import annotations
import io
import logging
from typing import Callable

from services.http_client_pool import get_client

logger = logging.getLogger(__name__)


async def download_and_parse_pdf(
    url: str,
    is_url_safe_func: Callable[[str], bool],
    timeout: float = 30.0,
    max_bytes: int = 5 * 1024 * 1024,
) -> str:
    """Download and extract raw text from a PDF URL non-blockingly."""
    if not is_url_safe_func(url):
        raise ValueError("URL resolves to a private or prohibited IP address")

    from pypdf import PdfReader

    client = await get_client()
    async with client.stream("GET", url, follow_redirects=False, timeout=timeout) as resp:
        resp.raise_for_status()
        content = bytearray()
        async for chunk in resp.aiter_bytes(chunk_size=8192):
            content.extend(chunk)
            if len(content) > max_bytes:
                raise ValueError(f"Response size exceeds limit of {max_bytes} bytes")

    pdf_file = io.BytesIO(content)
    with PdfReader(pdf_file) as doc:
        pages_text = []
        for page in doc.pages:
            p_text = page.extract_text() or ""
            if p_text and p_text.strip():
                pages_text.append(p_text.strip())
        raw_text = "\n\n".join(pages_text)

    import unicodedata
    raw_text = raw_text.replace("\x00", "").replace("<|begin_of_text|>", "").replace("<|eot_id|>", "").replace("<|end_of_text|>", "")
    raw_text = unicodedata.normalize("NFC", raw_text).strip()

    try:
        from services.doctrine_terms import apply_corrections
        return apply_corrections(raw_text)
    except Exception:
        return raw_text
