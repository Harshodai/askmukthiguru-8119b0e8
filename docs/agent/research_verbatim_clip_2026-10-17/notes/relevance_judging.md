# Low-latency relevance judging for verbatim clip serving: LLM-as-judge vs cross-encoder rerankers, and parallel gates

Method note for the report writer: direct page fetches (arxiv.org, huggingface.co, aclanthology.org, dev.to) failed with DNS errors in this environment, so primary papers could NOT be opened. Every finding below comes from web-search result summaries that name the primary paper. Numbers are only given where a search summary stated them; anything stated by a secondary source is flagged. Treat all figures as "UNVERIFIED against the original PDF" unless noted otherwise. No numbers were invented.

## 1. Published comparisons: LLM relevance judgments vs human labels and vs cross-encoder rerankers (agreement, latency)

### Takeaway
LLM judges (GPT-4 class) are reported as roughly as accurate as human labelers for relevance labelling and give high system-ranking correlation (Kendall tau about 0.86-0.94), but they are lenient relative to humans and sensitive to prompt wording. Listwise LLM reranking (RankGPT) can match or beat supervised cross-encoders on benchmarks, but cross-encoders are far cheaper per pair. No source found directly compares a BGE cross-encoder against an LLM pointwise judge on binary "should we show this clip" precision.

### Cited Findings
- Thomas, Spielman, Craswell, Mitra (Microsoft/Bing, arXiv 2309.10621, SIGIR 2024): LLMs "are about as accurate as human labellers and as useful for identifying the best systems and hardest queries"; prompt changes (even simple paraphrases) affect accuracy, which the authors use to argue for high-quality gold labels. — [Microsoft Research page](https://www.microsoft.com/en-us/research/publication/large-language-models-can-accurately-predict-searcher-preferences/) (via search summary; paper body not opened)
- Bing uses GPT-4 "with human oversight" for relevance labelling at web scale (NTCIR-17 keynote by Paul Thomas). — [NTCIR-17 keynote PDF](https://research.nii.ac.jp/ntcir/workshop/OnlineProceedings17/pdf/ntcir/01-NTCIR17-KEYNOTE-ThomasP.pdf) (search summary only)
- UMBRELA (open reproduction of Bing's assessor, arXiv 2406.06519) follows Thomas et al.'s settings; reported run-level Kendall tau between LLM-based and human-based system rankings of 0.87-0.94 on TREC DL 2019-2023 and about 0.86-0.89 on TREC 2024 RAG (301 topics). Both figures are relayed by secondary sources (a Waterloo thesis and a survey), NOT confirmed against the originals. — [UMBRELA](https://arxiv.org/pdf/2406.06519); [Waterloo thesis](https://uwspace.uwaterloo.ca/items/4d18073e-d9b6-45e5-91b3-e530dd88dd5f); [survey, arXiv 2504.12558](https://arxiv.org/html/2504.12558v1)
- Humans were stricter than the LLM on TREC DL 2019-2021: humans labelled 13% more documents non-relevant (17,376 vs 14,961 by the summary's counts), LLM labelled 26% more as perfectly relevant (3,063 vs 2,429). Leniency is the relevant risk for a precision-first serve gate. — [survey, arXiv 2504.12558](https://arxiv.org/html/2504.12558v1) (secondary relay of UMBRELA authors' result)
- Survey proposes tau >= 0.9 as a minimum bar for accepting LLM labels in place of human ones; UMBRELA sits near that line. System-level tau is a different quantity from per-item agreement. — [survey, arXiv 2504.12558](https://arxiv.org/html/2504.12558v1)
- Binary kappa for human-vs-LLM agreement is reported to range "slight to moderate" (0.07-0.49 in one review; kappa 0.26 in another paper); a different task showed GPT-4 vs human 0.79. These come from different tasks, not from relevance-at-serve. — [Perspectives on LLMs for Relevance Judgment, arXiv 2304.09161](https://arxiv.org/pdf/2304.09161) and others as returned by search; ranges are UNVERIFIED as to which paper reports which.
- Critique: Clarke and Dietz argue LLM assessment "still can't replace human relevance assessment", citing circularity when systems use the same LLM as a reranker and gaming of automatic metrics. This is directly relevant: our relevance scorer is also the serve gate, so it is both system and judge. — [arXiv 2412.17156](https://arxiv.org/html/2412.17156v2)
- RankGPT (Sun et al., EMNLP 2023, arXiv 2304.09542): properly instructed LLMs give results competitive with or better than state-of-the-art supervised methods on TREC, BEIR, Mr.TyDi; a 440M model distilled from ChatGPT permutations outperforms a 3B supervised model on BEIR; NovelEval was built to control contamination. — [ACL Anthology 2023.emnlp-main.923](https://aclanthology.org/2023.emnlp-main.923) (via search summary)
- A DeAR paper table lists RankGPT-4 (reranking the top 30 from RankGPT-3.5) at nDCG@10 75.59 on DL19 and 70.56 on DL20, and monoT5-3B at 68.89 on DL20 (DL19 cell not visible). Setups differ, so this is not a clean head-to-head. — [DeAR, arXiv 2508.16998](https://arxiv.org/pdf/2508.16998)
- Cost/latency of cross-encoders: a reproduction reports monoT5-3B at 0.73 s/query for 50 documents and 14.63 s/query for 1,000 documents on an A100. — as relayed in search results for [arXiv 2508.16757](https://arxiv.org/pdf/2508.16757) (attribution of the figure to that specific paper is UNVERIFIED)
- Rank-DistiLLM (arXiv 2405.07920) title states the aim of closing the effectiveness gap between cross-encoders and LLMs via distillation; its numbers were not retrieved. — [Rank-DistiLLM](https://arxiv.org/pdf/2405.07920)

### Inferences
- For per-item "show / don't show" precision, the published evidence is mostly system-ranking correlation, which can look excellent while individual-label error is much higher. Do not read tau 0.9 as 90% per-clip precision.
- The documented LLM leniency (more "perfect" labels than humans) supports the project's choice of a strict score-3-only rule plus an independent judge, and argues against letting the same model be both selector and sole auditor.
- Circularity (Clarke/Dietz) applies: the project already uses an independent Opus judge, which is the right mitigation; keep the evaluation judge a different model family from the serving judge.

### Gaps
- No primary source opened for exact Thomas et al. kappa/accuracy figures (paper body not reachable).
- No head-to-head of BGE-reranker-v2-m3 (or similar cross-encoder) vs an LLM pointwise judge on binary relevance with per-item agreement against humans; not found.
- No data on spiritual/teaching-clip or conversational-question relevance; all benchmarks are web/MS MARCO/BEIR-style.

## 2. Can cross-encoder scores support an abstain threshold (calibration)?

### Takeaway
Raw reranker scores are rank-correct logits, not portable probabilities; sigmoid normalisation does not change that. A usable abstain threshold is possible but must be fitted on labelled in-domain data (including out-of-corpus and near-miss queries) and refit when the checkpoint changes. A reranker-specific abstention paper exists but its results were not retrieved.

### Cited Findings
- BAAI model card: raw score can be mapped to [0,1] with a sigmoid (`normalize=True` in FlagEmbedding); example maps about -5.65 to about 0.0035. Sigmoid is monotonic, so it changes scale, not ranking. — [BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3) (via search summary)
- Cohere guidance: scores are in [0,1], should not be read as ratios, and depend on the query and the passages sent; it recommends an empirical process for choosing a threshold. — [Cohere reranking best practices](https://docs.cohere.com/docs/reranking-best-practices) (via search summary; exact wording not retrieved)
- ZeroEntropy glossary: most rerankers produce rank-correct scores but arbitrary absolute values, so thresholds break across queries. Vendor view; one page also contradicted itself on whether pointwise scores are calibrated. — [ZeroEntropy score calibration](https://www.zeroentropy.dev/concepts/score-calibration/)
- Practitioner post (low authority, hypothesis only): top score is often a per-query logit because listwise softmax training is invariant to a constant offset; a 0.5 cutoff broke after a checkpoint change. — [dev.to post](https://dev.to/ji_ai/cross-encoder-reranker-score-calibration-why-05-cutoffs-fail-1k9b)
- Gisserot-Boukhlef et al., "Towards Trustworthy Reranking: A Simple yet Effective Abstention Mechanism" (TMLR 2024, arXiv 2402.12997): lightweight abstention at the reranking stage for black-box rerankers; reference-based method outperforms reference-free heuristics at no added cost; code/artifacts MIT-licensed. A third-party summary says linear regression is involved (UNVERIFIED). Results not retrieved. — [arXiv 2402.12997](https://arxiv.org/pdf/2402.12997)
- Risk-controlled thresholding literature: Learn-then-Test and conformal risk control are applied to ranked retrieval in "Two-stage Risk Control with Application to Ranked Retrieval" (IJCAI 2025). I found no source pairing Clopper-Pearson + fixed-sequence testing specifically for RAG abstention (the project's calibrator does this; the generic LTT framework is Angelopoulos et al. 2021, not opened). — [IJCAI 2025](https://www.ijcai.org/proceedings/2025/1012)
- A 2026 selective-prediction study (text-to-SQL, not retrieval) selects the threshold on one half of the data and reports coverage/risk on the held-out half, and finds some confidence signals cannot reach low-risk subsets at any threshold. — [arXiv 2607.06799](https://arxiv.org/pdf/2607.06799)

### Inferences
- A cross-encoder score can serve as a selective-prediction signal; whether it is good enough is an empirical question answered by a risk-coverage curve on labelled (question, clip) pairs, not by a literature claim. The project's existing fixed-sequence LTT calibrator can be reused unchanged with the reranker score as the feature, once enough human labels exist (the project notes 299 confident items with 0 errors are needed at 1% risk, delta 0.05).
- Cross-encoder scores are query-relative; use clip score margin vs the next candidate and an anchor set of known out-of-corpus queries as extra features, as a hypothesis to test.
- Cross-encoders cannot judge "is this clip a complete standalone answer" unless fine-tuned for it; they score topical relevance. The LLM scorer's 0-3 rubric encodes more than topical match.

### Gaps
- No published calibration curve for BGE-reranker-v2-m3 on any task found.
- Original TMLR paper numbers not retrieved.

## 3. Latency of BGE reranker v2 and LLM judges

### Takeaway
A multilingual cross-encoder over 3 pairs is on the order of tens to hundreds of milliseconds, versus seconds for an LLM API call. Figures are informal.

### Cited Findings
- Informal blog test: bge-reranker-v2-m3 via FlagEmbedding, 3 documents, about 0.35 s on CPU and about 0.08 s on a T4 GPU (single run, batch size/length/warmup not described). — [Medium "speed showdown reranker"](https://medium.com/@xiweizhou/speed-showdown-reranker-1f7987400077) (via search summary)
- A GPU hosting vendor claims about 80-120 ms for 100 candidates on an RTX 4060 Ti. Vendor claim, UNVERIFIED. — [gigagpu](https://gigagpu.com/?p=33008)
- Model is about 568M parameters (per a secondary page). A "7B, 35 ms per pair" figure on a leaderboard page looks mislabelled and should be ignored. — [presenc.ai](https://presenc.ai/research/best-open-weight-reranker-models-2026)
- Jina Reranker v2 multilingual (278M) on an RTX 4090: 748 pairs/s GPU vs 25 pairs/s CPU (about 1.3 ms vs 40 ms per pair); a different model, scale reference only. — [Medium/other result as returned by search](https://medium.com/@xiweizhou/speed-showdown-reranker-1f7987400077) (attribution UNVERIFIED)
- Project context (from the brief): uncached first-person latency is about 4-6 s, driven by the answerability gate (6 s budget) plus the relevance scorer (12 s budget, max_tokens 1024 because the scorer model reasons internally).

### Inferences
- The scorer's multi-second cost is mostly output reasoning tokens. Constraining or disabling reasoning for a pointwise 0-3 task, or replacing it with a cross-encoder first-pass filter, are the two main levers. Neither has been measured here.
- On a CPU-only host, 3 pairs of about 350 ms is plausible but unproven for this clip length; clip text (18-25 s of speech) is longer than typical MS MARCO passages, so measure.

### Gaps
- No rigorous per-pair CPU latency benchmark for bge-reranker-v2-m3 at clip-length inputs.
- No measurement of ONNX-INT8 reranker (the repo already ships one) on this workload; not researched.

## 4. Small-model (8B class) judges vs large models on binary relevance

### Takeaway
Evidence consistently shows accuracy drops with smaller judges, but the loss can be reduced by task decomposition and by a cascade; no source found gives a clean 8B-vs-frontier binary-relevance accuracy number.

### Cited Findings
- UMBRELA reproduction on other LLMs (Farzi and Dietz, SIGIR 2025, arXiv 2507.09483): DeepSeek V3 is very close to GPT-4o; Llama-3.3-70B slightly lower; "performance degrades further with smaller LLMs". Exact numbers not retrieved. — [arXiv 2507.09483](https://arxiv.org/html/2507.09483v1)
- Document-summarisation relevance study: GPT-4o has higher agreement with humans than Llama-3.1-8B on graded judgments across all datasets and metrics; smaller models also struggle to keep stable label distributions. — [arXiv 2512.05334](https://arxiv.org/pdf/2512.05334) (via search summary; binary table not seen)
- Schnabel et al., "Multi-stage LLM Pipelines Can Outperform GPT-4o in Relevance Assessment" (WebConf '25, arXiv 2501.14296): splitting into a binary relevance decision then a relevance classification helped, especially for the smaller model; one variant reported +18.4% Krippendorff's alpha over GPT-4o mini and +9.7% over GPT-4o; cheapest variant about 0.2 USD per million input tokens vs 5 USD for the GPT-4o baseline. One benchmark (TREC DL), no independent replication found. — [arXiv 2501.14296](https://arxiv.org/html/2501.14296v1)
- A sponsored-search paper reports a calibrated model cascade matching a single fine-tuned model at about half the relative cost (different domain). — [AutoRelAnnotator, arXiv 2606.25871](https://arxiv.org/pdf/2606.25871)
- A 2026 study claims open models outperform GPT-4.1/GPT-4o "most of the time" on original TREC topics, but the models were not identified in the summary. — [arXiv 2604.04140](https://arxiv.org/pdf/2604.04140)

### Inferences
- Do not expect an 8B zero-shot judge to hold the "score 3" precision of the current scorer. A cascade is the evidence-supported pattern: a cheap model (or cross-encoder) removes obvious rejects; the strong model only sees survivors. Because the serve rule is "only score 3", the cascade's cheap stage must be tuned for recall of true-3s (high threshold on the reject side), with the strong judge retaining the final say. This keeps precision at the strong judge's level while cutting latency only for rejects.
- Latency saving from a cascade comes only on the reject path; the served path still pays the strong judge's cost.

### Gaps
- No 8B-vs-large numbers specific to binary relevance on short conversational Q/spoken-passage pairs.
- Whether the project's current reasoning scorer (claude-haiku-5.5, per brief) is itself a "small" model for this purpose is not answerable from literature.

## 5. Parallel and speculative execution of gates and retrieval; reported savings

### Takeaway
Running a guardrail concurrently with the main work and releasing the result only if the guardrail passes is an established pattern (OpenAI cookbook, NeMo Guardrails). I found no published latency-saving percentages for it, and no paper on speculative gating for retrieval. Savings should be computed from our own timings: wall-clock approaches max(gate, retrieval+rerank) instead of the sum.

### Cited Findings
- OpenAI cookbook (guardrails): send guardrail checks asynchronously alongside the main LLM call; if triggered return the guardrail response, else return the LLM response; guardrails share the base LLM's vulnerabilities. — [OpenAI cookbook](https://cookbook.openai.com/examples/how_to_use_guardrails)
- NVIDIA NeMo Guardrails: input rails and main response generation can run in parallel ("speculative generation" in their wording); recommended for I/O-bound rails (external LLM/API calls), not CPU-bound rails; warns of race conditions if input rails mutate the input. — [NeMo Guardrails config docs](https://docs.nvidia.com/nemo/guardrails/latest/configure-guardrails/yaml-schema/guardrails-configuration)
- Practitioner distinction: parallelisation cuts wall-clock latency; short-circuiting cuts latency and cost by skipping downstream calls when an early check is decisive. — as summarised in search results (low-authority source; [open-exam-prep study guide](https://open-exam-prep.com/study-guides/anthropic-ccdv-f/ch7-foundations-workflows-patterns/parallelization-patterns) is a secondary source).
- No peer-reviewed paper with measured latency savings for speculative guardrail execution was found.

### Inferences
- The answerability gate reads only the question, so it has no dependency on retrieval output: it can start at t=0 in parallel with embedding/Qdrant retrieval and the relevance scorer. Expected saving is roughly the gate's duration (up to the 6 s budget) minus whatever retrieval takes, subject to measurement. The question-only gate could also be issued concurrently with the crisis pre-check, but the project's safety-first ordering (crisis before retrieval) should be preserved: run the crisis/topic rails first or concurrently with a hard rule that nothing from the speculative branch is served or logged as a result until the rails clear.
- Cheaper speculation: start the relevance scorer on top-1 and top-2 candidates concurrently with the gate (scorer calls are independent per pair); score top-3 pairs in parallel rather than as one batch call, with early exit on the first score of 3 in rank order only if rank order is the serve policy.
- Speculative calls spend tokens on questions that end up abstained (out-of-corpus), so measure cost per request. Cancel in-flight scorer calls when the gate returns NO.
- The shared-event-loop invariant in the repo (`run_llm_coroutine`, not `asyncio.run`) must be preserved when adding concurrency; this is project knowledge, not from literature.

### Gaps
- No reported percent savings for gate-parallel-with-retrieval designs.
- No evidence on how concurrent OpenRouter calls affect rate limits or tail latency.

## 6. Safe A/B methodology: metrics for precision at serve, abstain rate, independent-judge "don't show" share

### Takeaway
Treat this as selective prediction: evaluate on risk (error among served) vs coverage (share served), with the threshold chosen on one split and reported on a held-out split; use a different-family independent judge plus periodic human audit because LLM judges are lenient and prompt-sensitive.

### Cited Findings
- Selective-prediction protocol: pick threshold on one half, report coverage and risk on held-out half; some signals cannot reach low-risk subsets at any threshold. — [arXiv 2607.06799](https://arxiv.org/pdf/2607.06799)
- LLM judges: prompt paraphrase sensitivity (Thomas et al.) and leniency (UMBRELA authors) mean judge outputs need anchoring to human gold labels. — [Microsoft Research](https://www.microsoft.com/en-us/research/publication/large-language-models-can-accurately-predict-searcher-preferences/); [survey](https://arxiv.org/html/2504.12558v1)
- Circularity risk when the evaluation judge is also the system component. — [arXiv 2412.17156](https://arxiv.org/html/2412.17156v2)
- Fixed-sequence Learn-then-Test and conformal risk control give finite-sample guarantees for a threshold; see IJCAI 2025 two-stage work for ranked retrieval. — [IJCAI 2025](https://www.ijcai.org/proceedings/2025/1012)

### Inferences (design suggestions, not cited facts)
- Primary metrics per arm: (a) precision at serve = share of served clips judged showable by the independent judge/human (project's inverse is the "DON'T-SHOW share", currently 12% on 8 served in the last round, which is a tiny sample); (b) coverage = served / in-domain questions (currently 24-31%); (c) out-of-corpus leak count (must stay 0; use a larger OOC set than 13); (d) p50/p95 latency; (e) cost per request.
- Use a paired design: replay the same fixed question set through both arms and compare with paired tests (McNemar on show/don't-show). The project already notes LLM-generated question sets change between runs; keep the set fixed.
- Sample size caution: with 8 served items a 12% DON'T-SHOW share has an enormous confidence interval (Clopper-Pearson); require a pre-registered minimum number of served items per arm and report intervals, not point estimates.
- Shadow mode first: run the candidate (cross-encoder or small model or cascade) alongside the current scorer, serve only the current scorer's decision, log disagreements. Review all disagreements with the independent judge and a human sample, particularly cases where the candidate would serve and the current scorer abstains (the precision risk).
- Guardrail rule: a latency optimisation must be "precision non-inferior" at a pre-set margin, tested on served items; coverage drops are acceptable, precision drops are not.
- Rotate judge prompts or use a second judge family to guard against prompt-specific bias; keep a small human-labelled gold slice (project already has a human-gated plan) to anchor the LLM judge's agreement rate.

### Gaps
- No standard published threshold for "non-inferiority margin" in serve-time relevance; must be chosen by the project owner.
- No source defining the "DON'T-SHOW share" metric; it is project-specific.

## Summary of safe latency options, with evidence level
1. Run answerability gate concurrently with retrieval and scoring, cancel on NO: supported by OpenAI/NeMo patterns; savings unmeasured in literature, expected up to the gate duration (inference).
2. Score the top-3 pairs concurrently as separate calls instead of one reasoning call; cap reasoning/output tokens: inference, no source.
3. Cross-encoder (BGE v2 m3, repo already has an ONNX INT8 reranker) as pre-filter before the LLM scorer, tuned for high recall of true-3s so the LLM keeps final say; cuts LLM calls on rejects only. Calibration needs project-specific labels (sections 2 and 4).
4. Replacing the LLM scorer entirely with a cross-encoder or an 8B judge: literature shows degradation with smaller judges and non-portable reranker scores; do only after a shadow-mode precision non-inferiority result on held-out, human-anchored labels.
5. Fine-tune/distill a small cross-encoder from the LLM scorer's labels: RankGPT (440M student beating 3B supervised on BEIR) and Rank-DistiLLM are precedents, but the project's rule against fitting calibration on AI-authored labels still applies to the final threshold (project rule, not literature).
