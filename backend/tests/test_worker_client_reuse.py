from types import SimpleNamespace


def test_worker_embedding_service_is_cached(monkeypatch):
    import services.embedding_service as embedding_module
    import tasks.ingest_tasks as task_module

    created = []

    class FakeEmbeddingService:
        def __init__(self):
            created.append(self)

    monkeypatch.setattr(embedding_module, "EmbeddingService", FakeEmbeddingService)
    task_module._worker_embedding_service = None
    try:
        first = task_module._get_worker_embedding_service()
        second = task_module._get_worker_embedding_service()
        assert first is second
        assert len(created) == 1
    finally:
        task_module._worker_embedding_service = None


def test_worker_qdrant_client_is_cached_and_bounded(monkeypatch):
    import qdrant_client
    import tasks.ingest_tasks as task_module

    created = []

    class FakeQdrantClient:
        def __init__(self, **kwargs):
            created.append(SimpleNamespace(kwargs=kwargs))

    monkeypatch.setattr(qdrant_client, "QdrantClient", FakeQdrantClient)
    monkeypatch.setenv("QDRANT_URL", "http://qdrant.test:6333")
    monkeypatch.setenv("QDRANT_TIMEOUT", "30")
    task_module._worker_qdrant_client = None
    try:
        first = task_module._get_worker_qdrant_client()
        second = task_module._get_worker_qdrant_client()
        assert first is second
        assert len(created) == 1
        assert created[0].kwargs["check_compatibility"] is False
        assert created[0].kwargs["timeout"] == 30.0
    finally:
        task_module._worker_qdrant_client = None
