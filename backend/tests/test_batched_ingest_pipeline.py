"""Contract test for the currently supported raw-text ingestion API.

The former one-off transcript download/upload scripts were removed from the
repository. Keep this test focused on the supported ingestion contract rather
than importing deleted scripts at collection time.
"""

from app.api.ingest import IngestRequest, IngestResponse
from pydantic import ValidationError
import pytest


def test_ingest_request_accepts_supported_youtube_payload():
    request = IngestRequest(
        url="https://www.youtube.com/watch?v=abc12345678",
        max_accuracy=True,
        tags=["wisdom", "meditation"],
    )
    assert request.url == "https://www.youtube.com/watch?v=abc12345678"
    assert request.max_accuracy is True
    assert request.tags == ["wisdom", "meditation"]


def test_ingest_request_rejects_missing_url():
    with pytest.raises(ValidationError):
        IngestRequest()


def test_ingest_response_preserves_async_job_contract():
    response = IngestResponse(
        status="processing",
        message="Ingestion queued",
        source_url="https://www.youtube.com/watch?v=abc12345678",
        job_id="job-123",
    )
    assert response.status == "processing"
    assert response.job_id == "job-123"
    assert response.chunks_indexed == 0
    assert response.summaries_created == 0
