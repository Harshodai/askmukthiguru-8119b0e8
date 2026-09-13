# Deep Research 5/5: Config/Boolean Cleanup Inventory

Date: 2026-09-13. Lane 5/5 (+ follow-up for truncated tail). Scope: `backend/app/config.py` (1716 lines, ~100 booleans). Read-only; no writes. Pydantic `extra="ignore"` → deleting a field is safe for env files (stale env silently ignored, never crash).

## A. Flag table (verified by rg over `backend/`)

### A1. DEAD — zero runtime reads → GROUP 1 (each independently shippable; run `test_wiring_invariants.py` after each)

1. `semantic_router_enabled=True` (:181; config itself says "Unwired") + `semantic_router_top_k=3` (:182) + `semantic_router_fallback_llm=False` (:190) + dead `semantic_router_llm_fallback` string — NONE read. NOTE: live `use_semantic_router` family (:1211–1217, `confidence_threshold`, `shadow_mode`) KEEP — do not confuse; lines interleave, edit carefully. (~14 lines)
2. `use_qdrant_semantic_cache=True` (:963). (~3)
3. `data_audit_strict_mode=False` (:503; `quality_gate.py:693` reads only `data_audit_enabled`). (~3)
4. `semantic_cache_qdrant_collection` + `semantic_cache_hnsw_ef` (:933–934). (~5)
5. STT quintet `sarvam_stt_model/mode/language` (:492–494) + `stt_chunk_minutes/stt_max_audio_mb` (:495–496). Pre-verify `rg` (expect config+allowlist only). (~9)
6. `transcript_max_retries=3` (:473). (~3)
7. `ingestion_relation_cache_size=256` (:875). Pre-verify LRU site uses literal. (~3)
8. `llm_provider_chain` (:1161–1163 + comment :1153–1160; selection reads only `LLM_PROVIDER`). (~12)
9. `persona_max_paragraphs/sentence_words` (:1178–1180). (~8)
10. `sarvam_model_name` (:219; gateway reads `sarvam_cloud_model`). (~3)
11. `correlation_id_max_length=64` (:559). (~3)
12. `SERVICE_ORCID_MAP` (:268–273). (~8)
13. `csrf_secret` (:552–554): FIRST `rg csrf_secret backend`; delete only if zero non-config reads (config comment claims a `security_utils` getattr-read — unverified).
14. Dead env lines: `USE_OPENROUTER_FOR_SIMPLE` (compose:177 + `.env.example:31`, no code read) → delete both lines; `RATE_LIMIT_PER_MINUTE` (`.env.example:106` only; code uses `chat_rate_limit`) → delete line.
15. Undeclared-getattr literals → inline: `qdrant_timeout` (`services/qdrant/client.py:86`, always default) → literal `30.0`; `llm_generate_timeout` (`ingest/pipeline.py:251`) → literal `60.0`; `redis_password` (`ops/flush_cache.py:121`) → drop getattr arm, keep `os.getenv`.
16. G1 total ≈ 95–115 lines. Also delete the corresponding `KNOWN_EXTRA_DEAD`/`ALLOWED_DEAD` entries in `test_wiring_invariants.py` per item.

### A2. UNDECLARED-BUT-READ / ENV-DIRECT → declare-or-delete

- `SARVAM_RPM_LIMIT` (compose:169, `.env.example:19`): read only via `os.getenv` in `benchmarks/ruthless_benchmark.py:2033`, never app runtime → KEEP-doc (benchmark pacing), none.
- `SUPABASE_SERVICE_ROLE_KEY` (env/scripts; `seed_admin.py`, `verify_rls_policies.py`, `eu_ai_act_backfill.py:232`): DECISION D1 — KEEP raw reads, do NOT declare (telemetry bypass key must never land in dumpable Settings; test-pinned). Document as intentional exception.
- `web_ingest_request_timeout`: UNDECLARED-GETATTR-WITH-DEFAULT (`ingestion/web_ingest_pipeline.py:170`, default 30; absorbed in guards baseline debt) → declare `float = 30` or tombstone; do not rely on silent default.
- `OLLAMA_FAST_MODEL` (compose:223 only, zero code hits) → DELETE compose line or wire to Settings + reader.
- `SARVAM_DEBUG` (compose:279 only, zero code hits) → DELETE compose line unless debug reader (re)introduced.
- `OPENAI_API_KEY` (`.env.example:128` only, zero code hits) → KEEP as placeholder only if OpenAI-compatible path planned, else DELETE line. Never add unread Settings field.
- `CELERY_BROKER_VISIBILITY_TIMEOUT` / `CELERY_TASK_ALWAYS_EAGER` / `WEB_CONCURRENCY` / `OTEL_*` / `WEBSHARE_PROXY_URL` / `YOUTUBE_COOKIES_B64` / `SUPADATA_API_KEY` / `GOOGLE_*` / `FACEBOOK_*`: env-direct or infra-only by design → KEEP-doc, none.

### A3. DEAD-BUT-TEST-PINNED → GROUP 2 (deletion breaks suite; exact edits mapped)

- G2-1 `doctrine_cache_enabled` (default False): decl `config.py:141–143` DELETE 3 lines; `doctrine_cache_stage.py:41–42` DELETE gate (stage always runs; lookup refuses uncited per docstring) — OR delete whole file + builder registration if intent is kill-stage; `test_release_provenance.py:305–311` remove patch wrapper, dedent. KEEP-or-TOMBSTONE (live gate, not dead code).
- G2-2 `rag_parallel_verify` (zero runtime reads): decl `config.py:1280–1284` DELETE block; `test_quality_gate.py:412` DELETE monkeypatch line; `test_nodes.py:305–308` rewrite docstring; `test_wiring_invariants.py:94` DELETE allowlist line.
- G2-3 `verifier_pass_ratio` (zero runtime reads): decl `config.py:1235` DELETE; `test_thresholds.py:11` DELETE assert; `:33` + `:47` DELETE env-override lines; `test_wiring_invariants.py:93` DELETE allowlist line.

### A4. GENUINELY TOGGLED → KEEP (both states exercised)

`feature_memory_write` · `waitlist_enabled` · `rag_deep_research_enabled` · `use_dspy` · `hybrid_search_enabled` · `rag_use_hyde` + `rag_indic_use_hyde` · `rag_context_compression_enabled` · `rag_regenerate_before_rewrite` (comment forbids flip without A/B) · `rag_rewrite_query_fast_model` · `ollama_cloud_only` · `guardrails_llm_enabled` · `latency_benchmark_cache_disabled` · `enable_test_auth`/`is_production` (security) · `anon_quota_enabled` · `feature_memory_enabled` · `contradiction_resolution_enabled` · `graphrag_fusion_enabled` (False-only pin — keep as experiment lever) · `multilingual_guardrails` (True-only pin — keep as rollback lever).

### A5. LIVE SINGLE-STATE / OPS LEVERS → KEEP; G3 product decisions below

Keep: `sarvam_budget_guard_enabled` (dynamic from_settings — static scan misses it) · `serene_mind_enabled` · `feature_regex_prerouter` · openrouter privacy trio · budget guards + `fail_closed` pair · `reingest_late_chunking` (index-contract critical) · gemini translation pair · `use_boundary_chunker` · `guru_brain_tone_exemplars_enabled` · asr pair · `llm_speaker_role_fallback_enabled` · `enable_transcript_council` · `data_audit_enabled` · queue pair · `disable_public_registration` · `anon_quota_*` · capability flags (sso/push/profile/proactive) · KG pair · bm25 · retrieval/rerank/raptor/markitdown/okf/graph/lightrag/auto-extract flags · canonical-memory family (+`memory_shadow=False` A/B) · rerank family · ontology-write pair · `require_licensed_domain_reads` · corpus-release trio · cache pair · `phi_accrual_enabled` · correlation ids · meditation pair · `strip_canned_footer` · `langhanam_voice_enabled` · live semantic-router family · `lettucedetect_enabled` · `reranker_enabled_for_complex` · `deep_gate_skip_on_verified` · `important_kwd_boost_enabled` · `rag_cove_disabled` (+tiers) · `enable_colbert` · `whisperx_enabled` · `enable_scheduled_youtube_sync` · `use_hyper_extract_enrichment` · `llm_gateway_cross_provider_fallback` (audit OFF) · fresh latency opt-ins · `anthropic_extended_thinking_enabled` · `apns_use_sandbox` · `db_pool_pre_ping` · `neo4j_keep_alive`.

False-default keep (opt-in levers): `sarvam_complex_routing_enabled` (D2: KEEP — live reads + tiered-router tests; delete breaks suite) · web-search family (D7: KEEP — live reads, correctly default False) · `ab_testing_enabled` (D8: KEEP 2 lines as provider-experiment lever; tombstone only if Krutrim permanently abandoned) · `agentic_graph_traversal_enabled` + family (D9: KEEP — live reads, default False preserves hot paths) · `rag_citation_cosine_enabled` · `kg_export_enabled` (501-guard) · `use_request_queue` · `show_swagger`/`enable_test_auth`.

### A6. FINDINGS (fix, not removal)

- F1 `openrouter_fast_model` is NOT dead: `model_policy.py:95` reads it (verified live). Wiring-allowlist entry stale — update comment, keep field.
- F2 Reader-default disagreements (harmless while declared, confusing): `retrieval.py:1743` okf→False (decl True); `:1790/:1844` graph/lightrag→True (match); reranking/retrieval delta/dedup + `raptor_parent_summaries_enabled` + `rag_okf_auto_extract_enabled` + `guru_brain_tone_exemplars_enabled` →False (decl True); `rag_rewrite_query_fast_model`→False in all 3 services (decl True). Fix: align getattr defaults to declared values (10 one-liners, zero behavior change).
- F3 `memory_write=True` contradicts its own comment ("deliberately still off", :819). D4: FIX COMMENT, keep True (consent-gated fail-closed at `memory_stage.py:92–94,110–117`).
- F4 `rag_use_context_compression` decl `bool=False` but `test_tiered_routing_streaming.py:332` assigns `"auto"` and `generation.py:1523` reads `"auto"` — undeclared third state. D5: pick bool (delete auto-branch :1525–1527) or `str="auto"` with validator.
- F5 Compression duplication: `rag_use_context_compression` (generation) vs `rag_context_compression_enabled` (retrieval/multi-provider). D3: KEEP canonical (`retrieval.py:1953`, `multi_provider_llm.py:223`, tests); DELETE generation path (auto-branch unreachable while decl False); wire-or-fold `rag_compression_similarity_threshold:760` (live at `retrieval.py:1013`).
- F6 Compose-vs-default drift = local-dev overrides working as designed (RAG_USE_HYDE, RAG_MAX_REWRITES, LLM_TIMEOUT, PIPELINE_TIMEOUT, TRANSCRIPT_CONCURRENT_WORKERS, EMBEDDING_BACKEND onnx_int8 evidence-gated — do NOT "clean" by aligning; RERANKER_MODEL ms-marco≠mMiniLM/bge).
- F7 `context_budget_enabled`/`use_contextual_chunking` already absent — prior cleanup landed. No action.
- F8 Follow-ups needed (no removal proposed without grep): `smtp_*` (6 fields, presumed live), `teacher_personalities`, `frontend_url`, `emergent_llm_key`, `health_check_max_process_rss_mb`, `compliance_*`, `chat_*_rate_limit` family, `use_proposition_chunking="auto"` (`index_fingerprint.py:145`), `quality_*`, `benchmark_*`.

## B. Grouped removal plan

GROUP 1 (~95–115 lines, each independently shippable): items A1-1–13 + A1-14/15 + allowlist deletions in `test_wiring_invariants.py` per item. GROUP 2: G2-1/2/3 exact edits above. GROUP 3 decisions: D1 keep-raw + document; D2 keep; D3 canonical-keep + delete path; D4 comment fix; D5 decide-then-collapse; D6/D7/D8/D9 keep (documented above).

## Sources (flag hygiene)

- Tombstoning dead flags: https://martinfowler.com/articles/feature-toggles.html
- Debt ratchets: https://github.com/YucelOzcan/pytest-ratchet
- Identity-based allowlist ratchet: https://github.com/open-gsd/gsd-core/blob/next/scripts/lib/allowlist-ratchet.cjs
- Grandfathered-baseline gates: https://github.com/testland/qa/blob/main/plugins/qa-accessibility/skills/a11y-violation-gate/SKILL.md
- In-repo precedent: `backend/tests/test_settings_guards.py:20–37` (frozen baselines + 4 absorbed debt items)
