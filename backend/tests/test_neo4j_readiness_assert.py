"""P5 guard: startup readiness asserts required Memgraph uniqueness constraints.

Root cause: unconstrained concurrent MERGE is check-then-create and produces
duplicate nodes (neo4j/neo4j#13841). Startup previously never verified the
constraints from seed_ontology._migrations exist, so a dropped constraint
failed silently into graph corruption. The assert is read-only
(SHOW CONSTRAINT INFO) — startup schema mutation stays in the maintenance
runner.

SHOW CONSTRAINT INFO is Memgraph's constraint-listing command, not Neo4j's
SHOW CONSTRAINTS — Memgraph rejects the latter, and its output has no
constraint-name column (CREATE CONSTRAINT <name> ... discards the name with
a warning), so identity is matched by (label, properties) instead.
"""

import pytest

from app.main import _CONSTRAINT_LABEL_PROPERTY


class _FakeSession:
    def __init__(self, present=None, exc=None):
        self._present = present
        self._exc = exc

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def run(self, query):
        assert "SHOW CONSTRAINT INFO" in query, "assert must stay read-only"
        if self._exc is not None:
            raise self._exc
        return [
            {"constraint type": "unique", "label": label, "properties": list(props)}
            for label, props in (self._present or [])
        ]


class _FakeDriver:
    def __init__(self, present=None, exc=None):
        self._session = _FakeSession(present=present, exc=exc)

    def session(self):
        return self._session


def _all_present():
    return [(label, (prop,)) for label, prop in _CONSTRAINT_LABEL_PROPERTY.values()]


def test_all_constraints_present_passes():
    from app.main import assert_neo4j_constraints_ready

    assert assert_neo4j_constraints_ready(_FakeDriver(present=_all_present())) is None


def test_missing_constraints_raise_loud():
    from app.main import assert_neo4j_constraints_ready

    teacher = _CONSTRAINT_LABEL_PROPERTY["UNIQUE_TEACHER_NAME"]
    with pytest.raises(RuntimeError, match="UNIQUE_CONCEPT_NAME"):
        assert_neo4j_constraints_ready(
            _FakeDriver(present=[(teacher[0], (teacher[1],))])
        )


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
    assert "SHOW CONSTRAINT INFO" in src
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


def test_label_property_map_covers_every_required_constraint():
    from app.main import REQUIRED_NEO4J_CONSTRAINTS

    assert set(REQUIRED_NEO4J_CONSTRAINTS) == set(_CONSTRAINT_LABEL_PROPERTY)


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
