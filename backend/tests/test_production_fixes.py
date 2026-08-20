from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from ingest.pipeline import IngestionCheckpoint, IngestionPipeline


def test_cache_config_settings():
    assert settings.semantic_cache_similarity == 0.90
    assert settings.semantic_cache_ttl == 604800
    assert settings.guardrails_llm_enabled is False


@pytest.mark.asyncio
async def test_proactive_serene_mind_dict_return(monkeypatch):
    from types import SimpleNamespace

    from app.pipeline.stages.distress_stage import DistressStage

    container = MagicMock()
    container.serene_mind = None
    container.user_profile = MagicMock()
    ctx = SimpleNamespace(container=container)

    stage = DistressStage()
    assessment = MagicMock()
    chat_body = MagicMock()
    state = {}

    result = await stage._maybe_trigger_proactive_serene_mind(
        ctx, assessment, "test-user", chat_body, state
    )
    assert isinstance(result, dict)
    assert result == {"triggered": False}


@pytest.mark.asyncio
async def test_persistent_distress_checks_trend_without_a_new_keyword():
    from types import SimpleNamespace

    from app.pipeline.stages.distress_stage import DistressStage
    from services.serene_mind_engine import DistressAssessment, DistressLevel

    stage = DistressStage()
    # Explicit no-distress assessment: level.value (0) is below the 2 trigger
    # threshold, so run() reaches the trend check via distress_history only.
    stage._detect_distress = AsyncMock(
        return_value=DistressAssessment(
            level=DistressLevel.NONE,
            confidence=0.0,
            detected_signals=[],
            recommended_response_type="normal",
        )
    )
    stage._maybe_trigger_proactive_serene_mind = AsyncMock(return_value={"triggered": False})
    ctx = SimpleNamespace(
        state={"user_msg_en": "I had tea", "distress_history": [{"score": 2}]},
        user_id="test-user",
        request=MagicMock(),
    )

    await stage.run(ctx)

    # M1 fix: assessment now runs every turn (was keyword-gated). The point of
    # this test — the trend check fires without a new keyword — still holds via
    # the proactive assertion below.
    stage._detect_distress.assert_awaited_once()
    stage._maybe_trigger_proactive_serene_mind.assert_awaited_once()


@pytest.mark.asyncio
async def test_ingestion_deduplication(tmp_path, monkeypatch):
    checkpoint_file = tmp_path / "ingest_checkpoint.json"

    # Mock IngestionCheckpoint load/save path
    def mock_init(self, filepath=checkpoint_file):
        from pathlib import Path

        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(exist_ok=True)
        self.data = self._load()
        self.processed_chunks = set(self.data.keys())

    monkeypatch.setattr(IngestionCheckpoint, "__init__", mock_init)

    qdrant = MagicMock()
    embedder = MagicMock()
    ollama = MagicMock()
    pipeline = IngestionPipeline(qdrant, embedder, ollama)
    pipeline._auditor.run = AsyncMock(return_value=MagicMock(passed=True, score=90, reasons=[]))

    pipeline._split_text = MagicMock(return_value=["chunk1", "chunk2"])
    pipeline._augment_chunks = AsyncMock(return_value=["aug1", "aug2"])
    pipeline._embed_and_index = MagicMock(return_value=2)
    pipeline._raptor.build_tree = AsyncMock(return_value=1)

    text = "Hello world! This is a comprehensive test spiritual teaching on the Beautiful State and inner stillness."

    res1 = await pipeline.ingest_raw_text(text, "url1", "title1")
    assert res1["status"] == "success"
    assert res1["chunks_indexed"] > 0

    res2 = await pipeline.ingest_raw_text(text, "url1", "title1")
    assert res2["status"] == "success"
    assert res2["chunks_indexed"] == 0
    assert "already processed" in res2["message"]


def test_hierarchical_split_sentence_boundaries():
    qdrant = MagicMock()
    embedder = MagicMock()
    ollama = MagicMock()

    import numpy as np

    embedder.encode = MagicMock(return_value=[np.array([0.1] * 128) for _ in range(3)])

    pipeline = IngestionPipeline(qdrant, embedder, ollama)

    text = "This is first sentence. This is second sentence. This is third sentence."
    child_texts, child_metadatas = pipeline._hierarchical_split(text, title="Test Title")

    assert len(child_texts) > 0
    for child in child_texts:
        assert "[Source: Test Title]" in child
        actual_text = child.split("]\n", 1)[1]
        assert actual_text.endswith(".") or actual_text.endswith("!") or actual_text.endswith("?")


@pytest.mark.asyncio
async def test_proactive_serene_mind_returns_teaching_first_consent_offer(monkeypatch):
    from types import SimpleNamespace

    from app.pipeline.stages.distress_stage import DistressStage
    from services.serene_mind_engine import DistressAssessment, DistressLevel

    stage = DistressStage()
    proactive = DistressAssessment(
        level=DistressLevel.MODERATE,
        confidence=0.82,
        detected_signals=["persistent distress"],
        language_detected="en",
        recommended_response_type="meditation",
    )

    profile = MagicMock()
    profile.get_last_meditation_session = AsyncMock(return_value=None)
    profile_service = MagicMock()
    profile_service.analyze_distress_trend = AsyncMock(return_value=proactive)
    serene = MagicMock()
    serene.analyze_distress_trend = AsyncMock(return_value=proactive)
    serene.get_response.return_value = "optional support"
    container = SimpleNamespace(serene_mind=serene, user_profile=profile)
    ctx = SimpleNamespace(container=container)

    result = await stage._maybe_trigger_proactive_serene_mind(
        ctx, proactive, "test-user", SimpleNamespace(last_serene_mind_at=0), {}
    )

    assert result["triggered"] is True
    assert result["requires_consent"] is True
    assert result["duration_seconds"] == 225
    assert result["offer_reason"]
    assert result["teachings_prelude"]
