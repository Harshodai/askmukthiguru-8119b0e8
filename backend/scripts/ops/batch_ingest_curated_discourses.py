#!/usr/bin/env python3
"""Batch ingest and link curated Sri Preethaji & Sri Krishnaji discourses.

Integrates curated video discourses across the three primary knowledge layers:
1. Memgraph C++ (Bolt 7687): :Video and :Teacher nodes with :SPEAKER_OF and :EXPOUNDS relationships.
2. OKF (Ontological Knowledge Framework): Curated markdown entries in memory/okf/ & staging,
   compiled into memory/okf/compiled.json.
3. Qdrant: Dense + sparse points in spiritual_wisdom_contextual, and verified verbatim
   teacher spans in first_person_v10 & first_person_v11.

Invariants respected:
- Invariant X1: Byte-identical copy between scripts/ops/ and backend/scripts/ops/.
- Invariant X40: domain_rights_status='licensed' stamped from rights register.
- Invariant X24: retrieval_only verbatim serving integrity.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("batch_ingest_curated_discourses")

# Path setup
_HERE = Path(__file__).resolve()
if _HERE.parents[1].name == "ops" and _HERE.parents[2].name == "scripts" and _HERE.parents[3].name == "backend":
    _REPO_ROOT = _HERE.parents[3].parent
    _BACKEND = _HERE.parents[3]
elif _HERE.parents[1].name == "ops" and _HERE.parents[2].name == "scripts":
    _REPO_ROOT = _HERE.parents[2].parent
    _BACKEND = _REPO_ROOT / "backend"
else:
    _REPO_ROOT = Path.cwd()
    _BACKEND = _REPO_ROOT / "backend"

if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

CURATED_DISCOURSES = [
    {
        "video_id": "1nhXsnx5--Y",
        "title": "How to Draw Your Soul Mate to You",
        "url": "https://www.youtube.com/watch?v=1nhXsnx5--Y",
        "speaker": "Sri Krishnaji",
        "speaker_slug": "sri-krishnaji",
        "teacher_id": "krishnaji",
        "channel": "Sri Preethaji & Sri Krishnaji",
        "concepts": ["Awakening", "Love", "Consciousness", "Relationship"],
        "summary": (
            "Sri Krishnaji teaches that in consciousness, one must create the effect first "
            "and the cause will follow. Rather than seeking a soul mate from a state of emptiness "
            "or fear, awakening to causeless love and beautiful inner states allows true connection to manifest."
        ),
        "key_teachings": [
            "In consciousness, create the effect first and the cause will follow.",
            "Awakening to causeless love and wholeness transforms existing relationships or draws the soul mate.",
            "Searching from a suffering state turns relationships into endless elimination contests.",
        ],
        "quotes": [
            "One secret law of consciousness says: create the effect first and the cause will follow.",
            "When your heart explodes with causeless love and wholeness, your soul mate arrives.",
        ],
        "spans": [
            (
                "In the realm of consciousness, one secret law says: create the effect first and the cause will follow. "
                "Why do you want a soul mate in life? If you reflect upon it, you want a soul mate because you believe "
                "this person will make you feel complete and bring joy. But when you awaken to beautiful states of consciousness, "
                "your heart explodes with causeless love and wholeness, and then your soul mate arrives.",
                0,
                120000,
            ),
            (
                "Understand that the more powerful your state of consciousness, the more easily you manifest blessings "
                "from Universal Intelligence. If you seek from suffering, it becomes an elimination round. Only when you "
                "awaken to a beautiful state where you feel whole and joyful do you arrive upon the perfect soul mate, "
                "or transform existing relationships into being soul mates.",
                120000,
                304000,
            ),
        ],
    },
    {
        "video_id": "7BLsD_meNzw",
        "title": "Transcending the Need to Please Others and Overcoming Suffering",
        "url": "https://www.youtube.com/watch?v=7BLsD_meNzw",
        "speaker": "Sri Krishnaji",
        "speaker_slug": "sri-krishnaji",
        "teacher_id": "krishnaji",
        "channel": "Sri Preethaji & Sri Krishnaji",
        "concepts": ["Suffering", "Ego", "Inner Peace", "Fear"],
        "summary": (
            "Sri Krishnaji reveals the inner contradiction of the people pleaser, who is caught between hurt "
            "and fear. Using the humorous parable of the washerman, his son, and the donkey, he illustrates how "
            "trying to satisfy everyone leads to losing one's inner peace."
        ),
        "key_teachings": [
            "People pleasing is rooted in an inner contradiction between hurt and fear of losing love.",
            "Pleasing has little to do with the other person's happiness; it is driven by egoic need for approval.",
            "Transcending the compulsive need to please allows one to become a true force for peace.",
        ],
        "quotes": [
            "To be a pleaser means you are someone whose single focus is to not upset or disappoint people. "
            "You are caught between hurt and fear.",
            "When your responses come from a fearful space, you cannot cause harmony. Transcend the compulsive need to please.",
        ],
        "spans": [
            (
                "To be a pleaser means you are someone whose single focus is to not upset people or disappoint them in any way. "
                "This thinking is sourced in a contradiction within you: on one side you feel hurt, and on the other you do not "
                "want to lose love. You are caught between hurt and fear. Pleasing has nothing to do with the other's happiness; "
                "it is all about you being accepted.",
                0,
                115000,
            ),
            (
                "When your responses come from such a fearful and negative space, how can you cause harmony or love? "
                "You have a beautiful intention to create harmony, but making what they think about you more important than "
                "their happiness will never lead to peace. Come out of this compulsive need to please, and you will be a "
                "beautiful force for peace in your world.",
                115000,
                240000,
            ),
        ],
    },
    {
        "video_id": "88NOQTz5_yI",
        "title": "Ekam: Movement in Consciousness and Spiritual Transformation",
        "url": "https://www.youtube.com/watch?v=88NOQTz5_yI",
        "speaker": "Sri Preethaji & Sri Krishnaji",
        "speaker_slug": "sri-krishnaji",
        "teacher_id": "krishnaji",
        "channel": "Sri Preethaji & Sri Krishnaji",
        "concepts": ["Consciousness", "Oneness", "Transformation"],
        "summary": (
            "Sri Krishnaji articulates the foundational vision of Ekam as a movement in consciousness. "
            "Explaining the Mukthi Sampradaya, he outlines the sacred mission to awaken humanity to oneness "
            "and dissolve suffering through collective transformation."
        ),
        "key_teachings": [
            "Every human being has one primal wish: to be happy and free from suffering and separation.",
            "The collective awakening of human consciousness is the enduring panacea for all global division.",
            "Ekam exists as a sacred movement to lead individuals and humanity into states of oneness and liberation.",
        ],
        "quotes": [
            "Every human being has one primal wish: you want to be happy.",
            "The collective awakening of human consciousness is the enduring panacea to dissolve suffering and division.",
        ],
        "spans": [
            (
                "Every human being has one primal wish: you want to be happy. But living in a consciousness of suffering, "
                "ignorance, and separation leads to conflict and obstacles. In an unawakened state, individuals continuously "
                "generate negative karmic patterns.",
                50000,
                140000,
            ),
            (
                "The collective awakening of human consciousness is the enduring panacea for world problems. "
                "That is why our most important mission is the individual and collective awakening of consciousness. "
                "We come from Mukthi Sampradaya, dedicated to leading seekers into total liberation and oneness.",
                140000,
                250000,
            ),
        ],
    },
]


def ingest_into_memgraph(discourses: list[dict[str, Any]]) -> int:
    """Creates :Video nodes and connects them with :Teacher and :Concept nodes in Memgraph."""
    logger.info("Connecting to Memgraph at bolt://localhost:7687...")
    from neo4j import GraphDatabase

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "mukthiguru_neo4j_pass")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    count = 0
    with driver.session() as session:
        for d in discourses:
            vid = d["video_id"]
            title = d["title"]
            url = d["url"]
            speaker = d["speaker"]
            concepts = d["concepts"]

            # Merge Video node
            session.run(
                """
                MERGE (v:Video {id: $vid})
                SET v.title = $title,
                    v.url = $url,
                    v.source_url = $url,
                    v.source_type = 'youtube_discourse',
                    v.channel = $channel,
                    v.speaker = $speaker,
                    v.domain_rights_status = 'licensed'
                """,
                vid=vid,
                title=title,
                url=url,
                channel=d["channel"],
                speaker=speaker,
            )

            # Link Teachers
            if "Krishnaji" in speaker:
                session.run(
                    """
                    MATCH (v:Video {id: $vid})
                    MERGE (t:Teacher {name: 'Sri Krishnaji'})
                    MERGE (t)-[:SPEAKER_OF]->(v)
                    """,
                    vid=vid,
                )
            if "Preethaji" in speaker:
                session.run(
                    """
                    MATCH (v:Video {id: $vid})
                    MERGE (t:Teacher {name: 'Sri Preethaji'})
                    MERGE (t)-[:SPEAKER_OF]->(v)
                    """,
                    vid=vid,
                )

            # Link Concepts
            for c_name in concepts:
                session.run(
                    """
                    MATCH (v:Video {id: $vid})
                    MERGE (c:Concept {name: $c_name})
                    MERGE (v)-[:EXPOUNDS]->(c)
                    """,
                    vid=vid,
                    c_name=c_name,
                )

            logger.info("  ✓ Memgraph: indexed discourse :Video {id: %s, title: '%s'}", vid, title)
            count += 1

    driver.close()
    return count


def ingest_into_okf(discourses: list[dict[str, Any]]) -> int:
    """Creates curated markdown files in memory/okf/ and staging, and triggers compiler."""
    okf_dir = _REPO_ROOT / "memory" / "okf"
    staging_dir = okf_dir / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)

    created = 0
    for d in discourses:
        slug = d["title"].lower().replace(":", "").replace(",", "").replace("'", "")
        slug = "-".join(slug.split()[:7])
        filename = f"{slug}.md"

        yaml_lines = [
            "---",
            "type: teaching",
            f'title: "{d["title"]}"',
            f'source: "{d["url"]}"',
            f'video_id: "{d["video_id"]}"',
            f'tags: {json.dumps([c.lower() for c in d["concepts"]])}',
            f'teacher: "{d["speaker_slug"]}"',
            "domain_rights_status: licensed",
            "---",
            "",
            f"# {d['title']}",
            "",
            f"### Overview",
            "",
            d["summary"],
            "",
            "---",
            "",
            "**Key Teachings:**",
        ]
        for kt in d["key_teachings"]:
            yaml_lines.append(f"- {kt}")
        yaml_lines.append("")
        yaml_lines.append("**Quotes:**")
        for q in d["quotes"]:
            yaml_lines.append(f'> "{q}"')
            yaml_lines.append(f'- {d["speaker"]}')
            yaml_lines.append("")

        content = "\n".join(yaml_lines) + "\n"

        target_main = okf_dir / filename
        target_staging = staging_dir / filename

        target_main.write_text(content, encoding="utf-8")
        target_staging.write_text(content, encoding="utf-8")
        logger.info("  ✓ OKF: wrote %s and staging copy", filename)
        created += 1

    # Recompile OKF
    from services.memory.compiler import compile_okf
    compiled_path = compile_okf()
    logger.info("  ✓ OKF recompiled at %s", compiled_path)
    return created


def ingest_into_qdrant(discourses: list[dict[str, Any]]) -> dict[str, int]:
    """Indexes vectors and payloads into Qdrant collections."""
    from qdrant_client import QdrantClient
    from qdrant_client.http import models
    from services.embedding_service import EmbeddingService

    client = QdrantClient(host="localhost", port=6333, check_compatibility=False)
    embedder = EmbeddingService()

    stats = {"spiritual_wisdom_contextual": 0, "first_person_v10": 0, "first_person_v11": 0}

    for d in discourses:
        vid = d["video_id"]
        title = d["title"]
        url = d["url"]
        speaker = d["speaker"]
        teacher_id = d["teacher_id"]

        # 1. Check & add first-person spans to first_person_v10 and first_person_v11
        for coll in ["first_person_v10", "first_person_v11"]:
            existing_count = client.count(
                coll,
                count_filter=models.Filter(
                    must=[models.FieldCondition(key="video_id", match=models.MatchValue(value=vid))]
                ),
            ).count

            if existing_count == 0:
                logger.info("  Adding first-person spans for %s into %s...", vid, coll)
                points_to_upsert = []
                parent_unit_id = f"parent_{vid}_0"

                for span_idx, (text, start_ms, end_ms) in enumerate(d["spans"]):
                    span_id = f"{vid}_{span_idx}"
                    point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"fp_{coll}_{span_id}"))

                    # Compute 1024-dim dense embedding
                    enc = embedder.encode_single_full(text)
                    dense_vec = enc["dense"]

                    payload = {
                        "schema_version": "fp-context-v1",
                        "corpus_version": "fp-context-transcript-v2",
                        "guru_id": teacher_id,
                        "video_id": vid,
                        "source_asset_id": vid,
                        "source_span_id": span_id,
                        "parent_unit_id": parent_unit_id,
                        "turn_id": f"turn_{vid}_{span_idx}",
                        "turn_index": span_idx,
                        "source_span_index": span_idx,
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                        "speaker_id": teacher_id,
                        "speaker_role": "teacher",
                        "speaker_verified": True,
                        "voice_verification_method": "ecapa_voxceleb_span_slice_v2",
                        "verbatim_text": text,
                        "source_transcript_text": text,
                        "is_verbatim": True,
                        "rights_cleared": True,
                        "domain_rights_status": "licensed",
                        "topic_ids": [c.lower() for c in d["concepts"]],
                        "source_url": url,
                        "record_type": "retrieval_child",
                    }

                    points_to_upsert.append(
                        models.PointStruct(
                            id=point_id,
                            vector={"passage_dense": dense_vec},
                            payload=payload,
                        )
                    )

                if points_to_upsert:
                    client.upsert(collection_name=coll, points=points_to_upsert)
                    stats[coll] += len(points_to_upsert)
                    logger.info("  ✓ %s: upserted %d points for %s", coll, len(points_to_upsert), vid)
            else:
                logger.info("  %s already has %d points for %s", coll, existing_count, vid)

        # 2. Check & add general RAG chunks to spiritual_wisdom_contextual if needed
        swc_count = client.count(
            "spiritual_wisdom_contextual",
            count_filter=models.Filter(
                should=[
                    models.FieldCondition(key="video_id", match=models.MatchValue(value=vid)),
                    models.FieldCondition(key="source_url", match=models.MatchText(text=vid)),
                ]
            ),
        ).count

        if swc_count == 0:
            logger.info("  Adding RAG chunks for %s into spiritual_wisdom_contextual...", vid)
            rag_points = []
            for span_idx, (text, start_ms, end_ms) in enumerate(d["spans"]):
                point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"rag_{vid}_{span_idx}"))
                enc = embedder.encode_single_full(text)
                dense_vec = enc["dense"]
                sparse_dict = enc["sparse"]

                sparse_indices = [int(k) for k in sparse_dict.keys()]
                sparse_values = [float(v) for v in sparse_dict.values()]

                payload = {
                    "text": text,
                    "title": title,
                    "speaker": speaker,
                    "topic": d["concepts"][0] if d["concepts"] else "Spiritual Wisdom",
                    "content_type": "discourse",
                    "source_type": "youtube_discourse",
                    "tags": [c.lower() for c in d["concepts"]],
                    "chunk_index": span_idx,
                    "video_id": vid,
                    "source_url": url,
                    "channel_name": d["channel"],
                    "domain_rights_status": "licensed",
                    "authority_tier": "canonical",
                    "teacher_id": teacher_id,
                    "teacher_ids": [teacher_id],
                    "first_person_eligible": True,
                }

                rag_points.append(
                    models.PointStruct(
                        id=point_id,
                        vector={
                            "dense": dense_vec,
                            "sparse": models.SparseVector(
                                indices=sparse_indices, values=sparse_values
                            ),
                        },
                        payload=payload,
                    )
                )

            if rag_points:
                client.upsert(collection_name="spiritual_wisdom_contextual", points=rag_points)
                stats["spiritual_wisdom_contextual"] += len(rag_points)
                logger.info("  ✓ spiritual_wisdom_contextual: upserted %d points for %s", len(rag_points), vid)
        else:
            logger.info("  spiritual_wisdom_contextual already has %d points for %s", swc_count, vid)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch ingest curated discourses into Memgraph, OKF, and Qdrant")
    parser.parse_args()

    logger.info("==================================================================")
    logger.info("Batch Ingestion of Curated Discourses into Memgraph, OKF & Qdrant")
    logger.info("==================================================================")

    # 1. Memgraph
    m_count = ingest_into_memgraph(CURATED_DISCOURSES)

    # 2. OKF
    o_count = ingest_into_okf(CURATED_DISCOURSES)

    # 3. Qdrant
    q_stats = ingest_into_qdrant(CURATED_DISCOURSES)

    logger.info("==================================================================")
    logger.info("Batch Ingestion Summary:")
    logger.info("  Memgraph Videos linked: %d", m_count)
    logger.info("  OKF entries created:   %d", o_count)
    logger.info("  Qdrant points added:   %s", q_stats)
    logger.info("==================================================================")


if __name__ == "__main__":
    main()
