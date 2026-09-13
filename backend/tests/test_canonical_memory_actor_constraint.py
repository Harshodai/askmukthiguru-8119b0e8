"""Every actor the code writes must be permitted by the events table.

`canonical_memory_events` was created (20260912000000) with
`CHECK (actor IN ('user','system','admin'))` — written from assumption, not
from the writers. `resolver.py` writes `actor='resolver'` and `consolidator.py`
writes `actor='consolidator'`, so the audit insert raised 23514 and was
swallowed by resolver.py's try/except: the memory row committed with NO audit
trail, and the GDPR export under-reported it.

Measured 2026-09-13: 1 memory written, 0 audit rows. Widened in
20260913120000. This test fails if a new actor literal appears in the code
without being added to the constraint.
"""

import re
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_MIGRATIONS = _BACKEND.parent / "supabase" / "migrations"

_WRITER_SOURCES = (
    _BACKEND / "services" / "canonical_memory" / "resolver.py",
    _BACKEND / "services" / "canonical_memory" / "consolidator.py",
    _BACKEND / "app" / "api" / "canonical_memory.py",
)

_ACTOR_LITERAL = re.compile(r"""["']actor["']\s*:\s*["']([a-z_]+)["']""")


def _allowed_actors() -> set[str]:
    """The actor set from the most recent migration that defines the check."""
    latest = None
    for path in sorted(_MIGRATIONS.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        if "canonical_memory_events_actor_check" in text and "ADD CONSTRAINT" in text:
            latest = text
    assert latest, "no migration defines canonical_memory_events_actor_check"
    block = latest.split("ADD CONSTRAINT", 1)[1]
    return set(re.findall(r"'([a-z_]+)'", block))


def _actors_written_by_code() -> set[str]:
    found: set[str] = set()
    for path in _WRITER_SOURCES:
        if path.exists():
            found |= set(_ACTOR_LITERAL.findall(path.read_text(encoding="utf-8")))
    return found


def test_every_written_actor_is_allowed():
    allowed = _allowed_actors()
    written = _actors_written_by_code()
    assert written, "no actor literals found — the scan regex has drifted"
    missing = sorted(written - allowed)
    assert not missing, (
        f"actor(s) {missing} are written by the code but rejected by the "
        f"constraint (allowed: {sorted(allowed)}). The audit insert will raise "
        f"23514 and be swallowed, losing the trail silently."
    )


def test_the_known_writers_are_covered():
    """Pin the three that caused the incident."""
    allowed = _allowed_actors()
    for actor in ("user", "resolver", "consolidator"):
        assert actor in allowed, f"{actor} must remain permitted"
