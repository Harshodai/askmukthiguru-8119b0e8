# Advanced Research B/3: Context Engineering + Injection Defense + Structured Output

Date: 2026-09-13. Covers what the 5-lane pass did NOT cover. Repo today: delimiter fencing + authorization-first retrieval (partial) + lightweight regex guardrails; verification JSON string-parsed.

## 1. Context engineering (beyond compression)

### 1A. JIT retrieval + distractor-aware truncation [ROI #1 — do first]
Keep window as workbench, not warehouse: lightweight identifiers (chunk IDs, URLs) preloaded; payloads loaded at runtime via tools, then dropped. BABILong 25% retention, distractor-aware: Haiku +0.083, Sonnet +0.104; naive at same retention: Haiku −0.138, Sonnet −0.175, Opus −0.433. GraphWalks naive −0.35 to −0.43; signal-aware flat. Naive deletes answer in vast majority (fact survival <1% at 25%). Snipara: 500K→5K tokens (99% cut) holding quality. 5 relevant tools beats 40 preloaded.
Price: negative cost — fewer input tokens; stable prefix cached at 0.1× read. ~1–2 days.
Insertion: `chat_engine.py` + pipeline retrieval stage: two-phase — retriever returns `[{chunk_id, source_url, preview, score}]` (~300 toks), LLM emits `fetch_chunk(ids)` only for needed IDs. Add `search_tools(query)` meta-tool; ~6 always-on tools, rest discoverable.

### 1B. Tool-result clearing + recall-first compaction [ROI #2]
Clearing = surgical replace of old `tool_result` blocks (lossless, re-fetchable); compaction = summarize-and-restart (lossy). SelfCompact (2026): +18.1 pts math, 30–70% lower token cost vs fixed-interval. Governance Decay: progress-summarizers silently drop safety constraints stated 300 steps earlier — preserve guardrails verbatim. Claude API: `compact_20260112` trigger min 50K default 150K; `clear_tool_uses_20250919` default 100K keep last 3.
Price: 1 summarizer call per compaction; clearing free.
Insertion: `ContextManagerStage` after retrieval in `pipeline_builder.py`: clear tool outputs older than N turns; compact when input > ~40–50K. Compaction prompt carries: safety verbatim, language preference, citations-so-far, Second Brain pointers. Never compact `verification.method`/abstention state. Compaction state in session namespace only.

### 1C. Structured note-taking + sub-agent isolation [ROI #3]
Agent writes durable notes externally, window holds pointer; sub-agent spends fresh window on noisy subtask, returns 1–2K digest. ACB-2026 sim: context entropy −42%, completion +26pp, error recurrence 0.34→0.09, tokens 47.2K→31.8K. FIFO truncation regression rate 23%.
Price: sub-agents multiply calls; use only for noisy subtasks (LightRAG fan-out, multi-hop Neo4j).
Insertion: `recall(query)` JIT tool on `vault_index.py`/`memory_service.py` (not eager load); per-session scratchpad, cross-session via explicit recall only. Delegate LightRAG fan-out to sub-agent workers; lead synthesizes digests. Do not widen graph concurrency without cost gate.

### 1D. Effective-length budgets: RULER / NoLiMa / 40% rule [ROI #4 — free guardrail]
Claimed 128K–1M ≠ usable. RULER: only ~half models pass 4K-baseline at 32K (Llama3.1-8B 128K claimed → 32K effective; GPT-4 128K → 32–64K; Gemini-1.5-Pro 1M → >128K outlier). NoLiMa: at 32K, 11/13 models below 50% of short-context baseline (GPT-4o 99.3%→69.7%); effective length mostly 1–4K. Qwen2.5-7B cliff at 43.2% of max (−45.5%). Lost-in-middle U-shape persists. CoDaR: route by dependency — weak→RAG/chunk, strong→full-context.
Price: $0, saves money.
Insertion: `EFFECTIVE_CONTEXT_BUDGET_TOKENS` in config (32K or 40% of max) + per-query-class routing (factoid FAQ → chunked RAG; exegesis → full-section). Eval gate per class already required by Aug-22 invariants.

### 1E. Many-shot personalization [ROI #5 — targeted]
+5–15pp classification stability with 50–100 shots vs 5-shot; diminishing after ~100–200. NoLiMa caveat: keep shots short + diverse, rubric at END.
Insertion: freeze 20 canonical familiarity shots in cached system prefix; retrieve 5 user-specific shots JIT from `second_brain_vault`. Never stuff 3-year history eagerly.

## 2. Prompt-injection defense in depth (fencing alone insufficient)

### 2A. Instruction hierarchy + sandwich [ROI #1 in lane — $0]
OpenAI hierarchy System>Developer>User>Tool. Wallace 2024: extraction defense +63%, jailbreak robustness +30–34%, minimal regression. IH-Challenge: robustness 84.1%→94.1%, unsafe 6.6%→0.7% helpfulness held, red-team 63.8%→88.2%.
Insertion: explicit IH block in system prompt (Priority 0/10/20/30; attachments = Priority 30, already labelled untrusted); sandwich — repeat safety + citation instruction AFTER tool output, before generation. Extend assistant-config fingerprint with IH version so poisoned prompts never hit shared cache.

### 2B. Spotlighting: datamarking/encoding over delimiters [ROI #2 — cheap, big drop]
Hines 2024: delimiting < datamarking < encoding. GPT-family ASR >50% → <2% with spotlighting; encoding → ~0% on summarization/Q&A. Delimiting alone weakest.
Price: datamarking ~+10–15% tokens; encoding ~+33% (needs capable model to decode). Datamark default; encoding for upload-backed turns (10MB/file, 8K attachment_context).
Insertion: keep `<untrusted_source>` fences AND datamark Qdrant chunk text + attachment_context pre-generation. Per-session secret marker or encoding, not static string. Keep bounded-read + magic-byte sniffing.

### 2C. CaMeL-style isolation + least-privilege tools + outbound guard [ROI #3 — only provable defense]
Google CaMeL: control/data flow from TRUSTED query; untrusted data never alters flow. AgentDojo + Claude 3.5: 77% solved with provable security vs 84% undefended (−7pp). GPT-4o-mini + IH tool-calling still vulnerable to 276 attacks; + CaMeL: 0 vulnerabilities. Other defenses probabilistic only.
Price: highest eng cost in lane; runtime +1 policy check/call; −7pp utility.
Insertion: plan step derives allowed tool set from intent BEFORE retrieval (complete authorization-first); `check_tool_call` mid-loop backstop; `outbound_guard` second small model inspects send_email/push args pre-fire. Retrieved text never adds tools.

### 2D. Classifier + policy layer (honest FNR/FPR) [ROI #4]
CAPTURE (2025): ProtectAIv2 FNR 24–31%/FPR 27–49%; InjecGuard up to 100%/99%; PromptGuard FNR 0%/FPR 100% (blocks everything); Fmops 100%/0% (allows everything); GPT-4o detector FNR 7–16%/FPR 3–9%; CaptureGuard FNR 0–0.15%/FPR 0–2.05%. Over-defense kills Hindi/Telugu devotional phrasing — measure FPR on benign corpus turns.
Price: self-hosted ~$0 marginal; GPT-4o-as-detector ~$2–5/1M.
Insertion: keep lightweight regex L1; L2 small classifier ONLY on tool-output + upload paths; never log raw text in latency logs (Aug-22 privacy). Tune threshold for FPR <3% on own benign chats.

### 2E. Red-team harness measuring ASR correctly [ROI #5 — prerequisite to claims]
ASR-intermediate vs ASR-end-to-end, deterministic string-match (CANARY leak / forbidden tool), Wilson/bootstrap CIs, noise floor, utility signal. WASP: intermediate up to 86%, end-to-end 0–17% ("security by incompetence"). ARPIbench: strongest 3-turn completion 41%+ on EVERY model incl. GPT-5/Claude 4.5/Gemini 2.5; reflection doubles odds 8/12 models. IPI Arena (272K attempts): ASR 0.5%–8.5%; universal strategies transfer 21/41 behaviors. jkelly (2,028 trials): fencing+egress+allowlist +0.910 reduction; fencing alone +0.269 inside noise; live-model lesson: report compliance AND containment; empty result must fail.
Price: harness $0; live sweep ~2–3K calls (~$5–50/run).
Insertion: `test_prompt_injection_asr.py` — 30–40 curated attacks (direct, chunk-indirect, URL-hidden, multi-turn completion, reflected-repeat, memory-plant), deterministic judge + LLM-judge for ambiguous only, report ASR + Wilson 95% CI + utility rate. CI gate: fail if defended ASR >5% or utility <95%. Nightly (like `nightly-rls.yml`), not per-PR live. Never claim fencing works from mock-agent numbers — require live-model sweep.

## 3. Structured output reliability

### 3A. Constrained decoding (xgrammar default) [ROI #1 in lane]
XGrammar (MLSys'25): <40µs/token JSON Schema/CFG, up to 3× JSON / 100×+ CFG vs baselines, 80× end-to-end output rate; ~1% TPOT overhead. llguidance ~50µs/128K vocab single core. RAG guided-decoding study: Outlines best flexibility/enforcement balance; XGrammar fastest but needs manual rules; LMF strict, no beam/batch flexibility.
Price: $0 open-source; needs self-hosted vLLM/SGLang. API-only (OpenRouter/Sarvam/NIM) cannot logit-mask — use provider JSON-mode + server-side schema validator + 1 retry.
Insertion: Pydantic/JSON-Schema for `verification{method,passed,faithfulness_score,citations[]}` + eval judgments. Path A (self-hosted worker image): `guided_json` via vLLM+XGrammar. Path B (Railway API-only, current prod): prompt + `json.loads` + schema-validate + single repair retry; log `artifact_rate` (P0 L-INGEST-1/2/3). Constrained decoding eliminates the retry loop, NOT the `find_artifact` gate (CoT-leak/canned-string/ASR-loop vectors remain).

### 3B. Local judge models [ROI #2 — kills $/privacy cost]
Prometheus-2-8x7B: Pearson 0.63–0.69 vs GPT-4, pairwise 72–85% human agreement; 7B needs 16GB VRAM. SFR-Judge-70B: RewardBench 92.7% (first generative judge >90%), beats GPT-4o average; needs 1×A100/H100 or quantized 2×24GB. CompassJudger 7B (Qwen2.5): RewardBench ~88–90%, multilingual robust — 7B sweet spot. M-Prometheus 7B/14B beats Prometheus-2 multilingual. API judge cost today: ~$20–40/night for 2K evals. Local: $0 marginal after GPU.
Insertion: `run_ragas_eval.py --judge prometheus2-7b|sfr-12b|m-prometheus-7b`, default local, API opt-in. Store judge model+version per report. Calibrate once: 200 human/GPT-4 labels → Pearson >0.6 on HI/TE faithfulness (prefer M-Prometheus/SFR). Never use judge output as training signal without human spot-check; chunk evidence <4K per judgment (NoLiMa blindness).

## Lane ROI order

1. JIT/distractor-aware retrieval. 2. Clearing + recall-first compaction. 3. IH + sandwich ($0). 4. Datamark upgrade. 5. Constrained decoding. 6. Effective-length budgets. 7. ASR harness (required before claiming 3/4). 8. Local judge 7–12B. 9. CaMeL + outbound guard. 10. Notes + sub-agents (surgical). 11. Classifier layer (after FPR proven). 12. Many-shot familiarity (polish).

## Sources

- Anthropic context engineering: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents, https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools, https://platform.claude.com/docs/en/build-with-claude/compaction
- TrueFoundry JIT: https://www.truefoundry.com/blog/jit-context-just-in-time-context-agents
- SelfCompact: https://arxiv.org/abs/2606.23525
- Context rot: https://arxiv.org/html/2606.29718v2
- Distractor-aware truncation: https://export.arxiv.org/pdf/2608.03297, https://github.com/evolutionIdGmbH/memoreach
- Lost-in-middle: https://arxiv.org/abs/2307.03172, https://aclanthology.org/2026.findings-eacl.120.pdf, https://doi.org/10.18653/v1/2026.findings-acl.2097, https://arxiv.org/html/2601.15300, https://www.flowverify.co/blog/context-rot-production-llm-engineering
- RULER: https://arxiv.org/abs/2404.06654, https://github.com/nvidia/ruler
- NoLiMa: https://arxiv.org/abs/2502.05167, https://github.com/Adobe-Research/NoLiMa
- Instruction hierarchy: https://openai.com/index/the-instruction-hierarchy/, https://arxiv.org/pdf/2404.13208, https://openai.com/index/instruction-hierarchy-challenge/
- Spotlighting: https://arxiv.org/pdf/2403.14720
- CaMeL: https://arxiv.org/pdf/2503.18813, https://github.com/google-research/camel-prompt-injection
- CAPTURE: https://arxiv.org/html/2505.12368v1
- WASP: https://arxiv.org/html/2504.18575v3, https://github.com/ethz-spylab/agentdojo, https://alexcbecker.net/arpibench_paper.pdf, https://github.com/grayswansecurity/ipi_arena_os
- tripwire-eval: https://pypi.org/project/tripwire-eval/, https://github.com/jkelly-dev1/prompt-injection-benchmark
- XGrammar: https://arxiv.org/abs/2411.15100, https://github.com/Irfnfnkemed/xgrammar, https://dreaming.press/posts/outlines-vs-xgrammar-vs-llguidance.html, https://arxiv.org/html/2509.06631, https://github.com/noamgat/lm-format-enforcer
- Prometheus 2: https://arxiv.org/abs/2405.01535, https://github.com/prometheus-eval/prometheus-eval
- SFR-Judge: https://arxiv.org/pdf/2409.14664, https://github.com/SalesforceAIResearch/sfrjudge
