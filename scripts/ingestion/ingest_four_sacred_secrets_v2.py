"""
Enhanced Ingestion for The Four Sacred Secrets (PageIndex & Doctrinal Structure).

Ingests high-resolution paragraph chunks, chapter-level deep summaries, and master
foundational concept nodes into Qdrant vector database (spiritual_wisdom_contextual).

Enforces:
- Domain rights: licensed / rights_cleared=True
- Chunker version: boundary_v1:hierarchical
- Full enumeration of the 4 Sacred Secrets and 4 Life Journeys
- Soul Sync and Serene Mind practice preservation

Usage:
    export PYTHONPATH=$(pwd)/backend
    backend/.venv/bin/python scripts/ingestion/ingest_four_sacred_secrets_v2.py
"""

import os
import sys
import uuid
import json
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from langchain_text_splitters import RecursiveCharacterTextSplitter
from services.embedding_service import EmbeddingService
from services.qdrant_service import QdrantService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BOOK_CANONICAL_URL = "https://www.amazon.in/Four-Sacred-Secrets-Prosperity-Beautiful/dp/1846046319"

MASTER_OVERVIEW_CHUNKS = [
    {
        "title": "The Four Sacred Secrets — Master Overview of the Four Secrets & Four Life Journeys",
        "text": (
            "[Source: The Four Sacred Secrets | Master Doctrinal Synthesis]\n"
            "The Four Sacred Secrets is the landmark book authored by Sri Preethaji and Sri Krishnaji, "
            "founders of Ekam and O&O Academy. The book outlines a revolutionary journey in human consciousness "
            "from a 'Suffering State' (a state of stress, anxiety, separation, self-obsession, and inner conflict) "
            "into a 'Beautiful State' (a state of connection, peace, compassion, joy, and oneness with life).\n\n"
            "The teachings are structured into Four Sacred Secrets and Four Life Journeys:\n\n"
            "1. THE FIRST SACRED SECRET: LIVE WITH A SPIRITUAL VISION (authored by Sri Krishnaji)\n"
            "   - Core Teaching: Every experience in life arises from either a suffering state or a beautiful state. "
            "Living with a spiritual vision means taking absolute responsibility for your inner state, choosing to "
            "live in a beautiful state regardless of external circumstances.\n"
            "   - Practice: The Soul Sync Meditation Practice.\n\n"
            "2. THE SECOND SACRED SECRET: DISCOVER YOUR INNER TRUTH (authored by Sri Preethaji)\n"
            "   - Core Teaching: Recognizing the truth of your inner state without self-deception, guilt, or conflict. "
            "True transformation and greatness begin when you confront and observe your emotional truths with radical honesty.\n"
            "   - Associated Journey: The Second Life Journey: Dissolve the Inner Divide.\n\n"
            "3. THE THIRD SACRED SECRET: AWAKEN TO UNIVERSAL INTELLIGENCE (authored by Sri Preethaji)\n"
            "   - Core Teaching: Humanity is part of a vast, interconnected field of Universal Intelligence and Consciousness. "
            "When we move beyond isolation and fear, we tap into intuitive intelligence that guides our lives and relationships.\n"
            "   - Associated Journey: The Third Life Journey: Become a Heartful Partner.\n\n"
            "4. THE FOURTH SACRED SECRET: PRACTICE SPIRITUAL RIGHT ACTION (authored by Sri Krishnaji)\n"
            "   - Core Teaching: Spiritual right action is action born out of connection and love, never from turmoil, "
            "reaction, or inner division. Always dissolve inner turmoil before taking outer action.\n"
            "   - Associated Journey: The Fourth Life Journey: Emerge into a Conscious Wealth Creator."
        ),
        "metadata": {
            "source_url": BOOK_CANONICAL_URL,
            "title": "The Four Sacred Secrets — Master Overview of the Four Secrets & Four Life Journeys",
            "speaker": "Sri Preethaji & Sri Krishnaji",
            "topic": "Spiritual",
            "content_type": "concept_summary",
            "raptor_level": 2,
            "domain_rights_status": "licensed",
            "rights_cleared": True,
            "chunker_version": "boundary_v1:hierarchical",
            "teacher_id": "sri-preethaji-krishnaji",
            "teacher_ids": ["sri-preethaji", "sri-krishnaji"],
            "tags": ["four sacred secrets", "ekam", "suffering state", "beautiful state", "soul sync", "spiritual vision"],
        }
    },
    {
        "title": "The Four Life Journeys in The Four Sacred Secrets",
        "text": (
            "[Source: The Four Sacred Secrets | The Four Life Journeys]\n"
            "In The Four Sacred Secrets by Sri Preethaji and Sri Krishnaji, alongside the Four Sacred Secrets, "
            "the authors guide the reader through Four Essential Life Journeys:\n\n"
            "1. THE FIRST LIFE JOURNEY: HEAL THE WOUNDED CHILD\n"
            "   - Healing the foundational emotional wounds, feelings of unworthiness, rejection, and childhood conditioning "
            "that silently dictate adult relationships and emotional suffering.\n\n"
            "2. THE SECOND LIFE JOURNEY: DISSOLVE THE INNER DIVIDE\n"
            "   - Overcoming the warring self and self-hatred. Moving from inner conflict, judgment, and self-punishment "
            "into self-acceptance, inner peace, and harmonious wholeness.\n\n"
            "3. THE THIRD LIFE JOURNEY: BECOME A HEARTFUL PARTNER\n"
            "   - Transforming intimate relationships and marriages. Moving through the shadow of hurt, dissolving expectations, "
            "and establishing deep emotional connection and listening without judgment.\n\n"
            "4. THE FOURTH LIFE JOURNEY: EMERGE INTO A CONSCIOUS WEALTH CREATOR\n"
            "   - Moving away from wealth creation driven by greed, fear, or comparison. Creating wealth and impact "
            "as a spiritual contribution from a state of connection, abundance, and service to society."
        ),
        "metadata": {
            "source_url": BOOK_CANONICAL_URL,
            "title": "The Four Life Journeys in The Four Sacred Secrets",
            "speaker": "Sri Preethaji & Sri Krishnaji",
            "topic": "Spiritual",
            "content_type": "concept_summary",
            "raptor_level": 2,
            "domain_rights_status": "licensed",
            "rights_cleared": True,
            "chunker_version": "boundary_v1:hierarchical",
            "teacher_id": "sri-preethaji-krishnaji",
            "teacher_ids": ["sri-preethaji", "sri-krishnaji"],
            "tags": ["four life journeys", "heal wounded child", "heartful partner", "conscious wealth creator", "inner divide"],
        }
    }
]

def build_book_chunks(structure: list[dict]) -> list[dict]:
    """Build high-resolution child chunks and chapter summaries."""
    chunks = list(MASTER_OVERVIEW_CHUNKS)

    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=900,
        chunk_overlap=150,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""]
    )

    BOILERPLATE_TITLES = {"Front Matter", "Notes and References"}

    def traverse(nodes, parent_title="", level=0):
        for node in nodes:
            title = node.get("title", "")
            if title in BOILERPLATE_TITLES:
                continue

            context_title = f"{parent_title} > {title}" if parent_title and title else (title or parent_title)
            text = node.get("text", "").strip()
            summary = node.get("summary", "").strip()

            # Determine speaker from context
            lower_ctx = context_title.lower()
            if "by krishnaji" in lower_ctx:
                speaker = "Sri Krishnaji"
                teacher_id = "sri-krishnaji"
            elif "by preethaji" in lower_ctx:
                speaker = "Sri Preethaji"
                teacher_id = "sri-preethaji"
            else:
                speaker = "Sri Preethaji & Sri Krishnaji"
                teacher_id = "sri-preethaji-krishnaji"

            # 1. Chapter Summary Chunk (Raptor Level 1)
            if summary and len(summary) > 80:
                header = f"[Source: The Four Sacred Secrets | Chapter Summary: {context_title}]\n"
                chunks.append({
                    "text": header + summary,
                    "metadata": {
                        "source_url": BOOK_CANONICAL_URL,
                        "title": f"Summary: The Four Sacred Secrets — {context_title}",
                        "speaker": speaker,
                        "topic": "Spiritual",
                        "content_type": "summary",
                        "raptor_level": 1,
                        "domain_rights_status": "licensed",
                        "rights_cleared": True,
                        "chunker_version": "boundary_v1:hierarchical",
                        "teacher_id": teacher_id,
                        "teacher_ids": ["sri-preethaji", "sri-krishnaji"],
                        "chapter_title": context_title,
                    }
                })

            # 2. Detailed Paragraph Chunks (Raptor Level 0)
            if text and len(text) > 100:
                parent_id = str(uuid.uuid4())
                split_texts = child_splitter.split_text(text)
                header = f"[Source: The Four Sacred Secrets | {context_title}]\n"

                for child_text in split_texts:
                    chunks.append({
                        "text": header + child_text,
                        "metadata": {
                            "source_url": BOOK_CANONICAL_URL,
                            "title": f"The Four Sacred Secrets — {context_title}",
                            "speaker": speaker,
                            "topic": "Spiritual",
                            "content_type": "book",
                            "raptor_level": 0,
                            "parent_id": parent_id,
                            "domain_rights_status": "licensed",
                            "rights_cleared": True,
                            "chunker_version": "boundary_v1:hierarchical",
                            "teacher_id": teacher_id,
                            "teacher_ids": ["sri-preethaji", "sri-krishnaji"],
                            "chapter_title": context_title,
                        }
                    })

            # Recurse into children
            if "nodes" in node and node["nodes"]:
                traverse(node["nodes"], parent_title=context_title, level=level + 1)

    traverse(structure)
    return chunks

def main():
    candidate_paths = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend", "data", "book", "The_Four_Sacred_Secrets_structure.json")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "evals", "results", "The_Four_Sacred_Secrets_structure.json")),
    ]
    json_path = next((p for p in candidate_paths if os.path.exists(p)), None)
    if not json_path:
        logger.error(f"Book structure file not found in: {candidate_paths}")
        sys.exit(1)

    logger.info(f"Loading PageIndex structure from {json_path}...")
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    structure = data.get("structure", [])
    chunks = build_book_chunks(structure)
    logger.info(f"Built {len(chunks)} high-resolution book chunks (including master summaries).")

    # Set chunk_index sequentially
    for i, c in enumerate(chunks):
        c["metadata"]["chunk_index"] = i

    logger.info("Initializing Qdrant and Embedding services...")
    os.environ["QDRANT_URL"] = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant = QdrantService()
    embeddings = EmbeddingService()

    # First delete existing book chunks from spiritual_wisdom_contextual to prevent duplicates
    logger.info("Cleaning up old book chunks from spiritual_wisdom_contextual...")
    try:
        from qdrant_client.http import models as rest
        qdrant.get_client().delete(
            collection_name="spiritual_wisdom_contextual",
            points_selector=rest.FilterSelector(
                filter=rest.Filter(
                    must=[
                        rest.FieldCondition(
                            key="source_url",
                            match=rest.MatchValue(value=BOOK_CANONICAL_URL)
                        )
                    ]
                )
            ),
            wait=True
        )
        logger.info("Deleted previous book chunks successfully.")
    except Exception as e:
        logger.warning(f"Could not delete old book chunks: {e}")

    # Upsert in batches of 25
    batch_size = 25
    total = len(chunks)
    logger.info(f"Upserting {total} chunks in batches of {batch_size}...")

    for i in range(0, total, batch_size):
        batch = chunks[i : i + batch_size]
        texts = [b["text"] for b in batch]
        metadatas = [b["metadata"] for b in batch]

        encoded = embeddings.encode_batch(texts)
        dense_vectors = encoded["dense"]
        sparse_vectors = encoded["sparse"]

        qdrant.upsert_chunks(
            texts=texts,
            vectors=dense_vectors,
            metadatas=metadatas,
            sparse_vectors=sparse_vectors,
        )
        logger.info(f"  Upserted {min(i + batch_size, total)} / {total} chunks...")

    logger.info("The Four Sacred Secrets ingestion completed successfully!")

if __name__ == "__main__":
    main()
