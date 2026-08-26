from app.latency_catalog import RouteClass, budget_for, route_axis


def test_route_axis_is_observational_and_safety_first():
    assert route_axis(intent="DISTRESS", selected_variant="fast", language="en") is RouteClass.DISTRESS
    assert route_axis(intent="CASUAL", selected_variant="fast", language="en") is RouteClass.CASUAL
    assert route_axis(intent="QUERY", selected_variant="deep", language="en") is RouteClass.DEEP
    assert route_axis(intent="QUERY", selected_variant="standard", language="te") is RouteClass.STANDARD


def test_catalog_entries_are_unvalidated_hypotheses():
    budget = budget_for(RouteClass.MULTILINGUAL)
    assert budget.validated is False
    assert budget.minimum_samples >= 20
    assert "citation_or_abstention" in budget.required_checks
