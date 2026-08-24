import pytest

from scripts.ops.corpus_audit import _validate_qdrant_base_url


def test_qdrant_http_url_is_normalized():
    assert _validate_qdrant_base_url("http://qdrant:6333/") == "http://qdrant:6333"
    assert _validate_qdrant_base_url("https://qdrant.example.test/base") == "https://qdrant.example.test/base"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "data:text/plain,secret",
        "qdrant:6333",
        "http://user:password@qdrant:6333",
        "http://qdrant:6333?redirect=file:///etc/passwd",
        "http://qdrant:6333#fragment",
        "http:///missing-host",
    ],
)
def test_qdrant_url_rejects_unsafe_or_ambiguous_forms(url):
    with pytest.raises(ValueError):
        _validate_qdrant_base_url(url)
