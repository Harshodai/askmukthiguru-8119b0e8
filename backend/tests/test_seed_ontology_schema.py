"""Ontology seed: schema DDL must auto-commit, and failures must raise.

Memgraph rejects constraint/index DDL inside an explicit transaction, and the
seed used to swallow that error outside production while its only caller
(maintenance_runner) reported SUCCESS. See lessons.md L-SEED-FALSE-SUCCESS-1.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.db.seed_ontology as seed_module


def _run_seed(driver):
    with (
        patch.object(
            seed_module, "get_container", return_value=SimpleNamespace(neo4j_driver=driver)
        ),
        patch.object(seed_module.settings, "neo4j_uri", "bolt://test:7687"),
        patch.object(seed_module.settings, "is_production", False),
        patch.object(seed_module, "align_extracted_ontology"),
    ):
        seed_module.seed_spiritual_ontology()


def test_schema_ddl_auto_commits_and_never_runs_in_an_explicit_transaction():
    session = MagicMock()
    tx = MagicMock()
    session.execute_write.side_effect = lambda fn: fn(tx)
    driver = MagicMock()
    driver.session.return_value.__enter__.return_value = session

    _run_seed(driver)

    auto_committed = [call.args[0] for call in session.run.call_args_list]
    in_transaction = [call.args[0] for call in tx.run.call_args_list]
    assert any("CREATE CONSTRAINT" in q for q in auto_committed)
    assert any("CREATE INDEX" in q for q in auto_committed)
    assert not [q for q in in_transaction if "CREATE CONSTRAINT" in q or "CREATE INDEX" in q]
    assert in_transaction, "data seeding still runs in a write transaction"


def test_seed_failure_raises_outside_production():
    driver = MagicMock()
    driver.verify_connectivity.side_effect = ConnectionError("graph down")

    with pytest.raises(RuntimeError, match="graph down"):
        _run_seed(driver)
