"""
Mukthi Guru — Application Configuration

Uses Pydantic Settings for type-safe, validated configuration from .env files.
Implements the Singleton pattern via module-level instance for zero-cost DI.
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All application config, loaded from .env with sensible defaults.
    
    Design Pattern: Configuration-as-Code with Pydantic validation.
    Every setting is typed, documented, and env-overridable.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Ollama ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:latest"

    # --- Qdrant ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "spiritual_wisdom"
    qdrant_local_path: Optional[str] = None  # Set for local mode (no Docker)

    # --- Embeddings ---
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # --- Whisper ---
    whisper_model: str = "tiny"

    # --- OCR ---
    ocr_languages: str = "en,hi,te"

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:8080,http://localhost:3000"

    # --- RAPTOR ---
    raptor_cluster_size: int = 8
    raptor_summary_model: str = "llama3.2:latest"

    # --- RAG ---
    rag_top_k_retrieval: int = 20
    rag_top_k_rerank: int = 3
    rag_max_rewrites: int = 3
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 50

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        if not self.cors_origins or not self.cors_origins.strip():
            return []
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def ocr_languages_list(self) -> list[str]:
        """Parse comma-separated OCR languages into a list."""
        if not self.ocr_languages or not self.ocr_languages.strip():
            return []
        return [l.strip() for l in self.ocr_languages.split(",") if l.strip()]


@lru_cache()
def get_settings() -> Settings:
    """
    Cached settings factory.
    
    Design Pattern: Factory + Singleton via lru_cache.
    First call creates the Settings instance (reads .env),
    subsequent calls return the cached instance.
    """
    return Settings()


# Module-level convenience — import from anywhere:
# from app.config import settings
settings = get_settings()
