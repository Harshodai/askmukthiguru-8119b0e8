"""Attribution and sources lines must reach the glue translator as protected text."""

from app.pipeline.stages.first_person_bridge import _split_glue_and_quotes

QUOTE = "There are only two states."


def _unprotected(text):
    return [seg for protected, seg in _split_glue_and_quotes(text, [QUOTE]) if not protected]


def test_legacy_attribution_line_is_protected():
    text = f'Related, not a direct answer:\n\n"{QUOTE}"\n— Sri Krishnaji (hLg4WPG4ehE, 120s)'
    glue = "".join(_unprotected(text))
    assert "hLg4WPG4ehE" not in glue and "Krishnaji" not in glue


def test_continuous_layout_attribution_and_sources_are_protected():
    text = (
        f"> {QUOTE}\n— Sri Preethaji · On Suffering · ▶ 01:20\n\n"
        "Related, not a direct answer\n---\nSources: [1] On Suffering @ 01:20"
    )
    glue = "".join(_unprotected(text))
    assert "On Suffering" not in glue and "Sri Preethaji" not in glue
    assert "Related, not a direct answer" in glue  # real glue still translates


def test_midline_dash_in_glue_is_not_protected():
    glue = "".join(_unprotected("Take a breath — then listen."))
    assert "Take a breath" in glue
