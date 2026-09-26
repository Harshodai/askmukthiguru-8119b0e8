# AskMukthiGuru — Ruthless Completion Prompt
## Paste this entire file as your opening message to Claude Code

---

## CONTEXT: What You Are Picking Up

You are continuing work on **AskMukthiGuru** — a production-safe verbatim-answer RAG pipeline for Sri Preethaji and Sri Krishnaji teachings. A prior session ran ~15 hours, shipped substantial code, and verified what was done and what was not.

**Repo:** `/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8`
**Backend venv:** `backend/.venv/bin/python3`
**Data dir (outside git):** `~/mukthiguru_attribution_data/`
**Governing files to read first:** `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `handoff.md`, `backend/CLAUDE.md`, `docs/agent/NON_NEGOTIABLES.md`

---

## INVARIANTS — NON-NEGOTIABLE, NEVER VIOLATE

1. **Zero AI fabrication.** Gold labels come from human Annotator A only. Never generate gold labels.
2. **Persistent writes:** Dry-run → Report → Snapshot → Explicit Owner Approval → Apply. Never skip steps.
3. **No `git commit` or `git push`** without explicit user instruction.
4. **Every LLM `.generate()` output reaching Qdrant MUST pass `find_artifact()`** (from `services.text_quality_filter`).
5. **No ASR (Whisper/Parakeet) while benchmark is running.** Check `pgrep -fl evaluation.bench` first.
6. **Use MCP graph tools BEFORE grep/glob.** See `GEMINI.md` for tool priority order.
7. **Write plan to `.claude/tasks/TASK_NAME.md` before touching code. Ask user to review before starting.**

---

## WHAT IS CURRENTLY WORKING (DO NOT BREAK)

| System | State |
|---|---|
| Backend test suite | 7,726 passed, 0 failed (`cd backend && .venv/bin/python3 -m pytest tests/ -q`) |
| Frontend vitest | 631 passed |
| Docker: mukthiguru-backend | healthy, RestartCount=1 |
| Docker: qdrant, redis, memgraph | healthy, RestartCount=0 |
| Gap 1 — long-speech sub-chunking | DONE — `speaker_diarization.py:168-229` |
| Gap 3 — sparse vector wired | DONE — `api/first_person.py:81-96` |
| Gap 4 — Conformal Risk Control profile loader | DONE — `first_person_pipeline.py:65` |
| Live eval (116 questions, 3 runs) | PASS — top-1=0.434, p95<210ms, 0 non-teacher, 0 hash failures |
| Benchmark Run 1 | LIVE — DO NOT KILL — check `pgrep -fl evaluation.bench` |

---

## WHAT YOU MUST COMPLETE — 4 TASKS IN PRIORITY ORDER

---

### TASK 1 (CRITICAL — Do First): Fix Benchmark Auth Session Pooling

**Why critical:** Benchmark Run 1 has a **74% ERR rate** (646/866 questions timing out at 180s). Root cause: `bench.py` calls `POST /api/auth/anon-session` per question, hitting the 5 req/60s rate limit.

**The session pool is implemented in `backend/evaluation/session_pool.py`.** Check whether it has been wired into `bench.py` (search for `session_pool` or `BenchmarkSessionPool` in bench.py). If already wired, skip to verifying the pool behaves correctly under 429 rate limits. If not yet wired, proceed with the steps below.

**Steps:**
1. Read `backend/evaluation/bench.py` lines 440–510 — find `mint_anon_session()` and all callers.
2. Read `backend/evaluation/session_pool.py` (full file).
3. Wire `BenchmarkSessionPool` into `bench.py`:
   - At benchmark startup, call `pool.warm_up()` to pre-mint `concurrency * 2` sessions (spaced 12.5s apart).
   - Each worker task uses `async with pool.acquire_session() as token:` instead of calling `mint_anon_session()` per question.
   - Pass the leased token to the question-asking code exactly as the minted token was before.
4. Write `backend/tests/test_bench_session_pool.py`:
   - Test `warm_up()` mints exactly N tokens.
   - Test `acquire_session()` is reentrant — token returns to pool after context exit.
   - Test HTTP 429 on warm_up raises correctly.
5. Run: `cd backend && .venv/bin/python3 -m pytest tests/test_bench_session_pool.py -v`
6. Run full suite: `cd backend && .venv/bin/python3 -m pytest tests/ -q --tb=short`

> **DO NOT kill benchmark PID.** Fix applies to Run 2 which starts automatically after Run 1.

---

### TASK 2: Gap 2 — Dexa Acoustic Pre-Roll & Resonance Tail in Citation

**Problem:** `_build_citation()` at `backend/services/first_person_pipeline.py:397-418` only emits `timestamp_seconds`. Missing:
- `playback_start_seconds` = max(0, start_ms/1000 − 2.5) — 2.5s acoustic lead-in
- `playback_end_seconds` = end_ms/1000 + 1.8 — 1.8s resonance tail
- `playback_url` = YouTube deep link built from `playback_start_seconds`

**Current code (lines 397-418):**
```python
def _build_citation(clip, clip_confidence, provenance_kind):
    sec = clip["start_ms"] // 1000
    video_id = clip["video_id"]
    return {
        "timestamp_seconds": sec,
        "source_url": f"https://www.youtube.com/watch?v={video_id}&t={sec}s",
        # ... no playback fields
    }
```

**What to add (additive only — keep all existing keys):**

Add at module top (near line 59):
```python
CITATION_PRE_ROLL_S: float = 2.5
CITATION_TAIL_S: float = 1.8
```

Inside `_build_citation()`:
```python
playback_start = max(0.0, clip["start_ms"] / 1000.0 - CITATION_PRE_ROLL_S)
playback_end = clip["end_ms"] / 1000.0 + CITATION_TAIL_S
playback_url = f"https://www.youtube.com/watch?v={video_id}&t={int(playback_start)}s"
```

Add to returned dict:
```python
"playback_start_seconds": round(playback_start, 2),
"playback_end_seconds": round(playback_end, 2),
"playback_url": playback_url,
```

**Tests to add in `backend/tests/test_first_person_pipeline.py`:**
- Assert `playback_start_seconds = max(0, start_ms/1000 - 2.5)`
- Assert `playback_end_seconds = end_ms/1000 + 1.8`
- Assert `playback_url` contains `&t=` with correct offset
- Assert `playback_start_seconds=0` when `start_ms < 2500` (floor case)
- Assert existing tests still pass (do not break integrity gate)

Run: `cd backend && .venv/bin/python3 -m pytest tests/test_first_person_pipeline.py -v`

---

### TASK 3: Gap 5 — Whisper ASR Hardening (SACRED_VOCABULARY_PROMPT)

**Problem:** `grep -r "SACRED_VOCABULARY_PROMPT\|condition_on_previous_text" backend/` returns zero results. Whisper hallucination suppression is completely absent for Ekam/Sanskrit terminology.

**Create `backend/services/speech_config.py`:**

```python
"""
Whisper ASR hardening for AskMukthiGuru spiritual corpus.
Prevents hallucination on Ekam/Sanskrit terminology via vocabulary seeding.
Reference: Whisper paper §4.5 (initial_prompt), OpenAI cookbook.
"""

# Sacred vocabulary hint for the Whisper decoder.
# Must stay under 224 tokens (Whisper context window for the prompt).
SACRED_VOCABULARY_PROMPT: str = (
    "Preethaji, Krishnaji, Ekam, deeksha, Antaryamin, moola mantra, "
    "Oneness, Mukti, Ananda, awakening, consciousness, suffering, beautiful state, "
    "compassion, presence, neurobiology, Four Sacred Secrets, "
    "Sri Preethaji, Sri Krishnaji, World Oneness University, "
    "Ekam World Peace Festival, O&O Academy, satsang, darshan."
)

# Apply these kwargs at every Whisper transcribe() call site.
WHISPER_HARDENING_KWARGS: dict = {
    "initial_prompt": SACRED_VOCABULARY_PROMPT,
    "condition_on_previous_text": False,  # prevents hallucination cascade
}
```

**Wire it:** Search for `model.transcribe\|whisper.transcribe\|mlx_whisper\|faster_whisper` across the repo and spread `**WHISPER_HARDENING_KWARGS` at each call site.

**Create `backend/tests/test_speech_config.py`:**
- Assert `SACRED_VOCABULARY_PROMPT` is non-empty string
- Assert `len(SACRED_VOCABULARY_PROMPT.split()) <= 220`
- Assert `WHISPER_HARDENING_KWARGS["condition_on_previous_text"] is False`
- Assert `WHISPER_HARDENING_KWARGS["initial_prompt"] == SACRED_VOCABULARY_PROMPT`
- Assert "Preethaji" and "Krishnaji" appear in the prompt

Run: `cd backend && .venv/bin/python3 -m pytest tests/test_speech_config.py -v`

---

### TASK 4: Gap 6 — Frontend Citation Contract Tests for Playback Fields

**Depends on Task 2 being done first.**

**Problem:** `src/test/citation-contract.test.tsx` (109 lines, 11 tests) has zero assertions for `playback_start_seconds`, `playback_end_seconds`, `playback_url`.

**Step A — Update the TypeScript type** in `src/lib/chat/types.ts` (or wherever `DiscourseCitation` is defined):
```typescript
playbackStartSeconds?: number;
playbackEndSeconds?: number;
playbackUrl?: string;
```

**Step B — Update `normalizeCitations`** to map:
- `playback_start_seconds` → `playbackStartSeconds` (treat 0 as valid, not absent)
- `playback_end_seconds` → `playbackEndSeconds`
- `playback_url` → `playbackUrl`

**Step C — Update `DiscourseVideoModal`** to prefer `playbackStartSeconds` over `startTimestamp` for the iframe `start=` parameter.

**Step D — Add tests to `src/test/citation-contract.test.tsx`:**
```typescript
it('maps playback_start_seconds, playback_end_seconds, playback_url to camelCase', () => {
  const [citation] = normalizeCitations([{
    url: 'https://youtu.be/abc123',
    playback_start_seconds: 39.5,
    playback_end_seconds: 67.3,
    playback_url: 'https://www.youtube.com/watch?v=abc123&t=39s',
  }]);
  expect(citation.playbackStartSeconds).toBe(39.5);
  expect(citation.playbackEndSeconds).toBe(67.3);
  expect(citation.playbackUrl).toBe('https://www.youtube.com/watch?v=abc123&t=39s');
});

it('treats playback_start_seconds of 0 as valid — not absent', () => {
  const [citation] = normalizeCitations([{
    url: 'https://youtu.be/abc123',
    playback_start_seconds: 0,
  }]);
  expect(citation.playbackStartSeconds).toBe(0);
});

it('DiscourseVideoModal uses playbackStartSeconds as iframe start when present', () => {
  render(<DiscourseVideoModal isOpen onClose={() => {}} citation={{ ...baseCitation, playbackStartSeconds: 39 }} />);
  expect(document.querySelector('iframe')?.getAttribute('src')).toContain('start=39');
});

it('DiscourseVideoModal falls back to startTimestamp when playbackStartSeconds absent', () => {
  render(<DiscourseVideoModal isOpen onClose={() => {}} citation={{ ...baseCitation, startTimestamp: 42 }} />);
  expect(document.querySelector('iframe')?.getAttribute('src')).toContain('start=42');
});
```

Run: `cd /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8 && npx vitest run src/test/citation-contract.test.tsx`
Then: `npx vitest run`

---

## VERIFICATION GATE — Run All Before Declaring Done

```bash
# 1. Backend full suite
cd /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend
.venv/bin/python3 -m pytest tests/ -q --tb=short
# MUST: 0 failures, same or more tests than 7,726

# 2. New tests specifically
.venv/bin/python3 -m pytest \
  tests/test_bench_session_pool.py \
  tests/test_first_person_pipeline.py \
  tests/test_speech_config.py -v

# 3. py_compile on every touched Python file
.venv/bin/python3 -m py_compile \
  services/speech_config.py \
  services/first_person_pipeline.py \
  evaluation/bench.py \
  evaluation/session_pool.py

# 4. Frontend
cd /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8
npx vitest run
# MUST: 0 failures, 631+ passing

# 5. Benchmark still alive or completed cleanly
pgrep -fl "evaluation.bench"
```

---

## KEY FILES — READ THESE FIRST

```
CLAUDE.md                                             governing invariants
AGENTS.md                                             ingestion safety, deployment blockers
GEMINI.md                                             plan-before-code, MCP tool priority
handoff.md                                            full verified state as of 2026-09-25
backend/CLAUDE.md                                     backend commands, request flow, hard rules
backend/services/first_person_pipeline.py             _build_citation() at line 397
backend/evaluation/bench.py                           mint_anon_session() at line 447
backend/evaluation/session_pool.py                    BenchmarkSessionPool (complete, unwired)
src/test/citation-contract.test.tsx                   11 existing tests, needs 4 more
src/lib/chat/types.ts                                 normalizeCitations and DiscourseCitation type
docs/agent/WORLD_CLASS_AUDIO_VIDEO_RAG_RESEARCH_2026.md  full research synthesis
```

---

## WHAT NOT TO DO

- Do NOT run ASR — benchmark is live
- Do NOT `git commit` or `git push`
- Do NOT write to Qdrant/Neo4j without dry-run → approval cycle
- Do NOT generate gold labels with AI
- Do NOT use semantic cache for first-person route answers
- Do NOT use grep/glob before trying MCP graph tools (`semantic_search_nodes`, `get_impact_radius`)
- Do NOT claim done without running the full verification gate and showing output

---

## SUCCESS — All 7 Must Be True

1. `BenchmarkSessionPool` is used in `bench.py` — zero per-question anon-session calls
2. `_build_citation()` returns `playback_start_seconds`, `playback_end_seconds`, `playback_url`
3. `backend/services/speech_config.py` exists with `SACRED_VOCABULARY_PROMPT` and `WHISPER_HARDENING_KWARGS`
4. `citation-contract.test.tsx` has tests asserting all 3 playback fields
5. Backend: 0 failures (≥7,726 tests)
6. Frontend: 0 failures (≥631 tests)
7. Benchmark PID alive or completed cleanly — NOT killed
