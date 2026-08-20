import importlib.util
from pathlib import Path


def _load_module(relative_path: str, name: str):
    path = Path(__file__).resolve().parents[2] / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_backfill = _load_module("scripts/ops/backfill_qdrant_graph_links.py", "backfill_graph_links")
_eval = _load_module("scripts/eval/retrieval_evaluation_matrix.py", "retrieval_matrix")
build_graph_patch = _backfill.build_graph_patch
ndcg_at_k = _eval.ndcg_at_k


def test_graph_link_patch_is_deterministic_and_payload_only():
    payload = {
        "text": "Soul Sync practice supports inner stillness.",
        "source_url": "https://example.test/lesson",
        "chunk_index": 3,
        "title": "Soul Sync",
    }
    patch, entities = build_graph_patch(payload, "point-1", "ontology-v1")
    assert "Soul Sync" in entities
    assert {"Soul Sync", "Inner Stillness"}.issubset(set(patch["entity_ids"]))
    assert patch["graph_node_ids"] == patch["entity_ids"]
    assert patch["source_segment_ids"] == ["https://example.test/lesson#segment:3"]
    assert patch["ontology_version"] == "ontology-v1"
    assert 0.0 < patch["entity_resolution_confidence"] <= 1.0
    assert "text" not in patch
    assert "source_url" not in patch


def test_ndcg_at_k_is_held_out_and_bounded():
    assert ndcg_at_k(["seg-a", "seg-b"], {"seg-b"}, k=2) > 0.0
    assert ndcg_at_k(["seg-x"], {"seg-b"}, k=1) == 0.0
    assert ndcg_at_k(["seg-a"], set()) is None
