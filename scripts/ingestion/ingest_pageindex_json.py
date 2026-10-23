import asyncio
import json
import os
import sys

# Add the project root to the python path so we can import backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from services.embeddings import EmbeddingsService
from services.qdrant_service import QdrantService


def extract_nodes_from_pageindex(tree, current_level=1, cluster_id=None):
    """
    Recursively extracts nodes from a PageIndex structure.
    Leaf nodes become Level 0.
    Parent nodes become Level 1 (Summary Nodes).
    """
    summary_nodes = []
    leaf_nodes = []

    for node in tree:
        node_id = node.get("node_id", "unknown")
        title = node.get("title", "Untitled")
        text = node.get("text", "")
        summary = node.get("summary", node.get("prefix_summary", ""))
        children = node.get("nodes", [])

        # If no cluster_id is passed, this is a top-level node. Give it a new cluster_id based on node_id
        current_cluster_id = cluster_id if cluster_id else hash(node_id) % 100000

        if not children:
            # It's a leaf node -> Level 0
            if text:
                leaf_nodes.append(
                    {
                        "text": text,
                        "metadata": {
                            "source_url": "pageindex_document",
                            "title": title,
                            "content_type": "chunk",
                            "chunk_index": current_cluster_id,  # using cluster_id as a grouping key
                            "raptor_level": 0,
                            "cluster_id": current_cluster_id,
                            "node_id": node_id,
                        },
                    }
                )
        else:
            # It's a parent node -> Level 1 (Summary)
            if summary or text:
                summary_content = (
                    summary if summary else text[:1000]
                )  # Use text as fallback summary
                summary_nodes.append(
                    {
                        "text": summary_content,
                        "metadata": {
                            "source_url": "pageindex_document",
                            "title": title,
                            "content_type": "summary",
                            "chunk_index": current_cluster_id,
                            "raptor_level": 1,
                            "cluster_id": current_cluster_id,
                            "topic_label": title,
                            "node_id": node_id,
                        },
                    }
                )

            # Recursively process children
            child_summaries, child_leaves = extract_nodes_from_pageindex(
                children, current_level=0, cluster_id=current_cluster_id
            )
            summary_nodes.extend(child_summaries)
            leaf_nodes.extend(child_leaves)

    return summary_nodes, leaf_nodes


async def main():
    if len(sys.argv) < 2:
        print("Usage: python ingest_pageindex_json.py <path_to_structure.json>")
        return

    json_path = os.path.abspath(sys.argv[1])
    if not os.path.exists(json_path):
        print(f"File not found: {json_path}")
        return

    print(f"Reading PageIndex JSON from {json_path}...")
    with open(json_path, encoding="utf-8") as f:
        tree = json.load(f)

    summary_nodes, leaf_nodes = extract_nodes_from_pageindex(tree)

    print(f"Extracted {len(leaf_nodes)} leaf chunks and {len(summary_nodes)} summary nodes.")

    print("Initializing Qdrant and Embeddings...")
    qdrant = QdrantService()
    qdrant.init_collection()
    embeddings = EmbeddingsService()

    batch_size = 50
    # Upsert Level 0 (Leaf chunks)
    if leaf_nodes:
        print("Upserting Level 0 (Leaf) chunks...")
        for i in range(0, len(leaf_nodes), batch_size):
            batch = leaf_nodes[i : i + batch_size]
            texts = [item["text"] for item in batch]
            metadatas = [item["metadata"] for item in batch]
            vectors = await embeddings.aembed_documents(texts)
            qdrant.upsert_chunks(texts=texts, vectors=vectors, metadatas=metadatas)
            print(f"  Upserted {i + len(batch)} / {len(leaf_nodes)}")

    # Upsert Level 1 (Summary nodes)
    if summary_nodes:
        print("Upserting Level 1 (Summary) nodes...")
        for i in range(0, len(summary_nodes), batch_size):
            batch = summary_nodes[i : i + batch_size]
            texts = [item["text"] for item in batch]
            metadatas = [item["metadata"] for item in batch]
            vectors = await embeddings.aembed_documents(texts)
            qdrant.upsert_chunks(texts=texts, vectors=vectors, metadatas=metadatas)
            print(f"  Upserted {i + len(batch)} / {len(summary_nodes)}")

    print("Ingestion complete!")


if __name__ == "__main__":
    asyncio.run(main())
