import pytest
from services.kg_analytics import enrich_graph, export_d3blocks_html


@pytest.fixture
def sample_graph():
    return {
        "nodes": [
            {"id": "concept:A", "label": "A", "type": "Concept"},
            {"id": "concept:B", "label": "B", "type": "Concept"},
            {"id": "concept:C", "label": "C", "type": "Concept"},
            {"id": "memory:1", "label": "M1", "type": "Memory"},
        ],
        "edges": [
            {"source": "concept:A", "target": "concept:B"},
            {"source": "concept:B", "target": "concept:C"},
            {"source": "memory:1", "target": "concept:A"},
        ],
    }


def test_enrich_graph_adds_analytics_fields(sample_graph):
    result = enrich_graph(sample_graph, enabled=True)
    assert len(result["nodes"]) == 4
    a = next(n for n in result["nodes"] if n["id"] == "concept:B")
    assert "analytics" in a
    assert set(a["analytics"].keys()) == {
        "pagerank", "betweenness", "closeness", "degree", "hits_hub", "hits_authority"
    }
    assert "community" in a
    assert isinstance(a["community"], int)


def test_enrich_graph_disabled_returns_unchanged(sample_graph):
    result = enrich_graph(sample_graph, enabled=False)
    for n in result["nodes"]:
        assert "analytics" not in n
        assert "community" not in n


def test_enrich_graph_empty_graph():
    result = enrich_graph({"nodes": [], "edges": []}, enabled=True)
    assert result == {"nodes": [], "edges": []}


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__]))

def test_export_d3blocks_html_smoke(sample_graph):
    pytest.importorskip("d3blocks")
    html = export_d3blocks_html(sample_graph, title="Test Map")
    assert "<!DOCTYPE html>" in html or "<html" in html.lower()
    assert "Test Map" in html or "D3Blocks" in html
