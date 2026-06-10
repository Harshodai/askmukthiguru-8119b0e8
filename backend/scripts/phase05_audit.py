import asyncio
import logging
import os
import sys

# Setup paths and logger
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Phase0.5Audit")

from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.config import settings
from services.embedding_service import EmbeddingService


async def main():
    print("====================================================")
    print("PHASE 0.5 DIAGNOSTICS & VERIFICATION PROBES")
    print("====================================================")

    # --------------------------------------------------
    # Probe A: Embedding Model Identity & Payload Prefix
    # --------------------------------------------------
    print("\n--- PROBE A: Embedding Model Identity & Payload Prefix ---")
    print(f"Configured embedding model: {settings.embedding_model}")
    
    embedder = EmbeddingService()
    # Trigger lazy load
    print("Loading models (this might take a few seconds)...")
    embedder._ensure_models()
    
    encoder = embedder._encoder
    print(f"Loaded encoder class: {encoder.__class__.__name__}")
    
    # Try to inspect model paths or names
    if hasattr(encoder, "model"):
        model_name = getattr(encoder.model, "model_name_or_path", "unknown")
        print(f"Underlying encoder model_name_or_path: {model_name}")
    else:
        print("Encoder does not have 'model' attribute.")

    # Spot-check payload for instruction prefix
    qdrant_url = "http://localhost:6333"
    client = QdrantClient(url=qdrant_url)
    collection_name = "spiritual_wisdom"
    
    print(f"Scrolling 3 points from '{collection_name}'...")
    try:
        points, _ = client.scroll(
            collection_name=collection_name,
            limit=3,
            with_payload=True,
            with_vectors=True
        )
        for idx, p in enumerate(points):
            text = p.payload.get("text", "")
            print(f"\nPoint {idx + 1} Payload (first 150 chars):")
            print(repr(text[:150]))
            
            # Check if E5 prefix is prepended in payload text
            e5_prefix = "Given a spiritual teaching, retrieve relevant passages: "
            if text.startswith(e5_prefix):
                print(f"⚠️ FOUND E5 PREFIX in payload text: {repr(e5_prefix)}")
            else:
                print("No E5 prefix found in payload text.")
                
            # Check dense vector size
            if isinstance(p.vector, dict) and "dense" in p.vector:
                print(f"Dense vector dimension: {len(p.vector['dense'])}")
            elif isinstance(p.vector, list):
                print(f"Vector dimension: {len(p.vector)}")
    except Exception as e:
        print(f"Error scrolling points: {e}")

    # --------------------------------------------------
    # Probe B: Sparse Vector Audit on spiritual_wisdom
    # --------------------------------------------------
    print("\n--- PROBE B: Sparse Vector Audit ---")
    try:
        # Let's scroll points with vectors to see if sparse vectors are populated
        points, _ = client.scroll(
            collection_name=collection_name,
            limit=100,
            with_vectors=True
        )
        non_empty_sparse_count = 0
        empty_sparse_count = 0
        no_sparse_vector_field = 0
        
        for p in points:
            if isinstance(p.vector, dict):
                sparse = p.vector.get("sparse")
                if sparse is not None:
                    # check indices/values count
                    indices = getattr(sparse, "indices", None) or sparse.get("indices", [])
                    if len(indices) > 0:
                        non_empty_sparse_count += 1
                    else:
                        empty_sparse_count += 1
                else:
                    no_sparse_vector_field += 1
            else:
                no_sparse_vector_field += 1
                
        print("Checked 100 points:")
        print(f"  - Non-empty sparse vectors: {non_empty_sparse_count}")
        print(f"  - Empty sparse vectors: {empty_sparse_count}")
        print(f"  - Points with no sparse vector field: {no_sparse_vector_field}")
    except Exception as e:
        print(f"Error auditing sparse vectors: {e}")

    # --------------------------------------------------
    # Probe C: Corpus Coverage of canonical terms
    # --------------------------------------------------
    print("\n--- PROBE C: Corpus Coverage ---")
    terms = ["Deeksha", "Sri Preethaji", "Sri Krishnaji", "Ekam", "Four Sacred Secrets", "Manifest", "Oneness"]
    for term in terms:
        try:
            # Search using MatchText condition
            res = client.scroll(
                collection_name=collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="text",
                            match=models.MatchText(text=term)
                        )
                    ]
                ),
                limit=1,
                with_payload=False
            )
            count = len(res[0])
            # To get approximate total counts, let's do a search with limit=100
            res_all = client.scroll(
                collection_name=collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="text",
                            match=models.MatchText(text=term)
                        )
                    ]
                ),
                limit=100,
                with_payload=False
            )
            total_matches = len(res_all[0])
            suffix = "+" if total_matches == 100 else ""
            print(f"Term '{term}': {total_matches}{suffix} chunks match")
        except Exception as e:
            print(f"Error scrolling for term '{term}': {e}")

    # --------------------------------------------------
    # Probe D: LightRAG Routing and Service Check
    # --------------------------------------------------
    print("\n--- PROBE D: LightRAG Routing and Service Check ---")
    try:
        from services.lightrag_service import LightRAGService
        print("Initializing LightRAGService...")
        lightrag = LightRAGService()
        print("LightRAG initialized. Directory: data/lightrag")
        # Check if the directories exist
        if os.path.exists("data/lightrag"):
            print("LightRAG directory exists: data/lightrag")
            print("Files in LightRAG directory:")
            print(os.listdir("data/lightrag"))
        else:
            print("⚠️ LightRAG directory does NOT exist: data/lightrag")
    except Exception as e:
        print(f"Error checking LightRAG: {e}")

if __name__ == "__main__":
    asyncio.run(main())
