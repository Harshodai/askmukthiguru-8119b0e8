"""Web scraper helper module using Jina Reader (r.jina.ai), BeautifulSoup fallback, and RSS parsing."""

from __future__ import annotations
import logging
from typing import Any, Callable, Dict, List, Optional

from services.http_client_pool import get_client

logger = logging.getLogger(__name__)

_DEFAULT_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


async def fetch_web_article_jina(
    url: str,
    timeout: float = 30.0,
    max_bytes: int = 5 * 1024 * 1024,
) -> Optional[str]:
    """Fetch clean markdown content using Jina Reader (https://r.jina.ai/{url}).
    
    Returns Markdown string if successful, or None if Jina Reader fails/times out.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    jina_url = f"https://r.jina.ai/{url}"
    headers = {
        "User-Agent": _DEFAULT_UA,
        "Accept": "text/plain",
        "X-No-Cache": "true",
    }
    client = await get_client()

    try:
        async with client.stream("GET", jina_url, headers=headers, follow_redirects=True, timeout=timeout) as response:
            if response.status_code != 200:
                logger.warning("Jina Reader returned status %s for %s", response.status_code, url)
                return None

            content_bytes = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=8192):
                content_bytes.extend(chunk)
                if len(content_bytes) > max_bytes:
                    logger.warning("Jina Reader response for %s exceeded limit of %s bytes", url, max_bytes)
                    return None

            text = content_bytes.decode("utf-8", errors="replace").strip()
            if text and len(text) > 100:  # Minimum quality threshold
                logger.info("Successfully fetched article via Jina Reader: %s (%d chars)", url, len(text))
                return text
    except Exception as e:
        logger.warning("Jina Reader fetch failed for %s: %s (falling back to BeautifulSoup)", url, e)

    return None


async def scrape_and_clean_web_article(
    url: str,
    is_url_safe_func: Callable[[str], bool],
    timeout: float = 20.0,
    max_bytes: int = 5 * 1024 * 1024,
    use_jina: bool = True,
) -> str:
    """Scrape and extract clean text content from a web URL non-blockingly.
    
    Uses 2-Tier strategy:
      Tier 1: Jina Reader (https://r.jina.ai/{url}) for clean Markdown
      Tier 2: BeautifulSoup extraction fallback
    """
    if not is_url_safe_func(url):
        raise ValueError("URL resolves to a private or prohibited IP address")

    # Tier 1: Try Jina Reader
    if use_jina:
        jina_result = await fetch_web_article_jina(url, timeout=timeout, max_bytes=max_bytes)
        if jina_result:
            return jina_result

    # Tier 2: BeautifulSoup fallback
    from bs4 import BeautifulSoup

    headers = {"User-Agent": _DEFAULT_UA}
    client = await get_client()
    # follow_redirects=False: is_url_safe_func only validates this URL's own
    # hostname. Following a redirect would fetch whatever host the response
    # points to without re-checking it — an SSRF bypass. Same invariant as
    # backend/ingest/pdf_parser.py's download_and_parse_pdf.
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


def parse_rss_feed(
    feed_url: str,
    max_entries: int = 10,
) -> List[Dict[str, Any]]:
    """Parse RSS/Atom blog or podcast feed using feedparser.
    
    Returns list of entry dicts containing title, link, published, summary.
    """
    try:
        import feedparser
    except ImportError:
        logger.warning("feedparser package not installed. Cannot parse RSS feed: %s", feed_url)
        return []

    parsed = feedparser.parse(feed_url)
    entries = []
    for entry in getattr(parsed, "entries", [])[:max_entries]:
        entries.append({
            "title": getattr(entry, "title", "").strip(),
            "link": getattr(entry, "link", "").strip(),
            "published": getattr(entry, "published", getattr(entry, "updated", "")).strip(),
            "summary": getattr(entry, "summary", getattr(entry, "description", "")).strip(),
        })
    return entries


