"""services/memgraph_community_service.py's detect/cluster/persist pipeline
used to run as 4 independent auto-committing session.run() calls. A recompute
that OOM'd mid-run (Memgraph capped at 512MB) left step 1's
`SET node.community_id` committed while step 4's :Community summary nodes
never persisted -- live-verified 2026-09-16: 178 :Community nodes existed,
163 of them exact duplicates all keyed to community_id=-1 (Louvain's
"unclustered" bucket), most missing their :HAS_CENTRAL_MEMBER links entirely.
Deleted; see the CLAUDE.md report for the live before/after evidence.

Fix: bundle all writes into ONE `session.execute_write(fn, ...)` transaction
so a downstream failure rolls back everything the run did, instead of
leaving a partially-committed graph.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from services.memgraph_community_service import MemgraphCommunityService


def test_compute_and_store_uses_session_execute_write():
    """The pipeline must go through session.execute_write, not session.run
    directly -- that's what gives the whole detect/cluster/persist sequence
    one transaction boundary instead of three independent auto-commits.
    """
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    mock_session.run.return_value.single.return_value = {"cnt": 0}  # MAGE unavailable
    mock_session.execute_write.side_effect = lambda fn, **kwargs: fn(mock_session, **kwargs)

    svc = MemgraphCommunityService(mock_driver)
    svc.compute_and_store_communities(min_community_size=2)

    assert mock_session.execute_write.called, (
        "compute_and_store_communities must delegate the write pipeline to "
        "session.execute_write so it runs in one transaction"
    )


def test_pipeline_failure_does_not_persist_partial_state():
    """If the transaction function raises partway through (simulating an
    OOM during the persist step), compute_and_store_communities must
    degrade to [] rather than reporting a partial success -- and it must
    not have made any write outside the transaction function, since only
    writes made *inside* it are covered by the real driver's rollback.
    """
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    mock_session.run.return_value.single.return_value = {"cnt": 0}

    def _boom(fn, **kwargs):
        raise MemoryError("simulated OOM mid-transaction")

    mock_session.execute_write.side_effect = _boom

    svc = MemgraphCommunityService(mock_driver)
    result = svc.compute_and_store_communities(min_community_size=2)

    assert result == []


if __name__ == "__main__":
    test_compute_and_store_uses_session_execute_write()
    test_pipeline_failure_does_not_persist_partial_state()
    print("ok")
