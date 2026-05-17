#!/usr/bin/env python3
"""
Ingest pre-extracted PageIndex structure JSON into Qdrant.
Run inside Docker: docker exec mukthiguru-backend python3 scripts/ingest_structure_to_qdrant.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from app.config import settings
from services.qdrant_service import QdrantService
from services.embedding_service import EmbeddingService


def flatten_tree_for_ingestion(nodes, parent_title="", cluster_id=1):
    """Recursively flatten the tree structure into chunk items for Qdrant."""
    chunks = []

    for node in nodes:
        title = node.get("title", "")
        context_title = f"{parent_title} > {title}" if parent_title and title else (title or parent_title)

        text = node.get("text", "").strip()
        summary = node.get("summary", "").strip()

        if text:
            chunks.append({
                "text": text,
                "metadata": {
                    "source_url": "The_Four_Sacred_Secrets.pdf",
                    "title": context_title,
                    "content_type": "book",
                    "raptor_level": 0,
                    "cluster_id": cluster_id,
                    "node_id": node.get("node_id", ""),
                    "page_range": f"{node.get('start_index', '?')}-{node.get('end_index', '?')}"
                }
            })

        if summary:
            chunks.append({
                "text": summary,
                "metadata": {
                    "source_url": "The_Four_Sacred_Secrets.pdf",
                    "title": f"Summary: {context_title}",
                    "content_type": "summary",
                    "raptor_level": 1,
                    "cluster_id": cluster_id,
                    "node_id": node.get("node_id", "")
                }
            })

        if "nodes" in node and node["nodes"]:
            children_chunks = flatten_tree_for_ingestion(
                node["nodes"],
                parent_title=context_title,
                cluster_id=cluster_id
            )
            chunks.extend(children_chunks)

        cluster_id += 1

    return chunks


def main():
    structure_path = os.path.join(os.path.dirname(__file__), "..", "..", "results", "The_Four_Sacred_Secrets_structure.json")
    if not os.path.isfile(structure_path):
        print(f"❌ Structure file not found: {structure_path}")
        sys.exit(1)

    print(f"📖 Loading structure from: {structure_path}")
    with open(structure_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    tree = data.get("structure", [])
    print(f"   Tree has {len(tree)} root nodes")

    # Flatten
    chunks = flatten_tree_for_ingestion(tree)
    print(f"📦 Total chunks for ingestion: {len(chunks)}")

    # Init services
    print("\nInitializing Qdrant and Embedding services...")
    qdrant = QdrantService()
    qdrant.init_collection()
    embeddings = EmbeddingService()

    # Assign sequential chunk indices
    for i, chunk in enumerate(chunks):
        chunk["metadata"]["chunk_index"] = i

    print(f"Ingesting {len(chunks)} chunks into Qdrant...")

    batch_size = 20
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        texts = [item["text"] for item in batch]
        metadatas = [item["metadata"] for item in batch]

        encoded = embeddings.encode_batch(texts)
        dense_vectors = encoded["dense"]
        sparse_vectors = encoded["sparse"]

        qdrant.upsert_chunks(
            texts=texts,
            vectors=dense_vectors,
            metadatas=metadatas,
            sparse_vectors=sparse_vectors,
        )
        print(f"  Upserted {i + len(batch)} / {len(chunks)} chunks...")

    print("✅ Ingestion complete!")


if __name__ == "__main__":
    main()
