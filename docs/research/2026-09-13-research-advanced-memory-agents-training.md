# Advanced Research A/3: Memory Systems + Agentic/Test-Time + Training Flywheel

Date: 2026-09-13. Covers what the 5-lane pass did NOT cover. Repo reality: Second Brain vault = Qdrant `second_brain_vault` (user_id filter) + Postgres `user_brain_nodes` (encrypted); corpus RAG = Qdrant `spiritual_wisdom*` + Neo4j + LightRAG; faithfulness/verification gate exists; ONNX CPU budget exists.

Ordered by ROI (cheapest faithfulness/dollars first).

## 1. Thumbs up/down → DPO-pair flywheel (consent-gated) — HIGHEST ROI

Log (query, retrieved ctx ids, answer, faithfulness passed/failed, thumbs) → mine chosen/rejected pairs → offline DPO (no reward model, no PPO). DPO (Rafailov et al.): TL;DR win-rate ~61% vs human refs (vs PPO 57%); human judges prefer DPO 58% over PPO; only method beating chosen refs on Anthropic-HH; robust to temperature, beta barely tuned.
Price: training offline only; inference +0; storage 1 Postgres table; needs ~5–10k pairs before first run.
Insertion: `feedback {session, turn, up/down, reason}` table; export job `scripts/eval/build_dpo_pairs.py` (rejected = failed-faithfulness or down-voted, chosen = edited/up-voted or high-faithfulness grounded, same context). Explicit consent + per-user exclusion; never train on Second Brain plaintext, only opted-in doctrine turns. First action without training: use pairs as eval set for RAFT/verifier tuning.

## 2. RAFT (retrieval-aware FT) for doctrine RAG

SFT with (Q + oracle + 4 distractors, CoT answer with verbatim quote); teaches ignore-distractor + cite-then-answer. Berkeley Zhang et al.: LLaMA2-7B PubMed 73.3 vs DSF+RAG 71.6; Hotpot 35.28 vs DSF+RAG 4.41 (+30.87pp); HF API 74.0 vs 42.59 (+31.4pp); CoT ablation +9.66pp Hotpot, +14.93pp HF. Train with D*+3–4D optimal; oracle-only training hurts.
Price: one-time LoRA FT on 7–8B (single A100 in paper); inference same or smaller model, no extra latency (shorter quote-grounded answers). Risk: domain overfit — keep P~80% with-oracle / 20% no-oracle so abstention survives.
Insertion: `raft_spiritual.jsonl` from existing Qdrant chunks (Q from logs + synthetic, oracle = gold chunk, distractors = BM25 non-gold, A* = CoT + verbatim quote + final). LoRA adapter for generation only (retriever untouched). Gate: NDCG + faithfulness + abstention rate before replacing prompt-only generator.

## 3. Reasoning-model-as-verifier / selective test-time scaling

Keep single-pass fast path; escalate only low-confidence/abstain/comparative turns to N=3–5 samples + verifier pick (faithfulness scorer = reward). Self-consistency: GSM8K ~+10–18pp; R1-Zero AIME 15.6%→71% RL alone, 86.7% cons@16; CoT itself +9–15pp. Best-of-N scales log-linearly, plateaus ~N=32–128.
Price: N× generation on ~5–10% traffic only (~+15–25% blended bill, +2–4s tail on those turns). Bounded by existing timeouts.
Insertion: `if faithfulness<0.4 or verification=null or comparative-intent: sample N=3 @T0.7, re-run existing faithfulness gate as scorer, keep max`. No new infra. Never on greetings/FAQ fast path. Multi-agent debate strictly worse ROI — single-model self-consistency first.

## 4. Mem0-style extraction on top of existing vault (DO NOT replace vault)

Per-turn LLM extractor → salient facts (user_id-scoped) → Qdrant vault + Postgres encrypted row. Mem0 paper: LoCoMo J 67% vs best RAG ~61% (+10% rel), Mem0g 68.44% (+12% rel); p95 1.44s vs full-context 17s (−91%); search p50 0.148s; >90% token saving; 2026 managed: LoCoMo 91.6–92.5, LongMemEval 93.4–94.4. Letta counterpoint: plain filesystem + gpt-4o-mini hits 74.0% LoCoMo vs Mem0-graph 68.5% — retrieval discipline > exotic store.
Price: +1 extractor call per memory-worthy turn (small model, ~200–400 tok) + 1 write; read top-k ~150ms. Gate on explicit preference/practice statements, not every turn.
Insertion: keep `vault_index.py` + `user_brain_nodes`. Add `services/second_brain/extract.py: extract_facts(turn)→[{fact, salience, ttl}]` async via celery `memory` queue. Existing user_id-filtered dense search + recency boost; no schema change. Plaintext stays Postgres, vectors only Qdrant — complies as-is.

## 5. Graphiti/Zep temporal edges as second index (sadhana timelines)

Episodes → entities/facts with t_valid/t_invalid + BM25+vector+graph RRF hybrid. Zep paper: DMR 94.8% vs MemGPT 93.4%; LongMemEval-S 71.2% vs 60.2% full-context (+18.5%); latency 2.58s vs 28.9s (−90%), ~1.6k vs 115k tokens. Biggest wins: single-session-preference +184%, temporal +38–48%, multi-session +17–31%.
Price: write-heavy extraction per episode; read cheap (~0.68s). Needs Neo4j (have it) + per-user subgraph with tenant_id isolation.
Insertion: do NOT migrate vault. `tenant_id`-scoped Graphiti overlay in existing Neo4j for users with >N sessions; vault dense search otherwise. Temporal/preference queries only (router flag). Fact invalidation must hard-delete on `forget` (GDPR path exists).

## 6. A-MEM link-generation + memory-evolution (cheap Zettelkasten upgrade)

On write: note {context, keywords, tags} → link top-k past notes → evolve touched notes. NeurIPS'25: GPT-4o-mini LoCoMo multi-hop F1 27.02 vs ReadAgent 9.15 (~3×), temporal 45.85; ~1.2k tok/op (−85–93%), <$0.0003/op. Ablation: removing evolution drops multi-hop 27→21, both →9.6.
Price: 2–3 small LLM calls on write (async, off hot path). Read unchanged.
Insertion: worker-side `link_notes()` + `evolve_notes()` in celery `memory` queue. Best for multi-hop seeker questions ("how does my breath practice connect to stillness?"). Gate on dense histories.

## 7. Distill big reranker → small ONNX CPU

Teacher (BGE-m3/RankZephyr/GPT-rank) → Rank-DistiLLM hard-negative + pairwise loss → MiniLM/ELECTRA student → ONNX QInt8. Rank-DistiLLM: student matches RankGPT-4/RankZephyr on TREC-DL; monoELECTRA-base beats monoT5-3B with ~96% fewer params; 25s→300ms/query. Community BGE-m3→MiniLM-L6: NQ 0.580 vs 0.523, Hotpot 0.775 vs 0.724. Temsa QInt8: −74.5% size, +34–40% throughput, quality-neutral.
Price: offline distillation (1×A100). Serving ~15ms/15 cands CPU, ~200–250ms p95 @20 docs. Zero infra change.
Insertion: distill on spiritual pairs (query + gold vs hard negatives from current retriever), export pinned QInt8, validate with `validate_onnx_reranker.py` (Spearman>0.90). Highest infra-ROI after DPO/RAFT. Repo already pins ONNX SHAs + `RERANKER_BACKEND`.

## 8. ReAct/tool-use agent (SELECTIVE, not default)

Interleaved Thought/Act/Obs with Qdrant + Neo4j + vault tools. ALFWorld 71% vs Act-only 45% (+34pp); WebShop 40% vs 30%; Hotpot ReAct→CoT-SC 35.1 best; FEVER 60.9 vs 56.3.
Price: 3–8 LLM steps/query = 3–8× cost + seconds. Kills 4s FAQ SLO if default.
Insertion: keep 12-stage pipeline default. Agent lane only for multi-hop/comparative/deep-sadhana intents with step cap 4 + 12s timeout + faithfulness gate as halt. Reuse existing tools; no new framework (LangGraph/CrewAI unnecessary).

## 9. HippoRAG-2 PPR associative layer (corpus side, later)

OpenIE triples + passage nodes + query-to-triple PPR + LLM filter. Avg F1 59.8 vs NV-Embed-v2 57.0; associative +7pts (MuSiQue 48.6, 2Wiki 71.0 +9.5pp, Hotpot 75.5); factual held (NQ 63.3 vs 61.9).
Price: offline KG build over 89k points (heavy LLM extraction) + online triple linking + PPR. LightRAG already occupies this niche.
Insertion: pilot on English doctrine subset; compare vs hybrid + ONNX rerank on held-out NDCG/faithfulness before full build. No Neo4j schema change without maintenance-job procedure.

## 10. DAPT / RAG-end2end / RLVR-GRPO (LOWEST ROI now)

R1: AIME 15.6→79.8 (86.7 cons@16), MATH-500 97.3; −50% RL memory vs PPO. But: DAPT/end2end = GPU-weeks + rights review (Four Sacred Secrets scrub precedent); RLVR needs verifiable tasks — poor match for devotional tone, reward-hack risk on soft judgments.
Insertion: park until RAFT+DPO saturate. If ever: DAPT on public-domain texts only with CONTENT-RIGHTS sign-off; RLVR only for citation-format/tool-call verifiers, never doctrine content.

NOT doing: vendor memory cloud (privacy); global Redis flush; full-context stuffing (17–29s p95); default ReAct; training on Second Brain plaintext without consent.

## Sources

- Mem0: https://arxiv.org/abs/2504.19413, https://github.com/mem0ai/mem0
- Zep/Graphiti: https://arxiv.org/abs/2501.13956, https://github.com/getzep/graphiti
- Letta: https://www.letta.com/blog/benchmarking-ai-agent-memory/
- A-MEM: https://arxiv.org/abs/2502.12110, https://github.com/WujiangXu/AgenticMemory
- HippoRAG-2: https://arxiv.org/abs/2502.14802, https://github.com/OSU-NLP-Group/HippoRAG
- LoCoMo: https://arxiv.org/abs/2402.17753, https://github.com/snap-research/locomo
- ReAct: https://arxiv.org/abs/2210.03629, https://react-lm.github.io/
- RAFT: https://arxiv.org/abs/2403.10131, https://sky.cs.berkeley.edu/project/raft/
- DPO: https://proceedings.neurips.cc/paper_files/paper/2023/file/a85b405ed65c6477a4fe8302b5e06ce7-Paper-Conference.pdf
- R1/GRPO: https://arxiv.org/abs/2501.12948
- Rank-DistiLLM: https://ar5iv.labs.arxiv.org/html/2405.07920
