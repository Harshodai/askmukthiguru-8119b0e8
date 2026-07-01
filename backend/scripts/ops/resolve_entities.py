"""Entity resolution for LightRAG Neo4j knowledge graph.

Discovers duplicate entity nodes (e.g. "Krishnaji" vs "Sri Krishnaji"),
LLM-confirms identity, then merges aliases into a single canonical node.

LightRAG entity schema (from neo4j_impl.py upsert_node):
  - Label: :base + entity_type (e.g. :person)
  - Primary key: entity_id (= entity_name)
  - Properties: entity_id, entity_type, description, source_id,
                file_path, content
  - Edges: :DIRECTED between :base nodes

Usage:
  python -m scripts.ops.resolve_entities --dry-run
  python -m scripts.ops.resolve_entities --apply
  python -m scripts.ops.resolve_entities --stats
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Sequence

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from neo4j import AsyncGraphDatabase, exceptions as neo4j_exceptions  # noqa: E402

from app.config import settings  # noqa: E402
from services.embedding_service import EmbeddingService  # noqa: E402
from services.gateways import SarvamHTTPGateway  # noqa: E402
from services.sarvam_service import SarvamService  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema constants (from lightrag/kg/neo4j_impl.py upsert_node)
# MERGE (n:base {entity_id: $entity_id})
#   SET n += $properties
#   SET n:`<entity_type>`
# ---------------------------------------------------------------------------
NODE_LABEL = "base"
PK = "entity_id"  # primary key (= entity_name)

# Properties that always come from the survivor (winner), not the loser
_SURVIVOR_ONLY: frozenset[str] = frozenset(
    {
        "entity_id",  # immutable - the survivor's name IS the entity_id
        "entity_type",  # winner's type wins (same for confirmed duplicates)
    }
)

# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EntityNode:
    entity_id: str
    entity_type: str
    description: str
    source_id: str
    file_path: str
    content: str

    @classmethod
    def from_neo4j_record(cls, rec: dict) -> EntityNode:
        return cls(
            entity_id=rec.get("entity_id", ""),
            entity_type=rec.get("entity_type", "UNKNOWN"),
            description=rec.get("description", "") or "",
            source_id=rec.get("source_id", "") or "",
            file_path=rec.get("file_path", "") or "",
            content=rec.get("content", "") or "",
        )


# ---------------------------------------------------------------------------
# Neo4j connection (module-level driver, lazy init)
# ---------------------------------------------------------------------------
_driver: AsyncGraphDatabase | None = None


def _get_uri() -> str:
    return (
        os.environ.get("NEO4J_URI")
        or settings.neo4j_uri
        or "bolt://localhost:7687"
    )


def _get_auth() -> tuple[str, str]:
    return (
        os.environ.get("NEO4J_USERNAME", "") or settings.neo4j_user or "neo4j",
        os.environ.get("NEO4J_PASSWORD", "") or settings.neo4j_password or "",
    )


def _get_database() -> str:
    return os.environ.get("NEO4J_DATABASE", "neo4j")


async def _get_driver() -> AsyncGraphDatabase:
    global _driver
    if _driver is None:
        uri = _get_uri()
        user, password = _get_auth()
        _driver = AsyncGraphDatabase.driver(
            uri,
            auth=(user, password),
            max_connection_pool_size=50,
            connection_timeout=30.0,
            connection_acquisition_timeout=30.0,
            max_transaction_retry_time=30.0,
        )
        # Verify connectivity
        async with _driver.session(database=_get_database()) as session:
            await session.run("RETURN 1").consume()
        logger.info("Connected to Neo4j at %s", uri)
    return _driver


async def close_driver() -> None:
    """Call at shutdown to release the connection pool."""
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


# ---------------------------------------------------------------------------
# Neo4j queries
# ---------------------------------------------------------------------------
_FETCH_ALL_ENTITIES_QUERY = f"""
    MATCH (n:{NODE_LABEL})
    WHERE n.{PK} IS NOT NULL
    RETURN n.{PK} AS {PK},
           n.entity_type AS entity_type,
           n.description AS description,
           n.source_id    AS source_id,
           n.file_path    AS file_path,
           n.content      AS content
    ORDER BY n.{PK}
"""

_REWRITE_RELS_QUERY = f"""
MATCH (winner:{NODE_LABEL} {{{PK}: $winner_id}})
MATCH (loser:{NODE_LABEL} {{{PK}: $loser_id}})
// outgoing: loser -> other  ->  winner -> other
MATCH (loser)-[r_out:DIRECTED]-(other:{NODE_LABEL})
WHERE other.{PK} <> $winner_id
  AND NOT (winner)-[:DIRECTED]-(other)
MERGE (winner)-[r_new:DIRECTED]-(other)
SET r_new += properties(r_out)
WITH r_out, loser
DELETE r_out
// incoming: other -> loser  ->  other -> winner
MATCH (other2:{NODE_LABEL})-[r_in:DIRECTED]-(loser)
WHERE other2.{PK} <> $winner_id
  AND NOT (other2)-[:DIRECTED]-(winner)
MERGE (other2)-[r_new2:DIRECTED]-(winner)
SET r_new2 += properties(r_in)
WITH r_in, loser
DELETE r_in
RETURN count(*) AS rewired
"""

_DELETE_LOSER_QUERY = f"""
MATCH (loser:{NODE_LABEL} {{{PK}: $loser_id}})
DETACH DELETE loser
"""


async def fetch_all_entities() -> list[EntityNode]:
    """Return every LightRAG entity node from Neo4j."""
    driver = await _get_driver()
    async with driver.session(database=_get_database()) as session:
        result = await session.run(_FETCH_ALL_ENTITIES_QUERY)
        records = await result.fetch(100_000)
        await result.consume()
    return [EntityNode.from_neo4j_record(dict(r)) for r in records]


async def _fetch_degrees(entity_ids: set[str]) -> dict[str, int]:
    """Return {entity_id: degree} for every id in entity_ids in one query."""
    if not entity_ids:
        return {}
    driver = await _get_driver()
    query = f"""
        UNWIND $ids AS eid
        MATCH (n:{NODE_LABEL} {{{PK}: eid}})
        OPTIONAL MATCH (n)-[r]-()
        RETURN eid AS entity_id, count(r) AS degree
    """
    async with driver.session(database=_get_database()) as session:
        result = await session.run(query, ids=list(entity_ids))
        rows = await result.fetch(10_000)
        await result.consume()
    return {r["entity_id"]: r["degree"] for r in rows}


async def _rewire_relationships(winner_id: str, loser_id: str) -> int:
    driver = await _get_driver()
    async with driver.session(database=_get_database()) as session:
        result = await session.run(
            _REWRITE_RELS_QUERY,
            winner_id=winner_id,
            loser_id=loser_id,
        )
        rec = await result.single()
        await result.consume()
        return rec["rewired"] if rec else 0


async def _delete_loser(loser_id: str) -> None:
    driver = await _get_driver()
    async with driver.session(database=_get_database()) as session:
        await session.run(_DELETE_LOSER_QUERY, loser_id=loser_id)


async def _update_node_property(entity_id: str, key: str, value: str) -> None:
    driver = await _get_driver()
    query = f"MATCH (n:{NODE_LABEL} {{{PK}: $eid}}) SET n.{key} = $val"
    async with driver.session(database=_get_database()) as session:
        await session.run(query, eid=entity_id, val=value)


# ---------------------------------------------------------------------------
# Cosine similarity (pure Python, no numpy)
# ---------------------------------------------------------------------------
def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Return cosine similarity between two equal-length vectors."""
    if len(a) != len(b):
        raise ValueError(f"Vector length mismatch: {len(a)} vs {len(b)}")
    dot = aa = ab = 0.0
    for ai, bi in zip(a, b):
        dot += ai * bi
        aa += ai * ai
        ab += bi * bi
    denom = (aa * ab) ** 0.5
    return dot / denom if denom > 0 else 0.0


# ---------------------------------------------------------------------------
# Similarity batching
# ponytail: O(n^2) pairwise scan. Fine for typical Kg sizes (< 50k entities).
# Ceiling: at 50k entities -> ~1.25B comparisons -> needs locality-sensitive
# hashing or FAISS. Upgrade path: faiss.IndexFlatIP on embedded names.
# ---------------------------------------------------------------------------
def find_merge_candidates(
    entities: list[EntityNode],
    embeddings: list[list[float]],
    threshold: float = 0.85,
) -> list[tuple[int, int, float]]:
    """Return (i, j, score) for every pair above threshold.

    i < j always. Both indices refer to `entities` / `embeddings`.
    """
    n = len(entities)
    if n < 2:
        return []

    candidates: list[tuple[int, int, float]] = []
    for i in range(n):
        for j in range(i + 1, n):
            score = cosine_similarity(embeddings[i], embeddings[j])
            if score >= threshold:
                candidates.append((i, j, score))
    return candidates


# ---------------------------------------------------------------------------
# LLM confirmation via SarvamService
# ---------------------------------------------------------------------------
# ponytail: global singleton, created once at startup, not per-pair.
# Per-pair LLM calls are the configurable bottleneck; increase batch size
# later if throughput matters.
_llm_service: SarvamService | None = None
_gateway: SarvamHTTPGateway | None = None


def _init_llm() -> None:
    """Instantiate SarvamService once (safe to call multiple times)."""
    global _llm_service, _gateway
    if _llm_service is not None:
        return
    _gateway = SarvamHTTPGateway()
    _llm_service = SarvamService(_gateway)


def _llm_confirm(a_name: str, b_name: str) -> bool:
    """Ask LLM whether entity_a and entity_b refer to the same entity.

    Returns True only if the response starts with "yes".
    Sanic app loop -> get or create an event loop for sync context.
    """
    if _llm_service is None:
        _init_llm()

    prompt = (
        "Are these two entity names the same entity? "
        "Answer with exactly one word: yes or no.\n\n"
        f"Entity A: {a_name}\n"
        f"Entity B: {b_name}\n\n"
        "Same entity?"
    )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    coro = _llm_service._generate_fast("", prompt)
    if loop.is_running():
        # Run in a separate thread to avoid "loop already running" error
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        response = fut.result(timeout=30)
    else:
        response = loop.run_until_complete(coro)

    return response.strip().lower().startswith("yes")


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------
# ponytail: singleton, instantiated once (same motivation as _llm_service).
_embedder: EmbeddingService | None = None


def _get_embedder() -> EmbeddingService:
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingService()
    return _embedder


def _embed_names(names: list[str]) -> list[list[float]]:
    """Embed entity names; returns list aligned with input."""
    embedder = _get_embedder()
    if len(names) == 1:
        return [embedder.encode_single(names[0])]
    return embedder.encode(names)


# ---------------------------------------------------------------------------
# Survivor selection
# ponytail: naive degree-based. Upgrade: PageRank or community size.
# ---------------------------------------------------------------------------
def _pick_survivor(
    a: EntityNode,
    b: EntityNode,
    degree_a: int,
    degree_b: int,
) -> tuple[EntityNode, EntityNode]:
    """Return (winner, loser). Prefer higher node degree (more connected)."""
    if degree_b > degree_a:
        return b, a
    return a, b


# ---------------------------------------------------------------------------
# Merge execution
# ---------------------------------------------------------------------------
def _merge_descriptions(survivor: EntityNode, loser: EntityNode) -> str:
    """Append loser's description content to survivor's, avoiding duplicates."""
    s_text = survivor.description.strip()
    l_text = loser.description.strip()
    if not l_text:
        return s_text
    if not s_text:
        return l_text

    # Only append sentences not already present in survivor
    s_lower = s_text.lower()
    new_sentences = [
        s.strip()
        for s in l_text.split(". ")
        if s.strip() and s.strip().lower() not in s_lower
    ]
    if not new_sentences:
        return s_text
    return s_text + ". " + ". ".join(new_sentences)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def _resolve_async(
    cosine_threshold: float = 0.85,
    dry_run: bool = True,
    confirm_llm: bool = True,
) -> dict:
    """Core async implementation. See resolve_entities() for the sync wrapper."""
    t0 = time.monotonic()

    # 1. Fetch all entities
    entities = await fetch_all_entities()
    total = len(entities)
    logger.info("Loaded %d entity nodes from Neo4j", total)

    if total < 2:
        return {
            "status": "skipped",
            "total_entities": total,
            "candidates": 0,
            "confirmed": 0,
            "merged": 0,
            "elapsed_s": round(time.monotonic() - t0, 2),
        }

    # 2. Compute name embeddings
    names = [e.entity_id for e in entities]
    embeddings = _embed_names(names)
    logger.info("Computed embeddings for %d entity names", len(embeddings))

    # 3. Find pairwise candidates
    candidates = find_merge_candidates(entities, embeddings, threshold=cosine_threshold)
    logger.info(
        "Found %d cosine-similar pairs (threshold=%.2f)",
        len(candidates),
        cosine_threshold,
    )

    if not candidates:
        return {
            "status": "ok",
            "total_entities": total,
            "candidates": 0,
            "confirmed": 0,
            "merged": 0,
            "elapsed_s": round(time.monotonic() - t0, 2),
        }

    # 4. Fetch degrees once for all involved entities
    involved_ids = {
        entities[i].entity_id for i, j, _ in candidates
    } | {
        entities[j].entity_id for i, j, _ in candidates
    }
    degrees = await _fetch_degrees(involved_ids)

    # 5. Confirm candidates
    confirmed_pairs: list[tuple[int, int, float]] = []
    if confirm_llm:
        for i, j, score in candidates:
            a_name = entities[i].entity_id
            b_name = entities[j].entity_id
            try:
                same = _llm_confirm(a_name, b_name)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "LLM confirm failed for '%s'|'%s': %s", a_name, b_name, exc
                )
                same = False
            if same:
                confirmed_pairs.append((i, j, score))
            logger.debug(
                "LLM confirm %s|%s (score=%.3f) -> %s",
                a_name, b_name, score, "MERGE" if same else "skip",
            )
    else:
        confirmed_pairs = candidates  # trust cosine alone

    confirmed_count = len(confirmed_pairs)
    logger.info(
        "LLM-confirmed %d / %d candidates", confirmed_count, len(candidates)
    )

    if dry_run:
        print(f"\n{'-' * 60}")
        print(
            f"  DRY-RUN - {confirmed_count} planned merges "
            f"(threshold={cosine_threshold})"
        )
        print(f"{'-' * 60}")
        for i, j, score in confirmed_pairs:
            a, b = entities[i], entities[j]
            winner, loser = _pick_survivor(
                a, b,
                degrees.get(a.entity_id, 0),
                degrees.get(b.entity_id, 0),
            )
            print(
                f"  MERGE  '{loser.entity_id}' -> '{winner.entity_id}'  "
                f"(cosine={score:.3f}, degree "
                f"{degrees.get(loser.entity_id, 0)}->"
                f"{degrees.get(winner.entity_id, 0)})"
            )
        print(f"{'-' * 60}\n")
        return {
            "status": "dry_run",
            "total_entities": total,
            "candidates": len(candidates),
            "confirmed": confirmed_count,
            "merged": 0,
            "elapsed_s": round(time.monotonic() - t0, 2),
        }

    # 6. Apply merges
    merged = 0
    for i, j, _score in confirmed_pairs:
        a, b = entities[i], entities[j]
        winner, loser = _pick_survivor(
            a, b,
            degrees.get(a.entity_id, 0),
            degrees.get(b.entity_id, 0),
        )

        # Rewire edges: loser's DIRECTED relationships -> winner
        rewired = await _rewire_relationships(winner.entity_id, loser.entity_id)
        logger.info(
            "Rewired %d relationships: '%s' -> '%s'",
            rewired, loser.entity_id, winner.entity_id,
        )

        # Merge descriptions (append loser's content to winner's)
        merged_desc = _merge_descriptions(winner, loser)
        if merged_desc != winner.description:
            await _update_node_property(
                winner.entity_id, "description", merged_desc
            )

        # Delete loser node
        await _delete_loser(loser.entity_id)
        logger.info(
            "Deleted alias node '%s' -> merged into '%s'",
            loser.entity_id, winner.entity_id,
        )
        merged += 1

    elapsed = round(time.monotonic() - t0, 2)
    logger.info("Resolved %d entities in %.2fs", merged, elapsed)
    return {
        "status": "applied",
        "total_entities": total,
        "candidates": len(candidates),
        "confirmed": confirmed_count,
        "merged": merged,
        "elapsed_s": elapsed,
    }


# ---------------------------------------------------------------------------
# Sync entry points (for asyncio.to_thread / direct calls)
# ---------------------------------------------------------------------------
def resolve_entities(
    cosine_threshold: float = 0.85,
    dry_run: bool = True,
    confirm_llm: bool = True,
) -> dict:
    """Resolve duplicate entities in the LightRAG Neo4j knowledge graph.

    Args:
        cosine_threshold: Minimum cosine similarity to consider a pair.
        dry_run: If True, only print planned merges (no writes).
        confirm_llm: If True, use LLM to confirm each candidate pair.

    Returns:
        Summary dict with keys: status, total_entities, candidates,
        confirmed, merged, elapsed_s.
    """
    return asyncio.run(_resolve_async(cosine_threshold, dry_run, confirm_llm))


def entity_stats() -> dict:
    """Return basic graph stats: total nodes, total edges, distinct types."""
    loop = asyncio.get_event_loop()

    async def _stats() -> dict:
        driver = await _get_driver()
        async with driver.session(database=_get_database()) as session:
            nodes = (
                await session.run("MATCH (n) RETURN count(n) AS c")
            ).single()
            rels = (
                await session.run("MATCH ()-[r]-() RETURN count(r) AS c")
            ).single()
            labels_res = (
                await session.run(
                    f"MATCH (n:{NODE_LABEL}) "
                    "RETURN DISTINCT n.entity_type AS t, count(*) AS c "
                    "ORDER BY c DESC"
                )
            ).fetch(100)
            await (await session.run("RETURN 1")).consume()
            type_counts = {r["t"]: r["c"] for r in labels_res}
        return {
            "total_nodes": nodes["c"] if nodes else 0,
            "total_edges": rels["c"] if rels else 0,
            "by_type": type_counts,
        }

    return loop.run_until_complete(_stats())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Resolve duplicate entities in LightRAG Neo4j graph",
    )
    p.add_argument(
        "--cosine-threshold",
        type=float,
        default=0.85,
        help="Minimum cosine similarity to flag a candidate pair (default: 0.85)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    dry = sub.add_parser("dry-run", help="Print planned merges without writing")
    dry.add_argument("--no-confirm", action="store_true", help="Skip LLM confirmation")
    dry.add_argument(
        "--threshold", type=float, default=0.85,
        help="Override the default cosine threshold for this run",
    )

    apply = sub.add_parser("apply", help="Confirm with LLM and merge aliases")
    apply.add_argument(
        "--no-confirm", action="store_true", help="Skip LLM confirmation"
    )
    apply.add_argument(
        "--threshold", type=float, default=0.85,
        help="Override the default cosine threshold for this run",
    )

    stats = sub.add_parser("stats", help="Print entity graph statistics")

    return p


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    args = _build_parser().parse_args(argv)

    try:
        if args.command == "stats":
            stats = entity_stats()
            print(f"\nEntity graph stats:")
            print(f"  Total nodes  : {stats['total_nodes']}")
            print(f"  Total edges  : {stats['total_edges']}")
            print(f"  By entity type:")
            for t, c in sorted(stats["by_type"].items(), key=lambda x: -x[1]):
                print(f"    {t or '(none)'}: {c}")
            return

        threshold = getattr(args, "threshold", args.cosine_threshold)
        confirm = not getattr(args, "no_confirm", False)
        dry_run = args.command == "dry-run"

        result = resolve_entities(
            cosine_threshold=threshold,
            dry_run=dry_run,
            confirm_llm=confirm,
        )
        print(f"\nResult: {result}")
    finally:
        # Clean up the async driver pool (best-effort)
        try:
            asyncio.run(close_driver())
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
