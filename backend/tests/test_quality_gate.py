from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ingest.quality_gate import DataQualityGate
from services.doctrine_service import DoctrineService
from services.okf_quality_filter import OKFQualityFilter
from tasks.ingest_tasks import ingest_playlist, playlist_complete


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    # Mock return for quality score grading
    llm.generate.return_value = '{"score": 85, "reasons": ["Excellent educational content"]}'
    return llm

@pytest.fixture
def mock_supabase():
    client = MagicMock()
    # Mock insert/execute returns
    mock_execute = MagicMock()
    mock_execute.data = [{"id": "mock-job-id"}]
    client.table.return_value.insert.return_value.execute.return_value = mock_execute
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_execute
    client.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_execute
    return client

@pytest.mark.asyncio
async def test_data_quality_gate_pass(mock_llm, mock_supabase):
    gate = DataQualityGate(
        llm_service=mock_llm,
        supabase_client=mock_supabase,
        quality_threshold=70,
        enabled=True
    )
    long_spiritual_text = (
        "This is a highly spiritual teaching about meditation, focus, and inner peace. "
        "Let us settle into quiet observation and find our true alignment. "
        "We want to feel oneness with all that is, releasing any suffering states "
        "and resting in a beautiful state of consciousness."
    )
    result = await gate.run(long_spiritual_text, source_url="https://youtube.com/watch?v=123")
    assert result.passed is True
    assert result.score == 91
    assert "reasons" in result.__dict__

@pytest.mark.asyncio
async def test_data_quality_gate_fail_repetition(mock_llm, mock_supabase):
    gate = DataQualityGate(
        llm_service=mock_llm,
        supabase_client=mock_supabase,
        quality_threshold=70,
        enabled=True
    )
    # Text with high repetition to trigger the n-gram filter (deterministic fail)
    repetitive_text = (
        "meditation peace meditation peace meditation peace meditation peace meditation peace "
        "meditation peace meditation peace meditation peace meditation peace meditation peace "
        "meditation peace meditation peace meditation peace meditation peace meditation peace "
        "meditation peace meditation peace meditation peace meditation peace meditation peace"
    )
    result = await gate.run(repetitive_text, source_url="https://youtube.com/watch?v=123")
    assert result.passed is False
    assert result.score == 0
    assert any("repetitive" in r.lower() for r in result.reasons)

@pytest.mark.asyncio
async def test_okf_quality_filter():
    # Valid entry — provenance is mandatory: every OKF claim is cited to the seeker.
    valid, reason = OKFQualityFilter.validate_entry({
        "title": "Beautiful State",
        "type": "concept",
        "source": "Beautiful State — Sri Preethaji (YouTube TqxxCYnAxo8)",
        "body": "This is a very long body containing teachings of Sri Preethaji that exceeds one hundred characters easily."
    })
    assert valid is True, reason

    # Invalid entry
    invalid, reason = OKFQualityFilter.validate_entry({
        "title": "",
        "type": "concept",
        "body": "Short body"
    })
    assert invalid is False

    # Uncitable entry — no source means format_final_answer cannot attribute it.
    uncitable, reason = OKFQualityFilter.validate_entry({
        "title": "Sacred Secrets",
        "type": "teaching",
        "body": "A sufficiently long body about the teachings of Sri Preethaji and Sri Krishnaji, well past one hundred characters.",
    })
    assert uncitable is False and "source" in reason.lower()

    # Extraction artifact — the LLM's own prompt commentary must never be served as doctrine.
    leaked, reason = OKFQualityFilter.validate_entry({
        "title": "Sacred Secrets",
        "type": "teaching",
        "source": "auto-extracted from Qdrant (6 chunks)",
        "body": "The user wants me to analyze a spiritual teaching and list the top 3-5 distinct topics discussed in this long text.",
    })
    assert leaked is False and "leakage" in reason.lower()

@pytest.mark.asyncio
async def test_doctrine_service(mock_supabase):
    # Mock select return
    mock_execute = MagicMock()
    mock_execute.data = [{
        "synonyms_json": {
            "Beautiful State": ["beautiful state", "blissful state"],
            "Soul Sync": ["soul sync", "meditation sync"]
        },
        "canonical_terms": ["Beautiful State", "Soul Sync"]
    }]
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_execute

    service = DoctrineService(supabase_client=mock_supabase)
    
    # Test query enhancement
    enhanced = await service.inject_doctrine_keywords("I want to experience the blissful state", "preethaji_krishnaji")
    assert "Beautiful State" in enhanced
    
    # If already contains canonical, do not double-inject
    enhanced_dup = await service.inject_doctrine_keywords("I want to experience the Beautiful State", "preethaji_krishnaji")
    assert enhanced_dup.strip() == "I want to experience the Beautiful State"

@patch("tasks.ingest_tasks.orchestrate_ingestion")
@patch("ingest.youtube_loader.get_playlist_video_urls")
def test_ingest_playlist_chord(mock_get_urls, mock_orchestrate, mock_supabase):
    mock_get_urls.return_value = [
        {"url": "https://youtube.com/watch?v=v1", "title": "Video 1"},
        {"url": "https://youtube.com/watch?v=v2", "title": "Video 2"}
    ]
    
    with patch("celery.app.task.Task.update_state"), \
         patch("celery.chord", return_value=MagicMock()), \
         patch("tasks.ingest_tasks.update_job_progress") as mock_update, \
         patch("app.config.settings") as mock_settings, \
         patch("supabase.create_client") as mock_create_client:
        
        mock_create_client.return_value = mock_supabase
        
        # Call ingest_playlist
        res = ingest_playlist("https://youtube.com/playlist?list=123", tags=["spiritual"], job_id="parent-job")
        
        assert res["status"] == "queued"
        assert res["video_count"] == 2
        
        # Verify Supabase client was called to create child jobs
        assert mock_supabase.table.call_count > 0

def test_playlist_complete(mock_supabase):
    results = [
        {"status": "success", "indexing": {"count": 12}},
        {"status": "success", "indexing": {"count": 8}},
        {"status": "rejected"}
    ]
    
    with patch("tasks.ingest_tasks.update_job_progress") as mock_update:
        res = playlist_complete(results, "https://youtube.com/playlist?list=123", parent_job_id="parent-job", total_count=3)
        assert res["status"] == "success"
        assert res["success"] == 2
        assert res["rejected"] == 1
        assert res["chunks_indexed"] == 20
        
        # Verify parent job completion update
        mock_update.assert_called_once_with(
            "parent-job",
            "completed",
            progress_pct=100,
            chunks_indexed=20,
            error_message=None
        )
