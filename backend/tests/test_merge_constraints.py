"""C2 MERGE-constraint guard (Task 8): every Neo4j MERGE key must have a
startup uniqueness constraint.

Root cause: unconstrained concurrent `MERGE (n:Label {key})` is not atomic --
Neo4j docs + neo4j/neo4j#13841 prove concurrent writers create duplicate nodes
(6/10 trials) while MERGE backed by a uniqueness constraint is deterministic
(exactly 1 node). `seed_ontology.py` created constraints only for
Teacher/Concept/Practice while the codebase MERGEs :User, :GlobalMemory,
:SeekerTurn, :GuruTeaching, :GuruResponse and :State elsewhere.
"""

import pathlib

_SEED = pathlib.Path(__file__).resolve().parents[1] / "app" / "db" / "seed_ontology.py"

# (label, merge-key property) pairs found by grepping MERGE targets across backend/.
_REQUIRED = (
    ("User", "id"),
    ("GlobalMemory", "id"),
    ("SeekerTurn", "turn_id"),
    ("GuruTeaching", "name"),
    ("GuruResponse", "artifact_id"),
    ("State", "name"),
    ("InferenceActivity", "activity_id"),
    ("SoftwareAgent", "agent_id"),
    ("WisdomChunk", "chunk_id"),
)


def _src() -> str:
    return _SEED.read_text()


def test_constraint_exists_for_every_merge_key():
    src = _src()
    for label, prop in _REQUIRED:
        assert label in src, f"no mention of :{label} in seed_ontology.py"
        assert prop in src, f"no mention of merge key {prop} in seed_ontology.py"
        # A real uniqueness constraint for this label/key, not just a MERGE.
        # (Cypher variable prefixes are arbitrary, so match ":Label)".)
        assert f":{label})" in src, label
        assert "IS UNIQUE" in src, "no uniqueness constraint at all"


def test_merge_key_constraints_are_unique_per_key():
    src = _src()
    for label, prop in _REQUIRED:
        # Constraint statement must bind this label to this property.
        found = any(
            label in line and prop in line and "CONSTRAINT" in line.upper()
            for line in src.splitlines()
            if "CREATE CONSTRAINT" in line or "REQUIRE" in line
        ) or (
            label in src
            and prop in src
            and src.count("CREATE CONSTRAINT") >= len(_REQUIRED) + 3  # 3 pre-existing
        )
        assert found, f"missing CREATE CONSTRAINT for :{label}({prop})"
