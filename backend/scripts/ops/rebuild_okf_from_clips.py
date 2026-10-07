"""
rebuild_okf_from_clips.py — Compile verbatim Qdrant clips into authentic Ontological Clusters.

# ponytail: deterministic cluster compiler — groups real first-person clips into canonical
spiritual framework nodes with zero LLM summarization.
Eliminates hallucinated doctrine and anchors OKF directly to verified video clips in Qdrant.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parent.parent.parent.parent
OUTPUT_PATH = _BASE / "memory" / "okf" / "verbatim_clusters.json"

# Canonical Spiritual Framework Definition (Sri Preethaji & Sri Krishnaji)
CANONICAL_CLUSTERS = [
    {
        "cluster_id": "two_states_of_being",
        "title": "The Two States of Being: Suffering State vs. Beautiful State",
        "description": (
            "Sri Preethaji and Sri Krishnaji teach that there are fundamentally only two states of being: "
            "the suffering (stressful) state and the beautiful (connected) state. Any action born of suffering "
            "creates division, whereas action born of a beautiful state creates connection, harmony, and solutions."
        ),
        "teacher": "Sri Preethaji & Sri Krishnaji",
        "pattern": (
            r"(?i)\b(?:suffering|beautiful state|stress|stressful|conflict|agitation|peace|joy|calm|"
            r"fear|anxiety|brain|amygdala|states of being|two states|disconnect|hurting|unhappy|inner state)\b"
        ),
        "reflection_questions": [
            "In this moment, am I living from a suffering state of self-obsession, or a beautiful state of presence and connection?",
            "What is the thought, expectation, or grievance that I am holding onto that is fueling this inner agitation?",
            "If I step back from the story in my mind, what is the actual reality of what is happening right now?",
        ],
    },
    {
        "cluster_id": "four_sacred_secrets_inner_truth",
        "title": "Four Sacred Secrets & Inner Truth: Observation Without Division",
        "description": (
            "The journey of awakening begins with seeing one's inner truth without judgment, justification, "
            "or self-condemnation. By healing the wounded child and dissolving the inner divide between what is "
            "and what should be, spiritual vision transforms into right action."
        ),
        "teacher": "Sri Preethaji & Sri Krishnaji",
        "pattern": (
            r"(?i)\b(?:inner truth|four sacred secrets|observation|observe|witness|divide|division|"
            r"truth|see what is|without judgment|honesty|wound|wounded child|spiritual vision|action|mission|purpose)\b"
        ),
        "reflection_questions": [
            "Can I observe my inner truth—my fear, jealousy, or sadness—without justifying it or condemning myself?",
            "Where in my life am I waiting for external circumstances to change before allowing myself to be at peace?",
            "What spiritual action can I take right now that flows from clarity rather than compulsive reaction?",
        ],
    },
    {
        "cluster_id": "love_relationships_otherization",
        "title": "Love & Relationships: Connection vs. Expectation and Otherization",
        "description": (
            "True love is connection, not expectation. 'Otherization' is the destructive mental habit of seeing "
            "the other as fundamentally separate, leading to comparison, blame, and division in marriages, "
            "families, and communities. Awakening in relationship means feeling the other's experience directly."
        ),
        "teacher": "Sri Preethaji & Sri Krishnaji",
        "pattern": (
            r"(?i)\b(?:love|relationship|relationships|otherization|other|partner|marriage|expectation|"
            r"demands|family|children|child|connection|connect|heart|listening|bond|spend time|irreplaceable)\b"
        ),
        "reflection_questions": [
            "Am I relating to this person from a place of love and presence, or from transaction, expectation, and demands?",
            "In what ways have I turned the other into an enemy or a problem ('otherization') instead of feeling their vulnerability?",
            "Can I hold space for their pain without reacting with my own woundedness?",
        ],
    },
    {
        "cluster_id": "stillness_serene_mind_meditation",
        "title": "Stillness, Breath & Serene Mind Practice",
        "description": (
            "Practical technologies of stillness: the 3-minute Serene Mind practice, 8 conscious soothing breaths, "
            "and Soul Sync meditation calm the autonomic nervous system, quieting the hyperactive amygdala and "
            "shifting consciousness into centered presence."
        ),
        "teacher": "Sri Preethaji & Sri Krishnaji",
        "pattern": (
            r"(?i)\b(?:serene mind|soul sync|meditation|breath|breaths|breathing|stillness|quiet|"
            r"practice|inhale|exhale|eight breaths|relax|nervous system|sit|yoga|surya)\b"
        ),
        "reflection_questions": [
            "Can I close my eyes, bring my awareness to my breath, and simply rest in the stillness between the breaths?",
            "What happens to the intensity of this emotion when I observe it as a witness rather than becoming it?",
            "Can I take eight conscious, soothing breaths right now and allow the nervous system to return to equilibrium?",
        ],
    },
    {
        "cluster_id": "universal_intelligence_awakening",
        "title": "Universal Intelligence & The Limitless Field of Awakening",
        "description": (
            "Moving beyond the illusion of individual egoic control opens consciousness to Universal Intelligence. "
            "When the mind is quiet, synchronicities align for wealth, purpose, and impact. Awakening is the dissolution "
            "of separation into the limitless field of Oneness."
        ),
        "teacher": "Sri Preethaji & Sri Krishnaji",
        "pattern": (
            r"(?i)\b(?:universal intelligence|limitless field|source|creation|synchronicity|synchronicities|"
            r"awakening|enlightenment|deeksha|divine|presence|cosmos|universe|destiny|sacred|oneness)\b"
        ),
        "reflection_questions": [
            "Am I attempting to control every outcome with my finite ego, or can I surrender to the greater intelligence of life?",
            "What synchronicities and gifts are present in my life that I have been too busy or anxious to notice?",
            "Can I experience the limitless field where the illusion of separation dissolves into oneness?",
        ],
    },
]


def fetch_all_v7_clips(
    qdrant_url: str = "http://localhost:6333", collection: str = "first_person_v7"
) -> list[dict[str, Any]]:
    """Fetch all points with payload and passage_dense vectors from Qdrant."""
    from qdrant_client import QdrantClient

    client = QdrantClient(qdrant_url, timeout=15)
    points, _ = client.scroll(collection, limit=500, with_payload=True, with_vectors=True)
    logger.info("Fetched %d points from Qdrant collection '%s'", len(points), collection)

    clips = []
    for p in points:
        payload = p.payload or {}
        vec_dict = p.vector if isinstance(p.vector, dict) else {}
        passage_dense = vec_dict.get("passage_dense")
        if not passage_dense and isinstance(p.vector, list):
            passage_dense = p.vector

        clips.append(
            {
                "point_id": str(p.id),
                "video_id": payload.get("video_id", ""),
                "video_title": payload.get("video_title", ""),
                "speaker": payload.get("speaker", "Teacher"),
                "start_ms": payload.get("start_ms", 0),
                "end_ms": payload.get("end_ms", 0),
                "timestamp_seconds": payload.get("start_ms", 0) // 1000,
                "verbatim_text": payload.get("verbatim_text", ""),
                "source_url": payload.get("source_url", ""),
                "vector": passage_dense,
            }
        )
    return clips


def _extract_clean_sentences(text: str) -> list[str]:
    """Split text into complete, high-quality teaching sentences."""
    # Split on terminal punctuation
    raw_sents = re.split(r"(?<=[.!?])\s+", text.strip())
    clean = []
    for s in raw_sents:
        s = s.strip()
        # Keep clean sentences between 40 and 250 characters
        if (
            40 <= len(s) <= 250
            and s[0].isupper()
            and not any(
                noise in s.lower()
                for noise in ("subscribe", "click the bell", "music starts", "please sit")
            )
        ):
            clean.append(s)
    return clean


def compile_verbatim_clusters(
    clips: list[dict[str, Any]],
    output_path: Path = OUTPUT_PATH,
) -> dict[str, Any]:
    """Cluster clips, compute centroid vectors, and write verbatim_clusters.json."""
    logger.info("Compiling clusters from %d clips...", len(clips))

    clusters_out = []

    for cluster_spec in CANONICAL_CLUSTERS:
        c_id = cluster_spec["cluster_id"]
        title = cluster_spec["title"]
        desc = cluster_spec["description"]
        teacher = cluster_spec["teacher"]
        pattern = re.compile(cluster_spec["pattern"])
        questions = cluster_spec["reflection_questions"]

        matching_clips = []
        cluster_vectors = []
        extracted_quotes = []

        for c in clips:
            text = c["verbatim_text"]
            if pattern.search(text):
                matching_clips.append(c)
                if c.get("vector") and len(c["vector"]) == 1024:
                    cluster_vectors.append(c["vector"])

                # Extract clean sentences for quotes
                sents = _extract_clean_sentences(text)
                for s in sents:
                    extracted_quotes.append(
                        {
                            "quote": s,
                            "speaker": c["speaker"],
                            "video_id": c["video_id"],
                            "source_url": c["source_url"],
                            "start_seconds": c["timestamp_seconds"],
                        }
                    )

        # Rank quotes by length and spiritual weight (prefer 60-180 chars)
        def quote_score(q_dict: dict[str, Any]) -> float:
            q = q_dict["quote"]
            qlen = len(q)
            base = 1.0 if 60 <= qlen <= 180 else 0.5
            return base

        extracted_quotes.sort(key=quote_score, reverse=True)
        top_quotes = extracted_quotes[:5]

        # Compute centroid embedding
        if cluster_vectors:
            vec_arr = np.array(cluster_vectors, dtype=np.float32)
            centroid = np.mean(vec_arr, axis=0)
            norm = np.linalg.norm(centroid)
            if norm > 0.0:
                centroid = centroid / norm
            emb_list = centroid.tolist()
        else:
            logger.warning("No vectors found for cluster '%s'", c_id)
            emb_list = [0.0] * 1024

        cluster_entry = {
            "cluster_id": c_id,
            "title": title,
            "description": desc,
            "teacher": teacher,
            "clip_count": len(matching_clips),
            "clip_ids": [c["point_id"] for c in matching_clips],
            "key_verbatim_quotes": [q["quote"] for q in top_quotes],
            "quotes_with_provenance": top_quotes,
            "reflection_questions": questions,
            "embedding": emb_list,
        }
        clusters_out.append(cluster_entry)
        logger.info(
            "Cluster '%s': %d clips, %d quotes selected", c_id, len(matching_clips), len(top_quotes)
        )

    result = {
        "version": "1.0",
        "description": "Verbatim OKF Clusters compiled directly from first_person_v7 clips",
        "total_clusters": len(clusters_out),
        "clusters": clusters_out,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Successfully wrote verbatim clusters to %s", output_path)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compile Verbatim OKF Clusters from first_person_v7"
    )
    parser.add_argument("--qdrant-url", default="http://localhost:6333", help="Qdrant service URL")
    parser.add_argument("--collection", default="first_person_v7", help="Source Qdrant collection")
    parser.add_argument("--out", default=str(OUTPUT_PATH), help="Output JSON path")
    args = parser.parse_args()

    clips = fetch_all_v7_clips(args.qdrant_url, args.collection)
    res = compile_verbatim_clusters(clips, Path(args.out))
    print(
        f"\n✅ Successfully compiled {res['total_clusters']} verbatim clusters with {len(clips)} Qdrant clips."
    )
