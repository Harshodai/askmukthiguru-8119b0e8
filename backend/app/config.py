"""
Mukthi Guru — Application Configuration

Uses Pydantic Settings for type-safe, validated configuration from .env files.
Implements the Singleton pattern via module-level instance for zero-cost DI.

Includes configs for:
  - Sarvam 30B (Indian multilingual LLM via Ollama)
  - faster-whisper (4x faster Whisper transcription)
  - Multi-language transcript extraction (10 Indian languages)
  - Concurrent playlist ingestion workers
"""

from __future__ import annotations

import os

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

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

    # --- LLM Provider ---
    # Set LLM_PROVIDER to switch between backends:
    #   "sarvam_cloud" → Sarvam Cloud API (recommended, free tier)  [DEFAULT]
    #   "ollama"       → Local Ollama (requires model downloads)
    llm_provider: str = "sarvam_cloud"

    # --- Model Preset (for Ollama mode only) ---
    # Set MODEL_PRESET to switch between Ollama model configurations:
    #   "qwen"    → Qwen3-30B-A3B (generation) + Qwen3-14B (classification)
    #   "sarvam"  → Sarvam 30B (generation) + llama3.2:3b (classification)   [Requires custom GGUF import]
    #   "custom"  → Use OLLAMA_MODEL + OLLAMA_CLASSIFY_MODEL below
    model_preset: str = "qwen"

    # --- Sarvam Cloud API ---
    sarvam_api_key: str = ""  # API subscription key from dashboard.sarvam.ai
    sarvam_cloud_model: str = "sarvam-30b"  # Main generation model — any Sarvam model works (sarvam-30b, sarvam-105b, sarvam-m)
    sarvam_cloud_classify_model: str = (
        "sarvam-30b"  # Classification model — can be same or different from generation model
    )
    sarvam_cloud_complex_model: str = "sarvam-105b"  # Optional long-context/complex-question model; runtime falls back if unavailable
    sarvam_complex_routing_enabled: bool = (
        False  # Enable only after account/model access is verified
    )
    sarvam_complex_context_chars: int = (
        20000  # Route long packed contexts to complex model when enabled
    )
    sarvam_base_url: str = (
        "https://api.sarvam.ai/v1"  # Sarvam API base URL (override for proxy/staging)
    )
    sarvam_reasoning_effort: str = "medium"  # Default reasoning effort for main generation (low | medium | high)
    sarvam_reasoning_effort_fast: str = "low"   # Effort for fast/classification calls (intent routing, grading)
    sarvam_reasoning_effort_complex: str = "high"  # Effort for complex multi-hop, CoVe, and deep-reasoning queries
    # Per-call HTTP timeout. Sarvam Cloud has a 30s server-side limit; Ollama tends to hang on
    # slow models. Must be smaller than pipeline_timeout. Individual LLM calls that exceed this
    # trigger retry logic in OllamaService.generate() (max_retries attempts with backoff).
    llm_timeout: int = 60
    # Total outer pipeline timeout — must comfortably exceed (llm_timeout × num_retries × num_calls).
    # With 8 sequential LLM calls at 10-20s each and up to 2 retries, 120s gives healthy headroom.
    pipeline_timeout: int = 180
    llm_max_retries: int = 2  # Max retry attempts per LLM call (exponential backoff starts at 0.5s)

    # --- Timeout Budget ---
    pipeline_timeout_budget: int = 300  # Total pipeline timeout budget in seconds
    node_timeout_fast: int = 20  # Default fast-model node timeout
    node_timeout_main: int = 90  # Default main-model node timeout

    serene_mind_enabled: bool = True  # Enable/disable Serene Mind distress detection engine

    # --- Feature Flags & Memory Layer ---
    feature_memory_enabled: bool = True
    feature_memory_write: bool = True
    feature_lightweight_classifier: bool = False   # Gemini Flash for fast nodes
    feature_regex_prerouter: bool = True
    node_model_overrides: dict[str, str] = {}
    graph_hard_deadline_s: float = 20.0   # DEAD CONFIG — not used by LangGraph, kept for compatibility

    # --- Safety Limits ---
    chat_history_max_messages: int = 20  # Cap conversation context to prevent OOM/timeouts
    max_input_length: int = 2000  # Max user message length in characters

    # --- Guardrails ---
    # Provider: "nemo" (NeMo Guardrails), "lightweight" (regex-based), "disabled"
    guardrails_provider: str = "nemo"  # Falls back to lightweight if NeMo unavailable
    guardrails_audit_enabled: bool = True  # Structured audit logging for blocked requests

    # --- Ollama (local mode) ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""  # Auto-set by preset, or override with MODEL_PRESET=custom
    ollama_classify_model: str = ""  # Auto-set by preset, or override with MODEL_PRESET=custom
    sarvam_model_name: str = "sarvam-30b:latest"  # Explicit Sarvam reference for scripts

    # --- OpenRouter (free tier for simple queries) ---
    openrouter_api_key: str = ""  # Optional: free tier works without key for some models
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_fast_model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct"
    openrouter_generation_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    openrouter_classify_model: str = "meta-llama/llama-3.2-3b-instruct:free"
    use_openrouter_for_simple: bool = True
    openrouter_rpm_limit: int = 20

    # --- Qdrant ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "spiritual_wisdom"

    # --- Supabase (Docker Local) ---
    supabase_url: str = "http://host.docker.internal:54321"
    supabase_key: str = ""  # SERVICE_ROLE_KEY for backend write access
    qdrant_local_path: Optional[str] = None  # Set for local mode (no Docker)

    # --- Neo4j ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    # --- Embeddings (config-driven: switch models via env vars) ---
    # Supported: "BAAI/bge-m3" (default, best multilingual, 1024-dim dense+sparse+ColBERT)
    #            "intfloat/multilingual-e5-large" (alternative multilingual, 1024-dim)
    #            "sentence-transformers/all-MiniLM-L6-v2" (English-only, 384-dim, fast)
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # --- Whisper / Transcription ---
    whisper_model: str = "large-v3"  # Whisper model size
    whisper_backend: str = (
        "faster-whisper"  # Backend: 'faster-whisper' (4x faster) or 'openai-whisper'
    )
    whisper_compute_type: str = "float16"  # GPU: float16, CPU: int8 or float32
    whisper_local_model: str = "mlx-community/whisper-large-v3-turbo"
    whisper_local_device: str = "mps"

    # --- Transcript Extraction ---
    transcript_languages: str = (
        "en,hi,bn,te,mr,ta,ur,gu,kn,ml,or,pa,as,mai,sa,ks,ne,sd,kok,doi,mni,sat,brx"
    )
    transcript_max_retries: int = 3  # Retry per tier before falling to next
    transcript_concurrent_workers: int = 1  # Kept at 1 to avoid YouTube 429 rate limits

    # --- Transcript Council (Dual-STT Quality Check) ---
    # When enabled: fetches captions AND runs Sarvam STT on audio, then picks best result.
    enable_transcript_council: bool = True  # Run both YouTube captions + Sarvam STT per video
    sarvam_stt_model: str = "saaras:v3"  # Sarvam Batch STT model
    sarvam_stt_mode: str = "transcribe"  # Options: transcribe, codemix, translate
    sarvam_stt_language: str = "en-IN"  # Language hint (en-IN for English w/ Indian accent)
    stt_chunk_minutes: int = 55  # Chunk long audio into N-minute pieces (Batch API max 1hr)
    stt_max_audio_mb: int = 200  # Skip STT if audio file exceeds this size (MB)

    # --- OCR ---
    ocr_languages: str = "en,hi"

    # --- Data Quality ---
    data_audit_enabled: bool = True  # Enable LLM-based quality checks

    # --- Redis ---
    # Default uses 'redis' resolving inside Docker Compose. For local non-docker dev, override with REDIS_URL=redis://localhost:6379/0 via .env
    redis_url: str = "redis://redis:6379/0"

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:8080,http://localhost:3000"
    # --- Security ---
    csrf_secret: Optional[str] = (
        None  # Secret for CSRF token signing (generate with secrets.token_hex(32))
    )
    csrf_token_ttl: int = 3600  # CSRF token lifetime in seconds
    correlation_id_max_length: int = 64  # Max length for X-Correlation-ID header
    allowed_hosts: str = "localhost,127.0.0.1"  # Trusted hosts for Origin/Referer validation

    # --- Auth & Rate Limiting ---
    # Default to PRODUCTION (secure-by-default). Override with IS_PRODUCTION=false for local dev only.
    is_production: bool = True
    # Explicit opt-in for the X-Test-Key backdoor strategy. NEVER enable in production.
    enable_test_auth: bool = False
    jwt_secret: Optional[str] = None  # Shared with Supabase for token validation
    supabase_jwt_audience: str = "authenticated"
    benchmark_secret: Optional[str] = None
    # Default to disabled: the frontend uses Supabase auth, so the FastAPI
    # /api/auth/register endpoint has no legitimate public use case and would
    # otherwise expose an email-enumeration surface. Override with the
    # DISABLE_PUBLIC_REGISTRATION env var only for explicit internal flows.
    disable_public_registration: bool = True
    chat_rate_limit: str = "20/minute"
    registration_rate_limit: str = "5/minute"
    admin_rate_limit: str = "5/minute"

    # --- RAPTOR ---
    raptor_cluster_size: int = 8
    raptor_summary_model: str = ""  # Auto-set from model_preset

    # --- RAG ---
    rag_top_k_retrieval: int = 30
    rag_top_k_rerank: int = 10
    rag_max_rewrites: int = 1
    rag_chunk_size: int = 1500
    rag_chunk_overlap: int = 200
    rag_use_hyde: bool = True
    rag_context_window: int = 2  # Fetch N chunks before/after each retrieved chunk
    rerank_min_score: float = 0.35  # Min CrossEncoder score (sigmoid-normalized) to keep a doc
    rag_use_context_compression: bool = False  # Set to True to enable LLM-based context compression
    rag_context_compression_threshold: int = (
        10000  # Only compress context if character length exceeds this threshold
    )
    # MMR (Maximal Marginal Relevance) diversity re-ranking
    rag_mmr_lambda: float = 0.5  # Balance between relevance and diversity (0=diversity, 1=relevance)
    max_tokens_per_request: int = 12000  # Maximum tokens per LLM request (covers persona+knowledge+history+instructions)

    # --- FlashRank Reranking & Ingestion Service Config ---
    use_flashrank: bool = True
    flashrank_model: str = "auto"
    use_adaptive_chunking: bool = True
    adaptive_chunking_min_chars: int = 5000
    use_proposition_chunking: str = "auto"
    proposition_char_limit: int = 15000

    # --- Semantic Cache ---
    semantic_cache_enabled: bool = True  # Embedding-based semantic caching
    semantic_cache_similarity: float = 0.92  # Cosine similarity threshold for cache hit
    semantic_cache_ttl: int = 604800  # Cache TTL in seconds (7 days)
    guardrails_llm_enabled: bool = False  # Toggle LLM-based guardrail checks

    # --- User Profiles & Persistence ---
    user_profile_enabled: bool = True  # Enable user profiles and persistent memory
    krutrim_api_key: str = ""  # Fallback Indian LLM provider

    # --- Proactive Serene Mind ---
    proactive_serene_mind_enabled: bool = True
    proactive_distress_avg_threshold: float = 1.5  # Minimum average distress to consider
    proactive_distress_trend_threshold: float = 0.5  # Minimum escalation rate
    proactive_distress_frequency_threshold: float = 0.6  # Minimum frequency of moderate+
    proactive_min_conversation_points: int = 3  # Minimum data points needed

    # --- A/B Testing ---
    ab_testing_enabled: bool = False  # Randomly switch between primary LLM and Krutrim
    ab_testing_ratio: float = 0.1  # 10% traffic to Krutrim

    # --- Web Search (Real-Time Temporal Queries) ---
    web_search_enabled: bool = False  # Enable temporal web search for real-time queries
    web_search_provider: str = "duckduckgo"  # "duckduckgo" | "searxng"
    web_search_allowed_domains: str = "ekam.org,theonenessmovement.org"
    web_search_max_results: int = 5
    web_search_timeout: int = 10  # Web search timeout in seconds
    web_search_parallel: bool = True  # Run web search in parallel with RAG retrieval
    searxng_url: str = "http://searxng:8080"  # Self-hosted SearXNG instance URL

    # --- Observability ---
    enable_correlation_ids: bool = True  # Add UUID correlation IDs to all logs/traces

    # --- Meditation Routing (Phase A bug fixes — see .claude/tasks/WORLD_CLASS_MUKTHIGURU.md) ---
    # Number of guided steps in the canonical Serene Mind meditation flow.
    # Source of truth is rag.prompts.MEDITATION_STEPS; this setting allows runtime override
    # without touching code and is referenced by rag.meditation.MAX_STEP.
    meditation_max_step: int = 4
    # First step number in a meditation flow (always 1, but exposed for future variants).
    meditation_start_step: int = 1
    # If True (default), an LLM-classified MEDITATION intent is demoted to FACTUAL whenever
    # the user message reads as an interrogative ("can I ...?", "what is ...?") AND no
    # active meditation session is in progress. This kills the "Soul Sync on Mars" hijack
    # where adversarial / interrogative queries containing meditation nouns were being
    # routed into the meditation flow with step=0, returning the misleading literal
    # "The meditation is complete. Thank you for practicing with me." string.
    intent_demote_meditation_on_interrogative: bool = True
    # When handle_meditation is invoked with step<=0 and no script keyword in the query
    # (i.e. the user did not actually ask to begin a meditation), the fallback behaviour
    # is to demote to FACTUAL via the answer wrapper rather than emit a misleading
    # "meditation is complete" string. Setting this to False reverts to the old behaviour.
    meditation_safe_fallback: bool = True

    # --- LLM Gateway (Phase A7 — unified provider chain via emergentintegrations) ---
    # When llm_provider == "emergent", the LLMGateway uses the emergentintegrations
    # library and picks a model from the comma-separated chain in
    # `llm_provider_chain`. Format: "provider:model,provider:model,..."
    # Example: "anthropic:claude-sonnet-4-6,anthropic:claude-haiku-4-5-20251001,openai:gpt-5.4"
    # The gateway tries each in order on transient failure. NEVER hardcode model names
    # in service code; always read from settings.
    emergent_llm_key: str = ""  # Universal key, prefix sk-emergent-...
    llm_provider_chain: str = (
        "anthropic:claude-sonnet-4-6,"
        "anthropic:claude-haiku-4-5-20251001,"
        "openai:gpt-5.4"
    )
    llm_gateway_streaming_default: bool = True
    llm_gateway_session_prefix: str = "mukthi-guru"
    llm_gateway_max_tokens: int = 4096
    llm_gateway_request_timeout_s: int = 60

    # --- Persona controls (Phase B — guru voice quality) ---
    # When True, the generation node strips the canned "*Note: Based on what I found...*"
    # footer that was breaking immersion. The context-aware close is generated dynamically
    # from the intent + citation count instead.
    strip_canned_footer: bool = True
    # Maximum paragraphs in a single answer (cadence control).
    persona_max_paragraphs: int = 4
    # Maximum words in a single sentence (cadence control). Trips a soft warning in logs.
    persona_max_sentence_words: int = 35

    # --- LLM Judge (Phase A2 — eval) ---
    # Provider:model for LLM-as-judge groundedness/doctrine eval. Defaults to the
    # strongest available model so judge != generator (avoid grading own work).
    llm_judge_provider_model: str = "anthropic:claude-sonnet-4-6"
    llm_judge_session_prefix: str = "mukthi-guru-judge"

    # --- Semantic Router (Phase A — replaces hardcoded keyword/regex lists) ---
    # Path to the YAML route table. Empty string means "use bundled default at
    # backend/config/router_routes.yaml". Override per-environment via the
    # ROUTER_CONFIG_PATH env var.
    router_config_path: str = ""
    # Feature flag: when True, intent classification consults SemanticRouter
    # BEFORE the LLM classifier. When False, the legacy regex prerouter is used.
    use_semantic_router: bool = True
    # When True, the LLM classifier is consulted whenever SemanticRouter returns
    # no match. When False, an unmatched query is treated as FACTUAL (fast path)
    # without consulting the LLM.
    semantic_router_llm_fallback: bool = True

    # --- Anthropic Gateway (Phase A7 — direct API with prompt caching + Citations) ---
    # All values env-overridable. Empty api_key disables the gateway and the
    # consumer code is expected to fall back to the legacy LLM stack.
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    anthropic_api_version: str = "2023-06-01"
    anthropic_beta_features: str = "prompt-caching-2024-07-31"
    # Default model for the gateway. Single source of truth — never hardcode
    # this string in service code.
    anthropic_gateway_model: str = "claude-sonnet-4-6"
    anthropic_gateway_max_tokens: int = 2048
    anthropic_gateway_temperature: float = 0.7
    anthropic_gateway_timeout_s: int = 60
    # Prompt cache TTL. "5m" (Anthropic default) or "1h" (extended; higher
    # write cost but cheaper if the same prefix is reused within the hour).
    # Empty string disables caching even when the gateway is configured.
    anthropic_gateway_cache_ttl: str = "1h"
    # Extended thinking (only on supported models). Off by default; turn on
    # for high-stakes adversarial or doctrinal-trap queries via per-call flag.
    anthropic_extended_thinking_enabled: bool = False
    anthropic_extended_thinking_budget_tokens: int = 0

    # --- HTTP Connection Pooling ---
    http_max_connections: int = 100  # Maximum number of HTTP connections in the pool
    http_max_keepalive_connections: int = 20  # Maximum number of keepalive connections
    http_keepalive_expiry: float = 30.0  # Keepalive expiry time in seconds

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
        return [lang.strip() for lang in self.ocr_languages.split(",") if lang.strip()]

    @property
    def web_search_allowed_domains_list(self) -> list[str]:
        """Parse comma-separated web search allowed domains into a list."""
        if not self.web_search_allowed_domains or not self.web_search_allowed_domains.strip():
            return []
        return [d.strip().lower() for d in self.web_search_allowed_domains.split(",") if d.strip()]

    @property
    def transcript_languages_list(self) -> list[str]:
        """Parse comma-separated transcript languages into a list."""
        if not self.transcript_languages or not self.transcript_languages.strip():
            return []
        return [lang.strip() for lang in self.transcript_languages.split(",") if lang.strip()]

    # --- Model Preset Resolution ---
    # These define the preset configurations for each model family.
    _PRESETS = {
        "sarvam": {
            "generation": "sarvam-30b:latest",
            "classification": "llama3.2:3b",
        },
        "qwen": {
            "generation": "qwen3:30b-a3b",
            "classification": "qwen3:14b",
        },
    }

    @property
    def is_sarvam_cloud(self) -> bool:
        """Check if using Sarvam Cloud API."""
        return self.llm_provider.lower() == "sarvam_cloud"

    @property
    def model_for_generation(self) -> str:
        """Resolve the main generation model from preset or custom config."""
        if self.is_sarvam_cloud:
            return self.sarvam_cloud_model
        if self.llm_provider.lower() == "openrouter":
            return self.openrouter_generation_model
        if self.ollama_model:  # Explicit override
            return self.ollama_model
        preset = self._PRESETS.get(self.model_preset.lower(), {})
        return preset.get("generation", "sarvam-30b:latest")

    @property
    def model_for_classification(self) -> str:
        """Resolve the fast classification model from preset or custom config."""
        if self.is_sarvam_cloud:
            return self.sarvam_cloud_classify_model
        if self.llm_provider.lower() == "openrouter":
            return self.openrouter_classify_model
        if self.ollama_classify_model:  # Explicit override
            return self.ollama_classify_model
        preset = self._PRESETS.get(self.model_preset.lower(), {})
        return preset.get("classification", "llama3.2:3b")

    @property
    def model_for_raptor(self) -> str:
        """Resolve the RAPTOR summary model from preset or custom config."""
        if self.raptor_summary_model:  # Explicit override
            return self.raptor_summary_model
        return self.model_for_generation  # Default to generation model


@lru_cache
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
