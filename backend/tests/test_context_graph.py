from rag.context_graph import plan_context_graph


def test_entity_faq_on_fast_tier_bypasses_the_context_graph():
    """tier2_simple takes the fast-lane bypass added in a0f54b8e.

    This asserted mode == "local" and had been red since that change, while
    test_ruthless_phase3_planner.py asserted mode == "none" for the same tier
    and passed — two tests contradicting each other about one behaviour. The
    bypass is deliberate: simple queries skip graph planning for latency.
    """
    plan = plan_context_graph(
        "How can Soul Sync support the Beautiful State?",
        intent="QUERY",
        query_tier="tier2_simple",
    )
    assert plan.mode == "none"


def test_entity_faq_uses_local_context_graph_off_the_fast_lane():
    """Entity extraction still drives a local plan when the tier allows it."""
    plan = plan_context_graph(
        "How can Soul Sync support the Beautiful State?",
        intent="QUERY",
        query_tier="standard",
    )
    assert plan.mode == "local"
    assert plan.max_hops == 1
    assert "Soul Sync" in plan.entity_ids
    assert "Beautiful State" in plan.entity_ids


def test_comparative_entity_query_uses_bounded_multi_hop_graph():
    plan = plan_context_graph(
        "Compare the Beautiful State and Suffering State and explain the practices that lead between them.",
        intent="COMPARATIVE",
        query_tier="tier3_complex",
    )
    assert plan.mode == "multi_hop"
    assert plan.max_hops == 2
    assert plan.token_budget == 2600


def test_non_entity_question_stays_on_qdrant_path():
    plan = plan_context_graph("What should I do this morning?", intent="QUERY")
    assert plan.mode == "none"
    assert plan.entity_ids == []
    assert plan.max_hops == 0
