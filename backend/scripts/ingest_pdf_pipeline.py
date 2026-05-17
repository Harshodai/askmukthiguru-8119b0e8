#!/usr/bin/env python3
"""
Mukthi Guru — PDF Ingestion via Unified Pipeline (LightRAG enabled)
===================================================================
Ingests The_Four_Sacred_Secrets.pdf using the IngestionPipeline so it 
runs through both dense embeddings (Qdrant) and graph extraction (LightRAG).

Usage (run inside Docker backend container):
    python3 scripts/ingestion/ingest_pdf_pipeline.py
"""

import sys
import os
import asyncio
import time

# Add backend to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from app.dependencies import get_container

async def main():
    start_time = time.time()
    
    print("=" * 70)
    print("Mukthi Guru — PDF Pipeline Ingestion (LightRAG enabled)")
    print("=" * 70)

    print("\nInitializing Service Container...")
    container = get_container()
    pipeline = container.ingestion

    pdf_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "The_Four_Sacred_Secrets.pdf"))
    
    if not os.path.exists(pdf_path):
        print(f"❌ Error: Could not find PDF at {pdf_path}")
        return

    print(f"\n📋 Starting ingestion of {os.path.basename(pdf_path)}...")
    
    # We use max_accuracy=True so it builds hierarchical chunks, RAPTOR tree, and LightRAG graph
    try:
        result = await pipeline.ingest_file(
            file_path=pdf_path,
            max_accuracy=True,
            on_progress=lambda msg, pct: print(f"  [{pct*100:3.0f}%] {msg}")
        )
        
        status = result.get("status", "unknown")
        chunks = result.get("chunks_indexed", 0)
        summaries = result.get("summaries_created", 0)
        
        print(f"\n✅ Ingestion Complete: {status}")
        print(f"  Chunks Indexed: {chunks}")
        print(f"  RAPTOR Summaries: {summaries}")
        
    except Exception as e:
        print(f"\n❌ Ingestion Failed: {type(e).__name__}: {e}")

    elapsed = time.time() - start_time
    print(f"\n{'='*70}")
    print(f"Elapsed time: {elapsed/60:.1f} minutes")
    print(f"{'='*70}")

if __name__ == "__main__":
    asyncio.run(main())
