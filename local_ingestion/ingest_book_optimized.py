#!/usr/bin/env python3
"""
Optimized Book Ingestion Pipeline
=================================
Processes 'The Four Sacred Secrets' (or other structured PDFs) leveraging:
1. Accurate PageIndex hierarchy detection
2. DeepSeek Proposition Splitting (semantic, independent chunks)
3. LightRAG Neo4j Entity Extraction (GraphRAG)
4. Dense + Sparse Qdrant Upsertion
"""

import asyncio
import logging
import os
import sys

# Setup Paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))  # For pageindex module

# Must set environment BEFORE importing dependencies which loads config
from dotenv import load_dotenv

load_dotenv(os.path.join(BASE_DIR, "backend", ".env"))

os.environ["LLM_PROVIDER"] = "ollama"
os.environ["OLLAMA_MODEL"] = "deepseek-r1:7b"
os.environ["SARVAM_API_KEY"] = "none"
os.environ["NEO4J_URI"] = "bolt://localhost:7687"
os.environ["QDRANT_URL"] = "http://localhost:6333"
if "REDIS_URL" not in os.environ:
    raise RuntimeError("REDIS_URL env var is required")

from app.dependencies import get_container

from scripts.smart_extract_and_ingest import (
    add_text_to_tree,
    assign_node_ids,
    build_tree_from_sections,
    detect_sections_programmatic,
    get_known_structure,
    get_page_tokens,
    verify_structure,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("book_optimized")


async def optimize_and_ingest(pdf_path: str, model: str = "ollama/deepseek-r1:7b"):
    logger.info(f"🚀 Starting Optimized Ingestion for: {pdf_path}")

    # 1. Parse PDF Structure
    pages = get_page_tokens(pdf_path, model=model)
    known = get_known_structure(pdf_path)
    sections = known if known else detect_sections_programmatic(pages)

    tree = build_tree_from_sections(sections)
    assign_node_ids(tree)
    add_text_to_tree(tree, pages)

    accuracy, _, _, _ = verify_structure(tree, pages)
    logger.info(f"✅ Structure Accuracy: {accuracy:.1%}")

    # 2. Initialize Container Services
    logger.info("Initializing Backend Services...")
    container = get_container()

    # Disable GPTCache for ingestion to prevent FAISS dimension errors
    from langchain.globals import set_llm_cache

    set_llm_cache(None)

    pipeline = container.ingestion
    lightrag = container.lightrag
    splitter = pipeline._proposition_split  # Using the existing Proposition Splitter from pipeline

    # 3. Extract text sections for processing
    flat_sections = []

    def _flatten(node, parent_title=""):
        title = node.get("title", "")
        context_title = (
            f"{parent_title} > {title}" if parent_title and title else (title or parent_title)
        )

        text = node.get("text", "").strip()
        if text:
            flat_sections.append(
                {
                    "title": context_title,
                    "text": text,
                    "node_id": node.get("node_id", ""),
                    "page_range": f"{node.get('start_index', '?')}-{node.get('end_index', '?')}",
                }
            )

        if "nodes" in node:
            for child in node["nodes"]:
                _flatten(child, context_title)

    for root_node in tree:
        _flatten(root_node)
    logger.info(f"Found {len(flat_sections)} structural sections.")

    total_chunks = 0
    # 4. Process each section
    for idx, section in enumerate(flat_sections):
        logger.info(
            f"\n--- Processing Section {idx+1}/{len(flat_sections)}: {section['title']} ---"
        )
        raw_text = section["text"]

        # A. Proposition Splitting (DeepSeek)
        logger.info("🧠 Generating Propositions (DeepSeek)...")
        # pipeline._proposition_split takes a chunk and returns propositions. We might need to pre-chunk raw_text if it's too long
        # Using basic chunking first if section is huge
        max_chars = 3000
        raw_chunks = [raw_text[i : i + max_chars] for i in range(0, len(raw_text), max_chars)]

        propositions = []
        for rc in raw_chunks:
            try:
                props = await splitter(rc)
                propositions.extend(props)
            except Exception as e:
                logger.error(f"Proposition splitting failed, falling back to raw: {e}")
                propositions.append(rc)

        logger.info(f"✨ Extracted {len(propositions)} propositions.")

        # B. Qdrant Ingestion (Vector Database)
        logger.info("📥 Ingesting to Qdrant...")
        count = pipeline._embed_and_index(
            propositions,
            source_url=os.path.basename(pdf_path),
            title=section["title"],
            speaker="Sri Preethaji & Sri Krishnaji",
            topic="The Four Sacred Secrets",
            content_type="book",
        )
        total_chunks += count

        # C. Neo4j Knowledge Graph Extraction (LightRAG)
        if lightrag:
            logger.info("🕸️ Extracting Graph Entities into Neo4j (DeepSeek)...")
            try:
                await lightrag.ainsert(raw_text)
            except Exception as e:
                logger.error(f"Graph extraction failed for section: {e}")

    logger.info(
        f"\n🎉 Optimized Book Ingestion Complete! Total semantic chunks indexed: {total_chunks}"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf_path", default="The_Four_Sacred_Secrets.pdf")
    args = parser.parse_args()

    os.environ["LLM_PROVIDER"] = "ollama"
    os.environ["OLLAMA_MODEL"] = "deepseek-r1:7b"
    os.environ["SARVAM_API_KEY"] = "none"

    asyncio.run(optimize_and_ingest(args.pdf_path))
