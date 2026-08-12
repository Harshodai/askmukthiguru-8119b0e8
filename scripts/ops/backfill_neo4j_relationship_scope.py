#!/usr/bin/env python3
"""Backfill corpus provenance on legacy ontology relationships.

Only relationships between ontology ``:base`` nodes are touched. The command is
safe by default: it reports the candidate count unless ``--apply`` is supplied.
Run it against a non-production clone first and retain the output in release
evidence before changing a production graph.
"""

from __future__ import annotations

import argparse
import os
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-id", default="askmukthiguru")
    parser.add_argument("--apply", action="store_true", help="perform the backfill; default is dry run")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USER")
    password = os.environ.get("NEO4J_PASSWORD")
    if not all((uri, user, password)):
        print("Neo4j connection variables are required", file=sys.stderr)
        return 2

    from neo4j import GraphDatabase

    candidate_query = """
    MATCH (s:base)-[r]->(o:base)
    WHERE r.corpus_id IS NULL
    RETURN count(r) AS candidates
    """
    backfill_query = """
    MATCH (s:base)-[r]->(o:base)
    WHERE r.corpus_id IS NULL
    SET r.corpus_id = $corpus_id,
        r.scope_backfilled_at = datetime()
    RETURN count(r) AS updated
    """

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            candidates = session.run(candidate_query).single()["candidates"]
            print(f"legacy ontology relationships without corpus_id: {candidates}")
            if not args.apply:
                print("dry run only; re-run with --apply after non-production verification")
                return 0
            updated = session.run(backfill_query, corpus_id=args.corpus_id).single()["updated"]
            print(f"backfilled corpus_id={args.corpus_id!r} on {updated} relationships")
            return 0
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
