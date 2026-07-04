from unittest.mock import MagicMock, patch
import pytest
import time
from ingest.pipeline import IngestionCheckpoint

def test_checkpoint_redis_primary():
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    
    with patch("redis.from_url", return_value=mock_redis), \
         patch("app.config.settings.redis_url", "redis://localhost:6379/0"):
        
        checkpoint = IngestionCheckpoint()
        assert checkpoint.redis_client is not None
        assert checkpoint.supabase_client is None
        
        # Test save and check via Redis
        checkpoint.save("chunk_123", {"timestamp": 12345})
        mock_redis.set.assert_called_once()
        
        checkpoint.is_processed("chunk_123")
        mock_redis.exists.assert_called_once()

def test_checkpoint_supabase_fallback():
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    
    # Mock Redis failure, but Supabase active
    with patch("redis.from_url", side_effect=Exception("Redis down")), \
         patch("supabase.create_client", return_value=mock_supabase), \
         patch("app.config.settings.redis_url", "redis://localhost:6379/0"), \
         patch("app.config.settings.supabase_url", "http://localhost:54321"), \
         patch("app.config.settings.supabase_key", "service-key"):
        
        checkpoint = IngestionCheckpoint()
        assert checkpoint.redis_client is None
        assert checkpoint.supabase_client is not None
        
        # Test save to Supabase
        checkpoint.save("chunk_abc", {"timestamp": 54321})
        mock_supabase.table.assert_called_with("ingestion_checkpoints")
        mock_table.upsert.assert_called_once()
        
        # Test check processed on Supabase
        mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"chunk_id": "chunk_abc"}])
        processed = checkpoint.is_processed("chunk_abc")
        assert processed is True

def test_checkpoint_json_fallback(tmp_path):
    checkpoint_file = tmp_path / "ingest_checkpoint.json"
    
    # Mock both failure
    with patch("redis.from_url", side_effect=Exception("Redis down")), \
         patch("supabase.create_client", side_effect=Exception("Supabase down")):
        
        checkpoint = IngestionCheckpoint(filepath=str(checkpoint_file))
        assert checkpoint.redis_client is None
        assert checkpoint.supabase_client is None
        
        # Test save to JSON
        checkpoint.save("chunk_xyz", {"timestamp": 9999})
        assert checkpoint_file.exists()
        
        # Test check processed on JSON
        processed = checkpoint.is_processed("chunk_xyz")
        assert processed is True
        
        processed_not_existing = checkpoint.is_processed("chunk_missing")
        assert processed_not_existing is False
