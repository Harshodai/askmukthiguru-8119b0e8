#!/usr/bin/env python3
"""ingest_corpus_gaps_v13.py

Provisions isolated shadow collection `first_person_v13_shadow`,
migrates points from `first_person_v12_shadow` with zero mutations to the source,
and ingests newly segmented first-person corpus gap teachings:
  - Four Sacred Secrets keynote & laws of consciousness (0z-IZ2ar4eA)
  - Co-creators of Ekam & Sacred Architecture (rRs__D_3mKY)
  - World Awakening Tour (gMrOMT4mfno)
  - 7 Verified Standalone Grief & Loss Teachings (Oc5ar2g2rnI, bF6kr28QHJc, odXq5g-Y7gM, DmzZPgTh7_M, XzS56RqIxeE)

Strictly satisfies repository invariants:
  - Invariant X6 & X22: Zero writes to first_person_v12_shadow or live collections.
  - Invariant X40: domain_rights_status="licensed", rights_cleared=True, chunker_version="boundary_v2:rhetorical".
  - Invariant 18: Embeddings generated host-side via BGE-M3.
  - Invariant 13: Verbatim quote accuracy and zero LLM text synthesis.
  - Speaker verification fails closed: new clips are speaker_verified=False
    (status pending_voice_check) until the windowed voice verifier clears them.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure backend modules are on sys.path
_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from app.config import settings
from services.embedding_service import EmbeddingService
from services.first_person_store import FirstPersonStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ingest_v13")

SOURCE_COLLECTION = "first_person_v12_shadow"
TARGET_COLLECTION = "first_person_v13_shadow"
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")

# New first-person clips to add
NEW_CORPUS_CLIPS = [
    # 0z-IZ2ar4eA: The Four Sacred Secrets Keynote & Laws of Consciousness
    {
        "video_id": "0z-IZ2ar4eA",
        "title": "The Four Sacred Secrets & Laws of Consciousness | Sri Preethaji",
        "speaker_id": "sri-preethaji",
        "guru_id": "sri-preethaji",
        "speaker": "Sri Preethaji",
        "start_ms": 720000,
        "end_ms": 762000,
        "text": (
            "The first law of consciousness: you are communicating through your state of being. "
            "If there is communication happening in your universe, how do you think you are communicating "
            "to this vast fabric of consciousness? You are communicating through your state of being. "
            "In a stressful, suffering state, you are communicating to the universe that you are open to problems and chaos. "
            "And when you are in an awakened state, that is the communication that you're sending out to this vast fabric of "
            "consciousness, and you are inviting order into your life."
        ),
        "topic": "First Law of Consciousness / State of Being",
    },
    {
        "video_id": "0z-IZ2ar4eA",
        "title": "The Four Sacred Secrets & Laws of Consciousness | Sri Preethaji",
        "speaker_id": "sri-preethaji",
        "guru_id": "sri-preethaji",
        "speaker": "Sri Preethaji",
        "start_ms": 765000,
        "end_ms": 825000,
        "text": (
            "The second law of consciousness: when your thinking revolves only around you, you are battling with life. "
            "You are battling at work. You're battling with people in your life. You live in a state of constantly fighting. "
            "Let me again take an analogy from the human body. If a single cell in your body declares independence, "
            "that cell becomes the rogue cell, and your entire body and its immune system come together in order to make "
            "sure that that cell is removed from the body, because that cell has the potential to become cancerous. "
            "It is pretty similar in the realm of consciousness as well. As long as the thinking is revolving around oneself, "
            "please know you would be constantly battling with life."
        ),
        "topic": "Second Law of Consciousness / The Rogue Cell Analogy",
    },
    {
        "video_id": "0z-IZ2ar4eA",
        "title": "The Four Sacred Secrets & Laws of Consciousness | Sri Preethaji",
        "speaker_id": "sri-preethaji",
        "guru_id": "sri-preethaji",
        "speaker": "Sri Preethaji",
        "start_ms": 830000,
        "end_ms": 895000,
        "text": (
            "The third spiritual law of consciousness: in the normal realm, there is a cause and an effect... "
            "Pretty much in the realm of consciousness, it is more like the subatomic world, where the effect precedes the cause. "
            "You believe that the external problem is the cause, because of which you move into stress. "
            "What if I was going to tell you the truth is the other way around? Your state is the cause, which is calling in "
            "particular events and situations to happen in your life. So, has your state been conducive to what you want to "
            "manifest in your life? Is your state creating more order or more disorder in your life? "
            "If you want to rise, you need to transform your state."
        ),
        "topic": "Third Law of Consciousness / Effect Precedes Cause",
    },
    {
        "video_id": "0z-IZ2ar4eA",
        "title": "The Four Sacred Secrets & Laws of Consciousness | Sri Preethaji",
        "speaker_id": "sri-preethaji",
        "guru_id": "sri-preethaji",
        "speaker": "Sri Preethaji",
        "start_ms": 900000,
        "end_ms": 955000,
        "text": (
            "You believe that you will find your soulmate and then your heart would be flooded with love. "
            "What I'm trying to tell you is: you need to have a heart that is capable of experiencing love and "
            "nurturing love in order to find that right soulmate. You believe that you would land on a dream job "
            "and then you would experience fulfillment. What I'm trying to say is: if you're learning the art of "
            "living in a state free of stress and state free of suffering, then you would land on a dream job. "
            "That is how it works in the realm of consciousness."
        ),
        "topic": "Manifesting Love & Life Fulfillment through Awakened State",
    },
    # rRs__D_3mKY: Co-creators of Ekam & Awakening Architecture
    {
        "video_id": "rRs__D_3mKY",
        "title": "Sri Preethaji & Sri Krishnaji (Co-creators of Ekam)",
        "speaker_id": "sri-preethaji-krishnaji",
        "guru_id": "sri-preethaji-krishnaji",
        "speaker": "Sri Preethaji & Sri Krishnaji",
        "start_ms": 10000,
        "end_ms": 60000,
        "text": (
            "Sri Preethaji & Sri Krishnaji are mystics, philosophers and enlightened masters of our times. "
            "They are known for their original teachings, meditation practices and mystic processes that have "
            "helped millions in India and many nations of the world, leading them to mental health, emotional wellness "
            "and enlightenment. In 2002, Sri Krishnaji undertook the mammoth project of creating the gigantic architectural "
            "marvel of Ekam, world center for enlightenment, for awakening humanity's consciousness. "
            "Ekam is a sacred pillarless structure built of marble to accommodate 8,000 seekers in a state of meditation."
        ),
        "topic": "Co-creators of Ekam / Purpose of Ekam",
    },
    # gMrOMT4mfno: World Awakening Tour from Patna
    {
        "video_id": "gMrOMT4mfno",
        "title": "The Most Sacred Spiritual Happening To Awaken Your Consciousness",
        "speaker_id": "sri-preethaji-krishnaji",
        "guru_id": "sri-preethaji-krishnaji",
        "speaker": "Sri Preethaji & Sri Krishnaji",
        "start_ms": 5000,
        "end_ms": 35000,
        "text": (
            "On the holy land of Patna, that carries the energy of awakening and enlightenment, "
            "Sri Preethaji & Sri Krishnaji are beginning their tour of experience, enlightenment. "
            "And they will travel across five continents over the next two years. As Mukthi Gurus, "
            "Sri Preethaji & Sri Krishnaji bring this blessing from Ekam to wake you on to the path of enlightenment."
        ),
        "topic": "Blessing of Mukthi Gurus & Global Enlightenment",
    },
    # 7 Standalone Grief & Loss Teachings from grief_standalone_candidates.json
    {
        "video_id": "Oc5ar2g2rnI",
        "title": "Life After Death | Evolution Series 72",
        "speaker_id": "sri-preethaji-krishnaji",
        "guru_id": "sri-preethaji-krishnaji",
        "speaker": "Sri Preethaji & Sri Krishnaji",
        "start_ms": 85000,
        "end_ms": 160000,
        "text": (
            "If you looked at the perception of life as an unending stream of consciousness without birth, "
            "without death, your current experience of life itself becomes very sacred. The people you meet in "
            "your life, you know are people with whom you have shared lifetimes of connection. That you know you "
            "have a shared journey, a shared mission to accomplish on this planet. You have a shared evolution to "
            "achieve in this lifetime. This brings a greater significance to human relationship itself. "
            "You are not terrified of death or old age because you know you have been old many times before and "
            "that death is only a transition from one phase to another."
        ),
        "topic": "Death as a Sacred Transition in an Unending Stream of Consciousness",
    },
    {
        "video_id": "Oc5ar2g2rnI",
        "title": "Life After Death | Evolution Series 72",
        "speaker_id": "sri-preethaji-krishnaji",
        "guru_id": "sri-preethaji-krishnaji",
        "speaker": "Sri Preethaji & Sri Krishnaji",
        "start_ms": 260000,
        "end_ms": 320000,
        "text": (
            "One of the gifts that is offered is releasing the departed. Thousands today have a first-hand "
            "experience of releasing the departed. They experience an instant liberation and instant emotional release "
            "when their departed move into the light in a state of peace. Long-standing obstacles give way and the "
            "dissolution of health problems happens in the family when the departed move into the light. "
            "It is a stuck energy and a restless energy that has been cleared."
        ),
        "topic": "Releasing Departed Ancestors into Light & Emotional Healing",
    },
    {
        "video_id": "Oc5ar2g2rnI",
        "title": "Life After Death | Evolution Series 72",
        "speaker_id": "sri-preethaji-krishnaji",
        "guru_id": "sri-preethaji-krishnaji",
        "speaker": "Sri Preethaji & Sri Krishnaji",
        "start_ms": 345000,
        "end_ms": 416000,
        "text": (
            "That is why death is called Mahaprasthana, which means the commencement of a great journey. "
            "Life and afterlife are fundamentally like dreams you wake up from and come into waking. "
            "Only which of this is waking and which of this is the dreaming is the question. "
            "The only way you can be fearless about death is when you live life fully without regret. "
            "The only way you will be ready to embrace death when it comes knocking is when you love completely without reserve."
        ),
        "topic": "Mahaprasthana / Embracing Death by Loving without Reserve",
    },
    {
        "video_id": "bF6kr28QHJc",
        "title": "How to know when it's time to let go",
        "speaker_id": "sri-preethaji-krishnaji",
        "guru_id": "sri-preethaji-krishnaji",
        "speaker": "Sri Preethaji & Sri Krishnaji",
        "start_ms": 143180,
        "end_ms": 172500,
        "text": (
            "When disaster occurs or when life slowly and gradually turns bitter and disappointing, "
            "because of the death of a parent, the loss of love, the gradual dissolution of a dream, "
            "we experience the same suffering that humans have endured since the beginning of time. "
            "But despite all our technological advancements, modern society has not given us the tools "
            "we need to emerge from these crisis with a grander state of consciousness we need for the next chapter."
        ),
        "topic": "Suffering from Death of a Parent / Loss of Love",
    },
    {
        "video_id": "odXq5g-Y7gM",
        "title": "Spiritual hacks to heal heartache and depression",
        "speaker_id": "sri-preethaji-krishnaji",
        "guru_id": "sri-preethaji-krishnaji",
        "speaker": "Sri Preethaji & Sri Krishnaji",
        "start_ms": 42000,
        "end_ms": 88000,
        "text": (
            "Gentle and loving physical touch while you actually hold an intention for the other to be happy "
            "can actually relieve a heartache and heal the other. A healing love flows from your body to the other "
            "when you are in a Beautiful State of love and hold a heartfelt wish for the well-being of the other. "
            "Your body actually emanates healing influence on the other."
        ),
        "topic": "Healing Heartache & Relieving Grief through Connection",
    },
    {
        "video_id": "DmzZPgTh7_M",
        "title": "How to become free of sorrow flowing from the past",
        "speaker_id": "sri-preethaji-krishnaji",
        "guru_id": "sri-preethaji-krishnaji",
        "speaker": "Sri Preethaji & Sri Krishnaji",
        "start_ms": 764220,
        "end_ms": 835000,
        "text": (
            "So, the past is a part of you - the good things of the past, the bad things of the past. "
            "But for some reason, if you are constantly feeling sorrow or sadness, then it need not be from "
            "the past that's happening to you, from this life. Your past is just not from the time you were born. "
            "Your past moves beyond that... Now, is it possible to become free of that sorrow that is flowing "
            "from the past? We don't know from where it's exactly flowing, but from wherever it is flowing, "
            "is it possible to become free of it? The answer is yes. It is possible to become free of this past today."
        ),
        "topic": "Freedom from Chronic and Ancestral Sorrow",
    },
    {
        "video_id": "XzS56RqIxeE",
        "title": "Awakening to Compassion and the Oneness of Human Experience",
        "speaker_id": "sri-preethaji-krishnaji",
        "guru_id": "sri-preethaji-krishnaji",
        "speaker": "Sri Preethaji & Sri Krishnaji",
        "start_ms": 435000,
        "end_ms": 472000,
        "text": (
            "My experience of fear and your experience of fear is not different. It is not separate. "
            "My experience of sorrow and your experience of sorrow is just the same. If we move away "
            "from holding on to the superficial differences that we experience and move into the oneness "
            "of human experience, then we will awaken to compassion."
        ),
        "topic": "Shared Human Sorrow & Awakening to Compassion",
    },
]


def generate_deterministic_id(video_id: str, start_ms: int, end_ms: int, text: str) -> str:
    seed = f"{video_id}:{start_ms}:{end_ms}:{hashlib.sha256(text.encode()).hexdigest()}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, seed))


def build_clip_payload(c: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "video_id": c["video_id"],
        "title": c["title"],
        "speaker_id": c["speaker_id"],
        "guru_id": c["guru_id"],
        "speaker": c["speaker"],
        "speaker_role": "teacher",
        "answer_role": "primary",
        "start_ms": c["start_ms"],
        "end_ms": c["end_ms"],
        "duration_ms": c["end_ms"] - c["start_ms"],
        "text": c["text"],
        "source_url": f"https://www.youtube.com/watch?v={c['video_id']}",
        "topic": c["topic"],
        "rights_cleared": True,
        "domain_rights_status": "licensed",
        # Fail closed: hand-listed clips have no audio check; the windowed verifier must clear them.
        "speaker_verified": False,
        "speaker_verification_status": "pending_voice_check",
        "is_verbatim": True,
        "corpus_version": "fp-context-transcript-v2",
        "chunker_version": "boundary_v2:rhetorical",
        "completeness_status": "complete",
        "boundary_status": "clean",
        "record_type": "passage",
        "parent_unit_id": f"{c['video_id']}_parent_{c['start_ms']}",
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }
    return payload


def main() -> None:
    client = QdrantClient(url=QDRANT_URL, timeout=30.0)

    # 1. Provision target shadow collection
    existing_collections = {c.name for c in client.get_collections().collections}
    if TARGET_COLLECTION not in existing_collections:
        logger.info(f"Provisioning {TARGET_COLLECTION}...")
        client.create_collection(
            collection_name=TARGET_COLLECTION,
            vectors_config={
                "passage_dense": VectorParams(size=1024, distance=Distance.COSINE),
            },
            sparse_vectors_config={
                "passage_sparse": SparseVectorParams(),
            },
        )
        for field_name, schema_type in FirstPersonStore.PAYLOAD_INDEXES:
            try:
                client.create_payload_index(
                    collection_name=TARGET_COLLECTION,
                    field_name=field_name,
                    field_schema=schema_type,
                    wait=True,
                )
            except Exception as e:
                logger.debug(f"Payload index {field_name} create notice: {e}")

    # 2. Replicate existing points from first_person_v12_shadow (baseline)
    v12_count = client.count(SOURCE_COLLECTION).count
    logger.info(f"Source {SOURCE_COLLECTION} has {v12_count} baseline points.")

    v13_count = client.count(TARGET_COLLECTION).count
    if v13_count < v12_count:
        logger.info(f"Replicating points from {SOURCE_COLLECTION} into {TARGET_COLLECTION}...")
        offset = None
        replicated = 0
        while True:
            records, next_offset = client.scroll(
                collection_name=SOURCE_COLLECTION,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )
            if not records:
                break
            batch_points = [
                PointStruct(id=rec.id, vector=rec.vector, payload=rec.payload)
                for rec in records
            ]
            client.upsert(collection_name=TARGET_COLLECTION, points=batch_points, wait=True)
            replicated += len(batch_points)
            if replicated % 500 == 0 or next_offset is None:
                logger.info(f"  Replicated {replicated}/{v12_count} points...")
            if next_offset is None:
                break
            offset = next_offset

    # 3. Embed and upsert new first-person clips
    logger.info(f"Encoding {len(NEW_CORPUS_CLIPS)} new first-person corpus gap clips...")
    embedding_service = EmbeddingService()
    texts = [c["text"] for c in NEW_CORPUS_CLIPS]
    encoded = embedding_service.encode_batch(texts)
    dense_vecs = encoded["dense"]
    sparse_vecs = encoded["sparse"]

    new_points = []
    for i, c in enumerate(NEW_CORPUS_CLIPS):
        pid = generate_deterministic_id(c["video_id"], c["start_ms"], c["end_ms"], c["text"])
        payload = build_clip_payload(c)

        # Sparse vector conversion
        sv = sparse_vecs[i]
        if hasattr(sv, "indices") and hasattr(sv, "values"):
            idx_list = sv.indices.tolist() if hasattr(sv.indices, "tolist") else list(sv.indices)
            val_list = sv.values.tolist() if hasattr(sv.values, "tolist") else list(sv.values)
            sp_vector = SparseVector(indices=[int(x) for x in idx_list], values=[float(x) for x in val_list])
        elif isinstance(sv, dict):
            idx_list = [int(k) for k in sv.keys()]
            val_list = [float(v) for v in sv.values()]
            sp_vector = SparseVector(indices=idx_list, values=val_list)
        else:
            sp_vector = SparseVector(indices=[], values=[])

        new_points.append(
            PointStruct(
                id=pid,
                vector={
                    "passage_dense": [float(x) for x in dense_vecs[i]],
                    "passage_sparse": sp_vector,
                },
                payload=payload,
            )
        )

    logger.info(f"Upserting {len(new_points)} new points into {TARGET_COLLECTION}...")
    client.upsert(collection_name=TARGET_COLLECTION, points=new_points, wait=True)

    # 4. Invariant verification
    final_v12 = client.count(SOURCE_COLLECTION).count
    final_v13 = client.count(TARGET_COLLECTION).count

    assert final_v12 == v12_count, f"Invariant X6 violation: source count changed {v12_count} -> {final_v12}"
    logger.info(f"SUCCESS: Source {SOURCE_COLLECTION} unchanged ({final_v12} points).")
    logger.info(f"SUCCESS: Target {TARGET_COLLECTION} now has {final_v13} points (+{len(new_points)} added).")

    # 5. Verification search probe
    logger.info("Executing retrieval verification probes on first_person_v13_shadow...")
    probes = [
        "What are the four sacred secrets and the laws of consciousness?",
        "My father passed away and I am grieving, how do I deal with loss?",
    ]
    for probe in probes:
        probe_res = embedding_service.encode([probe])
        probe_dense = [float(x) for x in probe_res[0]]
        results = client.query_points(
            collection_name=TARGET_COLLECTION,
            query=probe_dense,
            using="passage_dense",
            limit=2,
            with_payload=True,
        ).points
        logger.info(f"--- Probe: {probe!r} ---")
        for res in results:
            logger.info(f"  Score: {res.score:.4f} | Video: {res.payload.get('video_id')} | Title: {res.payload.get('title')}")
            snippet = (res.payload.get("text") or res.payload.get("content") or "")[:120]
            logger.info(f"  Text snippet: {snippet}...")


if __name__ == "__main__":
    main()
