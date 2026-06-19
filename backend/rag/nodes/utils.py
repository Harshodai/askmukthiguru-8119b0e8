"""Shared utilities and helper functions for RAG pipeline nodes."""

from __future__ import annotations

import functools
import logging
import re
import time
from typing import Any, Optional


# Proxy to allow settings to be patched dynamically at the package level in tests
class SettingsProxy:
    def __getattr__(self, name: str) -> Any:
        import sys
        nodes = sys.modules.get("rag.nodes")
        if nodes is not None and hasattr(nodes, "settings") and nodes.settings is not None:
            return getattr(nodes.settings, name)
        from app.config import settings as app_settings
        return getattr(app_settings, name)

settings = SettingsProxy()

from app.metrics import PIPELINE_STAGE_LATENCY
from rag.states import GraphState
from rag.timeout_utils import get_node_timeout
from services.rrf_ranker import reciprocal_rank_fusion

from . import _services

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase-2 / Truth-3: SSE status emission helper
# ---------------------------------------------------------------------------
async def emit_status(config: Optional[dict], message: str) -> None:
    """
    Push an SSE `event: status` frame onto the stream queue if the orchestrator
    provided one via LangGraph's `configurable`.

    Safe to call from any node. No-op when:
      - config is None (non-streaming /api/chat path)
      - config has no stream_queue (graph compiled without queue)
      - queue is full / not a Queue (defensive)

    Pattern mirror of `rag/nodes/retrieval.py:retrieve_documents` lines 248-255,
    extracted so the other 17 nodes can opt in with a single line.

    Why this matters: between `retrieve_documents` (which already emits) and
    `generate_answer` (which streams tokens), the user otherwise stares at a
    blank screen for 8-30 seconds while decompose/grade/verify run silently.
    """
    if config is None:
        return
    try:
        if hasattr(config, "get"):
            configurable = config.get("configurable", {}) or {}
        elif hasattr(config, "configurable"):
            configurable = config.configurable or {}
        else:
            return
        q = configurable.get("stream_queue")
        if q is None:
            return
        await q.put({"event": "status", "data": message})
    except Exception:
        # Status emission must never break the pipeline.
        pass

# -----------------------------------------------------------------------
# COT Patterns & Reasoning Markers
# -----------------------------------------------------------------------
_COT_PATTERNS = [
    r"<think>.*?</think>",
    # Catch standard CoT preambles
    r"(?is)^\s*(we are given|we need to|we must|let me analyze|i need to analyze|analysis:|let's draft|now,?\s*count|we have used|we can write|we have cited|we must check|we must ensure|we must not|we must output).*?(?=\n\n|beloved|dear one|seeker|friend|the teaching|according to|$)",
    r"(?im)^\s*(step\s*\d+|reasoning|chain of thought|scratchpad)\s*[:.-].*$",
    r"(?im)^\s*(first,?\s*)?i(?:'| a)?ll analyze.*$",
    # Sarvam-specific: catch lines that are purely internal verification
    r"(?im)^\s*(?:Note|Checklist|Verification|Important):.*$",
    # Catch numbered bold lists of reasoning steps (e.g. 1. **Analyze...** or 1. **Deconstruct...**)
    # Applied iteratively in strip_cot so sequential steps like "2. **Initial Scan**" are all removed.
    r"(?im)^\s*\d+[\s.)]+(?:\*\*)?(?:Analyze|Scan|Initial Scan|Formulate|Draft|Evaluate|Check|Verify|Review|Identify|Translate|Filter|Retrieve|Select|Generate|Output|Synthesize|Compare|Determine|Process|Resolve|Find|Cite|Locate|Deconstruct|Read|Parse|Extract|Consider|Assess|Start|Address|Keep|Explain|Write|Answer|State|Structure)\b.*?(?=\n\s*\d+|\n\n(?![*\s])|\Z)",
    # Catch lines starting with bullets or drafts reasoning about rules
    r"(?im)^\s*\*?\s*(?:Draft|This seems|Let's|Final check|Start with|Address|Keep it|Drafting)\b.*$",
]

# Markers that signal start of Sarvam's internal reasoning monologue
# when they appear AFTER the real answer has already started.
_SARVAM_REASONING_MARKERS = [
    "now, count words:",
    "we must check:",
    "we must ensure",
    "we must not",
    "we can write:",
    "let's draft:",
    "we have cited",
    "we have used",
    "we have not repeated",
    "that's within",
    "that's acceptable",
    "we must output",
    "now, we must",
    "we must keep it within",
    "count words:",
    "we are consistent",
    "we must check the token count",
    # Sarvam-30b internal analysis markers
    "initial scan of the context",
    "i'll quickly read through",
    "quickly read through the provided",
    "scan of the context",
    "let me quickly scan",
]

# Canonical URL map: keywords that appear in LLM answers -> authoritative web URLs.
_CANONICAL_URL_MAP: list[tuple[list[str], str]] = [
    # Topic-keyword triggers -> canonical sources (for KG/LightRAG docs without source_url)
    (["soul sync", "breath awareness", "humming", "golden light", "guided meditation"],
     "https://www.youtube.com/c/pkconsciousness"),
    (["four sacred secrets", "sacred secret", "inner truth", "spiritual vision",
      "spiritual right action", "universal intelligence", "connected consciousness"],
     "https://www.amazon.in/Four-Sacred-Secrets-Prosperity-Beautiful/dp/1846046319"),
    (["manifest 2026", "monthly power", "karma cleansing", "power of intention",
      "lokaa foundation", "lokaa", "village welfare"],
     "https://theonenessmovement.org/manifest"),
    (["deeksha", "oneness blessing", "parietal lobe", "frontal lobe",
      "neuroscience", "brain activation"],
     "https://www.ekam.org/"),
    (["ekam world peace festival", "world peace festival", "day 7", "peace festival",
      "collective human evolution"],
     "https://www.ekam.org/"),
    (["serene mind", "breathing room app", "breathingroom"],
     "https://www.breathingroom.com/"),
    # URL-mention triggers -> direct citations
    (["ekam.org", "ekam world", "world centre for enlightenment"], "https://www.ekam.org/"),
    (["youtube.com/c/pkconsciousness", "pkconsciousness", "official youtube channel"],
     "https://www.youtube.com/c/pkconsciousness"),
    (["theonenessmovement.org", "oneness movement"],
     "https://theonenessmovement.org/"),
    (["amazon.com/Four-Sacred-Secrets", "amazon"],
     "https://www.amazon.in/Four-Sacred-Secrets-Prosperity-Beautiful/dp/1846046319"),
    (["amazon.in/Four-Sacred-Secrets", "amazon.in", "amazon india"],
     "https://www.amazon.in/Four-Sacred-Secrets-Prosperity-Beautiful/dp/1846046319"),
    (["simon & schuster", "simonandschuster.com", "simon and schuster"],
     "https://www.amazon.in/Four-Sacred-Secrets-Prosperity-Beautiful/dp/1846046319"),
]

# -----------------------------------------------------------------------
# Doctrinal Synonyms — Query Expansion for Spiritual Teachings
# -----------------------------------------------------------------------
DOCTRINE_SYNONYMS: dict[str, list[str]] = {
    # Core teachings
    "beautiful state": ["beautiful state", "blissful state", "state of bliss", "state of calm", "state of joy"],
    "suffering state": ["suffering state", "state of suffering", "painful state", "state of pain"],
    "surrender": ["surrender", "letting go", "giving up control", "relinquishing", "total surrender"],
    "oneness": ["oneness", "unity", "non-duality", "non-dual", "advaita", "non separation"],
    "consciousness": ["consciousness", "awareness", "higher consciousness", "divine consciousness", "universal consciousness"],
    "ekam": ["ekam", "ekam world", "world centre for enlightenment", "world center for enlightenment"],
    "deeksha": ["deeksha", "oneness blessing", "divine blessing", "energy transmission", "sacred transfer"],
    "soul sync": ["soul sync", "soul synchronization", "breath meditation", "breath awareness meditation"],
    "four sacred secrets": ["four sacred secrets", "4 sacred secrets", "sacred secrets", "the four secrets"],
    "sri preethaji": ["sri preethaji", "preethaji", "preetha ji", "sree preethaji"],
    "sri krishnaji": ["sri krishnaji", "krishnaji", "krishna ji", "sree krishnaji"],
    "meditation": ["meditation", "dhyana", "dhyan", "contemplation", "mindfulness practice"],
    "dharma": ["dharma", "righteousness", "righteous path", "duty", "cosmic order"],
    "karma": ["karma", "karmic", "action and consequence", "law of cause and effect"],
    "moksha": ["moksha", "liberation", "enlightenment", "spiritual freedom", "self-realization"],
    "atma": ["atma", "atman", "soul", "inner self", "higher self", "true self"],
    "brahman": ["brahman", "brahman", "universal self", "supreme reality", "absolute reality"],
    "samsara": ["samsara", "cycle of birth", "rebirth", "worldly cycle"],
    "guru": ["guru", "master", "spiritual teacher", "spiritual guide", "enlightened master"],
    "sadhna": ["sadhna", "sadhana", "spiritual practice", "spiritual discipline", "spiritual sadhana"],
    "sadhak": ["sadhak", "seeker", "spiritual seeker", "practitioner", "devotee"],
    "mahavakya": ["mahavakya", "great saying", "great pronouncement", "vedic statement"],
    "satsang": ["satsang", "spiritual gathering", "spiritual discourse", "divine gathering"],
    "sankalpa": ["sankalpa", "intention", "resolve", "sacred intention", "spiritual resolve"],
    "vairagya": ["vairagya", "dispassion", "detachment", "non-attachment", "renunciation"],
    "bhakti": ["bhakti", "devotion", "divine devotion", "loving devotion", "devotional practice"],
    "jnana": ["jnana", "knowledge", "spiritual knowledge", "divine wisdom", "higher knowledge"],
    "kriya": ["kriya", "action", "spiritual action", "sacred action", "purificatory practice"],
    "mantra": ["mantra", "sacred sound", "sacred syllable", "divine chant", "spiritual chant"],
    "mayic force": ["mayic force", "illusion force", "deluding force", "maya", "illusory power"],
    "dharma prabhu": ["dharma prabhu", "lord of dharma", "lord of righteousness", "divine lawkeeper"],
    "jeevan mukta": ["jeevan mukta", "jeevanmukta", "liberated while living", "living liberated one"],
    "paramatma": ["paramatma", "paramatman", "supreme soul", "universal soul", "supreme self"],
    "prarabdha": ["prarabdha", "prarabdha karma", "matured karma", "destined karma", "fruit of past actions"],
}


class TokenBudgetExceeded(Exception):
    """Raised when an LLM call would exceed its per-node token budget."""

    def __init__(self, node: str, estimated: int, budget: int):
        self.node = node
        self.estimated = estimated
        self.budget = budget
        super().__init__(
            f"[{node}] Estimated tokens ({estimated:,}) exceed budget ({budget:,}). "
            "Reduce context or increase budget."
        )


def _estimate_tokens(text: str) -> int:
    """Fast heuristic: ~1.3 tokens per word (works for English + Indic)."""
    if not text:
        return 0
    return int(len(text.split()) * 1.3)


def _enforce_token_budget(node_name: str, text: str, budget: int) -> None:
    """Hard enforcement: raises TokenBudgetExceeded if text exceeds budget."""
    estimated = _estimate_tokens(text)
    if estimated > budget:
        raise TokenBudgetExceeded(node_name, estimated, budget)


def expand_query_with_synonyms(query: str) -> str:
    """Expand user query with doctrinal synonyms for better retrieval coverage."""
    query_lower = query.lower()
    expansions: list[str] = []
    for canonical, alternates in DOCTRINE_SYNONYMS.items():
        if canonical in query_lower:
            # Add alternate forms not already in the query
            for alt in alternates:
                if alt not in query_lower and alt != canonical:
                    expansions.append(alt)
    if expansions:
        expanded = f"{query} (also: {', '.join(expansions[:5])})"
        logger.info(f"Query expansion: added {len(expansions)} synonym(s) -> {expanded[:120]}...")
        return expanded
    return query


def inject_doctrine_keywords(query: str) -> str:
    """Inject known doctrine keywords into a query to improve retrieval coverage.
    
    Delegates to the comprehensive keyword_injection module with 9 doctrine categories.
    """
    from rag.nodes.keyword_injection import inject_doctrine_keywords as _ki
    return _ki(query, top_k=3)


def _remove_repetition_loops(text: str) -> str:
    """Detect and remove generation loops: lines/paragraphs repeating 3+ times."""
    if not text or len(text) < 120:
        return text

    lines = text.split("\n")
    seen_counts: dict[str, int] = {}
    result_lines: list[str] = []
    for line in lines:
        key = line.strip()
        if len(key) >= 20:
            seen_counts[key] = seen_counts.get(key, 0) + 1
            if seen_counts[key] > 2:
                logger.warning(
                    f"Repetition loop detected at line #{len(result_lines)}: '{key[:60]}...' — truncating."
                )
                return "\n".join(result_lines).rstrip()
        result_lines.append(line)

    paragraphs = re.split(r"\n{2,}", "\n".join(result_lines))
    if len(paragraphs) >= 4:
        seen_paras: dict[str, int] = {}
        result_paras: list[str] = []
        for para in paragraphs:
            key = para.strip()[:120]
            if len(key) >= 30:
                seen_paras[key] = seen_paras.get(key, 0) + 1
                if seen_paras[key] > 2:
                    logger.warning("Paragraph repetition loop detected — truncating.")
                    return "\n\n".join(result_paras).rstrip()
            result_paras.append(para)

    return "\n".join(result_lines)


def _grounded_citation_urls(docs: list[dict]) -> list[str]:
    """Extract citable web URLs from retrieved docs."""
    urls = []
    seen = set()
    for doc in docs:
        url = (doc.get("source_url") or "").strip()
        if not url or url.lower() in {"none", "n/a", "knowledge_graph"}:
            continue
        if not url.startswith("http://") and not url.startswith("https://"):
            continue
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _inject_canonical_citations(answer: str, existing_citations: list[str]) -> list[str]:
    """Scan the LLM answer for known canonical URLs and topic keywords and inject citations."""
    if not answer:
        return existing_citations

    answer_lower = answer.lower()
    enriched = list(existing_citations)
    existing_set = {u.lower() for u in existing_citations}

    for keywords, canonical_url in _CANONICAL_URL_MAP:
        if canonical_url.lower() in existing_set:
            continue
        if any(kw.lower() in answer_lower for kw in keywords):
            enriched.append(canonical_url)
            existing_set.add(canonical_url.lower())

    return enriched


def _trace_update(state: GraphState, **updates) -> dict:
    trace = dict(state.get("evaluation_trace") or {})
    trace.update(updates)
    return trace


async def _llm_retrieval_expansions(state: GraphState) -> list[str]:
    """Ask the model to propose retrieval-only reformulations without encoding doctrine in code."""
    if state.get("query_tier") in ("fast", "tier2_simple"):
        return []
    
    ollama = _services._ollama
    if ollama is None:
        return []

    question = state.get("rewritten_query") or state["question"]
    history = state.get("chat_history", [])[-6:]
    history_lines = []
    for msg in history:
        role = msg.get("role", "user")
        content = (msg.get("content") or "")[:300]
        history_lines.append(f"{role}: {content}")

    prompt = (
        "You are the retrieval planner for Mukthi Guru. Generate up to 3 search queries "
        "that would help retrieve source teachings for the user's question. Use only "
        "terms implied by the question and conversation history. Do not answer the "
        "question. Do not invent facts. Return one query per line, no numbering.\n\n"
        f"Conversation history:\n{chr(10).join(history_lines) if history_lines else '(none)'}\n\n"
        f"User question:\n{question}\n\nSearch queries:"
    )
    try:
        raw = await ollama._generate_fast(
            system_prompt="You create concise retrieval search queries only.",
            user_prompt=prompt,
            timeout=get_node_timeout("default_fast", getattr(settings, "node_timeout_fast", 15)),
            max_retries=1,
        )
    except Exception as e:
        logger.warning(f"LLM retrieval expansion failed; continuing without expansion: {e}")
        return []

    queries: list[str] = []
    for line in raw.splitlines():
        cleaned = re.sub(r"^\s*[-*\d.)]+\s*", "", line).strip().strip('"')
        if cleaned and cleaned.lower() != question.lower() and len(cleaned) <= 240:
            queries.append(cleaned)
    return list(dict.fromkeys(queries))[:3]


def strip_cot(text: str) -> str:
    """Remove leaked reasoning scaffolding from model output before it reaches users."""
    if not text:
        return text

    cleaned = text
    # Apply CoT patterns iteratively until the text stabilises.  A single pass
    # can leave partial traces (e.g. step-2 after step-1 is removed) because the
    # regex lookahead anchors on adjacent numbered steps that no longer exist.
    for _ in range(4):  # max 4 iterations — prevents infinite loops on edge cases
        prev = cleaned
        for pattern in _COT_PATTERNS:
            cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL).strip()
        if cleaned == prev:
            break  # stable — no more changes

    # Split into paragraphs and filter out any paragraph that starts with a reasoning marker
    paragraphs = cleaned.split("\n\n")
    filtered_paragraphs = []
    for para in paragraphs:
        para_strip = para.strip()
        if not para_strip:
            continue
        para_lower = para_strip.lower()
        normalized_para = re.sub(r"^[\s\d.*#_()\[\]-]+", "", para_lower)
        
        is_reasoning = False
        for marker in _SARVAM_REASONING_MARKERS:
            if normalized_para.startswith(marker):
                is_reasoning = True
                break
        
        if not is_reasoning:
            filtered_paragraphs.append(para_strip)
            
    cleaned = "\n\n".join(filtered_paragraphs)

    cleaned_lower = cleaned.lower()
    for marker in _SARVAM_REASONING_MARKERS:
        idx = cleaned_lower.find(marker)
        if idx != -1 and idx > 100:
            cleaned = cleaned[:idx].strip()
            cleaned_lower = cleaned.lower()

    for marker in ["Final answer:", "Answer:", "Mukthi Guru:"]:
        idx = cleaned.lower().find(marker.lower())
        if idx != -1:
            cleaned = cleaned[idx + len(marker) :].strip()

    cleaned = _remove_repetition_loops(cleaned)
    if not cleaned:
        return "I apologize, but I am unable to formulate a complete response right now. Please allow me to share some relevant teachings from the sacred knowledge base instead."
    return cleaned


def _generation_kwargs(state: GraphState) -> dict:
    """Bound generation length by routing tier while preserving room for distress care."""
    intent = state.get("intent", "FACTUAL")
    query_tier = state.get("query_tier")

    base = {}
    if intent == "DISTRESS":
        base["num_predict"] = 2048
    elif query_tier in ("fast", "tier2_simple"):
        base["num_predict"] = 512
    elif intent in {"FACTUAL", "QUERY"}:
        base["num_predict"] = 1024
    elif intent in {"RELATIONAL", "ADVERSARIAL"}:
        base["num_predict"] = 768
    else:
        base["num_predict"] = 768

    # Temperature per graph mode (Phase 2.1)
    if query_tier in ("fast", "tier2_simple"):
        base["temperature"] = settings.generation_temp_fast
    elif query_tier in ("deep", "tier3_complex"):
        base["temperature"] = settings.generation_temp_deep
    else:
        base["temperature"] = settings.generation_temp_standard

    # Record generation metrics (Phase 2.1)
    try:
        from app.metrics import GENERATION_TEMPERATURE, GENERATION_TOP_K
        tier_label = "fast" if query_tier in ("fast", "tier2_simple") else "deep" if query_tier in ("deep", "tier3_complex") else "standard"
        GENERATION_TEMPERATURE.labels(strategy=tier_label).set(base.get("temperature", 0.7))
        GENERATION_TOP_K.labels(strategy=tier_label).set(base.get("num_predict", 1024))
    except Exception:
        pass

    return base


def select_llm_model(query: str, context_len: int) -> str:
    """Determines optimal model routing to balance latency and context capacity."""
    complex_enabled = getattr(settings, "sarvam_complex_routing_enabled", False)
    if not complex_enabled:
        return getattr(settings, "sarvam_cloud_model", "sarvam-30b")

    threshold = getattr(settings, "sarvam_complex_context_chars", 20000)
    if context_len >= threshold or len(query) > 2000:
        return getattr(settings, "sarvam_cloud_complex_model", "sarvam-105b")

    return getattr(settings, "sarvam_cloud_model", "sarvam-30b")


def _rrf_docs(ranked_lists: list[list[dict]], k: int = 60) -> list[dict]:
    """Apply Reciprocal Rank Fusion to lists of document dicts."""
    id_to_doc: dict[int, dict] = {}
    id_rankings: list[list[int]] = []

    for ranked_list in ranked_lists:
        id_list = []
        for doc in ranked_list:
            key = id(doc)
            id_to_doc[key] = doc
            id_list.append(key)
        id_rankings.append(id_list)

    sorted_ids = reciprocal_rank_fusion(id_rankings, k=k)
    return [id_to_doc[key] for key in sorted_ids]


def _generation_route(state: GraphState, context_chars: int = 0) -> dict:
    """Select generation model via config, not benchmark-answer hardcoding."""
    kwargs = _generation_kwargs(state)
    provider = getattr(settings, "llm_provider", "unknown")
    decision = state.get("query_tier") or "default"

    question = state.get("rewritten_query") or state.get("question", "")
    model = select_llm_model(question, context_chars)

    complex_enabled = getattr(settings, "sarvam_complex_routing_enabled", False)
    complex_model = getattr(settings, "sarvam_cloud_complex_model", "")
    is_complex = state.get("query_tier") in ("deep", "tier3_complex") or bool(state.get("is_complex"))
    is_high_risk = state.get("intent") in {"ADVERSARIAL", "RELATIONAL"}

    if complex_enabled and complex_model and (is_complex or is_high_risk):
        model = complex_model
        decision = "complex_model"

    if model and provider.lower() == "sarvam_cloud":
        kwargs["model"] = model

    kwargs["_route_metadata"] = {
        "model_used": model,
        "model_provider": provider,
        "route_decision": decision,
    }
    return kwargs


def _extract_source_id(citation_str: str) -> str | None:
    """Extract a canonical source identifier from a citation URL.
    For YouTube: returns the video ID. For other URLs: returns netloc+path."""
    if not citation_str or not isinstance(citation_str, str):
        return None
    # YouTube ID
    import re
    m = re.search(r"[?&]v=([^&]+)", citation_str)
    if m:
        return m.group(1)
    # Direct timestamp or /watch/ URLs
    m = re.search(r"youtu\.be/([^/?&]+)", citation_str)
    if m:
        return m.group(1)
    # Generic: strip query params, use netloc+path
    from urllib.parse import urlparse
    try:
        parsed = urlparse(citation_str)
        return f"{parsed.netloc}{parsed.path}"
    except Exception:
        return citation_str


def enforce_source_diversity(citations: list[dict | str], min_distinct: int = 2) -> list[dict | str]:
    """Ensure top citations draw from at least min_distinct sources.
    Works with both dict docs (source_id/video_id) and plain URL strings."""
    if not citations or len(citations) < min_distinct:
        return list(citations)

    top = list(citations[:3])
    sources: set[str | None] = set()
    for c in top:
        if isinstance(c, dict):
            sid = c.get("source_id") or c.get("video_id")
            sources.add(sid)
        else:
            sources.add(_extract_source_id(c))

    # Remove None from set
    distinct = {s for s in sources if s}
    if len(distinct) >= min_distinct:
        return list(citations)

    # Promote a citation from a different source into the top-3
    result = list(citations)
    existing: set[str | None] = set()
    for c in top:
        existing.add(_extract_source_id(c) if not isinstance(c, dict) else (c.get("source_id") or c.get("video_id")))

    for i, c in enumerate(result[3:], start=3):
        sid = _extract_source_id(c) if not isinstance(c, dict) else (c.get("source_id") or c.get("video_id"))
        if sid and sid not in existing:
            result.insert(2, result.pop(i))
            break

    return result


def log_metrics(func):
    """Decorator to log execution time of nodes and record into GraphState.node_timings.

    Also implements per-node error boundaries (Phase 2.2): if a node raises,
    the error is caught, logged, and a fallback result is returned instead of
    crashing the entire pipeline.
    """

    @functools.wraps(func)
    async def wrapper(state: GraphState, *args, **kwargs):
        start = time.time()
        node_name = func.__name__
        request_id = state.get("request_id")
        log_extra = {"request_id": request_id} if request_id else {}

        try:
            result = await func(state, *args, **kwargs)
        except Exception as e:
            duration = time.time() - start
            duration_ms = round(duration * 1000, 1)
            logger.error(
                f"Node '{node_name}' failed after {duration:.4f}s ({duration_ms}ms): {e}",
                extra=log_extra,
                exc_info=True,
            )
            from app.metrics import NODE_ERROR_TOTAL, NODE_FALLBACK_TOTAL
            try:
                NODE_ERROR_TOTAL.labels(node=node_name).inc()
                NODE_FALLBACK_TOTAL.labels(node=node_name).inc()
            except Exception:
                pass
            return {
                "error": str(e),
                "node": node_name,
                "fallback": True,
                "node_timings": {node_name: duration_ms},
            }

        duration = time.time() - start
        duration_ms = round(duration * 1000, 1)

        logger.info(
            f"Node '{node_name}' finished in {duration:.4f}s ({duration_ms}ms)", extra=log_extra
        )

        try:
            PIPELINE_STAGE_LATENCY.labels(stage=node_name).observe(duration)
        except Exception:
            pass

        metrics = state.get("metrics") or {}
        metrics[node_name] = duration

        node_timings_update = {node_name: duration_ms}

        if isinstance(result, dict):
            existing_metrics = result.get("metrics", {})
            existing_metrics.update(metrics)
            result["metrics"] = existing_metrics
            existing_timings = result.get("node_timings", {})
            existing_timings.update(node_timings_update)
            result["node_timings"] = existing_timings

        return result

    return wrapper


def _require_state(state: GraphState, required: list[str]) -> Optional[dict]:
    """Helper to enforce node contracts. Returns an error dict if keys are missing."""
    missing = [k for k in required if k not in state]
    if missing:
        logger.error(f"NodeContractError: missing required keys: {missing}")
        return {"error": f"NodeContractError: missing required keys: {missing}"}
    return None