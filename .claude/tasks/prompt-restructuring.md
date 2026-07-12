# Task Plan: Prompt Restructuring for Prompt Caching Optimization

## Objective
Optimize prompt templates across the codebase for stable prefix/prompt caching. By placing static instructions and expected schemas at the beginning of the prompt and dynamic variables (e.g. user messages, conversation history, retrieved context, transcript snippets) at the end, the LLM provider can cache the static prefix, reducing latency and cost.

## Files & Changes

### 1. `backend/rag/prompts/system.py`
- **Target**: `MULTI_TURN_PROMPT`
- **Current Layout**:
  - Dynamic `{history}` block is at the top.
  - Static instructions block (`INSTRUCTIONS FOR MULTI-TURN COHERENCE`) is below it.
- **Change**:
  - Move the static instruction list to the beginning.
  - Move the `{history}` block to the end under a header.

### 2. `backend/rag/nodes/intent.py`
- **Target**: `prompt` inside `handle_distress` (around lines 740-750)
- **Current Layout**:
  - Dynamic user message (`{question}`) and retrieved context (`{context}`) are at the top.
  - Static instructions (empathy, meditation offer, guidelines) are at the bottom.
- **Change**:
  - Move static instructions to the beginning.
  - Move `{question}` and `{context}` to the end.

### 3. `backend/rag/nodes/verification.py`
- **Target**: `_cove_subquestion_check` prompts (around lines 288-307)
- **Current Layout (prompt)**:
  - Dynamic inputs (`Question: {question}\nAnswer: {answer}`) are first, then static instructions.
- **Change (prompt)**:
  - Move static instructions first, followed by dynamic `Question` and `Answer` inputs at the end.
- **Current Layout (verify_prompt)**:
  - Dynamic `Context:\n{context}` is first, followed by dynamic `Sub-question: {sq}` and static instructions.
- **Change (verify_prompt)**:
  - Move static instructions ("Does the context support a 'yes' answer...") first, followed by dynamic `Context` and `Sub-question` inputs at the end.

### 4. `backend/services/memory_service.py`
- **Target 1**: `consolidate_memories` user message (around lines 450-462)
  - Current Layout: Dynamic memories (`{memory_list_str}`) first, then static schema instructions.
  - Change: Static schema and instructions first, followed by dynamic memories.
- **Target 2**: `extract_memories` user message (around lines 610-628)
  - Current Layout: Dynamic/mixed guidelines, then dynamic `dedup_section`, then dynamic `transcript`, then static schema.
  - Change: Static guidelines and schema first, followed by dynamic `dedup_section` and `transcript`.

### 5. `backend/services/memory_service_v2.py`
- **Target**: `extract_memories`/classification user message (around lines 116-124)
  - Current Layout: Dynamic reflection content (`{content}`) first, then static schema.
  - Change: Static instructions and schema first, followed by dynamic reflection content.

## Verification & Testing
1. Run `pytest backend/tests/test_prompts_decomposition.py -v`
2. Run `pytest backend/tests/test_memory_service.py -v`
3. Commit with `feat(caching): restructure prompts for stable prefix caching`

## Security/Design Safety
- The changes are strictly text/formatting restructurings in strings and f-strings. No runtime dependencies or application logic are altered.
- All f-string variables are preserved exactly as named to avoid NameErrors.
