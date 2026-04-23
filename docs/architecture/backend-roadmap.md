# Mukthi Guru — Consolidated backend roadmap

> **Source of truth note**: This document consolidates two upstream research
> reports — `source-report.md` (draft) and `source-verified-report.md`
> (fact-checked). **Where they disagree, `source-verified-report.md` is
> authoritative.** Items below have already been corrected against the
> verified facts. Read [`README.md`](./README.md) for the full conflict list.

---

## Legend

- 🟥 **Critical** — blocks production launch
- 🟧 **High** — meaningful UX, cost, or quality impact
- 🟨 **Medium** — nice-to-have, do after launch
- 🟦 **FE** — implementable in this Lovable React repo
- 🟫 **BE** — requires changes in `backend/` (Python FastAPI)

Effort estimates are rough developer-days for an experienced engineer.

---

## ✅ Already shipped in this repo (frontend)

These items came out of the reports and are now **live** in the React app:

| Item | Files | Notes |
|------|-------|-------|
| 22-language UI picker (was 4) | `src/components/chat/LanguageSelector.tsx` | All 22 scheduled Indian languages + English. Browser STT/TTS capability detected per language and surfaced as a small badge. |
| Citations rendered as a "Sources" card | `src/components/chat/ChatMessage.tsx`, `src/lib/chatStorage.ts` | Was raw markdown links inline. Now a collapsible footer card. |
| 401 / 429 error states surfaced as toasts | `src/lib/aiService.ts`, `src/components/chat/ChatInterface.tsx` | New `errorCode` on `AIResponse`. Friendly copy for rate limits. |
| Connection-mode pill in app header | `src/components/layout/AppShell.tsx`, `src/lib/aiService.ts` | Polls `checkConnection()` every 30s. Shows `Offline Mode` / `Connected to Guru` / `Reconnecting…`. |
| Serene Mind reachable from anywhere | `src/components/common/SereneMindProvider.tsx`, `src/components/layout/AppShell.tsx`, `src/components/common/CommandPalette.tsx` | Global modal, header flame, ⌘K action. Modal now has Breathe / Audio / Video tabs. Distress responses open Audio tab. |

---

## 🟫 Backend tickets (NOT implemented here — open in `backend/`)

### 🟥 Critical

#### BE-1. Replace Ollama with Sarvam Cloud API
- **Source**: `source-verified-report.md` §2 (verified), `source-report.md` §3 (superseded — wrong pricing)
- **Verified facts**:
  - Sarvam Cloud is **currently free per token** (no published per-token price). Rate-limited.
  - Public model: `sarvamai/sarvam-30b` on Hugging Face. There is **no** "Sarvam-2B".
  - LangChain integration: `pip install langchain-sarvamcloud` (verified package).
- **Effort**: 2–3 days
- **Files to touch (backend)**: `backend/services/ollama_service.py` → new `sarvam_service.py`, `backend/rag/nodes.py`, `backend/.env.example`, `backend/requirements.txt`.
- **Risk**: Sarvam free tier may add pricing or stricter limits. Keep Ollama as a `LLM_PROVIDER=ollama` fallback.

#### BE-2. JWT auth + per-user rate limiting on `/api/chat`
- **Source**: `source-verified-report.md` §5
- **Plan**: `fastapi-users` for JWT, `slowapi` (Redis-backed) for rate limiting. Default: 10 req/min per user.
- **Effort**: 2 days
- **Surfaces 401 / 429** which the frontend already handles (see ✅ shipped list).

#### BE-3. Multilingual distress classifier
- **Current**: `mrm8488/distilroberta-finetuned-depression` — English-only.
- **Recommended**: `xlm-roberta-base` fine-tuned, or fall back to keyword + LLM zero-shot in 22 languages.
- **Source**: `source-verified-report.md` §3
- **Effort**: 3 days incl. eval set
- **Files**: `backend/services/depression_detector.py`

### 🟧 High

#### BE-4. Multilingual system prompts (only after BE-1)
- Test first whether Sarvam-30B handles Indic input with the **English** system prompt — verified report says it often does. Only translate prompts if eval shows quality drop.
- **Source**: `source-verified-report.md` §2
- **Effort**: 1 day testing + 2 days translation if needed
- **Files**: `backend/rag/prompts.py`

#### BE-5. YouTube channel auto-sync
- **Verified**: only `@PreetiKrishna` is confirmed authentic. Other channel handles in `source-report.md` (e.g. `@EkamOfficial`) are unverified — do not auto-ingest.
- **Plan**: cron job hits YouTube Data API for the verified channel only, queues new uploads through existing `ingest/pipeline.py`.
- **Effort**: 2 days
- **Files**: `backend/ingest/youtube_loader.py`, new scheduled task

#### BE-6. Semantic cache (Redis)
- Cache embeddings + final answers keyed by question hash + user language.
- **Source**: `source-verified-report.md` §4
- **Effort**: 1 day
- **Files**: `backend/services/cache_service.py` (extend), `backend/rag/nodes.py`

### 🟨 Medium

#### BE-7. MMR diversity reranking
- Current rerank picks top-k by score. MMR avoids near-duplicate chunks.
- **Effort**: 0.5 day
- **Files**: `backend/rag/nodes.py:rerank_documents`

#### BE-8. Observability — Opik or Phoenix
- Trace every LangGraph run. Helps debug hallucination cases.
- **Effort**: 1 day setup
- **Files**: `backend/app/main.py` (instrumentation), env config

#### BE-9. Eval harness — DeepEval or Ragas
- Golden set of ~50 spiritual Q&A. Run on every PR.
- **Effort**: 2 days
- **Files**: new `backend/tests/evals/`

---

## ❌ Rejected / corrected from the draft report

These items appeared in `source-report.md` but were debunked by
`source-verified-report.md`. **Do not implement.**

- ❌ "Self-host Sarvam-2B on a ₹55K–2.5L A100" — model does not exist; pricing wrong.
- ❌ "Auto-ingest @EkamOfficial channel" — channel unverified.
- ❌ "Switch to vLLM for 5× throughput on the 8GB GPU" — Sarvam-30B does not fit on 8GB; vLLM only relevant if BE-1 falls through and we self-host on an A100.
- ❌ "Use `sarvam-ai` HF org" — correct org is `sarvamai`.

---

## Dependency graph

```
BE-1 (Sarvam) ──► BE-4 (multilingual prompts)
              └─► BE-6 (cache uses Sarvam outputs)

BE-2 (auth) ──► (frontend errorCode handling — already shipped)

BE-3 (multilingual distress) ──► (independent)

BE-5 (YT sync) ──► (independent, uses existing ingest pipeline)
```

Recommended order: **BE-2 → BE-1 → BE-3 → BE-4 → BE-6 → BE-5 → BE-7 → BE-8 → BE-9**.
