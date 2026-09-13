"""Regression coverage for the 2026-09-13 ruthless production audit.

Each test below guards one confirmed finding. See the audit report for the
full evidence trail; this file only pins the fix.
"""

import inspect


def test_domain_rights_status_payload_index_declared():
    """R2: domain_rights_status is a `must` filter on every retrieval
    (rag/nodes/retrieval.py:805,1132) but was never in the payload-index
    list, so it silently ran unindexed on all 12,904 points."""
    from services.qdrant.client import QdrantClientManager

    fields = dict(QdrantClientManager._PAYLOAD_INDEXES)
    assert fields.get("domain_rights_status") == "keyword"


def test_teacher_id_index_still_declared():
    """Guards against accidentally dropping the teacher_id index while
    touching _PAYLOAD_INDEXES — it is legitimately declared even though it
    currently indexes 0 points (R1, a data gap, not a schema gap)."""
    from services.qdrant.client import QdrantClientManager

    fields = dict(QdrantClientManager._PAYLOAD_INDEXES)
    assert fields.get("teacher_id") == "keyword"


def test_chat_cost_log_carries_tenant_and_user():
    """finding-7: the CHAT_COST log line had no tenant_id/user_id, so a
    per-tenant cost breakdown could not be reconstructed from logs even
    though the CostTracker.record() call beside it always did."""
    from app.api import chat as chat_api

    src = inspect.getsource(chat_api)
    anchor = '"CHAT_COST endpoint=%s'
    log_call = src[src.index(anchor): src.index(anchor) + 400]
    assert "tenant_id=%s" in log_call
    assert "user_id=%s" in log_call
    assert "TenantContext.get()" in log_call


def test_admin_cost_breakdown_accepts_tenant_filter():
    """finding-7(b): admin.py's /cost-breakdown called get_usage_report(days=30)
    with no tenant argument, so the dashboard aggregated every tenant into
    one number with no way to scope it. Default behaviour (all tenants)
    must be unchanged when tenant_id is omitted."""
    from app.api import admin as admin_api

    sig = inspect.signature(admin_api.cost_breakdown)
    assert "tenant_id" in sig.parameters
    assert sig.parameters["tenant_id"].default is None


class TestMultitenancyGuardStillUnwired:
    """finding-6 (VERIFIED, NOT FIXED THIS PASS): `enforce_multitenancy`
    exists but has zero production callers, and its signature checks a
    `teacher_id` kwarg neither QdrantSearcher nor QdrantIndexer ever passes.
    Wiring it is a real security-hardening item (fail-closed on cross-tenant
    reads), but doing it safely means auditing every internal caller for
    `skip_tenant_check=True` exceptions first (RAPTOR summary fetches, admin
    paths, backfills) — out of scope for this pass. This test documents the
    current (unwired) state so a future fix has to consciously update it
    rather than silently leaving the guard undeployed forever."""

    def test_guard_has_no_production_decorator_site(self):
        import services.qdrant.indexer as indexer_mod
        import services.qdrant.searcher as searcher_mod

        indexer_src = inspect.getsource(indexer_mod)
        searcher_src = inspect.getsource(searcher_mod)
        assert "enforce_multitenancy" not in indexer_src
        assert "enforce_multitenancy" not in searcher_src


def test_teacher_scoped_retrieval_returns_nothing_today():
    """R1 (VERIFIED, NOT FIXED THIS PASS — see audit report for why a blind
    backfill was not run): CorpusScope.to_qdrant_filter() adds a `must
    teacher_id == X` whenever teacher_id is set, but teacher_id is indexed
    on 0 of 12,904 live points. Any code path that ever starts passing a
    concrete teacher_id will silently get zero results, not an error. This
    test documents the gap against the real filter-building code (not live
    Qdrant, so it runs without infra) so the day someone wires teacher
    scoping, this test forces them to notice the data side is still empty."""
    from rag.corpus_scope import CorpusScope

    scope = CorpusScope(
        tenant_id="oneness",
        corpus_id="askmukthiguru",
        teacher_id="amma-bhagavan",
    )
    qdrant_filter = scope.to_qdrant_filter()
    must_keys = {cond["key"] for cond in qdrant_filter["must"]}
    assert "teacher_id" in must_keys, (
        "CorpusScope must still build a teacher_id filter condition when "
        "teacher_id is set — if this assertion fails, the filter-building "
        "code changed and the R1 data gap may no longer matter the same way."
    )
