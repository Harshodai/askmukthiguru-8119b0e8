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

## Verification & Testing (Completed)
1. Run `backend/.venv/bin/pytest backend/tests/test_prompts_decomposition.py -v` (PASSED)
2. Run `backend/.venv/bin/pytest backend/tests/test_memory_service.py -v` (PASSED)
3. Commit with `feat(caching): restructure prompts for stable prefix caching` (Done, pushed to remote as `6b19d783`)

## Detailed Description of Changes

1. **`backend/rag/prompts/system.py`**:
   - `MULTI_TURN_PROMPT` restructured to place static instructions `INSTRUCTIONS FOR MULTI-TURN COHERENCE:` at the very beginning of the prompt, and the dynamic `{history}` variable at the end under a clean header block.

2. **`backend/rag/nodes/intent.py`**:
   - Inside `handle_distress` prompt construction, the static empathy instructions, meditation guidelines, and tone rules are now placed first.
   - Dynamic seeker message `{question}` and retrieved teachings `{context}` are placed at the end.

3. **`backend/rag/nodes/verification.py`**:
   - Inside lightweight CoVe subquestion check (`_cove_subquestion_check`):
     - `prompt`: Placed instructions first, followed by dynamic inputs (`Question: {question}`, `Answer: {answer}`).
     - `verify_prompt`: Placed instructions first, followed by dynamic `Context` and `Sub-question: {sq}`.

4. **`backend/services/memory_service.py`**:
   - Inside `consolidate_memories` user message: Placed JSON schema instructions first, followed by dynamic memory list `{memory_list_str}`.
   - Inside `extract_memories` user message: Placed extraction instructions and expected JSON schema block first, followed by dynamic deduplication context `{dedup_section}` and conversation transcript `{transcript}`.

5. **`backend/services/memory_service_v2.py`**:
   - Inside memory extraction/classification user message: Placed classification guidelines and expected JSON schema first, followed by the dynamic user reflection `{content}`.

All changes have been verified to pass tests cleanly, and were successfully committed and pushed to the remote repository.
