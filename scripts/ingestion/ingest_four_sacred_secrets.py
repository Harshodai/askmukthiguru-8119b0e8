"""
Ingest The Four Sacred Secrets (PageIndex Structure) into Qdrant vector database.

Uses the backend's EmbeddingService (bge-m3) for dense+sparse vectors
and QdrantService for hybrid search storage.

Usage:
    export PYTHONPATH=$(pwd)/backend
    backend/.venv/bin/python scripts/ingest_four_sacred_secrets.py
"""

import json
import os
import sys

# Add backend to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter
from services.embedding_service import EmbeddingService
from services.qdrant_service import QdrantService


def flatten_tree(nodes, parent_title="", level=0, cluster_id=1):
    """Recursively flatten the PageIndex tree structure into chunk items."""
    chunks = []

    # Initialize child text splitter for parent-child hierarchical chunking
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=50,
        length_function=len,
    )

    for node in nodes:
        # Build context-aware title
        title = node.get("title", "")
        if parent_title and title:
            context_title = f"{parent_title} > {title}"
        else:
            context_title = title or parent_title

        # Create chunk for current node text
        text = node.get("text", "").strip()
        summary = node.get("summary", "").strip()

        # If there's meaningful text, create child paragraph chunks linked to this parent text
        if text:
            parent_id = str(uuid.uuid4())
            child_paragraphs = child_splitter.split_text(text)

            # Prepend contextual header for UI provenance
            header = f"[Source: The_Four_Sacred_Secrets.pdf | Chapter: {context_title}]\n"

            for child_index, child_text in enumerate(child_paragraphs):
                chunks.append(
                    {
                        "text": header + child_text,
                        "metadata": {
                            "source_url": "The_Four_Sacred_Secrets.pdf",
                            "title": context_title,
                            "speaker": "Sri Preethaji & Sri Krishnaji",
                            "topic": "Spiritual",
                            "content_type": "book",
                            "raptor_level": 0,
                            "cluster_id": cluster_id,
                            "node_id": node.get("node_id", ""),
                            "page_range": f"{node.get('start_index', '?')}-{node.get('end_index', '?')}",
                            "parent_id": parent_id,
                            "parent_text": text,
                            "is_child": True,
                        },
                    }
                )

        # If there's a summary, add it as a Level 1 (Summary) chunk (no parent-child mapping needed)
        if summary:
            header = f"[Source: The_Four_Sacred_Secrets.pdf | Chapter Summary: {context_title}]\n"
            chunks.append(
                {
                    "text": header + summary,
                    "metadata": {
                        "source_url": "The_Four_Sacred_Secrets.pdf",
                        "title": f"Summary: {context_title}",
                        "speaker": "Sri Preethaji & Sri Krishnaji",
                        "topic": "Spiritual",
                        "content_type": "summary",
                        "raptor_level": 1,
                        "cluster_id": cluster_id,
                        "node_id": node.get("node_id", ""),
                    },
                }
            )

        # Recurse into children
        if "nodes" in node and node["nodes"]:
            children_chunks = flatten_tree(
                node["nodes"],
                parent_title=context_title,
                level=level + 1,
                cluster_id=cluster_id,
            )
            chunks.extend(children_chunks)

        cluster_id += 1

    return chunks


def main():
    json_path = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "results",
            "The_Four_Sacred_Secrets_structure.json",
        )
    )
    if not os.path.exists(json_path):
        print(f"Error: JSON structure not found at {json_path}")
        print("Please run 'bash run_pageindex_sarvam.sh' first to generate the structure.")
        return

    print("Initializing Qdrant and Embeddings...")
    qdrant = QdrantService()
    qdrant.init_collection()
    embeddings = EmbeddingService()

    print(f"Loading PageIndex structure from {json_path}...")
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    structure = data.get("structure", [])
    if not structure:
        print("Error: No 'structure' array found in JSON.")
        return

    print("Flattening tree structure into ingestible chunks...")
    all_chunks = flatten_tree(structure)

    # Assign sequential chunk indices
    for i, chunk in enumerate(all_chunks):
        chunk["metadata"]["chunk_index"] = i

    print(f"Extracted {len(all_chunks)} total chunks (text and summaries).")

    # Upsert chunks in batches
    batch_size = 20
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i : i + batch_size]
        texts = [item["text"] for item in batch]
        metadatas = [item["metadata"] for item in batch]

        # bge-m3 encode_batch returns {dense: [...], sparse: [...]}
        encoded = embeddings.encode_batch(texts)
        dense_vectors = encoded["dense"]
        sparse_vectors = encoded["sparse"]

        qdrant.upsert_chunks(
            texts=texts,
            vectors=dense_vectors,
            metadatas=metadatas,
            sparse_vectors=sparse_vectors,
        )
        print(f"  Upserted {i + len(batch)} / {len(all_chunks)} chunks...")

    print("Ingestion complete!")


if __name__ == "__main__":
    main()
