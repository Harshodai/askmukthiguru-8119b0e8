"""Tests for memory service summary persistence (Task 2) + forget_all_reflections.

Verifies:
  1. extract_and_write path passes `summary` in metadata to add_explicit.
  2. add_explicit inserts the `summary` column when present in metadata.
  3. forget_all_reflections issues a delete-all on guru_memories for the user.
  4. PGRST204 retry path drops `summary` along with claim/confidence/decay_score.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _build_service_with_supabase(supabase_mock):
    from services.memory_service import MemoryService
    emb = MagicMock()
    emb.encode_single_full = MagicMock(return_value={"dense": [0.0] * 1024})
    svc = MemoryService(supabase_client=supabase_mock, embedding_service=emb, llm_service=None)
    return svc


def test_add_explicit_persists_summary_column():
    """metadata['summary'] must reach the insert_data dict."""
    supa = MagicMock()
    insert_q = MagicMock()
    insert_q.insert = MagicMock(return_value=insert_q)
    insert_q.execute = MagicMock(return_value=MagicMock(data=[{"id": "m1"}]))
    supa.table = MagicMock(return_value=insert_q)

    svc = _build_service_with_supabase(supa)
    _run(
        svc.add_explicit(
            "user-1",
            "I felt calm during meditation today.",
            is_core=False,
            metadata={"insight": "Calm meditation", "summary": "User finding calm in practice."},
        )
    )
    insert_q.insert.assert_called_once()
    args, _ = insert_q.insert.call_args
    payload = args[0] if args else {}
    assert payload.get("summary") == "User finding calm in practice."
    assert payload.get("claim") == "Calm meditation"


def test_pgrst204_retry_drops_summary_too():
    """First insert raises PGRST204; retry must drop summary along with the other columns."""
    supa = MagicMock()
    call_count = {"n": 0}

    class _ExecMock:
        def __init__(self, is_first):
            self._is_first = is_first

        def __call__(self, *a, **kw):
            if self._is_first:
                raise Exception("PGRST204: Could not find column 'summary'")
            return MagicMock(data=[{"id": "m1"}])

    insert_q = MagicMock()

    def _insert(data):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise Exception("PGRST204: Could not find column 'summary'")
        return insert_q

    supa.table = MagicMock(return_value=insert_q)
    insert_q.insert.side_effect = _insert
    insert_q.execute = MagicMock(return_value=MagicMock(data=[{"id": "m1"}]))

    svc = _build_service_with_supabase(supa)
    _run(
        svc.add_explicit(
            "user-1",
            "content x",
            is_core=False,
            metadata={"insight": "I", "summary": "S", "confidence": 0.5, "decay_score": 1.0},
        )
    )
    # Second insert call (after PGRST204 retry): payload must lack summary/confidence/decay_score.
    second_call_data = insert_q.insert.call_args_list[1].args[0]
    assert "summary" not in second_call_data, second_call_data
    assert "confidence" not in second_call_data
    assert "decay_score" not in second_call_data
    assert "claim" not in second_call_data


def test_forget_all_reflections_deletes_all_user_rows():
    supa = MagicMock()
    delete_q = MagicMock()
    delete_q.delete = MagicMock(return_value=delete_q)
    delete_q.eq = MagicMock(return_value=delete_q)
    delete_q.execute = MagicMock(return_value=MagicMock(data=[{"id": "m1"}, {"id": "m2"}]))
    supa.table = MagicMock(return_value=delete_q)

    svc = _build_service_with_supabase(supa)
    n = _run(svc.forget_all_reflections("user-1"))
    assert n == 2, n
    delete_q.eq.assert_any_call("user_id", "user-1")


def test_forget_all_reflections_anonymous_returns_zero():
    svc = _build_service_with_supabase(MagicMock())
    n = _run(svc.forget_all_reflections("anonymous"))
    assert n == 0


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
