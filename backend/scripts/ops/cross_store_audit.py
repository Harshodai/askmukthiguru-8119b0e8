#!/usr/bin/env python3
"""Cross-store audit: LightRAG entities/chunks ↔ Neo4j ↔ Qdrant ↔ working dir.

Also provides anti-entropy drift auditing and reconciliation across stores (DE-2.3).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve()
if (_HERE.parents[2] / "backend").is_dir():
    _BACKEND = _HERE.parents[2] / "backend"
else:
    _BACKEND = _HERE.parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from neo4j import GraphDatabase
from qdrant_client import QdrantClient

from app.config import settings
from app.metrics import CORPUS_DRIFT_POINTS_TOTAL

logger = logging.getLogger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "")
LIGHTRAG_DIR = "data/lightrag"
LIGHTRAG_COLLECTION = os.getenv("QDRANT_COLLECTION", "ekam_lightrag")


def format_table(headers, rows):
    widths = [len(h) for h in headers]
    for row in rows:
        for i, v in enumerate(row):
            widths[i] = max(widths[i], len(str(v)))
    sep = "-+-".join("-" * w for w in widths)
    out = [" | ".join(f"{h:<{widths[i]}}" for i, h in enumerate(headers)), sep]
    for row in rows:
        out.append(" | ".join(f"{str(v):<{widths[i]}}" for i, v in enumerate(row)))
    return "\n".join(out)


def _scroll_all_point_ids(qdrant_client: Any, col: str, page_size: int = 2048) -> set[str]:
    """Read *every* point id in the collection, paging until the scroll is exhausted.

    The previous implementation issued a single `scroll(limit=10000)`, so any
    collection larger than one page contributed a truncated id set — which then
    made the "drift" set-difference meaningless and a repair call destructive.
    """
    ids: set[str] = set()
    offset = None
    while True:
        points, offset = qdrant_client.scroll(
            collection_name=col,
            limit=page_size,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        for p in points or []:
            pid = getattr(p, "id", None)
            if pid is None and isinstance(p, dict):
                pid = p.get("id") or p.get("point_id")
            if pid is not None:
                ids.add(str(pid))
        if offset is None:
            break
    return ids


def _supabase_point_ids(supabase_client: Any, page_size: int = 1000) -> tuple[set[str], str, bool]:
    """Read point ids from the first table that exposes them, paging past the PostgREST cap.

    Returns (ids, table_name, complete). `complete` is False when a page request
    failed part-way through, which callers must treat as "unknown", never as
    "these are all the ids that exist".
    """
    for table_name in ("corpus_records", "corpus_chunks", "documents"):
        ids: set[str] = set()
        start = 0
        complete = True
        try:
            while True:
                res = (
                    supabase_client.table(table_name)
                    .select("point_id, id")
                    .range(start, start + page_size - 1)
                    .execute()
                )
                rows = getattr(res, "data", None) or []
                if not rows:
                    break
                for r in rows:
                    if isinstance(r, dict):
                        pid = r.get("point_id") or r.get("id")
                        if pid:
                            ids.add(str(pid))
                if len(rows) < page_size:
                    break
                start += page_size
        except Exception as exc:
            logger.warning("cross_store_audit: reading %s failed: %s", table_name, exc)
            complete = False
        if ids:
            return ids, table_name, complete
    return set(), "", True


def audit_store_drift(
    qdrant_client: Any,
    supabase_client: Any = None,
    fix: bool = False,
    collection_name: Optional[str] = None,
    neo4j_driver: Any = None,
    confirm: bool = False,
    max_repair_fraction: float = 0.25,
) -> dict[str, Any]:
    """Audit drift between Qdrant points and Supabase / Graph records (DE-2.3).

    Computes set-difference drift between Qdrant points and other stores.
    Updates the Prometheus gauge CORPUS_DRIFT_POINTS_TOTAL with label store_pair.

    `fix=True` deletes orphan Qdrant points that have no corresponding Supabase
    record. Deletion is refused unless all of the following hold, because the
    Supabase side is the one that can be silently truncated:
      * `confirm=True` (the CLI requires --yes);
      * the Supabase read completed and returned at least one id;
      * the orphan set is not larger than `max_repair_fraction` of the collection.
    """
    col = collection_name or getattr(settings, "qdrant_collection", "spiritual_wisdom_contextual")
    logger.info("audit_store_drift: auditing collection %s (fix=%s)", col, fix)

    qdrant_ids: set[str] = set()
    qdrant_read_complete = True
    if hasattr(qdrant_client, "scroll"):
        try:
            qdrant_ids = _scroll_all_point_ids(qdrant_client, col)
        except Exception as e:
            logger.warning("audit_store_drift: error scrolling Qdrant: %s", e)
            qdrant_read_complete = False
    elif isinstance(qdrant_client, (set, list)):
        qdrant_ids = {str(x) for x in qdrant_client}
    elif hasattr(qdrant_client, "get_all_point_ids"):
        qdrant_ids = {str(x) for x in qdrant_client.get_all_point_ids()}

    supabase_ids: Optional[set[str]] = None
    supabase_table = ""
    supabase_complete = True
    if supabase_client is not None:
        if isinstance(supabase_client, (set, list)):
            supabase_ids = {str(x) for x in supabase_client}
        elif isinstance(supabase_client, dict):
            supabase_ids = {str(k) for k in supabase_client.keys()}
        elif hasattr(supabase_client, "table"):
            supabase_ids, supabase_table, supabase_complete = _supabase_point_ids(supabase_client)
        else:
            supabase_ids = set()

    graph_ids: Optional[set[str]] = None
    if neo4j_driver is not None:
        graph_ids = set()
        if hasattr(neo4j_driver, "session"):
            try:
                with neo4j_driver.session() as s:
                    res = s.run(
                        "MATCH (n:base) WHERE n.point_id IS NOT NULL RETURN n.point_id AS id"
                    )
                    for r in res:
                        gid = r.get("id")
                        if gid:
                            graph_ids.add(str(gid))
            except Exception as e:
                logger.debug("Failed querying neo4j: %s", e)
        elif isinstance(neo4j_driver, (set, list)):
            graph_ids = {str(x) for x in neo4j_driver}

    store_pair_drift: dict[str, int] = {}
    qdrant_only: set[str] = set()
    supabase_only: set[str] = set()
    if supabase_ids is not None:
        qdrant_only = qdrant_ids - supabase_ids
        supabase_only = supabase_ids - qdrant_ids
        sb_drift = len(qdrant_only) + len(supabase_only)
        store_pair_drift["qdrant_supabase"] = sb_drift
        try:
            CORPUS_DRIFT_POINTS_TOTAL.labels(store_pair="qdrant_supabase").set(sb_drift)
        except Exception as e:
            logger.debug("Failed setting metric for qdrant_supabase: %s", e)

    if graph_ids is not None:
        g_drift = len((qdrant_ids - graph_ids) | (graph_ids - qdrant_ids))
        store_pair_drift["qdrant_graph"] = g_drift
        try:
            CORPUS_DRIFT_POINTS_TOTAL.labels(store_pair="qdrant_graph").set(g_drift)
        except Exception as e:
            logger.debug("Failed setting metric for qdrant_graph: %s", e)

    repaired_count = 0
    repair_refusal: Optional[str] = None
    if fix:
        if not qdrant_read_complete:
            repair_refusal = "qdrant id read was incomplete; a partial set would over-delete"
        elif supabase_ids is None:
            repair_refusal = "no Supabase client supplied; nothing to reconcile against"
        elif not supabase_complete:
            repair_refusal = f"Supabase read of {supabase_table!r} did not complete"
        elif not supabase_ids:
            repair_refusal = f"no point ids found in Supabase table {supabase_table!r}"
        elif not qdrant_ids:
            repair_refusal = "qdrant returned no ids; refusing to treat that as 'all drift'"
        elif len(qdrant_only) > max(1.0, max_repair_fraction * len(qdrant_ids)):
            repair_refusal = (
                f"{len(qdrant_only)} of {len(qdrant_ids)} Qdrant points would be deleted "
                f"(> {max_repair_fraction:.0%}); this usually means the Supabase read was "
                "truncated. Re-run with a higher --max-repair-fraction only after verifying "
                "the counts."
            )
        elif not confirm:
            repair_refusal = "destructive repair requires explicit confirmation (--yes)"

    if fix and qdrant_only and repair_refusal is None:
        if hasattr(qdrant_client, "delete"):
            try:
                qdrant_client.delete(
                    collection_name=col,
                    points_selector=list(qdrant_only),
                )
                repaired_count = len(qdrant_only)
                remaining_drift = len(supabase_only)
                store_pair_drift["qdrant_supabase"] = remaining_drift
                try:
                    CORPUS_DRIFT_POINTS_TOTAL.labels(store_pair="qdrant_supabase").set(
                        remaining_drift
                    )
                except Exception:
                    pass
            except Exception as e:
                logger.warning("audit_store_drift: fix deletion failed: %s", e)
                repair_refusal = f"deletion failed: {e}"

    total_drift = sum(store_pair_drift.values())
    return {
        "status": "drift_detected" if total_drift > 0 else "in_sync",
        "collection": col,
        "qdrant_points_count": len(qdrant_ids),
        "qdrant_read_complete": qdrant_read_complete,
        "supabase_records_count": len(supabase_ids) if supabase_ids is not None else None,
        "supabase_table": supabase_table,
        "supabase_read_complete": supabase_complete,
        "drift_count": total_drift,
        "store_pair_drift": store_pair_drift,
        "orphan_qdrant_ids": sorted(list(qdrant_only)),
        "missing_qdrant_ids": sorted(list(supabase_only)),
        "fix_applied": bool(fix and repaired_count),
        "repair_refused_reason": repair_refusal,
        "repaired_count": repaired_count,
    }


class CrossStoreAuditor:
    def __init__(self):
        self.qdrant = QdrantClient(url=QDRANT_URL, timeout=15)
        self.neo4j = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        self.report = {"entities": {}, "chunks": {}, "working_dir": {}, "inconsistencies": []}

    def close(self):
        self.neo4j.close()

    def _inc(self, db, typ, sev, desc):
        self.report["inconsistencies"].append(
            {"database": db, "type": typ, "severity": sev, "description": desc}
        )

    def audit_entities(self):
        print("\n=== Entity Cross-Store Audit ===")
        with self.neo4j.session() as s:
            our_res = s.run(
                "MATCH (n:base) WHERE n.entity_id IS NOT NULL "
                "RETURN n.entity_id AS id, n.entity_type AS type, n.description AS desc"
            )
            our_entities = {}
            for r in our_res:
                eid = (r.get("id") or "").strip().lower()
                if eid:
                    our_entities[eid] = {
                        "type": r.get("type") or "",
                        "desc": (r.get("desc") or "")[:60],
                    }

            lr_res = s.run(
                "MATCH (n:LIGHTRAG) WHERE n.entity_id IS NOT NULL "
                "RETURN n.entity_id AS id, labels(n) AS labels, n.entity_type AS type "
                "LIMIT 10000"
            )
            lr_entities = {(r.get("id") or "").strip().lower() for r in lr_res}

        qdrant_entity_cols = [
            c.name
            for c in self.qdrant.get_collections().collections
            if c.name.startswith(f"{LIGHTRAG_COLLECTION}_entities_")
        ]
        qdrant_entities = set()
        for col_name in qdrant_entity_cols:
            cnt = self.qdrant.count(col_name, exact=True).count
            if cnt == 0:
                continue
            pts, _ = self.qdrant.scroll(col_name, limit=min(cnt, 2000), with_payload=True)
            for p in pts:
                eid = (
                    str(p.payload.get("entity_name") or p.payload.get("entity_id") or "")
                    .strip()
                    .lower()
                )
                if eid:
                    qdrant_entities.add(eid)

        our_set = set(our_entities.keys())
        our_in_lr = our_set & lr_entities
        our_missing_lr = our_set - lr_entities
        lr_extra = lr_entities - our_set
        _qdrant_in_both = our_set & qdrant_entities
        qdrant_missing_our = qdrant_entities - our_set

        self.report["entities"] = {
            "our_neo4j_total": len(our_set),
            "lightrag_neo4j_total": len(lr_entities),
            "lightrag_qdrant_total": len(qdrant_entities),
            "matched_neo4j": len(our_in_lr),
            "our_missing_from_lightrag_neo4j": len(our_missing_lr),
            "our_missing_from_lightrag_qdrant": len(our_set - qdrant_entities),
            "lightrag_extra_not_in_our_neo4j": len(lr_extra),
            "sample_our_missing_lr": sorted(our_missing_lr)[:20],
            "sample_lr_extra": sorted(lr_extra)[:20],
            "sample_qdrant_missing_our": sorted(qdrant_missing_our)[:20],
        }

        print(f"Our Neo4j entities:             {len(our_set)}")
        print(f"LightRAG Neo4j entities:         {len(lr_entities)}")
        print(f"LightRAG Qdrant entities:        {len(qdrant_entities)}")
        print(f"Matched (in both):               {len(our_in_lr)}")
        print(f"Our entities missing in LR Neo4j: {len(our_missing_lr)}")
        print(f"Our entities missing in LR Qdrant: {len(our_set - qdrant_entities)}")
        print(f"LR entities not in our Neo4j:    {len(lr_extra)}")

        if len(our_missing_lr) > 10:
            self._inc(
                "cross_store",
                "our_entities_missing_lightrag",
                "MEDIUM",
                f"{len(our_missing_lr)} entities exist in our Neo4j but are absent from LightRAG Neo4j. "
                "LightRAG will return no graph context for these entities.",
            )
        if len(lr_extra) > 10:
            self._inc(
                "cross_store",
                "lightrag_orphan_entities",
                "LOW",
                f"{len(lr_extra)} entities exist in LightRAG Neo4j but have no counterpart in our Neo4j. "
                "These might be stale/dangling from prior runs.",
            )

    def audit_chunks(self):
        print("\n=== Chunk Cross-Store Audit ===")
        chunk_cols = [
            c.name
            for c in self.qdrant.get_collections().collections
            if c.name.startswith(f"{LIGHTRAG_COLLECTION}_chunks_")
        ]
        total_chunks = 0
        chunk_count_by_col = {}
        for col_name in chunk_cols:
            cnt = self.qdrant.count(col_name, exact=True).count
            chunk_count_by_col[col_name] = cnt
            total_chunks += cnt

        with self.neo4j.session() as s:
            our_chunks = s.run(
                "MATCH (n:base) WHERE n.entity_type = 'chunk' RETURN count(n) AS c"
            ).single()["c"]
            our_docs = s.run(
                "MATCH (n:base) WHERE n.entity_type = 'document' RETURN count(n) AS c"
            ).single()["c"]

        self.report["chunks"] = {
            "lightrag_qdrant_chunks": total_chunks,
            "lightrag_qdrant_collections": chunk_count_by_col,
            "our_neo4j_chunks": our_chunks,
            "our_neo4j_documents": our_docs,
        }

        print(f"LightRAG Qdrant chunks (total): {total_chunks}")
        for c, n in sorted(chunk_count_by_col.items()):
            print(f"  {c}: {n}")
        print(f"Our Neo4j chunks:               {our_chunks}")
        print(f"Our Neo4j documents:            {our_docs}")

    def audit_working_dir(self):
        print("\n=== LightRAG Working Directory Audit ===")
        lr_path = Path(LIGHTRAG_DIR)
        if not lr_path.exists():
            print(f"  Working dir {LIGHTRAG_DIR} does not exist")
            return
        kv_json = list(lr_path.glob("*kv_store*.json"))
        doc_status = list(lr_path.glob("*doc_status*.json"))
        graphml = list(lr_path.glob("*.graphml"))
        chunk_files = list(lr_path.glob("chunks_*"))
        rd = self.report["working_dir"]
        rd["path"] = str(lr_path.resolve())
        rd["kv_store_files"] = [str(p.name) for p in kv_json]
        rd["doc_status_files"] = [str(p.name) for p in doc_status]
        rd["graphml_files"] = [str(p.name) for p in graphml]
        rd["chunk_files"] = [str(p.name) for p in chunk_files]
        rd["total_files"] = len(list(lr_path.iterdir()))

        print(f"  Path: {lr_path.resolve()}")
        print(f"  KV store files:     {len(kv_json)}")
        print(f"  Doc status files:   {len(doc_status)}")
        print(f"  GraphML files:      {len(graphml)}")
        print(f"  Chunk files:        {len(chunk_files)}")
        print(f"  Total items:        {rd['total_files']}")

        if kv_json:
            fpath = kv_json[0]
            try:
                data = json.loads(fpath.read_text())
                rd["kv_store_keys"] = list(data.keys())[:100]
                rd["kv_store_key_count"] = len(data)
                print(f"  KV store keys: {len(data)}")
            except Exception as e:
                print(f"  KV store read error: {e}")

    def run_all(self):
        self.audit_entities()
        self.audit_chunks()
        self.audit_working_dir()
        os.makedirs("logs", exist_ok=True)
        rpath = "logs/cross_store_audit_report.json"
        with open(rpath, "w") as f:
            json.dump(self.report, f, indent=2, default=str)
        print(f"\nReport saved to {rpath}")

        if self.report["inconsistencies"]:
            print("\n=== Inconsistencies Found ===")
            rows = []
            for inc in self.report["inconsistencies"]:
                rows.append(
                    [inc["database"], inc["type"], inc["severity"], inc["description"][:80]]
                )
            print(format_table(["DB", "Type", "Sev", "Description"], rows))
        else:
            print("\nNo inconsistencies found.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Cross-store audit and anti-entropy drift check (DE-2.3)"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--report-only",
        action="store_true",
        dest="report_only",
        help="audit and report drift without repairing (default)",
    )
    mode.add_argument(
        "--repair",
        "--fix",
        action="store_true",
        dest="fix",
        default=False,
        help="repair detected drift by deleting orphan Qdrant points (requires --yes)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        dest="confirm",
        help="confirm the destructive repair; without it --repair only reports what it would do",
    )
    parser.add_argument(
        "--max-repair-fraction",
        type=float,
        default=0.25,
        help=(
            "refuse the repair when the orphan set exceeds this fraction of the "
            "collection (guards against a truncated id read); default 0.25"
        ),
    )
    args = parser.parse_args()
    if args.report_only:
        args.fix = False
    return args


if __name__ == "__main__":
    args = parse_args()
    auditor = CrossStoreAuditor()
    try:
        auditor.run_all()
        supabase_client = None
        try:
            from app.telemetry_db import _get_client

            supabase_client = _get_client()
        except Exception as exc:
            logger.warning("cross_store_audit: no Supabase client available: %s", exc)

        drift_res = audit_store_drift(
            auditor.qdrant,
            supabase_client=supabase_client,
            fix=args.fix,
            confirm=args.confirm,
            max_repair_fraction=args.max_repair_fraction,
        )
        print("\n=== Store Drift Summary ===")
        print(f"Drift status: {drift_res['status']}")
        print(f"Drift count:  {drift_res['drift_count']}")
        if drift_res.get("store_pair_drift"):
            for pair, cnt in drift_res["store_pair_drift"].items():
                print(f"  {pair}: {cnt}")
        if drift_res.get("repair_refused_reason"):
            print(f"Repair refused: {drift_res['repair_refused_reason']}")
        if args.fix:
            print(f"Repaired points: {drift_res.get('repaired_count', 0)}")
    finally:
        auditor.close()
