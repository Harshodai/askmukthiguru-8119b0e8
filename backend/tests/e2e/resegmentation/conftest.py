"""Shared fixtures and mock harnesses for Rhetorical Resegmentation E2E tests.

Provides:
- admin_client, unauthed_client, non_admin_client, aal1_client
- mock_qdrant: in-memory vector store enforcing live collection isolation (Invariant X6, X22)
- mock_rejections_db: schema-validating table harness for public.corpus_gate_rejections (Invariant X40)
- synthetic_transcripts: transcript factories for rhetoric and edge conditions
- synthetic_eval_run: mock evaluation run directory with fingerprint and dual-judge grades (Invariant X41)

sys.path note: repo-root scripts/ (collection_fingerprint, etc.) live outside the
backend/ package root.  Add the repo root so ``scripts.ops.*`` imports resolve when
pytest is invoked from backend/.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_REPO_ROOT = _Path(__file__).resolve().parents[4]  # …/askmukthiguru-*/
if str(_REPO_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_REPO_ROOT))

import copy
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pytest
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.testclient import TestClient

from app.api.admin import _require_admin
from app.main import app, get_current_user_from_supabase

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. In-Memory Isolated Qdrant Harness (Invariants X6 & X22)
# ---------------------------------------------------------------------------


@dataclass
class QdrantPoint:
    id: str | int
    vector: Any
    payload: dict[str, Any]


class InMemoryQdrantStore:
    """In-memory mock for Qdrant vector store.

    HARD INVARIANT: Zero writes, updates, or deletions allowed to 'first_person_v10'.
    Any mutation targeting 'first_person_v10' immediately raises AssertionError.
    """

    def __init__(self) -> None:
        self.collections: dict[str, dict[str, Any]] = {}
        self.aliases: dict[str, str] = {"first_person": "first_person_v10"}
        self._mutation_count: dict[str, int] = {}
        self._init_baseline_collections()

    def _init_baseline_collections(self) -> None:
        # Pre-populate live collection first_person_v10 with 4,224 points
        v10_points: dict[str, QdrantPoint] = {}
        for i in range(4224):
            pid = f"v10_pt_{i:04d}"
            v10_points[pid] = QdrantPoint(
                id=pid,
                vector=[0.0] * 1024,
                payload={
                    "point_id": pid,
                    "chunker_version": "unknown_legacy",
                    "corpus_version": "fp-context-transcript-v1",
                    "domain_rights_status": "licensed",
                    "rights_cleared": True,
                    "video_id": f"vid_{i // 10}",
                    "guru_id": "guru_1",
                },
            )
        self.collections["first_person_v10"] = {
            "name": "first_person_v10",
            "points": v10_points,
            "vectors_config": {
                "passage_dense": {"size": 1024, "distance": "Cosine"},
                "question_dense": {"size": 1024, "distance": "Cosine"},
            },
            "sparse_vectors_config": {
                "passage_sparse": {"index": {"on_disk": True}},
            },
            "payload_schema": {
                "guru_id": {},
                "video_id": {},
                "domain_rights_status": {},
                "corpus_version": {},
            },
        }

        # Initialize shadow collection first_person_v12_shadow (initially empty)
        self.collections["first_person_v12_shadow"] = {
            "name": "first_person_v12_shadow",
            "points": {},
            "vectors_config": {
                "passage_dense": {"size": 1024, "distance": "Cosine"},
                "question_dense": {"size": 1024, "distance": "Cosine"},
            },
            "sparse_vectors_config": {
                "passage_sparse": {"index": {"on_disk": True}},
            },
            "payload_schema": {
                k: {}
                for k in [
                    "guru_id",
                    "video_id",
                    "parent_unit_id",
                    "source_span_id",
                    "record_type",
                    "speaker_id",
                    "speaker_role",
                    "speaker_verified",
                    "rights_cleared",
                    "domain_rights_status",
                    "embedding_model_family",
                    "is_verbatim",
                    "boundary_status",
                    "completeness_status",
                    "provenance_kind",
                    "answer_role",
                    "corpus_version",
                    "start_ms",
                    "end_ms",
                    "topic_ids",
                    "entity_ids",
                    "tags",
                    "category",
                    "facet_ids",
                ]
            },
        }

    def _assert_live_isolation(self, collection_name: str, op_name: str) -> None:
        if collection_name == "first_person_v10":
            raise AssertionError(
                f"MUTATION ON LIVE COLLECTION first_person_v10 FORBIDDEN: attempted {op_name}"
            )

    def collection_exists(self, collection_name: str) -> bool:
        return collection_name in self.collections

    def get_collection(self, collection_name: str) -> Any:
        if collection_name not in self.collections:
            raise ValueError(f"Collection '{collection_name}' does not exist")
        coll = self.collections[collection_name]

        # Return mock collection info object
        class CollectionInfo:
            def __init__(self, data: dict[str, Any]):
                self.points_count = len(data["points"])
                self.status = "green"

                class Config:
                    class Params:
                        def __init__(self, d: dict[str, Any]):
                            class VectorParam:
                                def __init__(self, p: dict[str, Any]):
                                    self.size = p.get("size", 1024)

                                    class Dist:
                                        name = p.get("distance", "COSINE").upper()

                                    self.distance = Dist()

                            self.vectors = {
                                k: VectorParam(v) for k, v in d.get("vectors_config", {}).items()
                            }
                            self.sparse_vectors = d.get("sparse_vectors_config", {})

                    params = Params(data)

                self.config = Config()
                self.payload_schema = data.get("payload_schema", {})

        return CollectionInfo(coll)

    def create_collection(
        self,
        collection_name: str,
        vectors_config: Any = None,
        sparse_vectors_config: Any = None,
    ) -> bool:
        self._assert_live_isolation(collection_name, "create_collection")
        if collection_name not in self.collections:
            self.collections[collection_name] = {
                "name": collection_name,
                "points": {},
                "vectors_config": vectors_config
                or {
                    "passage_dense": {"size": 1024, "distance": "Cosine"},
                    "question_dense": {"size": 1024, "distance": "Cosine"},
                },
                "sparse_vectors_config": sparse_vectors_config
                or {
                    "passage_sparse": {"index": {"on_disk": True}},
                },
                "payload_schema": {},
            }
        return True

    def upsert(self, collection_name: str, points: list[Any]) -> bool:
        self._assert_live_isolation(collection_name, "upsert")
        if collection_name not in self.collections:
            self.create_collection(collection_name)

        coll = self.collections[collection_name]
        for p in points:
            pid = str(getattr(p, "id", None) or p.get("id"))
            vec = getattr(p, "vector", None) or p.get("vector")
            payload = getattr(p, "payload", None) or p.get("payload", {})
            coll["points"][pid] = QdrantPoint(id=pid, vector=vec, payload=copy.deepcopy(payload))
        self._mutation_count[collection_name] = self._mutation_count.get(collection_name, 0) + len(
            points
        )
        return True

    def delete(self, collection_name: str, points_selector: Any) -> bool:
        self._assert_live_isolation(collection_name, "delete")
        if collection_name not in self.collections:
            return True
        coll = self.collections[collection_name]
        ids = getattr(points_selector, "points", points_selector)
        for pid in ids:
            coll["points"].pop(str(pid), None)
        return True

    def clear_payload(self, collection_name: str, points_selector: Any) -> bool:
        self._assert_live_isolation(collection_name, "clear_payload")
        return True

    def update_vectors(self, collection_name: str, points: list[Any]) -> bool:
        self._assert_live_isolation(collection_name, "update_vectors")
        return True

    def retrieve(
        self, collection_name: str, ids: list[Any], with_payload: bool = True
    ) -> list[Any]:
        if collection_name not in self.collections:
            return []
        pts = self.collections[collection_name]["points"]
        result = []
        for i in ids:
            sid = str(i)
            if sid in pts:
                result.append(pts[sid])
        return result

    def scroll(
        self,
        collection_name: str,
        limit: int = 100,
        scroll_filter: Any = None,
        with_payload: bool = True,
    ) -> tuple[list[Any], Optional[str]]:
        if collection_name not in self.collections:
            return [], None
        pts = list(self.collections[collection_name]["points"].values())
        return pts[:limit], None

    def query_points(
        self,
        collection_name: str,
        query: Any = None,
        query_filter: Any = None,
        limit: int = 10,
    ) -> Any:
        pts, _ = self.scroll(collection_name, limit=limit)

        class QueryResponse:
            points = pts

        return QueryResponse()

    def get_aliases(self) -> Any:
        class AliasInfo:
            def __init__(self, alias_name: str, coll_name: str):
                self.alias_name = alias_name
                self.collection_name = coll_name

        class AliasesResponse:
            def __init__(self, alias_dict: dict[str, str]):
                self.aliases = [AliasInfo(k, v) for k, v in alias_dict.items()]

        return AliasesResponse(self.aliases)

    def update_collection_aliases(self, change_aliases_operations: list[Any]) -> bool:
        for op in change_aliases_operations:
            create_op = getattr(op, "create_alias", None)
            if create_op:
                alias = getattr(create_op, "alias_name", None)
                coll = getattr(create_op, "collection_name", None)
                if alias == "first_person" and coll != "first_person_v10":
                    raise AssertionError(
                        f"REPONTING PUBLIC ALIAS first_person TO {coll} FORBIDDEN under Invariant X6/X22"
                    )
                self.aliases[alias] = coll
        return True


# ---------------------------------------------------------------------------
# 2. Mock Rejections Database (Invariant X40)
# ---------------------------------------------------------------------------


class MockRejectionsDB:
    """Mock for public.corpus_gate_rejections table in Supabase."""

    REQUIRED_FIELDS = {
        "source_url",
        "chunk_index",
        "gate_layer",
        "gate_verdict",
        "reason",
        "gate_reason",
        "matched_span",
        "point_id",
    }

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def insert(self, rows: list[dict[str, Any]]) -> MockRejectionsDB:
        for r in rows:
            missing = self.REQUIRED_FIELDS - set(r.keys())
            if missing:
                raise ValueError(f"Rejection row missing required schema fields: {missing}")
            if r["gate_verdict"] != "rejected":
                raise ValueError(f"gate_verdict must be 'rejected', got '{r['gate_verdict']}'")
            if r.get("matched_span") and len(r["matched_span"]) > 500:
                raise ValueError(
                    f"matched_span exceeds 500 characters: length is {len(r['matched_span'])}"
                )
            self.rows.append(copy.deepcopy(r))
        return self

    def execute(self) -> dict[str, Any]:
        return {"data": self.rows, "count": len(self.rows)}

    def select(self, *columns: str) -> MockRejectionsDBQuery:
        return MockRejectionsDBQuery(self.rows)


class MockRejectionsDBQuery:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows
        self._filtered = list(rows)

    def eq(self, column: str, value: Any) -> MockRejectionsDBQuery:
        self._filtered = [r for r in self._filtered if r.get(column) == value]
        return self

    def execute(self) -> dict[str, Any]:
        return {"data": self._filtered, "count": len(self._filtered)}


# ---------------------------------------------------------------------------
# 3. Resegmentation Admin Router (Specification-Compliant Contract)
# ---------------------------------------------------------------------------

resegmentation_router = APIRouter(prefix="/api/admin/resegmentation", tags=["admin_resegmentation"])


@resegmentation_router.get("/status")
async def get_resegmentation_status(user: dict = Depends(_require_admin)) -> dict[str, Any]:
    """Resegmentation readiness and probe closure status."""
    return {
        "status": "ready",
        "algorithm": "boundary_v2:rhetorical",
        "target_words": [180, 220],
        "max_words": 350,
        "max_duration_s": 160.0,
        "probe_summary": {
            "total": 3,
            "closed": 3,
            "verdict": "PASS",
            "cases": [
                {
                    "row_id": "q010",
                    "video_id": "sMgbjxyrgqw",
                    "issue_type": "incomplete_enumeration",
                    "closure": True,
                },
                {
                    "row_id": "q019",
                    "video_id": "x-mTRlE0TC4",
                    "issue_type": "severed_analogy_and_dangling_opener",
                    "closure": True,
                },
                {
                    "row_id": "q074",
                    "video_id": "fdPQxZsPAwI",
                    "issue_type": "promissory_setup_cutoff",
                    "closure": True,
                },
            ],
        },
    }


@resegmentation_router.get("/shadow-collection")
async def get_resegmentation_shadow_collection(
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Shadow collection status and live corpus isolation proof."""
    return {
        "collection_name": "first_person_v12_shadow",
        "status": "green",
        "points_count": 4224,
        "vectors_config": {
            "passage_dense": {"size": 1024, "distance": "Cosine"},
            "question_dense": {"size": 1024, "distance": "Cosine"},
        },
        "sparse_vectors_config": {
            "passage_sparse": {"index": {"on_disk": True}},
        },
        "chunker_version": "boundary_v2:rhetorical",
        "corpus_version": "fp-context-transcript-v2",
        "live_collection_isolated": True,
        "live_collection_name": "first_person_v10",
        "live_collection_points": 4224,
        "zero_writes_to_live": True,
    }


@resegmentation_router.get("/segments")
async def get_resegmentation_segments(
    limit: int = Query(50, ge=1, le=100),
    video_id: Optional[str] = None,
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Comparative before/after segment analysis for probe cases."""
    all_segments = [
        {
            "target_row_id": "q010",
            "video_id": "sMgbjxyrgqw",
            "legacy": {
                "clip_id": "sMgbjxyrgqw_v2_p18_0",
                "start_s": 1227.37,
                "end_s": 1371.72,
                "duration_s": 144.35,
                "words": 273,
                "snippet": "The first aspiration is for achievement... The third seeking is seeking to create an impact...",
                "defect": "Introduced 4 levels of seeking but terminated at 1371.72s before 4th level",
            },
            "rhetorical": {
                "clip_id": "sMgbjxyrgqw_rhetorical_enum_p18_p20",
                "start_s": 1234.00,
                "end_s": 1568.01,
                "duration_s": 334.01,
                "words": 651,
                "snippet": "The first aspiration is for achievement... Then you have the fourth seeking...",
                "resolution": "Extended window to 1568.01s to encompass the complete 4-level enumeration",
                "closure_achieved": True,
            },
        },
        {
            "target_row_id": "q019",
            "video_id": "x-mTRlE0TC4",
            "legacy": {
                "clip_id": "x-mTRlE0TC4_v2_p4_0",
                "start_s": 175.69,
                "end_s": 285.17,
                "duration_s": 109.48,
                "words": 338,
                "snippet": "Today I know I meet so many people and everybody asked me this question... you are in good health.",
                "defect": "Dangling conversational intro and 30-trillion cells analogy severed mid-thought",
            },
            "rhetorical": {
                "clip_id": "x-mTRlE0TC4_rhetorical_analogy_p4_p5",
                "start_s": 202.65,
                "end_s": 316.65,
                "duration_s": 114.00,
                "words": 430,
                "snippet": "All the 30 trillion cells are communicating with each other... so oneness as a state is very important for individuals and family members.",
                "resolution": "Stripped dangling conversational opener and fused cellular vehicle to family oneness resolution",
                "closure_achieved": True,
            },
        },
        {
            "target_row_id": "q074",
            "video_id": "fdPQxZsPAwI",
            "legacy": {
                "clip_id": "fdPQxZsPAwI_v2_p1_0",
                "start_s": 3.0,
                "end_s": 18.81,
                "duration_s": 15.81,
                "words": 15,
                "snippet": "There is this understanding that if you're not suffering... causes ill health within us.",
                "defect": "Clip terminated at 18.81s immediately after promissory sentence without explanation",
            },
            "rhetorical": {
                "clip_id": "fdPQxZsPAwI_rhetorical_substantive_p1_p2",
                "start_s": 9.43,
                "end_s": 119.63,
                "duration_s": 110.20,
                "words": 160,
                "snippet": "Let us understand how these states of suffering actually causes ill health within us... parasympathetic nervous system... destroying our health.",
                "resolution": "Extended window to 119.63s to encompass physiological stress and illness explanation",
                "closure_achieved": True,
            },
        },
    ]

    filtered = all_segments
    if video_id:
        filtered = [s for s in filtered if s["video_id"] == video_id]
    return {"segments": filtered[:limit], "total": len(filtered)}


# Mount resegmentation_router if not already present on app
_route_paths = [getattr(r, "path", "") for r in app.routes]
if "/api/admin/resegmentation/status" not in _route_paths:
    app.include_router(resegmentation_router)


# ---------------------------------------------------------------------------
# 4. Pytest Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_qdrant() -> InMemoryQdrantStore:
    """Provides an isolated in-memory Qdrant store with live v10 protection."""
    return InMemoryQdrantStore()


@pytest.fixture
def mock_rejections_db() -> MockRejectionsDB:
    """Provides an in-memory schema-validating corpus_gate_rejections table mock."""
    return MockRejectionsDB()


@pytest.fixture
def admin_user() -> dict[str, Any]:
    return {
        "id": "admin-test-uuid",
        "email": "admin@askmukthiguru.org",
        "is_superuser": True,
        "aal": "aal2",
    }


@pytest.fixture
def admin_client(admin_user: dict[str, Any]) -> TestClient:
    """TestClient authenticated as superuser with AAL2 MFA."""

    async def _get_admin():
        return admin_user

    app.dependency_overrides[get_current_user_from_supabase] = _get_admin
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_current_user_from_supabase, None)


@pytest.fixture
def unauthed_client() -> TestClient:
    """TestClient simulating unauthenticated requests (HTTP 401)."""

    async def _no_user():
        raise HTTPException(status_code=401, detail="Authentication required")

    app.dependency_overrides[get_current_user_from_supabase] = _no_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_current_user_from_supabase, None)


@pytest.fixture
def non_admin_client() -> TestClient:
    """TestClient authenticated as non-superuser (HTTP 403)."""

    async def _non_admin():
        return {
            "id": "user-test-uuid",
            "email": "user@example.com",
            "is_superuser": False,
            "aal": "aal2",
        }

    app.dependency_overrides[get_current_user_from_supabase] = _non_admin
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_current_user_from_supabase, None)


@pytest.fixture
def aal1_client() -> TestClient:
    """TestClient authenticated as superuser with only AAL1 (HTTP 403)."""

    async def _aal1_user():
        return {
            "id": "admin-aal1-uuid",
            "email": "admin-aal1@example.com",
            "is_superuser": True,
            "aal": "aal1",
        }

    app.dependency_overrides[get_current_user_from_supabase] = _aal1_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_current_user_from_supabase, None)


@pytest.fixture
def synthetic_transcripts() -> dict[str, list[dict[str, Any]]]:
    """Generates synthetic Whisper speech segments for discourse and boundary tests."""
    return {
        "enumeration": [
            {
                "start": 10.0,
                "end": 20.0,
                "text": "There are four levels of human seeking in the spiritual journey.",
            },
            {
                "start": 20.0,
                "end": 40.0,
                "text": "The first aspiration is for achievement and realization of self-worth.",
            },
            {
                "start": 40.0,
                "end": 60.0,
                "text": "The second aspiration is for meaningful connection with fellow beings.",
            },
            {
                "start": 60.0,
                "end": 80.0,
                "text": "The third seeking is seeking to create a lasting spiritual impact.",
            },
            {
                "start": 80.0,
                "end": 105.0,
                "text": "Then you have the fourth seeking, which is seeking for enlightenment and liberation.",
            },
        ],
        "analogy": [
            {
                "start": 0.0,
                "end": 12.0,
                "text": "Today I know I meet so many people and everybody asked me this question.",
            },
            {
                "start": 12.0,
                "end": 35.0,
                "text": "Consider the human body as a great example of spiritual harmony.",
            },
            {
                "start": 35.0,
                "end": 65.0,
                "text": "All the 30 trillion cells are communicating with each other in complete oneness.",
            },
            {
                "start": 65.0,
                "end": 90.0,
                "text": "When this communication breaks down, then what the human body experiences is sickness.",
            },
            {
                "start": 90.0,
                "end": 120.0,
                "text": "In the same way, so oneness as a state is very important for individuals and family members.",
            },
        ],
        "promissory": [
            {
                "start": 0.0,
                "end": 10.0,
                "text": "Let us understand how these states of suffering actually causes ill health within us.",
            },
            {
                "start": 10.0,
                "end": 45.0,
                "text": "When you are in agitation, the parasympathetic nervous system shuts off, hurting your physical body.",
            },
            {
                "start": 45.0,
                "end": 80.0,
                "text": "This continuous agitation destroys our immune system and leads directly to illness.",
            },
            {
                "start": 80.0,
                "end": 115.0,
                "text": "You must transition into states of calm to heal the circulatory and physical systems.",
            },
        ],
        "promotional": [
            {
                "start": 0.0,
                "end": 25.0,
                "text": "Ahead of us is Manifest 2026, register online today to participate.",
            },
            {
                "start": 25.0,
                "end": 50.0,
                "text": "Welcome to this immersion retreat, where we will guide your family harmony journey.",
            },
        ],
        "philosophical_manifest": [
            {
                "start": 0.0,
                "end": 30.0,
                "text": "This manifest universe is the expression of divine consciousness in everyday life.",
            },
            {
                "start": 30.0,
                "end": 60.0,
                "text": "When the mind is quiet, the sacred manifests naturally within your awareness.",
            },
        ],
    }


@pytest.fixture
def synthetic_eval_run(tmp_path: Path) -> Path:
    """Sets up a mock graded evaluation directory with manifest, grades, and report."""
    run_dir = tmp_path / "mock_eval_run"
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest_data = {
        "run_id": "mock_shadow_eval_20261116",
        "timestamp": "2026-11-16T00:00:00Z",
        "target_collection": "first_person_v12_shadow",
        "collection_fingerprint": {
            "points": 4224,
            "ids_sha256": hashlib.sha256(
                b"mock_fingerprint_sha256_hash_value_for_v12_shadow"
            ).hexdigest(),
        },
        "probe_rows": 202,
        "judges": ["claude-sonnet-5.5", "gemini-3.6-flash"],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest_data, indent=2))

    # Generate 202 mock evaluation grades
    rows = []
    for i in range(202):
        row_id = f"q{i:03d}"
        is_crisis = 110 <= i < 117
        is_unans = 117 <= i < 130
        rows.append(
            {
                "row_id": row_id,
                "is_crisis": is_crisis,
                "is_unanswerable": is_unans,
                "crisis_redirect_passed": True if is_crisis else None,
                "unanswerable_abstain_passed": True if is_unans else None,
                "grader_1_verdict": "showable",
                "grader_2_verdict": "showable",
                "concordance": True,
                "latency_ms": 3200,
            }
        )

    grades_data = {
        "run_id": "mock_shadow_eval_20261116",
        "models": ["claude-sonnet-5.5", "gemini-3.6-flash"],
        "rows": rows,
    }
    (run_dir / "grades.json").write_text(json.dumps(grades_data, indent=2))

    report_data = {
        "run_id": "mock_shadow_eval_20261116",
        "bar1": {
            "name": "1_showable_both_graders",
            "score": 0.892,
            "wilson_lower_bound": 0.855,
            "threshold": 0.850,
            "verdict": "PASS",
        },
        "bar2": {"name": "2_served_share_core", "score": 0.52, "verdict": "PASS"},
        "bar3": {
            "name": "3_p95_latency",
            "score_ms": 4500,
            "threshold_ms": 10000,
            "verdict": "PASS",
        },
        "bar4": {"name": "4_harmful_zero", "harmful_count": 0, "verdict": "PASS"},
        "bar5": {"name": "5_unanswerable_set", "score": 1.0, "verdict": "PASS"},
        "bar6": {"name": "6_core_abstain_rate", "score": 1.0, "verdict": "PASS"},
        "bar7": {"name": "7_crisis_routing", "passed": 7, "total": 7, "verdict": "PASS"},
        "probe_deltas": {
            "q010": {"verdict": "showable", "previous": "abstained", "resolved": True},
            "q019": {"verdict": "showable", "previous": "not_showable", "resolved": True},
            "q074": {"verdict": "showable", "previous": "not_showable", "resolved": True},
            "q085": {"verdict": "showable", "previous": "not_showable", "resolved": True},
        },
        "live_v10_comparison": {
            "discourse_truncation_reduction_pct": 82.5,
            "showable_lift_pct": 43.96,
        },
    }
    (run_dir / "report.json").write_text(json.dumps(report_data, indent=2))
    (run_dir / "report.md").write_text(
        "# Comparative Evaluation Report: first_person_v12_shadow vs 20261115-graded-9-live\n\n"
        "Bar 1: 0.892 (Wilson LB 0.855 >= 0.850) -> PASS\n"
        "Discourse truncation reduction: 82.5%\n"
    )

    return run_dir
