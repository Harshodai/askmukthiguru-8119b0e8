"""Knowledge graph analytics and export utilities.

Computes network statistics with networkx and optionally exports an interactive
D3Blocks HTML file. This module has no side effects and no Neo4j dependency.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

import networkx as nx

logger = logging.getLogger(__name__)


# Default analytics config
_MAX_NODES_FOR_HITS = 500  # HITS is O(N^2) per iteration; skip for huge graphs
_MAX_NODES_FOR_CLOSENESS = 1000  # closeness is all-pairs shortest path
_MAX_NODES_FOR_EXACT_BETWEENNESS = (
    2000  # exact betweenness is O(N^3); use k-sample approx above this
)


def _as_undirected(graph: dict[str, Any]) -> nx.Graph:
    """Build an undirected NetworkX graph from {nodes, edges}."""
    g = nx.Graph()
    for n in graph.get("nodes", []):
        nid = n.get("id")
        if nid:
            g.add_node(nid, **n)
    for e in graph.get("edges", []):
        src = e.get("source")
        dst = e.get("target")
        if src and dst and src != dst:
            g.add_edge(src, dst, **e)
    return g


def _as_directed(graph: dict[str, Any]) -> nx.DiGraph:
    """Build a directed NetworkX graph from {nodes, edges} (for HITS)."""
    g = nx.DiGraph()
    for n in graph.get("nodes", []):
        nid = n.get("id")
        if nid:
            g.add_node(nid, **n)
    for e in graph.get("edges", []):
        src = e.get("source")
        dst = e.get("target")
        if src and dst and src != dst:
            g.add_edge(src, dst, **e)
    return g


def _attach_analytics(
    graph: dict[str, Any],
    g: nx.Graph,
    directed_g: nx.DiGraph | None = None,
    compute_hits: bool = True,
    compute_closeness: bool = True,
) -> dict[str, Any]:
    """Return a new graph dict with analytics attached to each node.

    Uses the undirected ``g`` for community detection, centrality, and
    PageRank.  Uses ``directed_g`` (when provided) for HITS so the
    hub/authority decomposition respects distinct source→target roles.
    """
    if len(g.nodes) == 0:
        return graph

    degree = dict(g.degree)
    if len(g.nodes) > _MAX_NODES_FOR_EXACT_BETWEENNESS:
        sample_k = min(500, len(g.nodes))
        betweenness = nx.betweenness_centrality(g, k=sample_k, seed=42)
    else:
        betweenness = nx.betweenness_centrality(g)
    pagerank = nx.pagerank(g, weight="weight" if nx.is_weighted(g) else None)

    closeness: dict[str, float] = {}
    if compute_closeness:
        try:
            closeness = nx.closeness_centrality(g)
        except Exception as e:
            logger.warning(f"Closeness centrality failed: {e}")

    hubs: dict[str, float] = {}
    authorities: dict[str, float] = {}
    if compute_hits:
        try:
            hits_g = directed_g if directed_g is not None else g
            hubs, authorities = nx.hits(hits_g)
        except Exception as e:
            logger.warning(f"HITS failed: {e}")

    communities: list[set[str]] = []
    try:
        communities = nx.community.louvain_communities(g, seed=42)
    except Exception as e:
        logger.warning(f"Louvain community detection failed: {e}")
    community_map: dict[str, int] = {}
    for idx, comm in enumerate(communities):
        for nid in comm:
            community_map[nid] = idx

    node_by_id = {n["id"]: n for n in graph.get("nodes", [])}
    for nid in node_by_id:
        node_by_id[nid]["analytics"] = {
            "degree": degree.get(nid, 0),
            "betweenness": round(betweenness.get(nid, 0.0), 6),
            "closeness": round(closeness.get(nid, 0.0), 6) if closeness else 0.0,
            "pagerank": round(pagerank.get(nid, 0.0), 6),
            "hits_hub": round(hubs.get(nid, 0.0), 6) if hubs else 0.0,
            "hits_authority": round(authorities.get(nid, 0.0), 6) if authorities else 0.0,
        }
        node_by_id[nid]["community"] = community_map.get(nid, -1)

    return graph


def enrich_graph(
    graph: dict[str, Any],
    enabled: bool = True,
    max_nodes_for_hits: int = _MAX_NODES_FOR_HITS,
    max_nodes_for_closeness: int = _MAX_NODES_FOR_CLOSENESS,
) -> dict[str, Any]:
    """Attach network analytics to each node in the graph.

    Args:
        graph: Dict with ``nodes`` and ``edges``.
        enabled: If False, return the graph unchanged.
        max_nodes_for_hits: Skip HITS above this node count (perf guard).
        max_nodes_for_closeness: Skip closeness above this node count.

    Returns:
        The same dict reference with ``analytics`` and ``community`` added.
        Errors are logged and swallowed; the graph is returned unchanged on
        failure.
    """
    if not enabled or not graph:
        return graph

    try:
        g = _as_undirected(graph)
        dg = _as_directed(graph)
        return _attach_analytics(
            graph,
            g,
            directed_g=dg,
            compute_hits=len(g.nodes) <= max_nodes_for_hits,
            compute_closeness=len(g.nodes) <= max_nodes_for_closeness,
        )
    except Exception as e:
        logger.warning(f"Knowledge graph analytics failed: {e}")
        return graph


def export_d3blocks_html(graph: dict[str, Any], title: str = "Wisdom Map") -> str:
    """Generate a standalone interactive HTML file from the graph.

    Args:
        graph: Dict with ``nodes`` and ``edges``. Nodes should have ``label``;
            ``type`` and ``community`` are used for color if present.
        title: Title embedded in the HTML page.

    Returns:
        HTML string.

    Raises:
        ImportError: If ``d3blocks`` is not installed.
        ValueError: If the graph has no nodes or malformed edges.
    """
    try:
        from d3blocks import D3Blocks
    except ImportError as e:
        raise ImportError(
            "d3blocks is required for HTML export. Install: pip install d3blocks>=1.4.0"
        ) from e

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if not nodes:
        raise ValueError("Cannot export an empty graph")

    import pandas as pd

    # D3Blocks d3graph expects source/target/weight columns
    edge_rows = []
    for e in edges:
        src = e.get("source")
        dst = e.get("target")
        if src and dst and src != dst:
            edge_rows.append({"source": src, "target": dst, "weight": 1})
    df_edges = pd.DataFrame(edge_rows)

    if df_edges.empty:
        # D3Blocks requires at least one edge; add a self-loop placeholder
        df_edges = pd.DataFrame([{"source": nodes[0]["id"], "target": nodes[0]["id"], "weight": 1}])

    # color nodes by community if available, otherwise by type
    if "community" in pd.DataFrame(nodes).columns:
        color_map = {}
        for n in nodes:
            c = n.get("community")
            if c is not None:
                color_map[n["id"]] = int(c)
        node_color = [color_map.get(n["id"], 0) for n in nodes]
    else:
        type_color = {"Teacher": 1, "Concept": 2, "Practice": 3, "Memory": 4, "User": 5}
        node_color = [type_color.get(n.get("type"), 0) for n in nodes]

    import matplotlib as mpl

    cmap = mpl.colormaps["tab10"]
    hex_colors = [mpl.colors.rgb2hex(cmap(c % 10)[:3]) for c in node_color]

    sizes = [n.get("analytics", {}).get("degree", 1) + 1 for n in nodes]
    node_labels = [n.get("label", n["id"]) for n in nodes]

    # Create the temp file before calling d3graph so that D3Blocks writes
    # directly to our path rather than a default 'd3graph.html' in the cwd
    # or system temp directory.
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as tmp:
        tmp_path = tmp.name

    d3 = D3Blocks()

    if df_edges.empty:
        df_edges = pd.DataFrame([{"source": nodes[0]["id"], "target": nodes[0]["id"], "weight": 1}])

    # Process edges — pass our temp path so d3blocks never writes a stray default file.
    d3.d3graph(df_edges, showfig=False, filepath=tmp_path)

    # Build color/size/label arrays in adjacency-matrix column order
    adj_nodes = list(d3.D3graph.adjmat.columns)
    nid_to_idx = {n["id"]: i for i, n in enumerate(nodes)}
    labels_ordered = [
        node_labels[nid_to_idx[nid]] if nid in nid_to_idx else nid for nid in adj_nodes
    ]
    colors_ordered = [
        hex_colors[nid_to_idx[nid]] if nid in nid_to_idx else "#000080" for nid in adj_nodes
    ]
    sizes_ordered = [sizes[nid_to_idx[nid]] if nid in nid_to_idx else 5 for nid in adj_nodes]

    d3.D3graph.set_node_properties(
        label=labels_ordered,
        color=colors_ordered,
        size=sizes_ordered,
    )

    # Register any isolated nodes missing from the edge-derived node set
    for i, n in enumerate(nodes):
        nid = n["id"]
        if nid not in d3.D3graph.node_properties:
            d3.D3graph.node_properties[nid] = {
                "label": node_labels[i],
                "color": hex_colors[i],
                "size": sizes[i],
                "edge_size": 0.1,
            }

    try:
        d3.D3graph.show(
            filepath=tmp_path,
            title=title,
            showfig=False,
            dark_mode=True,
            show_controls=True,
        )
        with open(tmp_path, encoding="utf-8") as f:
            html = f.read()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    return html


if __name__ == "__main__":
    g = {
        "nodes": [
            {"id": "a", "label": "A", "type": "Concept"},
            {"id": "b", "label": "B", "type": "Concept"},
            {"id": "c", "label": "C", "type": "Concept"},
        ],
        "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
    }
    enriched = enrich_graph(g)
    print("Enriched nodes:", enriched["nodes"])
