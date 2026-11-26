"""Every custom request header the SPA sends must be in the production CORS allow-list.

Failure class (2026-11-19 and earlier): a header added in src/ (X-Brain-Unlock,
X-CSRF-Token) but missing from `cors_allow_headers` fails the browser preflight,
which the UI shows only as "failed (—)". This scans src/ so a new header cannot ship
without the backend allowing it.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "backend" / "app" / "main.py"
# CORS-safelisted request headers need no allow-list entry (Fetch spec).
_SAFELISTED = {"accept", "accept-language", "content-language"}
# Sent only to Supabase/third parties by their SDKs, never to our backend.
_NOT_OUR_BACKEND = {
    "apikey",
    "x-client-info",
    "add-padding",  # src/lib/passwordBreachCheck.ts -> Have I Been Pwned range API
    # DORMANT module (CLAUDE.md "Dormant modules"), imported nowhere in src/. Wiring it
    # requires adding Last-Event-ID to the production cors_allow_headers first.
    "last-event-id",  # src/lib/streaming/ResilientStreamTransport.ts
}
_NAME = r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+|Authorization"
# A key inside a `headers: { ... }` object (any line of it), or headers.set/append('X', ...).
_KEY_IN_OBJECT = re.compile(
    rf"""(?:['"]({_NAME})['"]|\b({_NAME})\b)\s*:"""
)  # every key on the line
_SUBSCRIPT = re.compile(rf"""\[\s*['"]({_NAME})['"]\s*\]\s*=(?!=)""")
_OPENER = re.compile(r"headers\b[^=\n]*=\s*\{|headers\s*:\s*\{", re.IGNORECASE)
_SET_CALL = re.compile(rf"""\.(?:set|append)\(\s*['"`]({_NAME})['"`]""")
_INLINE_KEY = re.compile(
    rf"""headers\s*:\s*\{{[^}}]*?(?:['"]({_NAME})['"]|\b({_NAME})\b)\s*:""", re.IGNORECASE
)
_X_LITERAL = re.compile(r"""['"`]([Xx]-[A-Za-z0-9-]+)['"`]""")


def _production_allow_headers() -> set[str]:
    src = MAIN.read_text(encoding="utf-8")
    block = re.search(r"cors_allow_headers = \[(.*?)\]", src, re.DOTALL)
    assert block, "cors_allow_headers list not found in app/main.py"
    return {h.lower() for h in re.findall(r'"([^"]+)"', block.group(1))}


def scan_headers(text: str) -> set[str]:
    """Header names a source file sends: object keys inside `headers: {`, .set/.append, X- literals."""
    found: set[str] = set()
    depth = 0  # brace depth inside an open `headers: {` object
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("//", "*")):
            continue
        found.update(m.lower() for m in _SET_CALL.findall(line))
        found.update(m.lower() for m in _SUBSCRIPT.findall(line))
        for m in _INLINE_KEY.findall(line):
            if isinstance(m, tuple):
                found.update(x.lower() for x in m if x)
            elif m:
                found.add(m.lower())
        if ".get(" not in line:  # reading a RESPONSE header is not sending one
            found.update(m.lower() for m in _X_LITERAL.findall(line))
        if depth:
            for m in _KEY_IN_OBJECT.findall(line):
                if isinstance(m, tuple):
                    found.update(x.lower() for x in m if x)
                elif m:
                    found.add(m.lower())
            depth = max(0, depth + line.count("{") - line.count("}"))
        else:
            opener = _OPENER.search(line)
            if opener:
                tail = line[opener.end() - 1 :]
                for m in _KEY_IN_OBJECT.findall(tail):
                    if isinstance(m, tuple):
                        found.update(x.lower() for x in m if x)
                    elif m:
                        found.add(m.lower())
                depth = max(0, tail.count("{") - tail.count("}"))
    return found - _SAFELISTED


def _spa_headers() -> set[str]:
    found: set[str] = set()
    for path in (ROOT / "src").rglob("*"):
        if path.suffix not in {".ts", ".tsx"} or "test" in path.parts or ".test." in path.name:
            continue
        found |= scan_headers(path.read_text(encoding="utf-8"))
    return found - _NOT_OUR_BACKEND


def test_scan_catches_every_way_a_header_is_written():
    src = """
    fetch(u, {
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': key,
        ...(t ? { Authorization: `Bearer ${t}` } : {}),
      },
    });
    const h = new Headers(); h.set('X-Brain-Unlock', getToken());
    fetch(u, { headers: { 'x-lower-case': '1' } });
    // 'X-Commented-Out': no
    const ttl = res.headers.get('Retry-After');
    const headers: Record<string, string> = {
      'Accept-Ranges-Custom': 'a',
    };
    req.headers['Last-Event-ID'] = id;
    fetch(u, { headers: { 'One-Key': 'a', 'Two-Key': 'b' } });
    """
    assert scan_headers(src) == {
        "authorization",
        "content-type",
        "idempotency-key",
        "x-brain-unlock",
        "x-lower-case",
        "accept-ranges-custom",
        "last-event-id",
        "one-key",
        "two-key",
    }


def test_scan_finds_the_known_headers():
    headers = _spa_headers()
    assert {"x-session-id", "content-type", "authorization"} <= headers, headers


def test_every_spa_header_is_allowed_in_production():
    missing = _spa_headers() - _production_allow_headers()
    assert not missing, (
        f"add to the production cors_allow_headers in app/main.py: {sorted(missing)}"
    )
