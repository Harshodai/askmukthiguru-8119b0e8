"""A failed Neo4j ontology write must not leave Qdrant and the graph disagreeing.

Two defects this pins:

1. With ontology_write_required=True the single-document paths returned
   ``chunks_indexed: 0`` without rolling the Qdrant write back — the return
   value said nothing was indexed while N chunks were live and retrievable.
   The playlist path already rolled back, so the same failure produced
   opposite states depending on the entry point.

2. With the default ontology_write_required=False the failure was logged at
   WARNING and the source was then checkpointed as processed, so it was never
   retried and the result still claimed a clean success.

NOTE ON STRENGTH: these are structural assertions over the source of the two
single-doc paths (which are byte-identical in this region). They catch the
regression cheaply but do not execute the failure path; a behavioural test
needs a fake Neo4j driver and is tracked separately.
"""

from __future__ import annotations

import inspect
import re

import pytest

from ingest.pipeline import IngestionPipeline

SINGLE_DOC_PATHS = ("_ingest_video", "_ingest_video_enhanced")


def _ontology_block(method_name: str) -> str:
    """The Neo4j materialization block through to the checkpoint save.

    Anchored on the materialization comment specifically — the enhanced path
    also carries a 'KG Phase 6: Hyper-Extract enrichment' block earlier, and a
    looser anchor swallows it along with its unrelated LightRAG warning.
    """
    src = inspect.getsource(getattr(IngestionPipeline, method_name))
    start = src.index("materialize extracted entities/relationships into Neo4j")
    end = src.index("checkpoint.save(", start)
    return src[start:end]


@pytest.mark.parametrize("method_name", SINGLE_DOC_PATHS)
def test_required_ontology_failure_rolls_back_qdrant(method_name: str):
    block = _ontology_block(method_name)
    assert "self._rollback_reindex(url, backup_collection)" in block, (
        f"{method_name}: required ontology write failure returns chunks_indexed=0 "
        "without rolling back the Qdrant upsert — the return value lies and the "
        "chunks stay live and retrievable"
    )


@pytest.mark.parametrize("method_name", SINGLE_DOC_PATHS)
def test_rollback_precedes_the_error_return(method_name: str):
    block = _ontology_block(method_name)
    assert block.index("self._rollback_reindex") < block.index(
        '"status": "error"'
    ), f"{method_name}: rollback must run before the error return, not after"


@pytest.mark.parametrize("method_name", SINGLE_DOC_PATHS)
def test_optional_ontology_failure_is_not_a_silent_warning(method_name: str):
    """Optional-mode failure still checkpoints, so it must at least be loud."""
    block = _ontology_block(method_name)
    assert "logger.warning" not in block, (
        f"{method_name}: an ontology write that is checkpointed as processed and "
        "never retried is a permanent split-brain, not a warning"
    )
    assert "logger.error" in block


@pytest.mark.parametrize("method_name", SINGLE_DOC_PATHS)
def test_result_reports_ontology_state(method_name: str):
    """Callers must be able to see the degradation without reading logs."""
    src = inspect.getsource(getattr(IngestionPipeline, method_name))
    assert re.search(r'"ontology_indexed":\s*ontology_indexed', src), (
        f"{method_name}: success result does not report ontology_indexed, so a "
        "source indexed into Qdrant with no graph nodes is indistinguishable "
        "from a clean success"
    )
    assert '"ontology_indexed": False' in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
