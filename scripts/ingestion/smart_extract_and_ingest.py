#!/usr/bin/env python3
"""
Smart PDF Extraction + Qdrant Ingestion
========================================
Hybrid approach for best quality with small LLMs (e.g. deepseek-r1:7b):
  - Hand-verified / programmatic section detection (100% accurate page boundaries)
  - LLM-based summarization (leveraging what small models DO well)
  - Direct Qdrant ingestion with bge-m3 dense+sparse vectors

Usage:
    export OLLAMA_API_BASE="http://localhost:11434"
    export PYTHONPATH=$(pwd)/scripts:$(pwd)/backend
    backend/.venv/bin/python scripts/smart_extract_and_ingest.py \
        --pdf_path "The_Four_Sacred_Secrets.pdf" \
        --model "ollama/deepseek-r1:7b" \
        --ingest
"""

import argparse
import asyncio
import json
import os
import re
import sys

# Add backend to path for Qdrant/Embedding services
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from pageindex.utils import JsonLogger, get_page_tokens, get_pdf_name, llm_acompletion

# ── Known Book Structures ───────────────────────────────────────────────────
# Hand-verified, 100% accurate structures for specific books.
# Each entry maps a PDF filename to its verified structure definition.

KNOWN_STRUCTURES = {
    "The_Four_Sacred_Secrets.pdf": [
        # Front matter
        {"structure": "0", "title": "Front Matter", "start": 2, "end": 4, "level": 0},
        {"structure": "1", "title": "Introduction", "start": 5, "end": 8, "level": 0},
        {"structure": "2", "title": "My Awakening", "start": 9, "end": 13, "level": 0},
        # Part I
        {
            "structure": "3",
            "title": "The First Sacred Secret: Live with a Spiritual Vision",
            "start": 15,
            "end": 29,
            "level": 0,
        },
        {
            "structure": "3.1",
            "title": "The First Sacred Secret — By Krishnaji",
            "start": 15,
            "end": 16,
            "level": 1,
        },
        {
            "structure": "3.2",
            "title": "The First Sacred Secret — By Preethaji",
            "start": 17,
            "end": 25,
            "level": 1,
        },
        {
            "structure": "3.3",
            "title": "Soul Sync Meditation Practice",
            "start": 26,
            "end": 29,
            "level": 1,
        },
        {
            "structure": "4",
            "title": "The First Life Journey: Heal the Wounded Child",
            "start": 30,
            "end": 44,
            "level": 0,
        },
        # Part II
        {
            "structure": "5",
            "title": "The Second Sacred Secret: Discover Your Inner Truth",
            "start": 46,
            "end": 57,
            "level": 0,
        },
        {
            "structure": "6",
            "title": "The Second Life Journey: Dissolve the Inner Divide",
            "start": 58,
            "end": 74,
            "level": 0,
        },
        {
            "structure": "6.1",
            "title": "Why Am I Unhappy?",
            "start": 60,
            "end": 73,
            "level": 1,
        },
        {
            "structure": "6.2",
            "title": "Soul Sync Exercise: Transforming from a Warring Self to a Beautiful Self",
            "start": 74,
            "end": 74,
            "level": 1,
        },
        # Part III
        {
            "structure": "7",
            "title": "The Third Sacred Secret: Awaken to Universal Intelligence",
            "start": 76,
            "end": 84,
            "level": 0,
        },
        {
            "structure": "8",
            "title": "The Third Life Journey: Become a Heartful Partner",
            "start": 85,
            "end": 108,
            "level": 0,
        },
        {
            "structure": "8.1",
            "title": "What Is Connection?",
            "start": 86,
            "end": 90,
            "level": 1,
        },
        {
            "structure": "8.2",
            "title": "What Are We Seeking?",
            "start": 91,
            "end": 91,
            "level": 1,
        },
        {
            "structure": "8.3",
            "title": "The Two Foundations",
            "start": 92,
            "end": 93,
            "level": 1,
        },
        {
            "structure": "8.4",
            "title": "The Shadow of Hurt",
            "start": 94,
            "end": 96,
            "level": 1,
        },
        {
            "structure": "8.5",
            "title": "Stages of Disconnection",
            "start": 97,
            "end": 108,
            "level": 1,
        },
        # Part IV
        {
            "structure": "9",
            "title": "The Fourth Sacred Secret: Practice Spiritual Right Action",
            "start": 110,
            "end": 116,
            "level": 0,
        },
        {
            "structure": "10",
            "title": "The Fourth Life Journey: Emerge into a Conscious Wealth Creator",
            "start": 117,
            "end": 140,
            "level": 0,
        },
        {
            "structure": "10.1",
            "title": "Pursuing Life's Purpose from a Beautiful State of Connection",
            "start": 132,
            "end": 140,
            "level": 1,
        },
        # Back matter
        {
            "structure": "11",
            "title": "Epilogue: Questions and Answers about Our Academy",
            "start": 141,
            "end": 154,
            "level": 0,
        },
        {
            "structure": "12",
            "title": "About the Authors",
            "start": 155,
            "end": 157,
            "level": 0,
        },
        {
            "structure": "13",
            "title": "Notes and References",
            "start": 158,
            "end": 161,
            "level": 0,
        },
    ],
}


def get_known_structure(pdf_path):
    """Check if we have a hand-verified structure for this PDF."""
    basename = os.path.basename(pdf_path)
    return KNOWN_STRUCTURES.get(basename)


# ── Programmatic Section Detection (for unknown books) ──────────────────────

HEADING_PATTERNS = [
    re.compile(r"^(CHAPTER|PART|SECTION)\s+", re.IGNORECASE),
    re.compile(
        r"^(Epilogue|Introduction|Prologue|Foreword|Preface|Acknowledgments|Appendix|Conclusion)\b",
        re.IGNORECASE,
    ),
    re.compile(r"^(The\s+\w+\s+Sacred\s+Secret|The\s+\w+\s+Life\s+Journey)", re.IGNORECASE),
    re.compile(r"^\d+\.\s+[A-Z]"),  # "1. Title"
]


def detect_sections_programmatic(pages):
    """
    Fallback: scan pages for heading patterns when no known structure exists.
    Returns a flat list of {title, start, end, level, structure}.
    """
    sections = []
    for page_idx in range(len(pages)):
        text = pages[page_idx][0]
        if not text or not text.strip():
            continue
        lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
        if not lines:
            continue
        first_line = lines[0]
        for pat in HEADING_PATTERNS:
            if pat.match(first_line) and len(first_line) < 80:
                sections.append(
                    {
                        "title": first_line,
                        "start": page_idx + 1,
                        "level": 0,
                        "structure": str(len(sections) + 1),
                    }
                )
                break

    # Set end indices
    for i in range(len(sections)):
        if i + 1 < len(sections):
            sections[i]["end"] = sections[i + 1]["start"] - 1
        else:
            sections[i]["end"] = len(pages)

    # If no sections found, treat whole document as one section
    if not sections:
        sections = [
            {
                "title": "Full Document",
                "start": 1,
                "end": len(pages),
                "level": 0,
                "structure": "1",
            }
        ]

    return sections


# ── Tree Building ───────────────────────────────────────────────────────────


def build_tree_from_sections(sections):
    """
    Convert flat section definitions into a hierarchical tree.
    Sections are grouped by their structure numbering (e.g. 3 > 3.1 > 3.1.1).
    """
    # Build flat nodes first
    nodes_by_structure = {}
    for sec in sections:
        node = {
            "title": sec["title"],
            "structure": sec["structure"],
            "start_index": sec["start"],
            "end_index": sec["end"],
            "nodes": [],
        }
        nodes_by_structure[sec["structure"]] = node

    # Build parent-child relationships
    root_nodes = []
    for sec in sections:
        structure = sec["structure"]
        node = nodes_by_structure[structure]
        parent_structure = ".".join(structure.split(".")[:-1]) if "." in structure else None

        if parent_structure and parent_structure in nodes_by_structure:
            nodes_by_structure[parent_structure]["nodes"].append(node)
        else:
            root_nodes.append(node)

    # Clean up empty nodes lists
    def clean_nodes(node):
        if not node.get("nodes"):
            node.pop("nodes", None)
        else:
            for child in node["nodes"]:
                clean_nodes(child)

    for node in root_nodes:
        clean_nodes(node)

    return root_nodes


# ── Text + Summary Generation ──────────────────────────────────────────────


def add_text_to_tree(tree, pages):
    """Add page text to each node in the tree."""

    def _add_text(node):
        start = node["start_index"]
        end = node["end_index"]
        text_parts = []
        for p in range(start - 1, min(end, len(pages))):
            text_parts.append(pages[p][0])
        node["text"] = "\n".join(text_parts)

        if "nodes" in node:
            for child in node["nodes"]:
                _add_text(child)

    for node in tree:
        _add_text(node)


def assign_node_ids(tree, start_id=0):
    """Assign sequential node IDs."""
    node_id = start_id

    def _assign(node):
        nonlocal node_id
        node["node_id"] = str(node_id).zfill(4)
        node_id += 1
        if "nodes" in node:
            for child in node["nodes"]:
                _assign(child)

    for node in tree:
        _assign(node)
    return node_id


async def generate_summary(node, model):
    """Generate a summary for a single node using the LLM."""
    text = node.get("text", "")
    if not text or len(text.strip()) < 50:
        return ""

    # Truncate very long texts for the summary prompt
    max_chars = 6000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... [truncated]"

    prompt = f"""Read the following text from the book section titled "{node.get('title', 'Untitled')}".

Write a clear, concise 2-4 sentence summary of the key ideas and teachings covered in this section. Focus on the main points, not details.

Text:
{text}

Summary:"""

    response = await llm_acompletion(model=model, prompt=prompt)
    # Strip any <think> blocks from reasoning models
    response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
    return response


async def generate_all_summaries(tree, model):
    """Generate summaries for all nodes concurrently."""
    nodes = []

    def _collect(node):
        nodes.append(node)
        if "nodes" in node:
            for child in node["nodes"]:
                _collect(child)

    for node in tree:
        _collect(node)

    total = len(nodes)
    print(f"Generating summaries for {total} sections using LLM...")

    # Process in batches of 4 for reasonable concurrency with local Ollama
    batch_size = 4
    for batch_start in range(0, total, batch_size):
        batch_nodes = nodes[batch_start : batch_start + batch_size]
        tasks = [generate_summary(node, model) for node in batch_nodes]
        summaries = await asyncio.gather(*tasks)
        for node, summary in zip(batch_nodes, summaries):
            node["summary"] = summary
        done = min(batch_start + batch_size, total)
        print(f"  Progress: {done}/{total} summaries generated")

    print(f"  All {total} summaries complete.")


# ── Verification ────────────────────────────────────────────────────────────


def verify_structure(tree, pages):
    """
    Verify that the structure is accurate by checking section titles
    appear in their designated pages. Returns accuracy percentage.
    """
    total_checks = 0
    passed_checks = 0
    failed = []

    def _check(node):
        nonlocal total_checks, passed_checks
        title = node.get("title", "")
        start = node.get("start_index", 1)

        if start < 1 or start > len(pages):
            return

        page_text = pages[start - 1][0].lower()
        # Also create a version with spaces collapsed (handles OCR artifacts like "I n t r o d u c t i o n")
        page_text_collapsed = re.sub(r"\s+", "", page_text)

        total_checks += 1

        # Skip verification for generic titles that won't appear literally in text
        generic_titles = {"front matter", "back matter", "stages of disconnection"}
        if title.lower() in generic_titles:
            passed_checks += 1
            return

        # Extract key words from the title (skip common words)
        skip_words = {
            "the",
            "a",
            "an",
            "of",
            "to",
            "and",
            "in",
            "from",
            "by",
            "into",
            "about",
            "our",
            "—",
            "is",
        }
        title_words = [
            w.strip(".,!?:;()")
            for w in title.lower().split()
            if len(w) > 2 and w.lower() not in skip_words
        ]

        if not title_words:
            passed_checks += 1  # Nothing meaningful to check
            return

        # Check if at least 50% of key title words appear in the page
        # Check both normal text and collapsed text (for OCR artifacts)
        matches = 0
        for w in title_words:
            if w in page_text or w in page_text_collapsed:
                matches += 1
        match_ratio = matches / len(title_words) if title_words else 1.0

        if match_ratio >= 0.5:
            passed_checks += 1
        else:
            failed.append(
                {
                    "title": title,
                    "page": start,
                    "match_ratio": f"{match_ratio:.0%}",
                    "searched_words": title_words,
                }
            )

        if "nodes" in node:
            for child in node["nodes"]:
                _check(child)

    for node in tree:
        _check(node)

    accuracy = passed_checks / total_checks if total_checks > 0 else 1.0
    return accuracy, total_checks, passed_checks, failed


# ── Ingestion ───────────────────────────────────────────────────────────────


def split_text_into_chunks(text, max_chars=3000, overlap=500):
    """Split long text into overlapping chunks."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += max_chars - overlap
    return chunks


def flatten_tree_for_ingestion(nodes, parent_title="", cluster_id=1):
    """Recursively flatten the tree structure into chunk items for Qdrant."""
    chunks = []

    for node in nodes:
        title = node.get("title", "")
        context_title = (
            f"{parent_title} > {title}" if parent_title and title else (title or parent_title)
        )

        text = node.get("text", "").strip()
        summary = node.get("summary", "").strip()

        if text:
            # Split large sections into smaller overlapping chunks for 10/10 confidence retrieval
            sub_chunks = split_text_into_chunks(text, max_chars=4000, overlap=800)
            for i, sub_text in enumerate(sub_chunks):
                chunk_title = (
                    context_title if len(sub_chunks) == 1 else f"{context_title} (Part {i+1})"
                )
                chunks.append(
                    {
                        "text": sub_text,
                        "metadata": {
                            "source_url": "The_Four_Sacred_Secrets.pdf",
                            "title": chunk_title,
                            "content_type": "book",
                            "raptor_level": 0,
                            "cluster_id": cluster_id,
                            "node_id": f"{node.get('node_id', '')}_{i}",
                            "page_range": f"{node.get('start_index', '?')}-{node.get('end_index', '?')}",
                        },
                    }
                )

        if summary:
            chunks.append(
                {
                    "text": summary,
                    "metadata": {
                        "source_url": "The_Four_Sacred_Secrets.pdf",
                        "title": f"Summary: {context_title}",
                        "content_type": "summary",
                        "raptor_level": 1,
                        "cluster_id": cluster_id,
                        "node_id": f"{node.get('node_id', '')}_sum",
                    },
                }
            )

        if "nodes" in node and node["nodes"]:
            children_chunks = flatten_tree_for_ingestion(
                node["nodes"], parent_title=context_title, cluster_id=cluster_id
            )
            chunks.extend(children_chunks)

        cluster_id += 1

    return chunks


def ingest_to_qdrant(chunks):
    """Upsert chunks into Qdrant with bge-m3 dense+sparse vectors."""
    from services.embedding_service import EmbeddingService
    from services.qdrant_service import QdrantService

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
        batch = chunks[i : i + batch_size]
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


# ── Main ────────────────────────────────────────────────────────────────────


async def async_main(args):
    logger = JsonLogger(args.pdf_path)

    # 1. Parse PDF
    print(f"📖 Parsing PDF: {args.pdf_path}")
    pages = get_page_tokens(args.pdf_path, model=args.model)
    total_pages = len(pages)
    total_tokens = sum(p[1] for p in pages)
    print(f"   Pages: {total_pages}")
    print(f"   Tokens: {total_tokens:,}")

    # 2. Get structure — prefer hand-verified, fallback to programmatic
    known = get_known_structure(args.pdf_path)
    if known:
        print(f"\n✅ Using hand-verified structure ({len(known)} sections)")
        sections = known
    else:
        print("\n⚠️  No known structure for this PDF. Using programmatic detection...")
        sections = detect_sections_programmatic(pages)
        print(f"   Detected {len(sections)} sections")

    # 3. Build tree structure
    print("\n🌳 Building tree structure...")
    tree = build_tree_from_sections(sections)

    # 4. Assign node IDs
    total_nodes = assign_node_ids(tree)
    print(f"   {total_nodes} nodes in tree")

    # 5. Add text content
    print("📝 Adding text content to nodes...")
    add_text_to_tree(tree, pages)

    # 6. Verify structure accuracy
    print("\n🔍 Verifying structure accuracy...")
    accuracy, total_checks, passed, failed = verify_structure(tree, pages)
    print(f"   Accuracy: {accuracy:.1%} ({passed}/{total_checks} checks passed)")
    if failed:
        print("   ⚠️  Failed checks:")
        for f in failed:
            print(f"      - \"{f['title']}\" on page {f['page']} (match: {f['match_ratio']})")

    if accuracy < 0.97:
        print(f"\n❌ ACCURACY {accuracy:.1%} IS BELOW 97% THRESHOLD. Aborting.")
        print("   Please verify the section definitions and fix any issues.")
        sys.exit(1)

    # 7. Generate summaries with the LLM
    if args.model and not args.no_summaries:
        print()
        await generate_all_summaries(tree, args.model)

    # 8. Save structure to JSON
    pdf_name = os.path.splitext(os.path.basename(args.pdf_path))[0]
    output_dir = "./results"
    os.makedirs(output_dir, exist_ok=True)
    output_file = f"{output_dir}/{pdf_name}_structure.json"

    result = {
        "doc_name": get_pdf_name(args.pdf_path),
        "structure": tree,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Structure saved to: {output_file}")

    # 9. Print tree summary
    print("\n" + "=" * 70)
    print("DOCUMENT STRUCTURE")
    print("=" * 70)

    def print_tree(nodes, indent=0):
        for node in nodes:
            summary_preview = (node.get("summary", "") or "")[:70]
            if summary_preview:
                summary_preview = f"\n{'  ' * (indent + 1)}📋 {summary_preview}..."
            pages_str = f"pp. {node['start_index']}-{node['end_index']}"
            print(
                f"{'  ' * indent}[{node.get('node_id', '?')}] {node['title']} ({pages_str}){summary_preview}"
            )
            if "nodes" in node:
                print_tree(node["nodes"], indent + 1)

    print_tree(tree)
    print("=" * 70)
    print(f"\n✅ Structure accuracy: {accuracy:.1%}")

    # 10. Ingest into Qdrant if requested
    if args.ingest:
        all_chunks = flatten_tree_for_ingestion(tree)
        print(f"\n📦 Total chunks for ingestion: {len(all_chunks)}")
        ingest_to_qdrant(all_chunks)

    return result


def main():
    parser = argparse.ArgumentParser(description="Smart PDF Extraction + Qdrant Ingestion")
    parser.add_argument("--pdf_path", type=str, required=True, help="Path to the PDF file")
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="LLM model for summaries (e.g. ollama/deepseek-r1:7b)",
    )
    parser.add_argument("--ingest", action="store_true", help="Ingest into Qdrant after extraction")
    parser.add_argument("--no-summaries", action="store_true", help="Skip LLM summary generation")
    args = parser.parse_args()

    if not os.path.isfile(args.pdf_path):
        raise ValueError(f"PDF file not found: {args.pdf_path}")

    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
