from scripts.ops.build_reingest_manifest import build_manifest


def test_manifest_is_planning_only_and_publish_gated():
    report = {
        "sources": [
            {"source_url": "https://example.com/a", "verdict": "MIGRATE", "chunks": 3},
            {"source_url": "https://example.com/b", "verdict": "REFETCH_FROM_ORIGIN", "chunks": 4},
            {"source_url": "", "verdict": "MIGRATE", "chunks": 1},
        ]
    }
    manifest = build_manifest(report, generated_from="fixture.json")
    assert manifest["planning_only"] is True
    assert manifest["source_count"] == 2
    assert manifest["verdict_counts"]["MIGRATE"] == 1
    assert all(row["publish_allowed"] is False for row in manifest["sources"])
