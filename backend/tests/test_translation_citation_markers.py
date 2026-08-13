from services.translation.citation_markers import citation_numbers, restore_citation_markers


def test_citation_numbers_preserve_unique_source_order():
    assert citation_numbers("A [2, 1] B [2] C [3]") == ["2", "1", "3"]


def test_restore_citation_markers_keeps_existing_grouped_markers_without_duplicates():
    source = "The original teaching [1, 2] is grounded in source [3]."
    translated = "Translated answer [2, 1]."
    assert restore_citation_markers(source, translated) == "Translated answer [2, 1]. [3]"


def test_restore_citation_markers_leaves_complete_translation_unchanged():
    text = "Translated answer [1] [2]."
    assert restore_citation_markers("Source [1, 2]", text) == text
