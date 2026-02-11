# SPEC_DEV.md — Mukthi Guru: Digital Spiritual Guide

> **This is the source of truth.** Every line of code that follows must trace back to this document. If it's not here, it doesn't get built. If it conflicts with this, this wins.

---

## Vision
A **privacy-first, zero-hallucination AI spiritual guide** grounded exclusively in Sri Preethaji and Sri Krishnaji's teachings. The simplest robust solution that a single developer can build, deploy on free infrastructure, and maintain indefinitely.

## Constraints (Non-Negotiable)
| Constraint | Value |
|------------|-------|
| Budget | $0 — Free tier only (Colab, Qdrant local, Ollama) |
| Hardware | Google Colab T4 (16GB VRAM) / Local HP Victus (4GB VRAM fallback) |
| Privacy | All processing local or user-controlled. Zero external API calls at inference. |
| Accuracy | Near-zero hallucination target (< 1%) via multi-layer verification (CRAG + Self-RAG + CoVe). When unsure → "I don't know" (see Hallucination Measurement below) |
| License | Every dependency must be open source (Apache 2.0, MIT, or Meta Community) |
| Latency | < 3 seconds per response (happy path) |
| Data Source | Only Sri Preethaji & Sri Krishnaji's YouTube videos + approved images (see Content Permissions below) |

## What We Are Building (v1)

### Core: Conversational RAG
- User sends a spiritual question via chat
- System retrieves relevant teachings from knowledge base
- System generates a grounded, cited answer
- **11-layer anti-hallucination pipeline** ensures accuracy

### Feature: Serene Mind Meditation
- System detects user distress via intent classification
- Triggers a 4-step guided meditation flow
- Waits for user confirmation between steps

### Feature: Knowledge Ingestion
- Admin pastes a YouTube URL or image URL
- System transcribes/OCRs → cleans → chunks → embeds → indexes
- RAPTOR builds hierarchical summaries for thematic queries

### Feature: Safety Guardrails
- Block: crypto, politics, medical prescriptions, explicit content
- Detect: Self-harm/suicide → redirect to helpline
- Enforce: Every response cites its source or returns fallback

## What We Are NOT Building (v1)
- ❌ Fine-tuning pipeline (Stimulus RAG replaces this)
- ❌ Multi-user authentication
- ❌ WhatsApp/Telegram integration
- ❌ GraphRAG / Knowledge Graphs (deferred to v2)
- ❌ Real-time streaming responses
- ❌ Multi-language translation (Bhashini deferred to v2)

## Users
| Persona | Need |
|---------|------|
| **Spiritual Seeker** | Asks questions about teachings, gets cited answers |
| **Troubled Soul** | Expresses distress, gets guided meditation |
| **Admin (You)** | Ingests new content via URL |

## Success Criteria
| Metric | Target |
|--------|--------|
| Hallucination rate | < 1% (with "I don't know" fallback — see below) |
| Response time | < 3 seconds |
| Distress detection accuracy | > 90% |
| Meditation completion rate | > 70% |
| Video indexing time | < 15 minutes |

### Hallucination Measurement Methodology

**Definition**: A "hallucination" is any claim in the generated response that is NOT directly supported by the retrieved context documents. An "I don't know" fallback is NOT a hallucination — it is a correct refusal. A guardrail refusal (e.g., blocking off-topic queries) is also NOT a hallucination.

**Labeling protocol**: Ground truth is determined by human annotator comparison of each claim in the response against the retrieved context chunks. A claim is "hallucinated" if no context chunk supports it.

**Production measurement**:
| Parameter | Value |
|-----------|-------|
| Sample size | 100 responses per evaluation cycle |
| Sampling cadence | Weekly (or after each ingestion batch) |
| Evaluation rubric | Binary per-claim: SUPPORTED or UNSUPPORTED |
| Annotator QA | Single annotator + spot-check 20% by second reviewer |
| Confidence interval | 95% CI via binomial proportion (Wilson interval) |
| Reporting | Hallucination rate = (responses with ≥1 unsupported claim) / total |

**Component-composition math** — how per-layer thresholds compound:

The three verification layers are applied sequentially. A hallucination reaches the user only if it passes ALL three:

```
P(hallucination reaches user) = P(CRAG miss) × P(Self-RAG miss) × P(CoVe miss)
```

| Layer | Pass threshold | Miss rate (1 − threshold) |
|-------|---------------|---------------------------|
| CRAG grading | ≥ 90% | 10% |
| Self-RAG faithfulness | ≥ 95% | 5% |
| CoVe verification | ≥ 85% | 15% |

```
P(hallucination) = 0.10 × 0.05 × 0.15 = 0.000750 = 0.075%
```

**Result**: With the above per-component thresholds, the theoretical compounded hallucination rate is **~0.075%**, well under the < 1% target. Even with 2× worse real-world performance on each layer (20%, 10%, 30%), the compound rate is `0.20 × 0.10 × 0.30 = 0.60%` — still under 1%.

## Tech Stack (Locked)
| Layer | Tool | Reason |
|-------|------|--------|
| LLM | Llama 3.2 (Ollama, 4-bit quantized) | Best open model for reasoning; fits T4. **4-bit trade-off**: reduced precision may affect grading/verification quality — see Testing Checklist below |
| Orchestration | LangGraph | Cyclic graphs for CRAG/Self-RAG loops |
| Vector DB | Qdrant (local mode) | Rust, fast, persists to disk |
| Embeddings | all-MiniLM-L6-v2 | 80MB, CPU, 384 dims |
| Reranker | CrossEncoder ms-marco-MiniLM-L-6-v2 | 90MB, CPU, huge precision boost |
| Transcription | Whisper tiny | 39MB, CPU, English/Hindi |
| OCR | EasyOCR | 80+ languages, CPU |
| Guardrails | NeMo Guardrails | Colang DSL, Apache 2.0 |
| API | FastAPI | Async, auto-docs |
| Frontend | Existing React (Vite + Tailwind + ShadCN) | Already built |

## Architecture Summary
```
User → React Frontend → FastAPI /api/chat
  → NeMo Input Rail (block harmful)
  → Intent Router (DISTRESS/QUERY/CASUAL)
  → [QUERY] → Decompose → Retrieve (Qdrant top-20) → Rerank (CrossEncoder top-3)
  → CRAG Grade → [fail 3x] → "I don't know"
  → [pass] → Stimulus RAG Hints → Generate + Citations
  → Self-RAG Faithfulness Check → [fail] → "I don't know"
  → CoVe Verification → [fail] → "I don't know"
  → NeMo Output Rail → ✅ Response
```

## Terminology
| Term | Meaning |
|------|---------|
| **Stimulus RAG** | Extract key hint phrases from retrieved docs before generation |
| **CRAG** | Corrective RAG — grade docs, rewrite query if poor |
| **Self-RAG** | LLM checks its own answer for faithfulness |
| **CoVe** | Chain of Verification — generate sub-questions to fact-check |
| **RAPTOR** | Recursive clustering + summarization of chunks into a tree |
| **Beautiful State** | Core teaching — state of calm, joy, connection |
| **Serene Mind** | Meditation flow triggered by distress detection |

## 4-Bit Quantization Testing Checklist
Before deploying with 4-bit quantization, validate reasoning quality:

| Test | Method | Pass Threshold |
|------|--------|----------------|
| CRAG grading accuracy | 20 relevant + 20 irrelevant docs | ≥ 90% correct classification |
| Self-RAG faithfulness | 10 faithful + 10 fabricated answers | ≥ 95% detection rate |
| CoVe verification | 10 verifiable + 5 unverifiable claims | ≥ 85% correct verdicts |
| Intent classification | 10 distress + 10 query + 10 casual | ≥ 90% accuracy |

**Fallback plan**: If tests fail, switch to 8-bit quantization (`ollama pull llama3.2:8b-q8_0`). Re-run checklist. If 8-bit also fails, use `llama3.1:8b` (larger context, better reasoning).

## Content Permissions Checklist
This project uses copyrighted content. **All items must be confirmed before deployment.**

| Item | Status | Details | Responsible |
|------|--------|---------|-------------|
| YouTube ToS reviewed for transcription/indexing | ✅ Reviewed | YouTube ToS [Section 4B](https://www.youtube.com/static?template=terms) — API-based access requires compliance with YouTube API ToS; direct transcription via `youtube-transcript-api` uses publicly available caption data. Fair use analysis applies for educational/non-commercial use with transformative purpose. | Developer |
| Copyright/IP clearance for listed videos | ☐ Pending | Requires written permission from Sri Preethaji & Sri Krishnaji (or authorized representative) before ingesting their content. | Developer |
| Written permission obtained (if required) | ☐ Pending | Upload signed permission document and set link below. | Developer |
| Permission documents linked | ☐ Placeholder | Set `permission_documents_link` to the URL of the uploaded document once obtained. | Developer |

**Tracked fields**:
| Field | Value | Notes |
|-------|-------|-------|
| `permissions_confirmed` | `false` | Set to `true` only after ALL items above are confirmed |
| `youtube_tos_reviewed` | `true` | Reviewed YouTube ToS Section 4B — compliant for caption-based access |
| `copyright_clearance` | `false` | Set to `true` only after obtaining signed written permission from content owners |
| `permission_documents_link` | `TBD` | URL to uploaded signed permission document |

> [!CAUTION]
> **Do not deploy publicly or run ingestion code until `permissions_confirmed` is `true`.**
> Written permission from the content owners is required before any content is ingested.
> The `copyright_clearance` field must only be set to `true` after uploading the signed permission document.
