"""India helpline ordering, status flags and no-hardcoded-numbers guard (WP3, 2026-10-07).

Tele-MANAS (14416) is the national mental-health line and must be the FIRST
India entry actually served; the generic 112 emergency number must not crowd
it out of the compact (two-line) crisis block. KIRAN was merged into Tele-MANAS
(announced Feb 2024) and is no longer served.
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


def test_kiran_is_not_served():
    # Merged into Tele-MANAS (announced Feb 2024); no source shows the number still answers.
    assert not any("KIRAN" in h.name for h in _fresh())
    assert not any("KIRAN" in h.name for h in crisis_helplines._FALLBACK_HELPLINES)


def test_aasra_uses_the_number_on_its_official_site():
    aasra = next(h for h in _fresh() if h.name == "AASRA")
    assert aasra.contact == "022 2754 6669"


def test_entries_have_no_status_flag():
    assert all(h.status is None for h in _fresh())


_NUMBER_PATTERNS = (
    "14416",
    "1800-599-0019",
    "1800-891-4416",
    "18005990019",
    "9152987821",
    "9820466726",
    "022 2754 6669",
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
