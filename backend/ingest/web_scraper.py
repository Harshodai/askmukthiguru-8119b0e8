"""Web scraper helper module using BeautifulSoup and non-blocking HTTP fetching."""

from __future__ import annotations
import logging
from typing import Callable

from services.http_client_pool import get_client

logger = logging.getLogger(__name__)


async def scrape_and_clean_web_article(
    url: str,
    is_url_safe_func: Callable[[str], bool],
    timeout: float = 20.0,
    max_bytes: int = 5 * 1024 * 1024,
) -> str:
    """Scrape and extract clean text content from a web URL non-blockingly."""
    if not is_url_safe_func(url):
        raise ValueError("URL resolves to a private or prohibited IP address")

    from bs4 import BeautifulSoup

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    client = await get_client()
    async with client.stream("GET", url, headers=headers, follow_redirects=False, timeout=timeout) as response:
        response.raise_for_status()
        content_bytes = bytearray()
        async for chunk in response.aiter_bytes(chunk_size=8192):
            content_bytes.extend(chunk)
            if len(content_bytes) > max_bytes:
                raise ValueError(f"Response size exceeds limit of {max_bytes} bytes")

    soup = BeautifulSoup(bytes(content_bytes), "html.parser")
    for element in soup(["script", "style", "nav", "header", "footer", "iframe", "aside"]):
        element.decompose()

    text = soup.get_text(separator="\n")
    cleaned_lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(cleaned_lines)
