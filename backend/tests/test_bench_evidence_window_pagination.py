"""Proves an `misattribution_unmeasured_rate` bug found in run1
(baseline_2026-09-25): 18/18 rows flagged `unmeasured_evidence_window` (never
`unmeasured_no_evidence` -- Qdrant WAS reachable) because `_citation_evidence`
fetched a single, flat 50-point page per answer regardless of how many
distinct URLs it cited, then declared the window "truncated" (unmeasurable)
whenever that one page came back full -- even when a second page would have
exhausted the cited sources completely.

Root cause: `qdrant_client.scroll(..., limit=_EVIDENCE_WINDOW)` was called
ONCE with no `offset`, so `window_truncated = len(pts) >= _EVIDENCE_WINDOW`
conflated "we hit our own arbitrary page size" with "there really is more
evidence out there we didn't look at". A citation set is 1-5 URLs; there is
no reason not to page through what Qdrant actually reports as available
before giving up.

Fix: `_citation_evidence` now paginates (bounded by `_EVIDENCE_WINDOW` total,
`_EVIDENCE_PAGE_SIZE` per call) and marks `window_truncated` only when Qdrant
itself reports a `next_page_offset` after that cap -- i.e. only when there
provably IS more evidence beyond what was fetched.
"""

from __future__ import annotations

from evaluation.bench import _EVIDENCE_WINDOW, _citation_evidence


class _Point:
    def __init__(self, url: str, text: str) -> None:
        self.payload = {
            "source_url": url,
            "provenance": "verbatim",
            "teacher_ids": ["preethaji"],
            "text": text,
        }


class _PaginatingQdrant:
    """Simulates a source with `total` matching points, served in
    `page_size`-sized pages via Qdrant's own scroll(limit, offset) contract:
    returns (points, next_page_offset), with next_page_offset=None once
    exhausted."""

    def __init__(self, total: int, page_size: int = 50) -> None:
        self.total = total
        self.page_size = page_size
        self.calls = 0

    def scroll(self, *, collection_name, scroll_filter, limit, offset=None, **_kwargs):
        self.calls += 1
        start = offset or 0
        end = min(start + limit, self.total)
        points = [_Point("http://x/vid", f"chunk {i}") for i in range(start, end)]
        next_offset = end if end < self.total else None
        return points, next_offset


def test_evidence_under_the_cap_is_not_marked_truncated():
    """68 points on a video, well under _EVIDENCE_WINDOW's cap -- previously
    this would have been truncated at the very first flat 50-point page even
    though pagination could exhaust it. Every point must be fetched and
    window_truncated must be False."""
    client = _PaginatingQdrant(total=68)
    evidence = _citation_evidence(client, "collection", ["http://x/vid"])
    assert len(evidence) == 68
    assert all(e["window_truncated"] is False for e in evidence)
    assert client.calls > 1, "must have paginated, not stopped at one page"


def test_evidence_beyond_the_cap_is_still_marked_truncated():
    """More real evidence exists than the harness is willing to fetch -- this
    must still honestly report UNMEASURED, not silently claim completeness."""
    client = _PaginatingQdrant(total=_EVIDENCE_WINDOW + 500)
    evidence = _citation_evidence(client, "collection", ["http://x/vid"])
    assert len(evidence) == _EVIDENCE_WINDOW
    assert all(e["window_truncated"] is True for e in evidence)


if __name__ == "__main__":
    test_evidence_under_the_cap_is_not_marked_truncated()
    test_evidence_beyond_the_cap_is_still_marked_truncated()
    print("test_bench_evidence_window_pagination self-check OK")
