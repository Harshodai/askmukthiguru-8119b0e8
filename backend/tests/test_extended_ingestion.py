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

    mock_doc = MagicMock()
    mock_page = MagicMock()
    mock_page.get_text.return_value = "Spiritual teachings text from PDF"
    mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))

    with patch("requests.get") as mock_get, \
         patch("fitz.open", return_value=mock_doc) as mock_fitz_open, \
         patch.object(pipeline._auditor, "run", new=AsyncMock(return_value=MagicMock(passed=True, score=85, reasons=[]))) as mock_auditor:
        mock_get.return_value.iter_content.return_value = [b"PDF_CONTENT"]
        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status = MagicMock()

        res = await pipeline.ingest_url("https://example.com/wisdom.pdf", max_accuracy=True)
        assert res["status"] == "success"
        pipeline.ingest_raw_text.assert_called_once()
        assert pipeline.ingest_raw_text.call_args[1]["content_type"] == "pdf"
        assert pipeline.ingest_raw_text.call_args[1]["max_accuracy"] is True

@pytest.mark.asyncio
async def test_web_page_scraping_routing():
    mock_qdrant = MagicMock()
    mock_embed = MagicMock()
    mock_ollama = MagicMock()
    
    pipeline = IngestionPipeline(mock_qdrant, mock_embed, mock_ollama)
    pipeline.ingest_raw_text = AsyncMock(return_value={"status": "success", "chunks_indexed": 3})

    with patch("requests.get") as mock_get, \
         patch.object(pipeline._auditor, "run", new=AsyncMock(return_value=MagicMock(passed=True, score=85, reasons=[]))) as mock_auditor:
        html = b"<html><head><title>Zen</title></head><body><h1>Wisdom</h1><p>Let go.</p></body></html>"
        mock_get.return_value.content = html
        mock_get.return_value.status_code = 200
        mock_get.return_value.iter_content.return_value = [html]

        res = await pipeline.ingest_url("https://example.com/zen-blog", max_accuracy=True)
        assert res["status"] == "success"
        pipeline.ingest_raw_text.assert_called_once()
        assert pipeline.ingest_raw_text.call_args[1]["content_type"] == "web_article"
        assert pipeline.ingest_raw_text.call_args[1]["max_accuracy"] is True
