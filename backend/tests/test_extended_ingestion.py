import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from ingest.pipeline import IngestionPipeline

@pytest.mark.asyncio
async def test_pdf_ingestion_routing():
    mock_qdrant = MagicMock()
    mock_embed = MagicMock()
    mock_ollama = MagicMock()
    
    pipeline = IngestionPipeline(mock_qdrant, mock_embed, mock_ollama)
    pipeline.ingest_raw_text = AsyncMock(return_value={"status": "success", "chunks_indexed": 5})

    mock_pdf_reader = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Spiritual teachings text from PDF"
    mock_pdf_reader.pages = [mock_page]

    with patch("requests.get") as mock_get, \
         patch("pypdf.PdfReader", return_value=mock_pdf_reader):
        mock_get.return_value.content = b"PDF_CONTENT"
        mock_get.return_value.status_code = 200

        res = await pipeline.ingest_url("https://example.com/wisdom.pdf")
        assert res["status"] == "success"
        pipeline.ingest_raw_text.assert_called_once()
        assert pipeline.ingest_raw_text.call_args[1]["content_type"] == "pdf"

@pytest.mark.asyncio
async def test_web_page_scraping_routing():
    mock_qdrant = MagicMock()
    mock_embed = MagicMock()
    mock_ollama = MagicMock()
    
    pipeline = IngestionPipeline(mock_qdrant, mock_embed, mock_ollama)
    pipeline.ingest_raw_text = AsyncMock(return_value={"status": "success", "chunks_indexed": 3})

    with patch("requests.get") as mock_get:
        mock_get.return_value.content = b"<html><head><title>Zen</title></head><body><h1>Wisdom</h1><p>Let go.</p></body></html>"
        mock_get.return_value.status_code = 200

        res = await pipeline.ingest_url("https://example.com/zen-blog")
        assert res["status"] == "success"
        pipeline.ingest_raw_text.assert_called_once()
        assert pipeline.ingest_raw_text.call_args[1]["content_type"] == "web_article"
