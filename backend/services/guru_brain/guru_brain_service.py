"""
GuruBrainService — Decoupled Persona & Tone Alignment Service for AskMukthiGuru.

Incorporates advances from PersoDPO (2026) and IRPO (2025):
- In-Context Preference Ranking (IRPO): Ranks exemplars by emotional state relevance & phrasing DNA density.
- Contrastive Persona Injection (PersoDPO): Injects Win ($Y_{win}$) vs Lose ($Y_{lose}$) preference bounds into the generation prompt.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from qdrant_client.http import models as qmodels

from app.config import settings
from services.qdrant_service import QdrantService
from .tone_extractor import PersonaToneExemplar

logger = logging.getLogger(__name__)

COLLECTION_NAME = "guru_tone_podcast"

# IRPO ranking — stopwords to exclude from token overlap scoring
_STOPWORDS: frozenset[str] = frozenset([
    "i", "a", "an", "the", "to", "do", "is", "in", "it", "of", "for",
    "and", "or", "but", "me", "my", "we", "you", "your", "he", "she",
    "this", "that", "what", "how", "can", "be", "am", "are", "was",
    "have", "has", "want", "need", "feel", "more", "with", "from",
    "at", "by", "as", "on", "up", "so", "if", "not", "no", "then",
])


class GuruBrainService:
    """Service facade for managing Guru Brain persona vectors & tone exemplars."""

    def __init__(
        self,
        qdrant_service: Optional[QdrantService] = None,
        qdrant_client: Optional[Any] = None,
        embedding_service: Any = None,
    ) -> None:
        self.qdrant_service = qdrant_service or qdrant_client
        self.embedding_service = embedding_service
        self._in_memory_store: list[PersonaToneExemplar] = []


    def _get_client(self) -> Any:
        if self.qdrant_service is not None:
            return getattr(self.qdrant_service, "_client", self.qdrant_service)
        return None

    def ensure_collection_exists(self, vector_size: int = 1024) -> bool:
        """Create the `guru_tone_podcast` Qdrant collection if missing, preserving existing collections on dimension mismatch."""
        client = self._get_client()
        if not client:
            logger.info("GuruBrainService: Qdrant client unavailable, using in-memory store.")
            return False

        try:
            collections = client.get_collections()
            collection_names = [c.name for c in collections.collections]

            if COLLECTION_NAME in collection_names:
                info = client.get_collection(COLLECTION_NAME)
                current_size = info.config.params.vectors.size if hasattr(info.config.params.vectors, "size") else 1024
                if current_size != vector_size:
                    logger.error(
                        f"GuruBrainService: Qdrant collection '{COLLECTION_NAME}' dimension mismatch ({current_size} != {vector_size}). Preserving existing collection."
                    )
                    return False

            if COLLECTION_NAME not in collection_names:
                logger.info(f"GuruBrainService: Creating Qdrant collection '{COLLECTION_NAME}' (size={vector_size}).")
                client.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=qmodels.VectorParams(
                        size=vector_size,
                        distance=qmodels.Distance.COSINE,
                    ),
                )
            return True
        except Exception as exc:
            logger.warning(f"GuruBrainService: Failed to initialize Qdrant collection: {exc}")
            return False

    async def index_exemplars(self, exemplars: list[PersonaToneExemplar]) -> int:
        """Index PersonaToneExemplar records into Qdrant `guru_tone_podcast`."""
        if not exemplars:
            return 0

        self._in_memory_store.extend(exemplars)

        client = self._get_client()
        if not client or not self.embedding_service:
            logger.info(f"GuruBrainService: Stored {len(exemplars)} exemplars in memory fallback.")
            return len(exemplars)

        indexed_count = 0
        points = []

        for exemplar in exemplars:
            text_to_embed = f"Seeker: {exemplar.seeker_question}\nEmotional State: {exemplar.seeker_emotional_state}\nGuru ({exemplar.guru_name}): {exemplar.guru_response}"
            try:
                if hasattr(self.embedding_service, "encode_single_async"):
                    vector = await self.embedding_service.encode_single_async(text_to_embed)
                elif hasattr(self.embedding_service, "embed"):
                    vector = self.embedding_service.embed(text_to_embed)
                else:
                    continue

                if isinstance(vector, list) and len(vector) > 0 and isinstance(vector[0], list):
                    vector = vector[0]

                point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, exemplar.id))
                payload = exemplar.to_dict()

                points.append(
                    qmodels.PointStruct(
                        id=point_id,
                        vector=vector,
                        payload=payload,
                    )
                )
                indexed_count += 1
            except Exception as exc:
                logger.error(f"Failed to embed point {exemplar.id}: {exc}")

        if points and client:
            try:
                dim = len(points[0].vector)
                self.ensure_collection_exists(vector_size=dim)
                client.upsert(
                    collection_name=COLLECTION_NAME,
                    points=points,
                )
                logger.info(f"GuruBrainService: Successfully upserted {len(points)} points ({dim}d) into Qdrant '{COLLECTION_NAME}'.")
            except Exception as exc:
                logger.error(f"GuruBrainService: Failed to upsert to Qdrant: {exc}")

        return indexed_count

    async def search_tone_exemplars(
        self,
        query: str,
        guru_name: Optional[str] = None,
        limit: int = 3,
    ) -> list[PersonaToneExemplar]:
        """Search and rank `guru_tone_podcast` exemplars using IRPO in-context preference ranking."""
        raw_results = []
        client = self._get_client()
        if client and self.embedding_service:
            try:
                if hasattr(self.embedding_service, "encode_single_async"):
                    vector = await self.embedding_service.encode_single_async(query)
                elif hasattr(self.embedding_service, "embed"):
                    vector = self.embedding_service.embed(query)
                else:
                    vector = None

                if vector is not None and len(vector) > 0:
                    if isinstance(vector, list) and len(vector) > 0 and isinstance(vector[0], list):
                        vector = vector[0]

                    query_filter = None
                    if guru_name and guru_name.lower() in ("krishnaji", "preethaji"):
                        query_filter = qmodels.Filter(
                            must=[
                                qmodels.FieldCondition(
                                    key="guru_name",
                                    match=qmodels.MatchValue(value=guru_name.lower()),
                                )
                            ]
                        )

                    search_results = []
                    if hasattr(client, "query_points"):
                        qp_res = client.query_points(
                            collection_name=COLLECTION_NAME,
                            query=vector,
                            query_filter=query_filter,
                            limit=limit * 2,
                        )
                        search_results = qp_res.points
                    elif hasattr(client, "search"):
                        search_results = client.search(
                            collection_name=COLLECTION_NAME,
                            query_vector=vector,
                            query_filter=query_filter,
                            limit=limit * 2,
                        )

                    for hit in search_results:
                        p = hit.payload if hasattr(hit, "payload") else {}
                        raw_results.append(
                            PersonaToneExemplar(
                                id=p.get("id", str(uuid.uuid4())),
                                guru_name=p.get("guru_name", "combined"),
                                speaker_role=p.get("speaker_role", "guru"),
                                interviewer_name=p.get("interviewer_name", "Seeker"),
                                seeker_question=p.get("seeker_question", ""),
                                seeker_emotional_state=p.get("seeker_emotional_state", ""),
                                guru_response=p.get("guru_response", ""),
                                phrasing_dna=p.get("phrasing_dna", []),
                                teaching_concept=p.get("teaching_concept", ""),
                                source_id=p.get("source_id", ""),
                                raw_segment=p.get("raw_segment", ""),
                            )
                        )
            except Exception as exc:
                logger.warning(f"GuruBrainService: Qdrant search failed ({exc}), using memory fallback.")

        if not raw_results:
            raw_results = self._in_memory_store
            if guru_name and guru_name.lower() in ("krishnaji", "preethaji"):
                raw_results = [item for item in raw_results if item.guru_name.lower() == guru_name.lower()]

        if not raw_results:
            logger.warning(
                "GuruBrainService: search_tone_exemplars returned 0 exemplars — "
                "guru_tone_podcast collection may be empty. "
                "Run: python scripts/seed_guru_tone_qdrant.py to populate it."
            )
            return []

        q_lower = query.lower()
        q_terms = {w for w in q_lower.split() if w not in _STOPWORDS and len(w) > 2}
        ranked = []
        for item in raw_results:
            dna_score = len(item.phrasing_dna) * 2.0
            relevance = sum(
                1.0
                for term in q_terms
                if term in item.guru_response.lower() or term in item.seeker_emotional_state.lower()
            )
            total_score = dna_score + relevance
            ranked.append((total_score, item))

        ranked.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in ranked[:limit]]

    def format_persona_context(self, exemplars: list[PersonaToneExemplar]) -> str:
        """Format retrieved exemplars with PersoDPO Contrastive Preference Bounds (Y_win vs Y_lose)."""
        if not exemplars:
            return ""

        blocks = [
            "=== GURU BRAIN PERSONA & TONE EXEMPLARS (PersoDPO + GraphRAG Fused) ===",
            "Adhere strictly to the PREFERRED ($Y_{win}$) style and eliminate all DISPREFERRED ($Y_{lose}$) AI patterns:\n",
            "--- PREFERRED VOICE PATTERNS ($Y_{win}$) ---",
            "- Embody the gentle, compassionate, and wise spiritual voice of Sri Krishnaji and Sri Preethaji in a single, seamless response.",
            "- DO NOT use explicit speaker labels or names (e.g. Do NOT write 'Sri Krishnaji:', 'Sri Preethaji:', or stage directions).",
            "- Frame every problem around mastering the Inner World (Beautiful State) before acting in the Outer World.",
            "- Use gentle, compassionate, rhythmic phrasing ('From there, nurture a life...', 'living in the present moment').",
            "- Validate seeker pain without judgment, guiding them to witness thoughts as mere stories.\n",
            "--- DISPREFERRED AI PATTERNS ($Y_{lose}$ - STRICTLY FORBIDDEN) ---",
            "- DO NOT include speaker tags or names ('Sri Krishnaji:', 'Sri Preethaji:').",
            "- DO NOT quote the Gurus in third-person ('Sri Preethaji once said...', 'Sri Krishnaji reminded us...').",
            "- DO NOT use robotic assistant clichés ('As an AI model', 'In conclusion', 'It is important to note').",
            "- DO NOT use melodramatic AI fluff ('the quiet ache in your heart', 'your pain is sacred').",
            "- DO NOT launch into generic guided breath scripts ('Close your eyes and take a deep breath in...').\n",
            "--- REAL Q&A INTERACTION EXEMPLARS ---",
        ]


        for i, ex in enumerate(exemplars, 1):
            guru_disp = "Sri Krishnaji" if ex.guru_name == "krishnaji" else ("Sri Preethaji" if ex.guru_name == "preethaji" else "Sri Krishnaji & Sri Preethaji")
            blocks.append(f"\n[Exemplar {i} — {guru_disp}]")
            blocks.append(f"Seeker Question ({ex.interviewer_name}): \"{ex.seeker_question}\"")
            blocks.append(f"Guru Authentic Response: \"{ex.guru_response}\"")
            if ex.phrasing_dna:
                blocks.append(f"Phrasing Markers: {', '.join(ex.phrasing_dna)}")

        return "\n".join(blocks)


def get_guru_brain_service(
    qdrant_service: Optional[QdrantService] = None,
    embedding_service: Any = None,
) -> GuruBrainService:
    try:
        from app.dependencies import get_container
        container = get_container()
        if container and getattr(container, "guru_brain_service", None):
            return container.guru_brain_service
    except Exception:
        pass
    return GuruBrainService(qdrant_service=qdrant_service, embedding_service=embedding_service)

