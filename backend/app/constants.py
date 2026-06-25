"""Centralized constants for LLM provider names and other shared identifiers.

Single source of truth to prevent hardcoding mismatches across the codebase.
"""

from enum import Enum


class LLMProvider(str, Enum):
    """LLM Provider identifiers - must match LLM_PROVIDER config values."""

    SARVAM_CLOUD = "sarvam_cloud"
    OLLAMA = "ollama"
    OPENROUTER = "openrouter"


class CircuitBreakerProvider(str, Enum):
    """Circuit breaker provider identifiers - must match LLMProvider values."""

    SARVAM_CLOUD = LLMProvider.SARVAM_CLOUD.value
    OLLAMA = LLMProvider.OLLAMA.value
    OPENROUTER = LLMProvider.OPENROUTER.value


class CachePrefix(str, Enum):
    """Redis cache key prefixes."""

    EXACT = "mukthiguru:cache"
    SEMANTIC = "mukthiguru:semcache"


class AuthProvider(str, Enum):
    """Authentication provider identifiers."""

    SUPABASE = "supabase"
    LOCAL = "local"
    TEST = "test"


class QueryTier(str, Enum):
    """Query routing tier identifiers."""

    FAST = "fast"
    STANDARD = "standard"
    DEEP = "deep"
    TIER2_SIMPLE = "tier2_simple"


class IntentType(str, Enum):
    """Intent classification types."""

    QUERY = "QUERY"
    FACTUAL = "FACTUAL"
    CASUAL = "CASUAL"
    DISTRESS = "DISTRESS"
    MEDITATION = "MEDITATION"
    MEDITATION_CONTINUE = "MEDITATION_CONTINUE"
    ADVERSARIAL = "ADVERSARIAL"
    SAFETY_VIOLATION = "SAFETY_VIOLATION"
    ERROR = "ERROR"


# Provider-specific circuit breaker configs
CIRCUIT_BREAKER_CONFIGS = {
    CircuitBreakerProvider.SARVAM_CLOUD: {
        "failure_threshold": 5,
        "recovery_timeout": 90.0,
        "half_open_max_calls": 3,
    },
    CircuitBreakerProvider.OLLAMA: {
        "failure_threshold": 3,
        "recovery_timeout": 60.0,
        "half_open_max_calls": 1,
    },
    CircuitBreakerProvider.OPENROUTER: {
        "failure_threshold": 5,
        "recovery_timeout": 60.0,
        "half_open_max_calls": 3,
    },
}


# Default timeouts per provider
DEFAULT_TIMEOUTS = {
    LLMProvider.SARVAM_CLOUD: 60.0,
    LLMProvider.OLLAMA: 30.0,
    LLMProvider.OPENROUTER: 30.0,
}

# Reasoning effort defaults per provider
REASONING_EFFORT_DEFAULTS = {
    LLMProvider.SARVAM_CLOUD: {
        "fast": "low",
        "standard": "medium",
        "complex": "high",
    },
    LLMProvider.OLLAMA: {
        "fast": "low",
        "standard": "medium",
        "complex": "high",
    },
}

# Models per provider
PROVIDER_MODELS = {
    LLMProvider.SARVAM_CLOUD: {
        "default": "sarvam-30b",
        "classify": "sarvam-30b",
        "complex": "sarvam-105b",
    },
    LLMProvider.OLLAMA: {
        "default": "deepseek-r1:7b",
        "classify": "deepseek-r1:7b",
    },
    LLMProvider.OPENROUTER: {
        "default": "meta-llama/llama-3.3-70b-instruct:free",
        "classify": "meta-llama/llama-3.1-8b-instruct",
        "fast": "meta-llama/llama-3.1-8b-instruct",
    },
}

# --- Phase 2 Ruthless Integration Constants ---
FEEDBACK_LESSONS_FILE_PATH = "backend/data/feedback_lessons.jsonl"
PROMPT_PATCHES_VALIDATED_FILE_PATH = "backend/data/prompt_patches_validated.jsonl"
CONCEPT_SIMILARITY_THRESHOLD = 0.78
MAX_COST_STEERED_HISTORY_TURNS = 3
COST_STEERED_BREVITY_LIMIT = 80