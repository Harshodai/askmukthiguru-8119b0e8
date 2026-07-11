"""Guard: _clean_inline_citations strips dangling CTA phrases the LLM appends without an
inline URL (the link is emitted in the citations array, not the text). Regression for the
"upcoming programs from Ekam" answer ending on a bare "Watch more here:" / "…website:".
"""

from rag.nodes.generation import _clean_inline_citations as clean


def test_dangling_watch_more_here_is_stripped():
    out = clean("Consistent action creates your destiny. Watch more here:")
    assert "here:" not in out.lower()
    assert "creates your destiny." in out


def test_dangling_website_cta_is_stripped():
    out = clean("You'll find them on the Ekam website:")
    assert "website:" not in out.lower()


def test_legit_url_cta_leaves_no_dangling_colon():
    out = clean("You can watch more here: https://youtube.com/c/pkconsciousness")
    assert "http" not in out
    assert "here:" not in out.lower()


def test_normal_text_untouched():
    src = "The beautiful state is calm, joy and connection."
    assert clean(src) == src


if __name__ == "__main__":
    for fn in (
        test_dangling_watch_more_here_is_stripped,
        test_dangling_website_cta_is_stripped,
        test_legit_url_cta_leaves_no_dangling_colon,
        test_normal_text_untouched,
    ):
        fn()
    print("dangling-CTA strip: all asserts passed")
