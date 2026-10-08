"""India helpline ordering, status flags and no-hardcoded-numbers guard (WP3, 2026-10-07).

Tele-MANAS (14416) is the national mental-health line and must be the FIRST
India entry actually served; the generic 112 emergency number must not crowd
it out of the compact (two-line) crisis block. KIRAN is reportedly being merged
into Tele-MANAS, so it stays listed but is flagged ``needs_call_confirmation``
and must never carry a ``last_verified`` date until a human has called it.
"""

from pathlib import Path

from services import crisis_helplines

REPO_ROOT = Path(__file__).resolve().parents[2]


def _fresh():
    crisis_helplines.get_helplines.cache_clear()
    return crisis_helplines.get_helplines()


def test_first_india_entry_served_is_tele_manas():
    india = [h for h in _fresh() if h.region == "India"]
    assert "Tele-MANAS" in india[0].name
    assert "14416" in india[0].contact


def test_compact_block_leads_with_tele_manas():
    _fresh()
    block = crisis_helplines.format_helplines_block(region="India", style="compact_two_line")
    india_line = next(line for line in block.splitlines() if line.startswith("• India"))
    assert "Tele-MANAS" in india_line and "14416" in india_line


def test_bullet_block_lists_tele_manas_before_everything_else():
    _fresh()
    block = crisis_helplines.format_helplines_block(region="India", style="bullet", intro="")
    assert "Tele-MANAS" in block.splitlines()[0]


def test_in_code_fallback_also_leads_with_tele_manas():
    india = [h for h in crisis_helplines._FALLBACK_HELPLINES if h.region == "India"]
    assert "Tele-MANAS" in india[0].name


def test_kiran_listed_but_flagged_not_verified():
    kiran = next(h for h in _fresh() if h.name.startswith("KIRAN"))
    assert kiran.contact == "1800-599-0019"
    assert kiran.status == "needs_call_confirmation"
    assert kiran.last_verified is None


def test_other_entries_have_no_status_flag():
    others = [h for h in _fresh() if not h.name.startswith("KIRAN")]
    assert all(h.status is None for h in others)


_NUMBER_PATTERNS = (
    "14416",
    "1800-599-0019",
    "1800-891-4416",
    "18005990019",
    "9152987821",
    "022-27546669",
    "9999 666 555",
    "919999666555",
    "741741",
    "tel:988",
    "tel:112",
)


def test_no_crisis_number_hardcoded_in_locales_or_components():
    offenders = []
    for base in (
        REPO_ROOT / "src" / "locales",
        REPO_ROOT / "src" / "components",
        REPO_ROOT / "src" / "pages",
    ):
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in {".json", ".ts", ".tsx"}:
                continue
            text = path.read_text(encoding="utf-8")
            offenders += [
                f"{path.relative_to(REPO_ROOT)}: {n}" for n in _NUMBER_PATTERNS if n in text
            ]
    assert not offenders, offenders[:10]


def test_verified_only_block_shows_call_verified_lines_and_112_only():
    _fresh()
    block = crisis_helplines.format_helplines_block(style="bullet", intro="", verified_only=True)
    lines = block.splitlines()
    assert any("Tele-MANAS" in line for line in lines)
    assert any(line.rstrip().endswith("112") or ": 112" in line for line in lines)
    for banned in ("KIRAN", "iCall", "AASRA", "Sneha", "Vandrevala", "988"):
        assert banned not in block
    assert "Tele-MANAS" in lines[0]


def test_verified_only_serves_a_line_once_it_is_call_verified(monkeypatch):
    base = _fresh()
    icall = next(h for h in base if h.name == "iCall")
    from dataclasses import replace

    patched = tuple(
        replace(h, last_verified_by_call="2026-10-09") if h is icall else h for h in base
    )
    monkeypatch.setattr(crisis_helplines, "get_helplines", lambda: patched)
    block = crisis_helplines.format_helplines_block(intro="", verified_only=True)
    assert "iCall" in block and "KIRAN" not in block


def test_verified_only_never_returns_empty(monkeypatch):
    base = _fresh()
    from dataclasses import replace

    stripped = tuple(
        replace(h, last_verified_by_call=None) for h in base if h.contact.strip() != "112"
    )
    monkeypatch.setattr(crisis_helplines, "get_helplines", lambda: stripped)
    assert crisis_helplines.format_helplines_block(intro="", verified_only=True)


def test_distress_crisis_header_uses_verified_only():
    src = (Path(__file__).resolve().parents[1] / "rag" / "nodes" / "intent.py").read_text()
    assert "available 24/7" in src
    assert "verified_only=True" in src
