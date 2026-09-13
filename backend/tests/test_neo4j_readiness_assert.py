"""P5 guard: startup readiness asserts required Neo4j uniqueness constraints.

Root cause: unconstrained concurrent MERGE is check-then-create and produces
duplicate nodes (neo4j/neo4j#13841). Startup previously never verified the
constraints from seed_ontology._migrations exist, so a dropped constraint
failed silently into graph corruption. The assert is read-only
(SHOW CONSTRAINTS) — startup schema mutation stays in the maintenance runner.
"""
import pytest


class _FakeRecords(list):
    pass


class _FakeSession:
    def __init__(self, names=None, exc=None):
        self._names = names
        self._exc = exc

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def run(self, query):
        assert "SHOW CONSTRAINTS" in query, "assert must stay read-only"
        if self._exc is not None:
            raise self._exc
        return [{"name": n} for n in (self._names or [])]


class _FakeDriver:
    def __init__(self, names=None, exc=None):
        self._session = _FakeSession(names=names, exc=exc)

    def session(self):
        if isinstance(self._session, Exception):
            raise self._session
        return self._session


def _all_names():
    from app.main import REQUIRED_NEO4J_CONSTRAINTS

    return list(REQUIRED_NEO4J_CONSTRAINTS)


def test_all_constraints_present_passes():
    from app.main import assert_neo4j_constraints_ready

    assert assert_neo4j_constraints_ready(_FakeDriver(names=_all_names())) is None


def test_missing_constraints_raise_loud():
    from app.main import assert_neo4j_constraints_ready

    with pytest.raises(RuntimeError, match="UNIQUE_CONCEPT_NAME"):
        assert_neo4j_constraints_ready(_FakeDriver(names=["UNIQUE_TEACHER_NAME"]))


def test_no_driver_skips_degraded():
    from app.main import assert_neo4j_constraints_ready

    assert assert_neo4j_constraints_ready(None) is None


def test_unreachable_neo4j_skips_degraded():
    from app.main import assert_neo4j_constraints_ready

    assert assert_neo4j_constraints_ready(_FakeDriver(exc=ConnectionError("down"))) is None


def test_assert_is_read_only():
    import inspect

    import app.main as main_module

    src = inspect.getsource(main_module.assert_neo4j_constraints_ready)
    assert "SHOW CONSTRAINTS" in src
    for verb in ("CREATE CONSTRAINT", "DROP CONSTRAINT", "CREATE INDEX"):
        assert verb not in src, f"startup assert must never mutate schema ({verb})"


def test_required_set_matches_seed_migrations():
    import pathlib
    import re

    from app.main import REQUIRED_NEO4J_CONSTRAINTS

    seed = pathlib.Path("app/db/seed_ontology.py").read_text()
    seed_names = set(re.findall(r"CREATE CONSTRAINT (\w+)", seed))
    assert set(REQUIRED_NEO4J_CONSTRAINTS) == seed_names, (
        "assert set drifted from seed_ontology._migrations: "
        f"missing={seed_names - set(REQUIRED_NEO4J_CONSTRAINTS)}, "
        f"extra={set(REQUIRED_NEO4J_CONSTRAINTS) - seed_names}"
    )
