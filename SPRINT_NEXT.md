# Next Sprint Plan — June 2026

**Theme**: Stability, Observability, and Code Quality

## Sprint Goals
1. Resolve all outstanding `TODO` / `FIXME` items in production code
2. Bring file sizes into ECC compliance (< 800 lines backend, < 400 lines frontend)
3. Strengthen telemetry (production wiring, not placeholders)
4. Run the LightRAG vs Qdrant benchmark and record findings
5. Migrate remaining hardcoded thresholds to `Settings` class

---

## Backlog

### P0 — Code Quality (ECC Compliance)
| # | Task | File(s) | Current Lines | Target |
|---|------|---------|---------------|--------|
| 1 | Refactor `main.py` into route modules | `backend/app/main.py` | 1,643 | < 800 |
| 2 | Split `ruthless_benchmark.php into sub-modules | `backend/benchmarks/ruthless_benchmark.py` | 1,659 | < 800 |
| 3 | Decompose `question_bank.py` into bank + runner | `backend/benchmarks/question_bank.py` | 2,073 | < 800 |
| 4 | Extract dashboard generators from benchmark scripts | `backend/benchmarks/generate_dashboard.py` | 1,287 | < 800 |
| 5 | Refactor `sarvam_service.py` into gateway + service | `backend/services/sarvam_service.py` | 1,193 | < 800 |
| 6 | Split `pipeline.py` into stages (fetch, correct, audit, embed, upsert) | `backend/ingest/pipeline.py` | 1,064 | < 800 |
| 7 | Decompose `telemetry_db.py` into per-domain modules | `backend/app/telemetry_db.py` | 1,372 | < 800 |
| 8 | Split `generation.py` into smaller files | `backend/rag/nodes/generation.py` | 810 | < 800 |
| 9 | Split `prompts.py` by node or strategy | `backend/rag/prompts.py` | 810 | < 800 |
| 10 | Refactor `ollama_service.py` into provider-specific modules | `backend/services/ollama_service.py` | 917 | < 800 |

### P0 — Frontend Refactoring
| # | Task | File(s) | Current Lines |
|---|------|---------|---------------|
| 11 | Decompose `ChatInterface.tsx` into sub-components (Header, Input, List, Status) | `src/components/chat/ChatInterface.tsx` | 1,689 |
| 12 | Split `AuthPage.tsx` into Login/Register/Reset sub-pages | `src/pages/AuthPage.tsx` | 836 |
| 13 | Refactor `ProfilePage.tsx` into feature sections | `src/pages/ProfilePage.tsx` | 768 |
| 14 | Split `aiService.ts` into streaming, REST, health modules | `src/lib/aiService.ts` | 688 |
| 15 | Decompose `ChatMessage.tsx` into message types | `src/components/chat/ChatMessage.tsx` | 726 |

### P1 — Telemetry & Observability
| # | Task | File | Status |
|---|------|------|--------|
| 16 | Wire `SupabaseSink.flush()` to actual Supabase `telemetry_events` table insert | `backend/app/telemetry/sinks.py` | ✅ Done |
| 17 | Wire `thumbs_up_rate` to real feedback table query | `backend/app/telemetry_db.py` | ✅ Done |
| 18 | Re-ranking weight pipeline on negative feedback | `backend/services/feedback_service.py` | ✅ Done (logs + background job stub) |
| 19 | Golden dataset collection on positive feedback | `backend/services/feedback_service.py` | ✅ Done (logs + dataset stub) |
| 20 | Add robust sentence splitting (no NLTK dep) | `backend/ingest/cleaner.py` | ✅ Done |

### P1 — Benchmarks & Evaluation
| # | Task | File | Status |
|---|------|------|--------|
| 20 | Run LightRAG vs Qdrant benchmark (20 queries) | `backend/benchmarks/lightrag_vs_qdrant_benchmark.py` | ⏳ Pending — needs live backend |
| 21 | Record results and decide if LightRAG justifies its latency cost | `lessons.md` / `GOAL.md` | ⏳ Pending |
| 22 | Add pytest config (`[tool.pytest.ini_options]`) in `pyproject.toml` for coverage, markers | `backend/pyproject.toml` | 🔲 Not started |

### P2 — Configuration Hardening
| # | Task | File | Notes |
|---|------|------|-------|
| 23 | Migrate remaining hardcoded thresholds to `Settings` | `backend/app/config.py` | Audit with `grep -R "0\.[0-9]\+" rag/` |
| 24 | Add unit tests for `clean_for_embedding` sentence splitter | `backend/tests/` | 🔲 Not started |
| 25 | Add unit tests for `FeedbackService` golden-dataset trigger | `backend/tests/` | 🔲 Not started |

---

## Definition of Done
- [ ] All `TODO` / `FIXME` / `HACK` / `XXX` comments in production code resolved or ticketed
- [ ] No backend Python file > 800 lines (except auto-generated or third-party)
- [ ] Benchmark report (`lightrag_vs_qdrant_report.json`) committed to repo
- [ ] `pyproject.toml` contains `[tool.pytest.ini_options]` with coverage and markers
- [ ] `lessons.md` updated with sprint outcomes

---

## Notes
- Do **not** add `nltk` or `spaCy` as dependencies; the lightweight sentence splitter in `cleaner.py` is sufficient.
- Do **not** start the benchmark until the backend is healthy (`make docker-rebuild-web` + health checks pass).
- File-size refactoring should be done one file at a time to avoid merge conflicts.
