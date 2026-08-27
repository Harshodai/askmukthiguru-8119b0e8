# Ingestion Safety — Hard Rules for LLM Output Persistence

> **Canonical safety reference for the Mukthi Guru ingestion pipeline.**
> Created Aug 28, 2026 after a production audit found 13.7% of 89,061 live
> Qdrant chunks contaminated with LLM artifacts, provider fallback strings,
> and phantom-success checkpoint desyncs.

---

## The Three Root-Cause Bug Classes

Every contamination incident in the corpus traces back to one of these three
classes. Each has a hard rule that MUST hold for all LLM call sites in
`backend/ingest/`, `backend/services/`, and `backend/scripts/`.

---

### Rule #1 — Every LLM Output Reaching Qdrant MUST Pass `find_artifact()`

**Root cause:** LLM-generated text (context headers, topic labels, RAPTOR
summaries, "Potential Questions", OKF entries) was concatenated into chunk
content and embedded/persisted to Qdrant **without any quality gate**. When a
reasoning-tuned model (Sarvam-105b, DeepSeek-R1) leaked chain-of-thought
("The user wants me to...", "Let me analyze this..."), the leaked text was
embedded as retrievable doctrine and quoted verbatim to seekers.

**Hard rule:**

```
EVERY call to llm.generate() / llm.summarize() / _call_api() whose output
(or any transformation of it) reaches Qdrant as chunk content, topic label,
RAPTOR summary, context header, potential question, or OKF entry MUST pass
through services.text_quality_filter.find_artifact() (or its wrappers
is_clean() / select_clean()) BEFORE persistence.

Adding a new LLM call site in backend/ingest/ or backend/services/ that
writes to Qdrant without this gate is a P0 bug.
```

**Per-provider failure modes:**

| Provider | Failure Mode | How `find_artifact()` Catches It |
|----------|-------------|----------------------------------|
| **Sarvam-105b** | Reasoning-tuned; leaks CoT ("The user wants me to...") when `operation` is not set (defaults to medium reasoning) | Regex: `\bThe user (?:wants me to\|has provided\|is asking)` |
| **DeepSeek-R1** (via Ollama) | Emits `<think>...</think>` blocks or inline reasoning | Regex: `\bLet me (?:analyze\|break this\|think about)` |
| **OpenRouter** | `_graceful_degradation()` returns canned string instead of raising | `is_graceful_degradation()` marker check inside `find_artifact()` |
| **NIM** | Same `_graceful_degradation()` pattern as OpenRouter | Same marker check |
| **Any provider** | Echoes instruction prompt back | Regex: `\bReturn ONLY a JSON\b`, `\bDo NOT include reasoning\b` |

**Guarded call sites (as of Aug 28, 2026):**

| File | Function | Gate |
|------|----------|------|
| `pipeline.py:_extract_topics` | Topic labels | `clean_topic_label()` on BOTH JSON happy path and fallback |
| `pipeline.py:_hypothetical_questions` | Potential questions | Inline `find_artifact()` at line 3022 + `select_clean` on write path |
| `pipeline.py:_embed_and_index` | All chunks → Qdrant | `select_clean()` at line 2640 |
| `raptor.py:build_tree` | RAPTOR summary nodes | `select_clean()` after faithfulness gate, before upsert |
| `proposition_service.py:extract_propositions` | Sub-chunk propositions | Replaced into chunks → `select_clean` in `_embed_and_index` |
| `corrector.py:_correct_chunk` | Corrected transcript | `_contains_prompt_leak` + downstream `select_clean` |
| `contextual_chunking_service.py:_enrich_one` | Context headers | `find_artifact()` with retry + fallback to unenriched chunk |
| `extract_okf_from_stores.py:_call_llm` | OKF entries | `find_artifact()` before return + `_write_okf_entry` body validation |
| `video_pipeline.py` | Video chunks | `select_clean()` at line 245 |
| `contextual_reingest.py` | Contextual chunks | `select_clean()` at line 1393 |
| `qdrant/indexer.py` | Final Qdrant write | `select_clean()` at line 107 |

**Verification:**

```bash
# Confirm every Qdrant write path has a quality gate
grep -rn "find_artifact\|is_clean\|select_clean\|is_graceful_degradation" \
    backend/ingest/ backend/services/ backend/scripts/ \
    --include="*.py" | grep -v test | grep -v __pycache__
```

---

### Rule #2 — Provider Graceful-Degradation Returns Content, Not Exceptions

**Root cause:** `OpenRouterService._graceful_degradation()` and
`NimService._graceful_degradation()` return a canned string ("I'm currently
experiencing a temporary connection issue...") **instead of raising an
exception** when the provider call fails. This is correct behavior for a
live chat reply (the user sees a friendly message), but **catastrophic when
the same code path is reused at ingestion time**: the canned string reaches
Qdrant verbatim as fake `[Context: ...]`, `[Potential Questions: ...]`, or
RAPTOR summary content.

**Hard rule:**

```
Ingestion code MUST treat a graceful-degradation return as an error, not
content. The canonical check is:

    from app.constants import is_graceful_degradation
    if is_graceful_degradation(text):
        raise RuntimeError("Provider returned fallback, not real content")

As of Aug 28, 2026, this check is wired into find_artifact() itself, so
any caller of find_artifact/is_clean/select_clean automatically catches it.
```

**Why the provider can't just raise:**

The `_graceful_degradation()` pattern exists because the live chat path needs
a user-visible fallback message when all providers are down. Changing it to
raise would break chat. The fix is at the **consumer** side: ingestion code
must validate that the LLM output is real content, not a fallback.

**Affected providers and their fallback strings:**

```python
# OpenRouterService._graceful_degradation():
"I'm currently experiencing a temporary connectivity issue..."

# NimService._graceful_degradation():
"I'm here and listening. Due to a temporary connection issue..."

# Both contain the canonical marker: "temporary connect"
# Detected by: app.constants.is_graceful_degradation(text)
# which checks: GRACEFUL_DEGRADATION_MARKER = "temporary connect"
```

**OllamaService** does NOT have this problem — it raises
`ModelUnavailableError` when the circuit breaker is open.

---

### Rule #3 — Every Idempotency Checkpoint MUST Cross-Validate Against Data Store State

**Root cause:** The ingestion pipeline has multiple independent idempotency
mechanisms that can desync from actual Qdrant/Neo4j state:

1. **`IngestionCheckpoint` (Redis)** — Two independent namespaces:
   - Outer: URL-keyed (`bulk_ingest_video.py` checks before calling `pipeline.ingest_url()`)
   - Inner: content-hash-keyed (inside `_ingest_video`, e.g. `pipeline.py:1229`)

2. **`ingestion_state.json` (local file)** — `contextual_reingest.py` caches
   processed `source_url`s locally.

If Qdrant/Neo4j data is wiped but only one checkpoint namespace is cleared
(or the local file persists), the surviving checkpoint silently short-circuits
and returns `{"status": "success", "chunks_indexed": 0}` — a **phantom success**
with zero real work done, difficult to notice because it still logs "✅ Success".

**Hard rule:**

```
Every checkpoint/dedup mechanism MUST cross-validate against the actual data
store before trusting its cached "already processed" state. If the target
Qdrant collection has 0 points but the checkpoint claims N sources processed,
the checkpoint is STALE and MUST be cleared.

When wiping Qdrant/Neo4j data, you MUST also clear:
  1. Redis IngestionCheckpoint (both URL and content-hash namespaces)
  2. Local ingestion_state.json (contextual_reingest.py)
  3. Any per-source "already indexed" flags

The safest approach: use the --force / skip_processed=False flag when
re-ingesting after a data wipe.
```

**Safe mechanisms (no desync risk):**

| Mechanism | Why Safe |
|-----------|---------|
| Qdrant deterministic point-ID + `upsert` | Wiped Qdrant → re-inserts same IDs |
| `check_source_exists()` scroll query | Queries live Qdrant state |
| LSH near-dup index seeded from Qdrant | Empty collection → empty index |
| Neo4j idempotent `MERGE` | Acts as `CREATE` after wipe |

---

## Adding a New LLM Call Site — Checklist

If you're adding a new `llm.generate()` call in the ingestion pipeline:

- [ ] Does the output reach Qdrant (directly or via transformation)? → MUST pass `find_artifact()`
- [ ] Does the call use Sarvam? → Set `operation="summarize"` (or appropriate operation for low reasoning)
- [ ] Is the call in a path shared with live chat? → Check for `is_graceful_degradation()` (already in `find_artifact()`)
- [ ] Does the function have a retry? → Ensure retry also checks `find_artifact()` on retry output
- [ ] Does the function have a fallback? → Fallback to unenriched/original content, NEVER to chunk loss
- [ ] Is the result cached/checkpointed? → Ensure the checkpoint cross-validates against data store state
- [ ] Is there a test? → Add a test with a contaminated input to verify the gate catches it
