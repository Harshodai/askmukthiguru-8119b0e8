"""Offline, read-only concept enrichment proposal for `first_person_v10` (work package U7).

Why: the graph and OKF expansion lanes filter v10 children with
`should=[topic_ids, entity_ids, tags] MatchAny(concepts)`
(`services/first_person_context_store.py` retrieve) but those payload fields are empty, so the
lanes can never add a candidate. This script PROPOSES additive payload patches in the exact
vocabulary the lanes emit (exact-case strings):

  * graph lane  -> Memgraph `entity_id` of 1-hop neighbours of the seeded concepts
                   (`rag/kg_expansion.py`; the seed itself is never emitted) -> `entity_ids`
  * OKF lane    -> `tags` exactly as stored in `memory/okf/compiled.json` (lowercase) -> `topic_ids`;
                   entry titles (<= 40 chars) of OKF entries whose source video is the point's
                   video -> `tags`
  * TU graph    -> TU_HAS_TOPIC names keyed by TeachingUnit `span_id` == child `source_span_id`

Matching is deterministic: whole-word, case-folded, over `verbatim_text`. No LLM. Nothing here
writes to Qdrant, Memgraph, OKF or Redis unless `--apply` is given with `--snapshot-confirmed`
and `--approved-by`; `--apply` only ever calls `set_payload` on topic_ids/entity_ids/tags.
It never touches `verbatim_text`, hashes or point ids (CLAUDE.md invariants 2, 4, 13).

Modes (host: `backend/.venv/bin/python3`; graph export runs in the container, no .env reads):
  scripts/ops/backend_py.sh backend/scripts/ops/enrich_fp_concepts.py --export-graph-vocab > graph.json
  backend/.venv/bin/python3 backend/scripts/ops/enrich_fp_concepts.py --graph-vocab graph.json [--simulate]
  backend/.venv/bin/python3 backend/scripts/ops/enrich_fp_concepts.py --self-test
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import statistics
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Optional

# Only these payload keys may ever be written. facet_ids/alias_ids and every text/hash/id key are out.
ALLOWED_KEYS: tuple[str, ...] = ("topic_ids", "entity_ids", "tags")
# Type labels / generic words that are not concepts, and non-concept graph entities
# (identity comes from voice, never from words in the text: backend/CLAUDE.md).
STOP_TERMS = frozenset({"teaching"})
EXCLUDED_GRAPH_LABELS = frozenset({"Teacher", "person", "organization", "Quarantined", "Video"})
MIN_SURFACE_LEN = 3
MAX_TITLE_LEN = 40  # first_person_okf_expansion.py only emits titles <= 40 chars
CHILD_RECORD_TYPE = "retrieval_child"
DEFAULT_COLLECTION = "first_person_v10"
DEFAULT_OUT = Path("audits/work/concept-enrichment-2026-11-16")
_PARENTS = Path(__file__).resolve().parents
REPO = _PARENTS[3] if len(_PARENTS) > 3 else Path.cwd()  # in-container stdin run has no repo root
_VIDEO_RE = re.compile(r"[?&]v=([\w-]{11})")


# --------------------------------------------------------------------------- matching


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text or "")).casefold().strip()


class Matcher:
    """Whole-word, case-folded matcher that returns the EXACT canonical strings."""

    def __init__(self, canon_to_surfaces: Mapping[str, Iterable[str]]) -> None:
        self._surface: dict[str, set[str]] = {}
        for canon, surfaces in canon_to_surfaces.items():
            for surface in {canon, *surfaces}:
                key = norm(surface)
                if len(key) >= MIN_SURFACE_LEN:
                    self._surface.setdefault(key, set()).add(canon)
        alts = sorted((re.escape(s) for s in self._surface), key=len, reverse=True)
        self._rx = re.compile(r"(?<!\w)(?:" + "|".join(alts) + r")(?!\w)") if alts else None

    def match(self, text: str) -> set[str]:
        if self._rx is None:
            return set()
        out: set[str] = set()
        for m in self._rx.finditer(norm(text)):
            out |= self._surface[m.group(0)]
        return out


def video_id_of(url: str) -> Optional[str]:
    m = _VIDEO_RE.search(url or "")
    return m.group(1) if m else None


def okf_vocab(entries: Iterable[Mapping[str, Any]]) -> tuple[set[str], dict[str, set[str]]]:
    """(tag strings exactly as stored, video_id -> titles the OKF lane can emit)."""
    tags: set[str] = set()
    titles: dict[str, set[str]] = {}
    for entry in entries:
        for tag in entry.get("tags") or []:
            if isinstance(tag, str) and tag.strip() and tag.strip().casefold() not in STOP_TERMS:
                tags.add(tag.strip())
        title = str(entry.get("title") or "").strip()
        vid = video_id_of(str(entry.get("source") or ""))
        if title and vid and len(title) <= MAX_TITLE_LEN:
            titles.setdefault(vid, set()).add(title)
    return tags, titles


def graph_entity_vocab(graph: Mapping[str, Any]) -> set[str]:
    """Reachable set: neighbour entity_ids of the seeded concepts, minus people/orgs/videos."""
    out: set[str] = set()
    for neighbours in (graph.get("neighbors") or {}).values():
        for n in neighbours:
            eid = n.get("entity_id")
            if not isinstance(eid, str) or not eid.strip():
                continue
            if EXCLUDED_GRAPH_LABELS & set(n.get("labels") or []):
                continue
            if eid.strip().casefold() in STOP_TERMS:
                continue
            out.add(eid)
    return out


# --------------------------------------------------------------------------- patches


def propose_patch(
    payload: Mapping[str, Any],
    entity_m: Matcher,
    tag_m: Matcher,
    video_titles: Mapping[str, set[str]],
    tu_topics: Mapping[str, Iterable[str]],
) -> dict[str, list[str]]:
    """Additive patch for one child: only non-empty keys, existing values kept (union)."""
    text = str(payload.get("verbatim_text") or "")
    new = {
        "entity_ids": entity_m.match(text),
        "topic_ids": tag_m.match(text) | set(tu_topics.get(str(payload.get("source_span_id")), ())),
        "tags": set(video_titles.get(str(payload.get("video_id")), ())),
    }
    patch: dict[str, list[str]] = {}
    for key in ALLOWED_KEYS:
        merged = {*(payload.get(key) or []), *new[key]}
        if merged:
            patch[key] = sorted(merged)
    return patch


def assert_patch_safe(patch: Mapping[str, Any]) -> None:
    bad = set(patch) - set(ALLOWED_KEYS)
    if bad:
        raise ValueError(f"patch touches non-allowlisted keys: {sorted(bad)}")


def apply_share_cap(
    patches: dict[str, dict[str, list[str]]], total: int, max_share: float
) -> dict[str, int]:
    """Drop (in place) any concept string on more than max_share of all children; return dropped."""
    per_concept: Counter[str] = Counter()
    for patch in patches.values():
        per_concept.update({c for vals in patch.values() for c in vals})
    dropped = {c: n for c, n in per_concept.items() if n > max_share * total}
    if dropped:
        for pid in list(patches):
            slim = {k: [v for v in vals if v not in dropped] for k, vals in patches[pid].items()}
            slim = {k: v for k, v in slim.items() if v}
            if slim:
                patches[pid] = slim
            else:
                del patches[pid]
    return dropped


def drop_terms(patches: dict[str, dict[str, list[str]]], terms: set[str]) -> dict[str, int]:
    """Drop (in place) exact-case generic terms from every patch; return per-term counts."""
    counts: Counter[str] = Counter()
    for pid in list(patches):
        slim: dict[str, list[str]] = {}
        for key, vals in patches[pid].items():
            counts.update(v for v in vals if v in terms)
            kept = [v for v in vals if v not in terms]
            if kept:
                slim[key] = kept
        if slim:
            patches[pid] = slim
        else:
            del patches[pid]
    return dict(counts)


def first_words(text: str, n: int = 10) -> str:
    return " ".join((text or "").split()[:n])


def summarize(
    children: list[dict[str, Any]],
    patches: Mapping[str, Mapping[str, list[str]]],
    dropped: Mapping[str, int],
    max_share: float,
    seed: int = 20261116,
) -> dict[str, Any]:
    total = len(children)
    per_point = [len({c for v in patches.get(ch["id"], {}).values() for c in v}) for ch in children]
    concept_points: Counter[str] = Counter()
    for patch in patches.values():
        concept_points.update({c for vals in patch.values() for c in vals})
    key_cov = {k: sum(1 for p in patches.values() if p.get(k)) for k in ALLOWED_KEYS}
    rng = random.Random(seed)
    samples = [
        {
            "point_id": ch["id"],
            "proposed": dict(patches.get(ch["id"], {})),
            "first_words": first_words(ch["payload"].get("verbatim_text", "")),
        }
        for ch in rng.sample(children, min(20, total))
    ]
    over = {c: n for c, n in concept_points.items() if n > max_share * total}
    return {
        "children": total,
        "coverage_ge1_id": sum(1 for n in per_point if n),
        "coverage_pct": round(100 * sum(1 for n in per_point if n) / total, 2) if total else 0.0,
        "per_key_points": key_cov,
        "ids_per_point": {
            "histogram": dict(sorted(Counter(min(n, 6) for n in per_point).items())),
            "mean": round(statistics.fmean(per_point), 3) if per_point else 0.0,
            "median": statistics.median(per_point) if per_point else 0,
            "max": max(per_point, default=0),
        },
        "distinct_concepts_proposed": len(concept_points),
        "top_concepts": concept_points.most_common(30),
        "max_share": max_share,
        "concepts_over_cap_after_drop": over,
        "concepts_dropped_for_exceeding_cap": dict(sorted(dropped.items(), key=lambda kv: -kv[1])),
        "samples": samples,
    }


# --------------------------------------------------------------------------- apply (gated)


def apply_patches(
    client: Any,
    collection: str,
    patches: Mapping[str, Mapping[str, list[str]]],
    existing: Mapping[str, Mapping[str, Any]],
    *,
    keys: Iterable[str],
    snapshot_confirmed: bool,
    approved_by: str,
) -> int:
    """set_payload on listed keys only. Refuses without snapshot + named approver; additive only."""
    if not snapshot_confirmed:
        raise PermissionError("refusing --apply: pass --snapshot-confirmed after taking a snapshot")
    if not (approved_by or "").strip():
        raise PermissionError("refusing --apply: --approved-by <name> is required")
    keys = tuple(keys)
    if not keys or set(keys) - set(ALLOWED_KEYS):
        raise ValueError(f"--keys must be a non-empty subset of {ALLOWED_KEYS}")
    written = 0
    for pid, patch in patches.items():
        assert_patch_safe(patch)
        body = {k: v for k, v in patch.items() if k in keys and v}
        clobber = [k for k in body if existing.get(pid, {}).get(k)]
        if clobber:
            raise ValueError(f"{pid}: already has non-empty {clobber}; refusing to overwrite")
        if body:
            client.set_payload(collection_name=collection, payload=body, points=[pid], wait=True)
            written += 1
    return written


# --------------------------------------------------------------------------- IO


def make_client(url: str) -> Any:
    from qdrant_client import QdrantClient

    return QdrantClient(url=url, api_key=os.environ.get("QDRANT_API_KEY") or None, timeout=60)


def scroll_children(client: Any, collection: str) -> list[dict[str, Any]]:
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    flt = Filter(
        must=[FieldCondition(key="record_type", match=MatchValue(value=CHILD_RECORD_TYPE))]
    )
    out: list[dict[str, Any]] = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection, scroll_filter=flt, limit=256, offset=offset, with_payload=True
        )
        out.extend({"id": str(p.id), "payload": dict(p.payload or {})} for p in points)
        if offset is None:
            return out


def export_graph_vocab() -> dict[str, Any]:
    """Read-only Cypher. Run inside the backend container (env creds come from app settings)."""
    from neo4j import GraphDatabase

    from app.config import settings
    from rag.kg_expansion import _SEEDED_CONCEPTS, _SEEDED_PRACTICES, _SEEDED_TEACHERS

    tenant = settings.default_tenant_id
    seeds = sorted({*_SEEDED_CONCEPTS, *_SEEDED_PRACTICES, *_SEEDED_TEACHERS})
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    from rag.nodes.utils import DOCTRINE_SYNONYMS

    out: dict[str, Any] = {
        "tenant": tenant,
        "neighbors": {},
        "tu_topic_edges": [],
        "synonyms": {k: list(v) for k, v in DOCTRINE_SYNONYMS.items()},
    }
    with driver.session() as s:
        for seed in seeds:
            rows = s.run(
                "MATCH (n {entity_id: $c})-[r]-(m) "
                "WHERE (r.tenant_id = $t OR r.tenant_id IS NULL) AND m.entity_id IS NOT NULL "
                "AND m.entity_id <> $c RETURN DISTINCT m.entity_id AS entity_id, labels(m) AS labels",
                c=seed,
                t=tenant,
            )
            out["neighbors"][seed] = [r.data() for r in rows]
        out["tu_topic_edges"] = [
            r.data()
            for r in s.run(
                "MATCH (a:TUTeachingUnit)-[:TU_HAS_TOPIC]->(b:TUTopic) "
                "RETURN a.span_id AS span_id, b.name AS topic"
            )
        ]
        out["tu_node_count"] = s.run("MATCH (a:TUTeachingUnit) RETURN count(a) AS c").single()["c"]
    driver.close()
    return out


def build_proposals(
    children: list[dict[str, Any]],
    okf_entries: list[dict[str, Any]],
    graph: Mapping[str, Any],
    synonyms: Mapping[str, list[str]],
    max_share: float,
) -> tuple[dict[str, dict[str, list[str]]], dict[str, int], dict[str, Any]]:
    tags, titles = okf_vocab(okf_entries)
    ents = graph_entity_vocab(graph)
    entity_m = Matcher({e: synonyms.get(e.casefold(), []) for e in ents})
    tag_m = Matcher({t: [] for t in tags})
    tu_topics: dict[str, list[str]] = {}
    for edge in graph.get("tu_topic_edges") or []:
        tu_topics.setdefault(str(edge["span_id"]), []).append(str(edge["topic"]))
    patches: dict[str, dict[str, list[str]]] = {}
    for ch in children:
        patch = propose_patch(ch["payload"], entity_m, tag_m, titles, tu_topics)
        if patch:
            assert_patch_safe(patch)
            patches[ch["id"]] = patch
    dropped = apply_share_cap(patches, len(children), max_share)
    span_ids = {str(c["payload"].get("source_span_id")) for c in children}
    meta = {
        "okf_tag_vocab": len(tags),
        "okf_video_title_videos": len(titles),
        "graph_entity_vocab": len(ents),
        "tu_topic_edges": len(tu_topics),
        "tu_topic_edges_matching_v10_children": sum(1 for s in tu_topics if s in span_ids),
        "tu_node_count": graph.get("tu_node_count"),
    }
    return patches, dropped, meta


# --------------------------------------------------------------------------- simulation


def simulate(
    client: Any,
    collection: str,
    questions: list[dict[str, str]],
    patches: Mapping[str, Mapping[str, list[str]]],
    graph: Mapping[str, Any],
    max_clips: int = 16,
    max_spans: int = 3,
) -> dict[str, Any]:
    """Replay the expansion lanes with the REAL store code; the concept filter is swapped for a
    HasId filter over points whose PROPOSED patch matches the emitted terms. Read-only."""
    from qdrant_client.models import Filter, HasIdCondition

    from rag.kg_expansion import _find_concepts_in_query
    from services.embedding_service import get_embedding_service
    from services.first_person_context_store import FirstPersonContextStore
    from services.first_person_okf_expansion import expand_concepts_via_okf

    class _SimStore(FirstPersonContextStore):
        allowed_ids: Optional[list[str]] = None

        def _query_groups(self, query_dense, *, query_filter, **kw):  # type: ignore[override]
            if self.allowed_ids is not None:
                query_filter = Filter(
                    must=[*(query_filter.must or []), HasIdCondition(has_id=self.allowed_ids)],
                    must_not=query_filter.must_not,
                )
            return super()._query_groups(query_dense, query_filter=query_filter, **kw)

    store = _SimStore(client, collection)
    emb = get_embedding_service()
    value_to_ids: dict[str, set[str]] = {}
    for pid, patch in patches.items():
        for vals in patch.values():
            for v in vals:
                value_to_ids.setdefault(v, set()).add(pid)

    def parents(vec: Mapping[str, Any], allowed: Optional[list[str]], terms: list[str]) -> set[str]:
        store.allowed_ids = allowed
        ctxs = store.retrieve(
            query_dense=vec["dense"],
            query_sparse=vec["sparse"],
            guru_id=None,
            limit_parents=max_clips,
            spans_per_parent=max_spans,
            concept_ids=terms or None,
        )
        return {c.parent.parent_unit_id for c in ctxs}

    rows = []
    for q in questions:
        vec = emb.encode_single_full(q["question"])
        primary = parents(vec, None, [])
        seeds = _find_concepts_in_query(q["question"])
        g_terms = sorted(
            {
                n["entity_id"]
                for s in seeds
                for n in (graph.get("neighbors") or {}).get(s, [])
                if isinstance(n.get("entity_id"), str)
            }
        )
        o_terms = expand_concepts_via_okf(vec["dense"], teacher_id=None)
        gain: dict[str, int] = {}
        for lane, terms in (("graph", g_terms), ("okf", o_terms)):
            ids = sorted({i for t in terms for i in value_to_ids.get(t, ())})
            new = parents(vec, ids, ["x"]) - primary if ids else set()
            gain[lane] = len(new)
        rows.append(
            {
                "id": q["id"],
                "graph_terms": len(g_terms),
                "okf_terms": len(o_terms),
                "primary_parents": len(primary),
                "new_graph": gain["graph"],
                "new_okf": gain["okf"],
            }
        )
    n = len(rows)
    return {
        "questions": n,
        "max_clips": max_clips,
        "max_spans": max_spans,
        "questions_with_graph_terms": sum(1 for r in rows if r["graph_terms"]),
        "questions_with_okf_terms": sum(1 for r in rows if r["okf_terms"]),
        "questions_gaining_via_graph": sum(1 for r in rows if r["new_graph"]),
        "questions_gaining_via_okf": sum(1 for r in rows if r["new_okf"]),
        "questions_gaining_any": sum(1 for r in rows if r["new_graph"] or r["new_okf"]),
        "rows": rows,
    }


def load_questions(path: Path) -> list[dict[str, str]]:
    seen: dict[str, dict[str, str]] = {}
    for line in path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            seen.setdefault(row["question_id"], {"id": row["question_id"], "question": row["question"]})
    return list(seen.values())


# --------------------------------------------------------------------------- CLI


def _self_test() -> None:
    m = Matcher({"Beautiful State": ["beautiful-state"], "Karma": []})
    assert m.match("Living in a BEAUTIFUL   state helps") == {"Beautiful State"}
    assert m.match("karmas and karmic") == set()  # whole word only
    assert m.match("his Karma, truly") == {"Karma"}
    assert Matcher({}).match("anything") == set()
    tags, titles = okf_vocab(
        [{"tags": ["teaching", "ego"], "title": "Ego", "source": "https://www.youtube.com/watch?v=abcdefghijk"}]
    )
    assert tags == {"ego"} and titles == {"abcdefghijk": {"Ego"}}
    graph = {"neighbors": {"Karma": [{"entity_id": "Dharma", "labels": ["base"]}, {"entity_id": "X", "labels": ["Teacher"]}]}}
    assert graph_entity_vocab(graph) == {"Dharma"}
    payload = {"verbatim_text": "Ego and dharma.", "source_span_id": "s", "video_id": "abcdefghijk"}
    patch = propose_patch(payload, Matcher({"Dharma": []}), Matcher({"ego": []}), titles, {"s": ["peace"]})
    assert patch == {"entity_ids": ["Dharma"], "topic_ids": ["ego", "peace"], "tags": ["Ego"]}
    assert_patch_safe(patch)
    try:
        assert_patch_safe({"verbatim_text": "x"})
        raise AssertionError("unsafe patch accepted")
    except ValueError:
        pass
    pats = {str(i): {"topic_ids": ["common"] + ([f"u{i}"] if i < 2 else [])} for i in range(10)}
    assert apply_share_cap(pats, 10, 0.25) == {"common": 10} and set(pats) == {"0", "1"}
    pats = {"a": {"topic_ids": ["x", "State"]}, "b": {"entity_ids": ["State"]}}
    assert drop_terms(pats, {"State"}) == {"State": 2} and pats == {"a": {"topic_ids": ["x"]}}
    try:
        apply_patches(None, "c", {}, {}, keys=ALLOWED_KEYS, snapshot_confirmed=False, approved_by="a")
        raise AssertionError("apply without snapshot accepted")
    except PermissionError:
        pass
    print("enrich_fp_concepts self-test passed")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--export-graph-vocab", action="store_true", help="read-only Memgraph export to stdout (container)")
    ap.add_argument("--graph-vocab", type=Path)
    ap.add_argument("--collection", default=DEFAULT_COLLECTION)
    ap.add_argument("--qdrant-url", default="http://localhost:6333")
    ap.add_argument("--okf", type=Path, default=REPO / "memory/okf/compiled.json")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--max-share", type=float, default=0.25)
    ap.add_argument("--drop-terms", default="", help="comma-separated exact-case generic terms to remove")
    ap.add_argument("--simulate", action="store_true", help="read-only expansion replay (loads BGE-M3 on the host)")
    ap.add_argument("--questions", type=Path, default=REPO / "evals/first_person/negative_controls.jsonl")
    ap.add_argument("--apply", action="store_true", help="WRITES to Qdrant; gated, never run without owner approval")
    ap.add_argument("--patches-file", type=Path, help="reviewed patches JSONL for --apply")
    ap.add_argument("--keys", default=",".join(ALLOWED_KEYS))
    ap.add_argument("--snapshot-confirmed", action="store_true")
    ap.add_argument("--approved-by", default="")
    args = ap.parse_args(argv)

    if args.self_test:
        _self_test()
        return 0
    if args.export_graph_vocab:
        json.dump(export_graph_vocab(), sys.stdout)
        return 0
    if args.apply:
        if not args.patches_file or not args.patches_file.is_file():
            raise SystemExit("--apply needs --patches-file <reviewed patches.jsonl>")
        client = make_client(args.qdrant_url)
        patches = {}
        for line in args.patches_file.read_text().splitlines():
            row = json.loads(line)
            patches[row["point_id"]] = row["set_payload"]
        existing = {c["id"]: c["payload"] for c in scroll_children(client, args.collection)}
        n = apply_patches(
            client, args.collection, patches, existing,
            keys=[k for k in args.keys.split(",") if k],
            snapshot_confirmed=args.snapshot_confirmed, approved_by=args.approved_by,
        )
        print(f"applied {n} patches by {args.approved_by}")
        return 0

    if not args.graph_vocab:
        raise SystemExit("--graph-vocab <file> required (see --export-graph-vocab)")
    graph = json.loads(args.graph_vocab.read_text())
    okf = json.loads(args.okf.read_text())["entries"]
    client = make_client(args.qdrant_url)
    children = scroll_children(client, args.collection)
    patches, dropped, meta = build_proposals(children, okf, graph, graph.get("synonyms") or {}, args.max_share)
    generic = {t for t in args.drop_terms.split(",") if t}
    dropped_generic = drop_terms(patches, generic) if generic else {}
    out = args.out_dir if args.out_dir.is_absolute() else REPO / args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    with (out / "proposed_patches.jsonl").open("w") as fh:  # ids only, no transcript text
        for pid, patch in sorted(patches.items()):
            fh.write(json.dumps({"point_id": pid, "set_payload": patch}, ensure_ascii=False) + "\n")
    summary = summarize(children, patches, dropped, args.max_share)
    summary.update(collection=args.collection, vocab=meta, generic_terms_dropped=dropped_generic, mode="dry-run (nothing written to any store)")
    if args.simulate:
        sim = simulate(client, args.collection, load_questions(args.questions), patches, graph)
        summary["simulation"] = {k: v for k, v in sim.items() if k != "rows"}
        (out / "simulation_rows.json").write_text(json.dumps(sim["rows"], indent=1))
    (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in summary.items() if k not in ("samples",)}, ensure_ascii=False)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
