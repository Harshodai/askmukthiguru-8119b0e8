"""Regression test for defect 1c: duplicated markdown headings in `doc_text()`.

`_strip_extraction_artifacts` already dropped an immediately-repeated
markdown heading LINE, but only compared the raw line (with its `#` prefix),
so two adjacent headings with the SAME TEXT at DIFFERENT levels (e.g. an
ingestion contextual `#` title directly followed by the chunk's own `###`
heading) survived untouched -- exactly the live golden_024 trace:
"# Deeksha and Spiritual Relationships ### Deeksha and Spiritual
Relationships ...".
"""

from __future__ import annotations

from rag.doc_utils import doc_text


def test_same_text_different_heading_level_is_deduped():
    text = "# Deeksha and Spiritual Relationships\n### Deeksha and Spiritual Relationships\nBody text here."
    result = doc_text({"text": text})
    assert result.count("Deeksha and Spiritual Relationships") == 1
    assert "Body text here." in result


def test_same_level_repeat_still_deduped():
    text = "## Soul Sync\n## Soul Sync\nBody."
    result = doc_text({"text": text})
    assert result.count("Soul Sync") == 1


def test_non_adjacent_repeat_is_untouched():
    text = "# Topic\nBody one.\n# Topic\nBody two."
    result = doc_text({"text": text})
    assert result.count("# Topic") == 2


if __name__ == "__main__":
    test_same_text_different_heading_level_is_deduped()
    test_same_level_repeat_still_deduped()
    test_non_adjacent_repeat_is_untouched()
    print("doc_utils heading-dedup self-check OK")
