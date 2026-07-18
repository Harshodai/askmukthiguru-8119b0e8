"""
Web content ingestion pipeline — feeds the doctrine corpus.

Skill applied: `playwright-scraper-skill`. Use this to ingest teaching pages,
transcripts, and blog posts that are JS-rendered or behind light anti-bot
protection, clean them, and hand structured chunks to your existing
`ingest/pipeline.py`.

Design (matches the skill's use-case matrix):
  * `fetch_static(url)`  — plain httpx for server-rendered pages (fast path).
  * `fetch_dynamic(url)` — Playwright headless Chromium for JS-heavy pages.
  * `fetch_stealth(url)` — Playwright with anti-bot hardening (real UA,
    navigator.webdriver hidden, human-like delays) for protected sources.
  * `extract_clean_text(html)` — readability-style main-content extraction.
  * `to_chunks(...)` — doctrine-ready chunks with provenance for GraphRAG
    grounding (every chunk carries source URL + retrieved_at so SHACL's
    "every teaching cites a source" rule holds).

Install once:
    pip install playwright httpx beautifulsoup4
    playwright install chromium

Run headless in your ingestion worker (Celery), not in the request path.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import re
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger("web_ingest")

# Approved source domains and YouTube channels
_ALLOWED_DOMAINS = {
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "youtu.be", "img.youtube.com",
}
_ALLOWED_CHANNEL_IDS = {
    "UCgpnCoXhTWbkblGdEGVHqGQ",  # Sri Preethaji
    "UCtnfOYa5C7jFBAz0mn1Zv1A",  # Sri Krishnaji
}
_ALLOWED_IMAGE_DOMAINS = {"img.youtube.com"}
_DENIED_PRIVATE_PREFIXES = ("10.", "172.16.", "172.17.", "172.18.", "172.19.",
                            "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
                            "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
                            "172.30.", "172.31.", "192.168.", "127.", "0.",
                            "169.254.", "::1", "fc00:", "fe80:", "fd00:")


def _extract_youtube_channel_id(url: str) -> Optional[str]:
    """Extract YouTube channel ID from various URL formats."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    
    # youtube.com/channel/UCxxx
    if host.endswith("youtube.com"):
        path = parsed.path
        if path.startswith("/channel/"):
            return path.split("/channel/")[1].split("/")[0]
        if path.startswith("/c/") or path.startswith("/user/"):
            # Custom URLs need API resolution - reject for safety
            return None
        # Watch URLs: /watch?v=xxx&channel=UCxxx or extract from video page
        if path == "/watch":
            query = parse_qs(parsed.query)
            if "channel" in query:
                return query["channel"][0]
    # youtu.be/xxx - short URLs don't contain channel info directly
    return None


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme must be http or https: {url}")
    host = parsed.hostname or ""
    if any(host.startswith(p) for p in _DENIED_PRIVATE_PREFIXES):
        raise ValueError(f"Private/internal address denied: {url}")
    if parsed.username or parsed.password:
        raise ValueError(f"Embedded credentials not allowed: {url}")
    # Domain allowlist check
    if host not in _ALLOWED_DOMAINS and not host.endswith(".youtube.com"):
        raise ValueError(f"Domain not allowed: {host}")
    # YouTube channel ownership validation
    if host.endswith("youtube.com") or host == "youtu.be":
        channel_id = _extract_youtube_channel_id(url)
        if channel_id and channel_id not in _ALLOWED_CHANNEL_IDS:
            raise ValueError(f"YouTube channel not allowed: {channel_id}")
        if channel_id is None:
            # Cannot verify channel ownership - reject unverified URLs
            if host.endswith("youtube.com"):
                path = parsed.path
                if path.startswith("/c/") or path.startswith("/user/") or (path == "/watch" and "channel" not in parse_qs(parsed.query)):
                    raise ValueError("YouTube custom URL or watch URL without channel parameter not allowed; use /channel/UCxxx format")
            if host == "youtu.be":
                raise ValueError("YouTube short URL (youtu.be) cannot be verified for channel ownership; use full /channel/UCxxx URL")
    return url

_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
       "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")


@dataclass
class IngestedDoc:
    url: str
    title: str
    text: str
    retrieved_at: float = field(default_factory=time.time)
    method: str = "static"

    @property
    def doc_id(self) -> str:
        return hashlib.sha256(self.url.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Static fetch (fast path)
# ---------------------------------------------------------------------------

async def fetch_static(url: str, *, timeout: float = 20.0) -> IngestedDoc:
    import httpx
    from app.config import settings as app_settings
    max_bytes = getattr(app_settings, "web_ingest_max_response_bytes", 5 * 1024 * 1024)
    request_timeout = getattr(app_settings, "web_ingest_request_timeout", 30)
    # Validate URL before any network request
    await _validate_and_normalize(url)
    async with httpx.AsyncClient(headers={"User-Agent": _UA}, follow_redirects=True,
                                 timeout=request_timeout) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            chunks = []
            total = 0
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    chunk = chunk[: max_bytes - (total - len(chunk))]
                    chunks.append(chunk)
                    break
                chunks.append(chunk)
            content = b"".join(chunks).decode("utf-8", errors="replace")
    title, text = extract_clean_text(content)
    return IngestedDoc(url=url, title=title, text=text, method="static")


# ---------------------------------------------------------------------------
# Dynamic fetch (Playwright, JS-rendered)
# ---------------------------------------------------------------------------

async def fetch_dynamic(url: str, *, wait_ms: int = 4000) -> IngestedDoc:
    from playwright.async_api import async_playwright
    from app.config import settings as app_settings
    page_timeout = getattr(app_settings, "web_ingest_page_timeout", 30_000)
    max_chars = getattr(app_settings, "web_ingest_max_dom_chars", 500_000)
    # Validate URL before any network request
    await _validate_and_normalize(url)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page(user_agent=_UA)
            await page.goto(url, wait_until="networkidle", timeout=page_timeout)
            await page.wait_for_timeout(wait_ms)
            html = (await page.content())[:max_chars]
        finally:
            await browser.close()
    title, text = extract_clean_text(html)
    return IngestedDoc(url=url, title=title, text=text, method="dynamic")


# ---------------------------------------------------------------------------
# Stealth fetch (anti-bot hardened — from the skill's playbook)
# ---------------------------------------------------------------------------

_STEALTH_INIT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
window.chrome = { runtime: {} };
"""

async def fetch_stealth(url: str, *, wait_ms: int = 6000) -> IngestedDoc:
    from playwright.async_api import async_playwright
    from app.config import settings as app_settings
    max_chars = getattr(app_settings, "web_ingest_max_dom_chars", 500_000)
    # Validate URL before any network request
    await _validate_and_normalize(url)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=[
            "--disable-blink-features=AutomationControlled",
        ])
        try:
            ctx = await browser.new_context(user_agent=_UA, locale="en-US")
            await ctx.add_init_script(_STEALTH_INIT)
            page = await ctx.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            # human-like behavior: small random delays + a scroll
            await page.wait_for_timeout(wait_ms + random.randint(500, 2000))
            await page.mouse.wheel(0, random.randint(300, 900))
            await page.wait_for_timeout(random.randint(800, 1800))
            html = (await page.content())[:max_chars]
        finally:
            await browser.close()
    title, text = extract_clean_text(html)
    return IngestedDoc(url=url, title=title, text=text, method="stealth")


# ---------------------------------------------------------------------------
# Clean-text extraction (readability-lite)
# ---------------------------------------------------------------------------

_BLOCK_TAGS = ("script", "style", "noscript", "nav", "header", "footer",
               "aside", "form", "iframe", "svg")

def extract_clean_text(html: str) -> tuple[str, str]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string if soup.title and soup.title.string else "").strip()
    for tag in soup(_BLOCK_TAGS):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text(separator="\n")
    # collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return title, text.strip()


# ---------------------------------------------------------------------------
# Chunking for the doctrine corpus (GraphRAG-grounded)
# ---------------------------------------------------------------------------

def to_chunks(doc: IngestedDoc, *, max_chars: int = 1200, overlap: int = 150) -> list[dict]:
    """Split into overlapping chunks, each carrying provenance. The `source`
    field is what the SHACL TeachingShape requires — no chunk without a source."""
    words = doc.text.split()
    chunks, i, n = [], 0, 0
    step = max(1, max_chars - overlap)
    advance = max(1, step // 5)
    while i < len(words):
        window = " ".join(words[i:i + max_chars // 5])  # ~5 chars/word
        if not window.strip():
            break
        chunks.append({
            "chunk_id": f"{doc.doc_id}-{n}",
            "text": window,
            "source": doc.url,
            "title": doc.title,
            "retrieved_at": doc.retrieved_at,
            "method": doc.method,
        })
        n += 1
        i += advance
    return chunks


async def _validate_and_normalize(url: str) -> str:
    _validate_url(url)
    return url


async def _validate_redirect(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Redirect target scheme must be http or https: {url}")
    host = parsed.hostname or ""
    if any(host.startswith(p) for p in _DENIED_PRIVATE_PREFIXES):
        raise ValueError(f"Redirect to internal address denied: {url}")
    if parsed.username or parsed.password:
        raise ValueError(f"Redirect target has embedded credentials: {url}")
    return url


async def ingest_url(url: str, *, mode: str = "auto") -> list[dict]:
    """One-call helper: fetch (auto-escalating) + chunk. `mode` ∈
    auto|static|dynamic|stealth. Auto tries static first, escalates on thin
    content or 403."""
    url = await _validate_and_normalize(url)
    doc: Optional[IngestedDoc] = None
    if mode in ("auto", "static"):
        try:
            doc = await fetch_static(url)
            if len(doc.text) < 400:
                mode = "dynamic"
        except Exception as exc:
            logger.info("static fetch failed for %s (%s)", url, type(exc).__name__)
            if mode == "static":
                raise
            mode = "dynamic"
    if doc is None or len(doc.text) < 400:
        try:
            doc = await (fetch_stealth(url) if mode == "stealth" else fetch_dynamic(url))
        except Exception as exc:
            logger.warning("%s fetch failed for %s (%s)", mode, url, type(exc).__name__)
            if mode != "stealth":
                doc = await fetch_stealth(url)
            else:
                raise
    return to_chunks(doc)


# ---------------------------------------------------------------------------
# Self-test (extraction + chunking only; no network)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    html = """<html><head><title>Breath Awareness — Ekam</title>
    <script>var x=1;</script><style>.a{}</style></head>
    <body><nav>menu</nav><main><h1>Breath Awareness</h1>
    <p>Observe the natural flow of breath without controlling it. """ + " ".join(["word"] * 400) + """</p>
    </main><footer>footer</footer></body></html>"""
    t, txt = extract_clean_text(html)
    assert t == "Breath Awareness — Ekam"
    assert "menu" not in txt and "footer" not in txt and "var x" not in txt
    doc = IngestedDoc(url="https://example.org/breath", title=t, text=txt)
    chunks = to_chunks(doc, max_chars=300)
    assert chunks and all(c["source"] == "https://example.org/breath" for c in chunks)
    print(f"web-ingest self-test OK — extracted {len(txt)} chars, {len(chunks)} chunks")
