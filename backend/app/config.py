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

import json
from functools import lru_cache
from typing import Annotated, Any, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    sarvam_30b_endpoint: Optional[str] = None  # e.g., "http://<E2E_INSTANCE_IP>:8000/v1"
    sarvam_30b_api_key: Optional[str] = None  # If E2E endpoint requires auth
    sarvam_reasoning_effort: str = "medium"  # Default reasoning effort for main generation (low | medium | high)
    sarvam_reasoning_effort_fast: str = "low"   # Effort for fast/classification calls (intent routing, grading)
    sarvam_reasoning_effort_complex: str = "high"  # Effort for complex multi-hop, CoVe, and deep-reasoning queries
    sarvam_max_tokens: int = 4096  # Hard output-token ceiling applied by SarvamHTTPGateway to every generation call
    # Per-call HTTP timeout. NIM/OpenRouter have low server-side limits; 45s provides
    # adequate headroom while keeping total pipeline latency acceptable.
    # Must be smaller than pipeline_timeout.
    llm_timeout: int = 45  # reduced from 60 — NIM India→US typically responds in <20s
    # Total outer pipeline timeout. With 3 sequential LLM calls at 15s each + retrieval,
    # 120s is comfortable headroom without hanging users for 3+ minutes.
    pipeline_timeout: int = 120  # reduced from 180
    llm_max_retries: int = 2  # Max retry attempts per LLM call (exponential backoff starts at 0.5s)

    # Explicit allowlist of proxy addresses whose X-Forwarded-For is trusted
    # (uvicorn forwarded_allow_ips). Required by start_railway.py: startup fails
    # when missing or "*". Set to the platform edge's private ranges, e.g.
    # "10.0.0.0/8" on Railway. Local dev runs uvicorn directly and is unaffected.
    forwarded_allow_ips: str = ""

    # P1-AI-1: hard output-token ceilings applied by the LLM gateway on EVERY
    # generation call. The gateway passes these as max_tokens (OpenAI-style)
    # and never forwards a bare unbounded call to a provider. A caller-supplied
    # max_tokens is capped down to the matching route ceiling (min), so a deep
    # call can never exceed its route budget even if a caller requests more.
    llm_max_tokens_fast: int = 800   # casual/standard/fast-route generation ceiling
    llm_max_tokens_deep: int = 1500  # deep/tier3_complex generation ceiling

    # --- Timeout Budget ---
    # pipeline_timeout_budget removed — dead config, never read. Use pipeline_timeout instead.
    node_timeout_fast: int = 15  # reduced from 20
    node_timeout_main: int = 20  # reduced from 90 — prevents 90s hangs on slow Qdrant/Neo4j

    serene_mind_enabled: bool = True  # Enable/disable Serene Mind distress detection engine
    doctrine_cache_enabled: bool = False  # Default OFF: built-in canned answers lack citations and hurt benchmark quality

    # --- Distress / Serene Mind safety dials ---
    semantic_distress_threshold: float = Field(default=0.72, ge=0.0, le=1.0)
    # Count of recent turns with distress_score > semantic_distress_history_score_threshold
    # required before persistent-distress escalation.
    semantic_distress_history_score_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    # Number of recent turns scanned for persistent distress escalation.
    semantic_distress_rolling_window: int = Field(default=5, gt=0)
    # Minimum distressed-turn count within rolling_window to escalate to SEVERE.
    semantic_distress_escalation_count: int = Field(default=3, gt=0)
    # Fraction of recent proactive-distress turns that must be distressed to trigger a nudge.
    proactive_distress_frequency_threshold: float = Field(default=0.6, ge=0.0, le=1.0)

    # --- Ontology soft-gate validation ---
    ontology_confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    # Minimum fraction of extracted facts supported by Neo4j for is_valid=True.
    ontology_validity_confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)

    # --- Web search result guardrails ---
    web_search_result_min_score: float = Field(default=0.6, ge=0.0, le=1.0)

    # --- RAPTOR summary faithfulness gate ---
    raptor_summary_faithfulness_floor: float = Field(default=0.35, ge=0.0, le=1.0)

    # --- Feature Flags & Memory Layer ---
    feature_memory_enabled: bool = True
    feature_memory_write: bool = False  # Explicit opt-in until single-memory-plane consent proof exists.
    memory_background_task_timeout_seconds: int = 30
    feature_regex_prerouter: bool = True

    # --- Semantic Model Router (embedding-based classification, zero-LLM) ---
    # Unwired: nothing in the codebase reads semantic_router_enabled or
    # semantic_router_top_k. The routing behavior these names imply is
    # actually gated by semantic_router_confidence_threshold /
    # semantic_router_shadow_mode below (see orchestrator_utils.py).
    semantic_router_enabled: bool = True
    semantic_router_top_k: int = 3
    # Trust the semantic router's tier when its confidence exceeds this; below it,
    # routing defaults to the expensive "standard" path (orchestrator_utils.py:254).
    # Lowered 0.65→0.55 so borderline queries use the router's (often "fast") tier
    # instead of the slow default — the logs showed many 0.5x-confidence queries
    # falling through to standard. This is a latency/quality knob: validate against
    # the 255-q benchmark and raise back toward 0.65 if doctrine/quality regresses.
    semantic_router_confidence_threshold: float = 0.55
    semantic_router_fallback_llm: bool = False  # If True, fall back to LLM classifier when confidence is low
    semantic_router_shadow_mode: bool = False   # If True, run semantic router alongside heuristic but return heuristic result (for A/B comparison)

    # --- Safety Limits ---
    chat_history_max_messages: int = 20  # Cap conversation context to prevent OOM/timeouts
    max_input_length: int = 2000  # Max user message length in characters

    # --- Guardrails ---
    # Provider: "nemo" (NeMo Guardrails), "lightweight" (regex-based), "llama_guard" (Llama Guard 3 1B + Rejection Classifier), "rejection_classifier", "disabled"
    guardrails_provider: str = "nemo"  # Falls back to lightweight if provider unavailable
    # CRIT-5: message-level language detection + translate-to-EN before EN
    # guardrail regexes, so an EN-preferred user typing in a non-EN script
    # gets the same injection/crisis protection. Gates three call sites:
    # InputGuardrailStage (pipeline), kg.py (admin KG query), srs_service.py
    # (flashcard content). Rollback = set False (restores raw-text scan at all
    # three sites; srs guardrail reverts to its prior latent-dead-code state).
    multilingual_guardrails: bool = True

    # --- Ollama (local mode / cloud tag) ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""  # Auto-set by preset, or override with MODEL_PRESET=custom
    ollama_classify_model: str = ""  # Auto-set by preset, or override with MODEL_PRESET=custom
    ollama_cloud_only: bool = True  # When True, refuse local-only models (no :cloud tag)
    sarvam_model_name: str = "sarvam-30b:latest"  # Explicit Sarvam reference for scripts

    # --- OpenRouter (free tier for simple queries) ---
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_fast_model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct"
    openrouter_generation_model: str = "google/gemini-3.6-flash"
    openrouter_generation_model_fallback: str = "google/gemini-2.5-flash"
    openrouter_classify_model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct"
    openrouter_rpm_limit: int = 20
    # Versioned server-side OpenRouter policy; pinned IDs keep benchmark evidence reproducible.
    openrouter_policy_id: str = "gemini-flash-budget-v1"
    # Optional comma-separated provider order; empty accepts only privacy-compliant routing.
    openrouter_allowed_providers: str = ""
    openrouter_require_no_training: bool = True
    openrouter_allow_provider_fallbacks: bool = True
    openrouter_enforce_model_policy: bool = True
    openrouter_daily_budget_usd: float = Field(default=0.25, gt=0)
    openrouter_monthly_budget_usd: float = Field(default=6.0, gt=0)
    # Redis-backed cross-replica reservation guard. Enable only after Redis health and budget drill pass.
    openrouter_budget_guard_enabled: bool = False
    openrouter_max_request_cost_usd: float = Field(default=0.03, gt=0)
    openrouter_budget_fail_closed: bool = True



    # --- Re-ingest & Late Chunking Settings ---
    reingest_openrouter_model: str = "google/gemma-3-12b-it"
    reingest_llm_provider: str = "ollama"
    # Default True so the committed config matches what the green collection
    # actually contains. Every point in spiritual_wisdom_contextual carries
    # pooling="mean", which only happens with late chunking on — meaning the run
    # that built it used an env override the repo did not encode. Anyone
    # re-running from committed defaults would have produced pooling="cls"
    # vectors and silently MIXED pooling modes in one collection; mean-pooled and
    # CLS-pooled vectors sit ~0.757 cosine apart, so mixing them corrupts ranking
    # for every query without failing anything.
    reingest_late_chunking: bool = True
    late_chunk_window_tokens: int = Field(default=2048, gt=2)
    late_chunk_window_batch_size: int = Field(default=4, ge=1)
    # In-flight contextualizer LLM calls. 8 suits a hosted endpoint (calls are
    # network-bound); _contextualize() clamps it back to 3 for local Ollama,
    # where extra concurrency only queues behind one model.
    reingest_contextualizer_concurrency: int = Field(default=8, ge=1, le=32)
    # Characters of the surrounding document sent with each chunk so the model
    # can situate it. 8,000 was sized for a local Ollama context window and, on
    # The_Four_Sacred_Secrets.pdf, meant every chunk saw the first and last 4,000
    # chars of a 424,302-char book — 1.9% of it, and the wrong 1.9%. Units are
    # now book SECTIONS averaging ~18k chars, so 24,000 fits most whole. Gemma-3
    # carries a 128k window; this is a cost/latency bound, not a model limit.
    reingest_contextualizer_doc_chars: int = Field(default=24_000, ge=1_000, le=200_000)
    # Chunks per encode_batch call. Bounds peak memory to a function of batch
    # size rather than source length — a single encode over all 332 chunks of one
    # source OOM-killed the whole Docker stack on 2026-08-01. 32 measured at
    # 3.1/7 GB peak; raise only with a memory reading, never on reasoning alone.
    reingest_embed_batch_size: int = Field(default=32, ge=1, le=256)

    # --- Gemini translation (layered ahead of Sarvam via OpenRouter) ---
    gemini_translation_enabled: bool = True
    gemini_model: str = "google/gemini-3.6-flash"
    gemini_fallback_to_sarvam: bool = True

    # --- Nvidia NIM (hosted API Catalog) ---
    nim_api_key: str = ""
    nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    nim_generation_model: str = "minimaxai/minimax-m2.7"
    nim_classify_model: str = "meta/llama-3.1-8b-instruct"
    nim_rpm_limit: int = 30

    # --- Qdrant ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "spiritual_wisdom_contextual"
    qdrant_api_key: str = ""  # empty = no auth (current default); set to require API-key auth
    # Quantization strategy for the Qdrant dense vector index.
    # Options: scalar_int8 (default, current production behavior), binary,
    # turboquant_1bit, turboquant_2bit, turboquant_4bit.
    qdrant_quantization: str = "scalar_int8"
    # Oversampling factor used for non-scalar quantizers (binary / TurboQuant).
    # Higher values improve recall at the cost of extra compute during search.
    qdrant_quantization_oversampling: float = 3.0

    # Hybrid search fusion strategy: "rrf" (Reciprocal Rank Fusion, rank-based,
    # unweighted — Qdrant's Fusion enum has no weight parameter) or "dbsf"
    # (Distribution-Based Score Fusion — normalizes score distributions before
    # merging, can favor one channel more when score ranges differ). Default
    # matches current production behavior.
    qdrant_fusion_strategy: str = "rrf"
    # RRF has no native weight knob, so channel influence is tuned indirectly via
    # prefetch pool size: a larger candidate pool from one channel gives it more
    # chances to rank into the fused top-K. 1.0 = current behavior (limit + 5 each).
    qdrant_dense_prefetch_multiplier: float = 1.0
    qdrant_sparse_prefetch_multiplier: float = 1.0

    # --- Chunking Strategies ---
    use_boundary_chunker: bool = True  # Respect sentence and verse boundaries


    # --- Multi-teacher personality (Phase E5) ---
    # When set, generation prepends a teacher-specific voice instruction.
    # Maps teacher_id → personality prompt fragment. JSON-encoded string in env.
    # Example: {"sadhguru":"Speak with the direct, earthy tone of a yogi.","preethaji":"Speak with warmth and stillness."}
    teacher_personalities: str = ""

    # --- Supabase (Docker Local & Production Hybrid Modes) ---
    supabase_url: str = "http://host.docker.internal:54321"
    supabase_key: str = ""  # SERVICE_ROLE_KEY for backend write access
    # Distinct service-role key for worker/admin paths (no RLS). Falls back
    # to supabase_key when unset, matching auth_service.get_current_user_from_supabase.
    supabase_service_key: Optional[str] = None
    # Public-facing frontend URL (for reactivation links in win-back emails).
    # Defaults to the Railway prod deploy; override via FRONTEND_URL env var.
    frontend_url: str = "https://askmukthiguru-8119b0e8-production.up.railway.app"

    # --- Hallucination anomaly thresholds (daily telemetry check) ---
    anomaly_hallucination_rate_threshold: float = 0.05
    anomaly_faithfulness_p50_threshold: float = 0.80
    anomaly_lookback_days: int = 1
    anomaly_output_path: str = "hallucination_anomaly.json"
    supabase_jwks_url: Optional[str] = None  # Optional JWKS URL for JWT validation (used in hybrid auth setups)
    supabase_jwt_issuer: Optional[str] = None  # Optional JWT Issuer for token validation (used in hybrid auth setups)
    qdrant_local_path: Optional[str] = None  # Set for local mode (no Docker)

    # --- Neo4j ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    # One bounded, process-shared driver pool per application process.
    neo4j_max_connection_pool_size: int = Field(default=20, ge=1, le=200)
    neo4j_connection_timeout_s: float = Field(default=15.0, gt=0, le=300)
    neo4j_connection_acquisition_timeout_s: float = Field(default=15.0, gt=0, le=300)
    neo4j_max_transaction_retry_time_s: float = Field(default=15.0, ge=0, le=300)
    neo4j_max_connection_lifetime_s: float = Field(default=300.0, gt=0, le=3600)
    neo4j_keep_alive: bool = True
    kg_max_query_len: int = Field(default=4_000, gt=0)
    kg_query_timeout_s: float = Field(default=5.0, gt=0)
    kg_subgraph_max_edges: int = Field(default=200, ge=1, le=2_000)

    # --- Embeddings (config-driven: switch models via env vars) ---
    # Supported: "BAAI/bge-m3" (default, best multilingual, 1024-dim dense+sparse+ColBERT)
    #            "intfloat/multilingual-e5-large" (alternative multilingual, 1024-dim)
    #            "sentence-transformers/all-MiniLM-L6-v2" (English-only, 384-dim, fast)
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024
    # "flagembedding" (default, fp32, current production behavior) or
    # "onnx_int8" (~75% smaller resident memory, ~0.989 cosine similarity to
    # fp32 per public benchmarks — see lessons.md "Cost & Pipeline
    # Optimization, part 2"). OFF by default: switching this requires
    # re-embedding the existing Qdrant collection first (it was indexed with
    # fp32 vectors), or query-time and index-time embeddings diverge. Do not
    # flip in production without a full re-index — see
    # scripts/validate_onnx_embedding.py.
    embedding_backend: str = "flagembedding"
    embed_torch_threads: int = Field(default=1, ge=1)
    hf_revision: Optional[str] = None
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    # CPU-only deployments (Railway) must NOT run bge-reranker-v2-m3:
    # 568M params on CPU costs ~4s/doc → 88s for 19 docs (verified in docker logs).
    # Use multilingual mMiniLMv2-L12 (~22M params) — same speed as ms-marco-MiniLM
    # but covers Hindi, Telugu, Tamil, Kannada, and all 6 app languages.
    # GPU/MPS path still uses bge-reranker-v2-m3 above.
    reranker_model_cpu: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    # ONNX INT8 reranker backend (Phase 1 optimization).
    # "onnx_int8" — use OnnxReranker (temsa pre-quantized, ~23 MB, ~2× faster).
    # "flagembedding" — fall back to sentence-transformers CrossEncoder (original).
    # Rollback: set RERANKER_BACKEND=flagembedding in .env and restart.
    reranker_backend: str = "onnx_int8"
    reranker_onnx_model: str = "temsa/mmarco-mMiniLMv2-L12-H384-v1-onnx-cpu-qint8"
    enable_colbert: bool = False

    # --- Whisper / Transcription ---
    # `whisper_model`, `whisper_backend` and `whisper_compute_type` were removed
    # on 2026-08-02: nothing read them. Transcription runs through WhisperX
    # (`whisperx_*` below, read in services/whisper_local_service.py) or MLX
    # (`whisper_local_model`). docker-compose.yml set all three as env vars, so
    # the deployed stack was "configuring" Whisper through knobs the code
    # ignored — WHISPER_MODEL=medium would have applied silently to nothing.
    # Configure WHISPERX_MODEL / WHISPERX_COMPUTE_TYPE / WHISPERX_DEVICE instead.
    whisper_local_model: str = "mlx-community/whisper-large-v3-turbo"

    # --- WhisperX (word-level alignment + diarization) ---
    # Opt-in: adds torch + whisperx + pyannote deps. When False (default), falls
    # back to MLX Whisper (segment-level timestamps only).
    whisperx_enabled: bool = False
    whisperx_device: str = "auto"  # "auto" detects cuda/cpu
    whisperx_compute_type: str = "auto"  # "auto" → float16 (cuda) / int8 (cpu)
    whisperx_model: str = "large-v3"  # Whisper model size for WhisperX
    whisperx_batch_size: int = 16
    diarization_min_speakers: int = 1
    diarization_max_speakers: int = 10
    # HuggingFace token for the gated pyannote/speaker-diarization-3.1 model.
    # If unset, diarization is skipped (alignment still runs).
    hf_token: Optional[str] = None

    # --- ASR Gate (§6.1 of corpus-remediation-and-migration-plan) ---
    # Reject degenerate transcripts BEFORE the LLM corrector. Decode-level
    # kwargs apply to whisperx/faster-whisper; segment-level floors apply to
    # whisperx output; the transcript backstop (5-gram x >=4 loop detector,
    # services/text_quality_filter) applies to every ASR path including MLX.
    asr_gate_enabled: bool = True
    asr_vad_filter: bool = False  # faster-whisper VAD; True skips silent segments
    asr_repetition_penalty: float = 1.0  # >1.0 suppresses decoder loops at decode time
    asr_compression_ratio_threshold: Optional[float] = None  # e.g. 2.4 (whisper default)
    asr_avg_logprob_floor: Optional[float] = None  # e.g. -1.0; below = reject segment
    asr_no_speech_prob_ceiling: Optional[float] = 0.6  # above = reject segment (music/silence-only audio)

    # --- LLM Speaker-Role Fallback ---
    # When whisperx diarization is unavailable (MLX-only, cross-process, or cache
    # empty), classify each chunk's speaker ROLE via LLM. Closed-set roles only —
    # never invents names. See `_resolve_chunk_speakers_with_llm` in ingest/pipeline.py.
    llm_speaker_role_fallback_enabled: bool = True

    # --- Transcript Extraction ---
    transcript_languages: str = (
        "en,hi,bn,te,mr,ta,ur,gu,kn,ml,or,pa,as,mai,sa,ks,ne,sd,kok,doi,mni,sat,brx"
    )
    transcript_max_retries: int = 3  # Retry per tier before falling to next
    transcript_concurrent_workers: int = 1  # Kept at 1 to avoid YouTube 429 rate limits

    # --- Scheduled external-content synchronization ---
    # Disabled by default: this job can fetch new videos and run ingestion
    # stages that call paid STT/LLM providers even when there is no user traffic.
    # Enable explicitly with ENABLE_SCHEDULED_YOUTUBE_SYNC=true after setting
    # an operational budget and monitoring plan.
    enable_scheduled_youtube_sync: bool = False

    # --- YouTube Cookie & Runtime Paths (macOS cookie extraction) ---
    # Override with YOUTUBE_COOKIES_PATH in .env to point to a custom cookies.txt location.
    youtube_cookies_path: str = ""
    # Override with YOUTUBE_YTDLP_HOST_PATH in .env to point to the host yt-dlp binary.
    youtube_ytdlp_host_path: str = ""

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
    data_audit_enabled: bool = True
    data_audit_strict_mode: bool = False  # Enable LLM-based quality checks

    # --- Redis ---
    # Default uses 'redis' resolving inside Docker Compose. For local non-docker dev, override with REDIS_URL=redis://localhost:6379/0 via .env
    redis_url: str = "redis://redis:6379/0"
    # --- Cache Mode ---
    # "best_effort" = try Redis, fall back to in-memory if unavailable (default).
    # "redis"       = require Redis; raise a clear startup error if unavailable.
    # "memory"      = use in-memory cache only (no Redis dependency).
    cache_mode: str = "best_effort"

    # --- Job Queue & Backpressure ---
    queue_enabled: bool = True
    queue_max_size: int = 50
    queue_concurrency: int = 5
    ingestion_concurrency: int = 5
    queue_job_ttl: int = 1800
    queue_default_timeout: int = 300
    # Max concurrent in-flight /api/chat (and /api/chat/v2, /api/chat/stream)
    # requests per replica. Exhausted → immediate 503 + Retry-After (no queueing).
    # Must be ≥1; zero or negative is rejected at startup by Pydantic validation.
    max_concurrent_chat: int = Field(default=20, ge=1)

    # --- Request Queue (Phase 1A — horizontal scaling) ---
    # When True, incoming requests are enqueued to Redis Streams and
    # processed by workers from a consumer group (enables multi-replica).
    # When False (default), requests are processed inline (current behaviour).
    use_request_queue: bool = False

    # --- LLM Queue (Concurrency Gating) ---
    llm_queue_enabled: bool = True
    llm_queue_max_concurrent: int = 5
    llm_queue_maxsize: int = 50

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:8080,http://localhost:3000"
    # --- Security ---
    # csrf_secret is kept as a general-purpose signing secret (used by
    # _rate_limit_key_digest in security_utils.py via getattr); there is no
    # dedicated rate-limit HMAC key. csrf_token_ttl was removed 2026-08-11:
    # the generate_csrf_token/validate_csrf_token helpers in security_utils.py
    # had zero callers, so the TTL setting was dead weight.
    csrf_secret: Optional[str] = (
        None  # Secret for CSRF token signing (generate with secrets.token_hex(32))
    )
    correlation_id_max_length: int = 64  # Max length for X-Correlation-ID header
    allowed_hosts: str = "localhost,127.0.0.1"  # Trusted hosts for Origin/Referer validation

    # --- Auth & Rate Limiting ---
    # Default to PRODUCTION (secure-by-default). Override with IS_PRODUCTION=false for local dev only.
    is_production: bool = True
    # Gate Swagger/OpenAPI docs. Disabled in production to avoid exposing the full API schema.
    show_swagger: bool = False
    # Explicit opt-in for the X-Test-Key backdoor strategy. NEVER enable in production.
    enable_test_auth: bool = False
    jwt_secret: Optional[str] = None  # Shared with Supabase for token validation
    jwt_private_key: Optional[str] = None  # Private key PEM for RS256 token signing
    jwt_public_key: Optional[str] = None   # Public key PEM for RS256 token verification
    # M5: HMAC secret for server-side signed anonymous session tokens
    # (POST /api/auth/anon-session). REQUIRED in production — the app refuses to
    # start if empty when IS_PRODUCTION=true. In dev/test it falls back to a
    # value derived from jwt_secret so existing tests pass without config.
    anon_session_hmac_secret: Optional[str] = None
    supabase_jwt_audience: str = "authenticated"
    benchmark_secret: Optional[str] = None
    # Benchmarks (ragas_eval.py) default their live --endpoint to this value
    # instead of reading the env directly, so the endpoint is validated the same
    # way as every other settings-sourced URL.
    benchmark_endpoint: str = "http://localhost:8000"
    # Comma-separated or JSON-list of HTTPS hostnames allowed to receive the
    # X-Test-Key benchmark secret (non-loopback targets only — see
    # benchmarks/ragas_eval.py::_validate_endpoint).
    benchmark_test_key_allowed_hosts: Annotated[list[str], NoDecode] = []
    benchmark_anon_session_timeout: float = Field(default=15.0, gt=0.0)
    benchmark_chat_timeout: float = Field(default=180.0, gt=0.0)

    @field_validator("benchmark_test_key_allowed_hosts", mode="before")
    @classmethod
    def _parse_benchmark_test_key_allowed_hosts(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (ValueError, json.JSONDecodeError):
                return [h.strip() for h in v.split(",") if h.strip()]
        return v

    # P1-SEC-1 (T4): Defense-in-depth admin allowlist. Comma-separated admin
    # user UUIDs. When non-empty, an AAL2 superuser MUST also be in this list
    # to reach admin/ingest/kg admin endpoints. Empty (default) = not enforced
    # (dev convenience; in prod set to the real admin UUIDs). The service_role
    # sentinel UUID is never in this list, so it is blocked even if aal2 were
    # somehow attached to its token.
    admin_user_ids: str = ""
    # M3: server-side persona allowlist. Comma-separated assistant slugs the
    # backend will honour as client-supplied personas. A request carrying a
    # slug NOT in this list keeps its slug for retrieval/telemetry but its
    # client-supplied system_prompt is cleared so the honesty guard stays ON
    # and no attacker persona replaces the guru. Default seeds the four
    # personas the frontend ships today.
    allowed_assistant_slugs: str = "guru,preethaji,krishnaji,serene_mind"
    # JSON map: approved assistant slug -> server-resolved corpus/teacher scope.
    # A supplied slug without a registry entry is rejected before graph execution.
    assistant_corpus_registry: str = (
        "{\"guru\": {}, \"preethaji\": {\"teacher_id\": \"preethaji\"}, "
        "\"krishnaji\": {\"teacher_id\": \"krishnaji\"}, \"serene_mind\": {}}"
    )
    # Default to disabled: the frontend uses Supabase auth, so the FastAPI
    # /api/auth/register endpoint has no legitimate public use case and would
    # otherwise expose an email-enumeration surface. Override with the
    # DISABLE_PUBLIC_REGISTRATION env var only for explicit internal flows.
    disable_public_registration: bool = True
    chat_rate_limit: str = "20/minute"
    registration_rate_limit: str = "5/minute"
    # --- Anonymous Quota (Progressive Auth) ---
    # Max user turns allowed per anonymous session within the window.
    anon_quota_messages: int = Field(default=5, gt=0)
    anon_quota_window_hours: float = Field(default=24.0, gt=0)
    anon_quota_enabled: bool = True
    # --- Compliance audit trail (Unit 24) ---
    # Legal basis recorded on each compliance_audit NDJSON record (GDPR Art. 6)
    # and the retention period advertised to downstream data-retention tooling.
    compliance_legal_basis: str = "consent"
    compliance_retention_days: int = 365
    # Early-access collection remains off until its migration and privacy copy are deployed.
    waitlist_enabled: bool = False
    google_sso_enabled: bool = True
    push_notifications_enabled: bool = True
    # ~USD equivalent of the ₹3,000/month operating envelope (see CLAUDE.md budget note).
    # Fixed conversion, not a live FX lookup — this is a soft alert threshold, not a hard cap.
    monthly_cost_budget_usd: float = 36.0
    admin_rate_limit: str = "5/minute"
    auth_backoff_base_seconds: float = 2.0
    auth_backoff_multiplier: float = 2.0
    # --- Support / Contact (SMTP) ---
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: Optional[str] = None
    support_to_email: str = "kharshaengineer@gmail.com"
    # When SMTP is not configured, support submissions fall back to file storage.
    support_storage_path: str = "data/support_messages"

    # --- RAPTOR ---
    raptor_cluster_size: int = 8
    raptor_summary_model: str = ""  # Auto-set from model_preset

    # --- RAG ---
    rag_top_k_retrieval: int = 20
    rag_top_k_rerank: int = 10
    rag_max_rewrites: int = 1
    rag_chunk_size: int = 1500
    rag_chunk_overlap: int = 200
    rag_use_hyde: bool = False
    rag_context_window: int = 2  # Fetch N chunks before/after each retrieved chunk
    rag_graph_context_cap_chars: int = 400  # Max chars for graph summary doc injected into enriched context
    rerank_min_score: float = 0.35  # Min CrossEncoder score (sigmoid-normalized) to keep a doc
    rag_use_context_compression: bool = False  # Set to True to enable LLM-based context compression
    rag_context_compression_threshold: int = (
        20000  # Only compress context if character length exceeds this threshold
    )
    # MMR (Maximal Marginal Relevance) diversity re-ranking
    rag_mmr_lambda: float = 0.5  # Balance between relevance and diversity (0=diversity, 1=relevance)
    max_tokens_per_request: int = 12000  # Maximum tokens per LLM request (covers persona+knowledge+history+instructions)

    # --- Retrieval context compression allowlist ---
    rag_context_compression_top_k: int = 5
    # Score-ratio floor for compressed documents relative to the top score.
    # Keeps high-scoring docs only, preserving diversity for deep/complex tiers.
    rag_context_compression_score_ratio: float = 0.75

    # --- Retrieval Quality Gates ---
    retrieval_score_delta_enabled: bool = True
    rerank_score_delta_enabled: bool = True
    retrieval_deduplication_enabled: bool = True
    ingestion_deduplication_enabled: bool = True
    rag_top_k_retrieval_after_cutoff: int = 10
    retrieval_dedup_threshold: float = 0.85
    ingestion_dedup_threshold: float = 0.85
    raptor_parent_summaries_enabled: bool = True
    use_markitdown_parser: bool = True
    # BM25 keyword search via native Qdrant sparse vectors
    bm25_retrieval_enabled: bool = True
    bm25_result_limit: int = 10
    rag_compression_similarity_threshold: float = 0.50
    rag_context_compression_enabled: bool = False
    # Stays True. The OKF bundle was cleared on 2026-08-01 for a clean rebuild from
    # the green corpus, so injection currently finds an empty index and contributes
    # nothing — harmless, and it means the layer switches back on by itself as soon
    # as entries are re-extracted, reviewed, and recompiled.
    rag_okf_injection_enabled: bool = True   # OKF as canonical knowledge layer
    rag_okf_auto_extract_enabled: bool = True  # post-ingestion OKF extraction; hardened w/ Celery retry + logging
    # Minimum cosine an OKF entry must reach before it is injected at all.
    okf_min_similarity: float = 0.45
    # Curated, human-reviewed doctrine outranks a raw chunk of equal similarity — margin, not a floor.
    okf_curation_boost: float = 1.10
    # Keyword-fallback gate (used only when EmbeddingService is unavailable): fraction
    # of the query's content words an entry must contain.
    okf_min_keyword_coverage: float = 0.30
    # Ceiling an OKF keyword-fallback score may reach so lexical overlap never outranks a real embedding match.
    okf_keyword_score_ceiling: float = 0.60
    # Threshold at which parent text gets adaptive excerpting instead of full injection.
    retrieval_adaptive_parent_threshold: int = 1800
    # Score-delta cutoff: drop documents whose score is less than this fraction of the top score.
    retrieval_score_delta_ratio: float = 0.5
    # Internal telemetry confidence assigned to an abstention (no supporting evidence).
    generation_no_evidence_confidence: float = 2.0
    # Persona system-prompt token budget; pinned by tests/test_answer_path_regressions.py.
    generation_persona_token_budget: int = 2048
    # Default max length for extractive document compression before truncation.
    generation_compression_max_chars: int = 1500
    # Truncation marker appended when compressed text still exceeds the char budget.
    generation_compression_truncation_suffix: str = " [...]"
    # Score bonus for sentences near the start of a document during extractive compression.
    generation_compression_position_bonus: float = 0.5

    # --- FlashRank Reranking & Ingestion Service Config ---
    use_flashrank: bool = True
    flashrank_model: str = "auto"
    use_cross_encoder_only: bool = False
    use_adaptive_chunking: bool = True
    adaptive_chunking_min_chars: int = 800
    use_proposition_chunking: str = "auto"
    proposition_char_limit: int = 15000

    # --- Implicit Teachings Concept Connector (ingestion optimization) ---
    # Cosine similarity below which entity-pair LLM relation classification is skipped.
    concept_similarity_threshold: float = 0.78
    # Optional smaller/faster model for ingestion-time relation extraction.
    # Empty string = use the configured classification model (provider default).
    ingestion_relation_model: str = ""
    # Max entity pairs classified in a single batched LLM call (reduces call count).
    ingestion_relation_batch_size: int = 5
    # LRU cache size for (entity_a, entity_b) -> relation lookups.
    ingestion_relation_cache_size: int = 256

    # --- Quality gate (Tier 1+) density / fact-check / bias stubs ---
    quality_min_information_density: float = 0.35  # unique meaningful words / total; below = penalty
    quality_bias_blocklist: str = ""  # comma-separated loaded/hate terms; empty = use built-in stub list

    # --- Hyper-Extract enrichment (Phase 5.3) ---
    use_hyper_extract_enrichment: bool = False  # Enable lightweight structure/entity/fact extraction
    hyper_extract_min_chars: int = 200  # Skip texts shorter than this
    hyper_extract_max_chars: int = 50_000  # Hard cap to keep enrichment fast and safe

    # --- KG Phase 6: Auto-extraction from ingestion ---
    write_ontology_to_neo4j: bool = True  # Materialize hyper_extract entities/relationships into Neo4j during ingestion
    ontology_write_required: bool = False  # Only block and roll back ingestion when graph materialization is explicitly mandatory.
    default_corpus_id: str = "askmukthiguru"  # Required scope for legacy/current teacher corpus data.
    # Single source of truth for the legacy/default tenant identity (Oneness —
    # Sri Preethaji & Sri Krishnaji's organization). services/tenant_context.py's
    # ContextVar/_LEGACY_TENANT and every CorpusScope(tenant_id=...) fallback
    # read this, so ingestion, Qdrant payload filters, and Neo4j coalesce
    # defaults stay consistent without hand-copied "default" string literals.
    default_tenant_id: str = "oneness"
    # Production retrieval requires an explicit licensed-domain payload stamp.
    # Disable only for isolated migration/test environments.
    require_licensed_domain_reads: bool = True
    # Governed source publication is opt-in until approval/rollback staging drills pass.
    corpus_release_registry_enabled: bool = False
    corpus_release_fallback_version: int = 1

    # --- Semantic Cache ---
    semantic_cache_enabled: bool = True  # Embedding-based semantic caching
    semantic_cache_similarity: float = 0.90  # E3.4: lowered from 0.87/0.92 to improve hit rate
    intent_prerouter_cache_hint_enabled: bool = True  # E3.1: hint cache-first for FACTUAL/CASUAL
    semantic_cache_ttl: int = 604800  # Cache TTL in seconds (7 days)
    guardrails_llm_enabled: bool = False  # Toggle LLM-based guardrail checks

    # Qdrant-backed semantic cache (Phase 1.2)
    semantic_cache_qdrant_collection: str = "semantic_cache"  # Qdrant collection name
    semantic_cache_hnsw_ef: int = 128  # HNSW ef parameter for cache lookups

    # --- P90/P99 Hybrid Search (Phase 1.1) ---
    faiss_cache_size: int = 500  # Number of top docs mirrored in local FAISS index
    hybrid_search_enabled: bool = True  # Feature flag: enable P90/P99 hybrid search

    # --- DSPy ---
    use_dspy: bool = False  # Enable DSPy-optimized generation (NIM-based)

    # --- Embedding Cache (Phase 1.3) ---
    embedding_cache_size: int = 10000  # LRU cache size for content-hash embeddings

    # --- Temperature per Graph Mode (Phase 2.1) ---
    generation_temp_fast: float = 0.3  # Temperature for fast-graph generation
    generation_temp_standard: float = 0.7  # Temperature for standard-graph generation
    generation_temp_deep: float = 0.9  # Temperature for deep-graph generation

    # --- Context Budget (Phase 3.2) ---
    context_window_total: int = 8192  # Total context window in tokens
    context_system_prompt_reserve: float = 0.20  # Fraction of budget reserved for system prompt
    context_history_reserve: float = 0.10  # Fraction of budget reserved for conversation history

    # --- Feature flags (Phase 2-3) ---
    phi_accrual_enabled: bool = True
    use_qdrant_semantic_cache: bool = True

    # --- Idempotency (Phase 3.3) ---
    idempotency_ttl_seconds: int = 86400
    idempotency_redis_prefix: str = "idempotency:"

    # --- Daily teachings cache (app/api/teachings.py) ---
    teachings_tips_ttl_seconds: int = 604_800  # 7 days

    # --- User Profiles & Persistence ---
    user_profile_enabled: bool = True  # Enable user profiles and persistent memory
    krutrim_api_key: str = ""  # Fallback Indian LLM provider

    # --- Proactive Serene Mind ---
    proactive_serene_mind_enabled: bool = True
    proactive_distress_avg_threshold: float = 1.5  # Minimum average distress to consider
    proactive_distress_trend_threshold: float = 0.5  # Minimum escalation rate
    proactive_min_conversation_points: int = 3  # Minimum data points needed

    # --- Proactive Healing Course Assignment (Task 10) ---
    # Assigns a short healing course (curriculum lives on the frontend in
    # src/lib/healingCourses.ts; backend maps SufferingSignal -> course slug)
    # when a seeker shows a sustained distress pattern. Triggers, in priority
    # order: >=consecutive_threshold distress turns in a row; distress in
    # >=frequency_threshold of the last frequency_window turns; escalating
    # severity; the same suffering signal repeated >=2x within
    # repeat_window_hours. Skips users who already hold an active course.
    proactive_course_assignment_enabled: bool = True
    proactive_course_consecutive_threshold: int = 2
    proactive_course_frequency_threshold: int = 3
    proactive_course_frequency_window: int = 5
    proactive_course_repeat_window_hours: int = 24

    # --- A/B Testing ---
    ab_testing_enabled: bool = False  # Randomly switch between primary LLM and Krutrim
    ab_testing_ratio: float = 0.1  # 10% traffic to Krutrim

    # --- Web Search (Real-Time Temporal Queries) ---
    web_search_enabled: bool = False  # Enable temporal web search for real-time queries
    live_logistics_enabled: bool = False  # Official-source event and booking lookup only.
    live_logistics_ttl_seconds: int = 900
    web_search_provider: str = "duckduckgo"  # "duckduckgo" | "searxng"
    web_search_allowed_domains: str = "ekam.org,theonenessmovement.org"
    web_search_allow_db_domain_override: bool = False  # DB may narrow, never widen the source-controlled official allowlist.
    web_search_max_results: int = 5
    searxng_url: str = "http://searxng:8080"  # Self-hosted SearXNG instance URL
    # Coverage-gap: if ALL retrieved docs score below this, treat as zero-coverage → fire web search
    web_search_coverage_threshold: float = 0.08
    # LightRAG per-call timeout headroom. LightRAG makes internal LLM calls for entity
    # extraction at query time — cap tightly to prevent single-query 30s hangs.
    # For tier2_simple queries, graph_stage.py skips LightRAG entirely.
    lightrag_retrieval_timeout: int = 30  # raised from 3 — KG now has 2,200+ relations, needs 15-25s for real graph traversals
    # Bound on kg_expansion.expand_query_with_ontology's Neo4j session.run() calls
    # (one per matched concept, no upstream timeout previously) — this call sits
    # sequentially before retrieve_documents' async fan-out, so a stalled/contended
    # Neo4j connection blocked the entire retrieval node with no ceiling.
    kg_ontology_expansion_timeout: float = Field(default=3.0, gt=0.0)
    # Per-query graph traversal enabled — LightRAG now holds 2,200+ relations
    # (well above the original 1,000-edge threshold). Each RELATIONAL/FACTUAL/QUERY
    # uses LightRAG for graph context alongside Qdrant vector search.
    # Ingestion, ontology seeder, and Qdrant-only paths are unaffected.
    knowledge_graph_query_enabled: bool = True
    # Knowledge graph analytics (PageRank, HITS, centrality, Louvain communities)
    kg_analytics_enabled: bool = True
    # Knowledge graph standalone HTML export via D3Blocks (requires d3blocks)
    kg_export_enabled: bool = False

    # --- GraphRAG Fusion (multi-hop vector + KG) ---
    graphrag_fusion_enabled: bool = Field(default=False, description="Enable GraphRAG fusion (multi-hop vector+KG)")
    graphrag_max_hops: int = Field(default=2, gt=0, le=5)
    graphrag_token_budget: int = Field(default=4000, gt=0, le=8000)

    @model_validator(mode="after")
    def validate_graphrag_token_budget(self):
        """Ensure graphrag_token_budget leaves safety headroom under max_tokens_per_request."""
        max_tokens = getattr(self, "max_tokens_per_request", 12000)
        budget = getattr(self, "graphrag_token_budget", 4000)
        # Reserve 20% headroom for prompt overhead, system instructions, history
        headroom = max_tokens * 0.8
        if budget > headroom:
            raise ValueError(
                f"graphrag_token_budget ({budget}) exceeds 80% of max_tokens_per_request "
                f"({max_tokens}). Reduce budget or increase max_tokens_per_request."
            )
        return self

    # --- HTTP Pool Limits ---
    http_pool_max_connections: int = Field(default=50, gt=0)
    http_pool_max_keepalive: int = Field(default=20, ge=0)

    @model_validator(mode="before")
    @classmethod
    def normalize_http_pool_limits(cls, data: Any) -> Any:
        """Ensure HTTP pool limits are positive integers and keepalive <= max_connections prior to Field validation."""
        if isinstance(data, dict):
            import math

            def _parse_int(val: Any, default: int, min_val: int = 1) -> int:
                if val is None:
                    return default
                if isinstance(val, float):
                    if not math.isfinite(val) or not val.is_integer():
                        return default
                elif isinstance(val, str):
                    val_str = val.strip()
                    if "." in val_str or "e" in val_str.lower() or "inf" in val_str.lower() or "nan" in val_str.lower():
                        return default
                try:
                    res = int(val)
                    if res < min_val:
                        return default
                    return res
                except (ValueError, TypeError, OverflowError):
                    return default

            conn = _parse_int(data.get("http_pool_max_connections"), default=50, min_val=1)
            keep = _parse_int(data.get("http_pool_max_keepalive"), default=20, min_val=0)

            if keep > conn:
                keep = conn

            data["http_pool_max_connections"] = conn
            data["http_pool_max_keepalive"] = keep
        return data




    # --- Web Ingestion ---
    web_ingest_max_response_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    web_ingest_page_timeout: int = Field(default=30_000, ge=5000, le=120_000)
    web_ingest_max_dom_chars: int = Field(default=500_000, ge=10_000, le=2_000_000)
    ingest_url_max_retries: int = Field(default=2, ge=0, le=10)
    ingest_url_retry_delay: int = Field(default=30, ge=1, le=3600)
    ingest_url_soft_time_limit: int = Field(default=120, ge=30, le=600)
    ingest_url_time_limit: int = Field(default=180, ge=60, le=900)

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

    # --- LLM Gateway cross-provider fallback (services/llm_gateway.py — the
    # actual LLMGateway class; distinct from the emergentintegrations concept
    # above). Default OFF: routing a failed request to a DIFFERENT vendor is a
    # deliberate security-audit decision (see app/container.py:188-190) — only
    # flip this on as an explicit opt-in.
    llm_gateway_cross_provider_fallback: bool = False

    # --- Persona controls (Phase B — guru voice quality) ---
    # When True, the generation node strips the canned "*Note: Based on what I found...*"
    # footer that was breaking immersion. The context-aware close is generated dynamically
    # from the intent + citation count instead.
    strip_canned_footer: bool = True
    # Maximum paragraphs in a single answer (cadence control).
    persona_max_paragraphs: int = 4
    # Maximum words in a single sentence (cadence control). Trips a soft warning in logs.
    persona_max_sentence_words: int = 35
    # Maximum age (days) of a stored persona before prepare_user_memory stops
    # injecting it into prompts; a stale persona is skipped, not served.
    persona_max_age_days: int = 30

    # --- Grounded guru voice ---
    # Voice is composed during generation from retrieved, attributable context.
    # It preserves verified first-person quotations but never synthesises founder
    # speech, forces Sanskrit, imitates an accent, or rewrites a finished answer.
    langhanam_voice_enabled: bool = True
    # "prompt" is the only active voice mode. "adapter" is accepted only for
    # backward-compatible configuration parsing and is a logged no-op; it must
    # never run a regex or LLM rewrite after citations are attached.
    guru_voice_mode: str = "prompt"
    # Benchmark gate: minimum mean rubric score (of 5.0) required before
    # langhanam_voice_enabled may be flipped on.
    guru_voice_gate_score: float = 4.0
    # Default output path for the guru voice benchmark report.
    guru_voice_benchmark_output: str = "benchmarks/reports/guru_voice_benchmark.json"

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

    # --- Thresholds (P1 — de-hardcoded magic numbers) ---
    lettuce_detect_threshold: float = 0.25
    # S3: when True, use the real LettuceDetect span-level detector
    # (RAGTruth-trained, 14 langs). When False, fall back to the heuristic.
    # Default False until eval against RAGTruth/FaithBench passes — see audit S3.
    lettucedetect_enabled: bool = False
    cove_supported_threshold: float = 0.8
    cove_partial_threshold: float = 0.5
    # WHY 0.60: measured LettuceDetect scores for GOOD grounded answers on this
    # corpus sit at 0.71-0.74 (spiritual paraphrase never reaches 0.8). At the
    # old 0.8 floor, reflect_on_answer rejected every complex answer → 2 CRAG
    # rewrites → fallback ("I don't have that specific teaching") in 60-140s.
    # 0.60 clears real answers with margin; garbage still fails (<0.25 detector
    # floor). Do not raise without re-measuring the score distribution.
    faithfulness_floor: float = 0.6
    confidence_gating_floor: float = 6.5
    verifier_pass_ratio: float = 0.5
    rerank_threshold_complex: float = 0.01
    rerank_threshold_simple: float = 0.05
    rerank_floor: float = 0.3
    cross_encoder_cutoff: int = 20  # Use cross-encoder primary path when <= this many docs
    reranker_enabled_for_complex: bool = True  # Enable cross-encoder reranker for tier3_complex queries
    # Adaptive-RAG confidence gate: when >=3 reranked docs score at or above this
    # (sigmoid-normalized [0,1]), skip the LLM grading and sufficiency calls for
    # complex queries — saves 2 serial LLM round-trips. 0 disables.
    crag_skip_confidence: float = 0.75
    # --- RAGFlow integration gaps ---
    rag_deep_research_enabled: bool = False  # ponytail: master switch; auto-fires for tier3_complex + standard
    rag_deep_research_max_depth: int = 2
    important_kwd_boost_enabled: bool = True
    important_kwd_boost_per_term: float = 0.2
    rag_citation_cosine_enabled: bool = False  # default Jaccard (faster, no embedder dependency)
    # Citation similarity thresholds — adaptive by query type
    # Higher = stricter (fewer false positive citations)
    # P1-AI-12: base raised 0.18 → 0.30 (and the CASUAL override 0.12 → 0.20)
    # because loosely-related sentences were clearing the old floor and
    # producing false grounding signals. Keep the cosine path unchanged.
    citation_jaccard_threshold: float = 0.30      # default Jaccard threshold
    citation_cosine_threshold: float = 0.65       # used only when rag_citation_cosine_enabled=True
    # Per-intent overrides (merge with defaults)
    citation_thresholds_by_intent: dict[str, dict[str, float]] = Field(
        default_factory=lambda: {
            "FACTUAL":   {"jaccard": 0.20, "cosine": 0.70},
            "RELATIONAL": {"jaccard": 0.18, "cosine": 0.65},
            "QUERY":     {"jaccard": 0.18, "cosine": 0.65},
            "CASUAL":    {"jaccard": 0.20, "cosine": 0.55},
            "GREETING":  {"jaccard": 0.10, "cosine": 0.50},
            "DISTRESS":  {"jaccard": 0.15, "cosine": 0.60},
            "GUIDED_TOUR": {"jaccard": 0.12, "cosine": 0.55},
        }
    )
    raptor_clustering_method: str = "kmeans"  # "kmeans" | "gmm"

    # --- TTFT Optimization (Ruthless Audit Phase 1) ---
    # When True, verification runs concurrently with streaming — the first chunk is sent
    # immediately; only a hard verification failure silently falls back to FALLBACK_RESPONSE.
    # When False, generation and verification are fully sequential (legacy behaviour).
    rag_parallel_verify: bool = True
    # When True, skip the CoVe (sub-question verification) LLM calls for tier3_complex queries.
    # CoVe adds ~60s and up to 4 small LLM calls. LettuceDetect faithfulness scoring remains.
    # Default False (enabled) because the Guru Brain overhaul mandates CoVe for tier3/tier4
    # and for any answer whose faithfulness falls below faithfulness_floor.
    rag_cove_disabled: bool = False
    # Tiers for which CoVe is explicitly disabled. Verification nodes check this list to
    # keep fast/standard paths cheap while enabling Chain-of-Verification for tier3/tier4.
    rag_cove_disabled_for_tiers: list[str] = ["fast", "tier2_simple", "standard"]
    # CoVe compulsory threshold: if faithfulness_score < this, CoVe fires regardless of tier.
    cove_compulsory_threshold: float = 0.6  # same as faithfulness_floor
    # Agentic Graph Traversal configuration (for COMPARATIVE intent + tier3_complex)
    agentic_graph_traversal_enabled: bool = True
    agentic_graph_max_steps: int = 3
    agentic_graph_fast_model: str = "nim:meta/llama-3.1-8b-instruct"
    agentic_graph_timeout_per_step: int = 15
    # TTL in seconds for the retrieval-level doc-ID cache keyed by (query_embedding_bucket, tenant_id).
    # Reduces Qdrant round-trips for repeated query patterns by ~40%.
    retrieval_cache_ttl: int = 300
    # When True, skip the LLM-based retrieval expansion call (parallel-fire from
    # retrieve_documents). Saves 1 LLM call on the standard/deep paths. Off by
    # default to avoid changing generation behavior.
    rag_skip_retrieval_expansions: bool = False
    # When True, use heuristic pronoun/reference matching instead of an LLM call
    # to detect and contextualize follow-up queries. Saves 1 LLM call per query
    # with chat history. Off by default to avoid changing generation behavior.
    rag_heuristic_followup: bool = False


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

    # --- Push Notifications (Task 7 — mobile app launch) ---
    firebase_credentials_json: str = ""  # Raw JSON string OR path to file
    apns_key_id: str = ""
    apns_team_id: str = ""
    apns_key_path: str = ""  # Path to .p8 key file
    apns_key_pem: str = ""   # Raw PEM, alternative to path
    apns_bundle_id: str = "com.askmukthiguru.app"
    # APNs host: production by default. Set APNS_USE_SANDBOX=true to target api.sandbox.push.apple.com.
    apns_use_sandbox: bool = False
    apns_host: str = ""  # Optional override; otherwise derived from apns_use_sandbox.
    fcm_multicast_batch_size: int = 500  # firebase-admin multicast cap is 500.
    push_register_rate_limit: str = "10/minute"
    push_send_rate_limit: str = "30/minute"

    # --- Database Connection Pooling ---
    db_pool_size: int = 10  # Number of connections to maintain in pool
    db_max_overflow: int = 20  # Max overflow connections beyond pool_size
    db_pool_timeout: int = 30  # Seconds to wait for a connection from pool
    db_pool_pre_ping: bool = True  # Verify connections before using
    db_pool_recycle: int = 3600  # Recycle connections after this many seconds

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
    def admin_user_ids_list(self) -> list[str]:
        """Parse comma-separated admin user UUIDs into a list (P1-SEC-1 T4)."""
        if not self.admin_user_ids or not self.admin_user_ids.strip():
            return []
        return [u.strip() for u in self.admin_user_ids.split(",") if u.strip()]

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
        if self.llm_provider.lower() == "nim":
            return self.nim_generation_model
        if self.ollama_model:
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
        if self.llm_provider.lower() == "nim":
            return self.nim_classify_model
        if self.ollama_classify_model:
            return self.ollama_classify_model
        preset = self._PRESETS.get(self.model_preset.lower(), {})
        return preset.get("classification", "llama3.2:3b")

    @property
    def model_for_raptor(self) -> str:
        """Resolve the RAPTOR summary model from preset or custom config."""
        if self.raptor_summary_model:  # Explicit override
            return self.raptor_summary_model
        return self.model_for_generation  # Default to generation model

    @model_validator(mode="after")
    def validate_semantic_distress_escalation(self):
        """A rolling-window escalation count can't exceed the window itself —
        a count above the window can never be satisfied, silently disabling
        persistent-distress escalation."""
        if self.semantic_distress_escalation_count > self.semantic_distress_rolling_window:
            raise ValueError(
                "semantic_distress_escalation_count "
                f"({self.semantic_distress_escalation_count}) must be <= "
                f"semantic_distress_rolling_window ({self.semantic_distress_rolling_window})"
            )
        return self

    @model_validator(mode="after")
    def validate_anon_session_secret(self):
        """M5: anonymous session HMAC secret must be set in production.

        In dev/test (IS_PRODUCTION=false), derive a stable value from
        jwt_secret so existing tests pass without explicit config. In
        production, fail-closed — an empty secret would let any client
        forge anonymous identities and hijack incognito sessions.
        """
        if not self.anon_session_hmac_secret:
            if self.is_production:
                raise ValueError(
                    "anon_session_hmac_secret is required in production. "
                    "Set it to a high-entropy random string (>= 32 bytes)."
                )
            # Dev/test fallback: derive a stable key from jwt_secret. Tests
            # set JWT_SECRET in conftest.py, so this always has a value.
            base = self.jwt_secret or "dev-anon-session-fallback-key"
            import hashlib

            self.anon_session_hmac_secret = "anon_hmac_" + hashlib.sha256(
                (base + "::anon_session").encode()
            ).hexdigest()
        return self

    @model_validator(mode="after")
    def validate_api_keys(self):
        """Fail-fast on missing required API keys for the active provider."""
        # CENTRALIZED FALLBACK: If sarvam_30b_endpoint is provided, make sure we fallback base_url and api_key
        if getattr(self, "sarvam_30b_endpoint", None):
            if not getattr(self, "sarvam_api_key", "") and getattr(self, "sarvam_30b_api_key", None):
                self.sarvam_api_key = self.sarvam_30b_api_key
            if getattr(self, "sarvam_base_url", "") == "https://api.sarvam.ai/v1":
                self.sarvam_base_url = self.sarvam_30b_endpoint

        # Sanitize redis_url to strip 'default:' username if present (fixes Celery/Redis connection issues)
        redis_url = getattr(self, "redis_url", "") or ""
        if "@" in redis_url:
            prefix = "rediss://" if redis_url.startswith("rediss://") else "redis://"
            parts = redis_url.split("@", 1)
            auth_part = parts[0].replace(prefix, "")
            if ":" in auth_part:
                username, password = auth_part.split(":", 1)
                if username == "default":
                    self.redis_url = f"{prefix}:{password}@{parts[1]}"

        provider = self.llm_provider.lower()
        required_keys = {
            "sarvam_cloud": "sarvam_api_key",
            "openrouter": "openrouter_api_key",
            "nim": "nim_api_key",
            "anthropic": "anthropic_api_key",
            "krutrim": "krutrim_api_key",
            "emergent": "emergent_llm_key",
        }
        key_attr = required_keys.get(provider)
        if key_attr:
            # If using custom Sarvam 30B endpoint, skip the hard requirement of standard key
            if provider == "sarvam_cloud" and getattr(self, "sarvam_30b_endpoint", None):
                return self
            value = getattr(self, key_attr, "") or ""
            if not value.strip():
                raise ValueError(f"{key_attr} is required when llm_provider='{provider}'")
        if provider == "openrouter":
            from app.model_policy import OpenRouterModelPolicy

            OpenRouterModelPolicy.from_settings(self)

        return self



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

if __name__ == "__main__":
    import json

    s = get_settings()
    validated = {
        "kg_max_query_len": s.kg_max_query_len,
        "kg_query_timeout_s": s.kg_query_timeout_s,
        "qdrant_quantization": s.qdrant_quantization,
        "qdrant_quantization_oversampling": s.qdrant_quantization_oversampling,
    }
    print(f"Settings ok: {json.dumps(validated)}")




