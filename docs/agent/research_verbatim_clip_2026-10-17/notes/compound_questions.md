# Answering compound, multi-part questions from verbatim clips (extractive only)

Research limits: WebFetch and direct curl to arxiv.org, aclanthology.org, Semantic Scholar and LlamaIndex docs were blocked in this environment (DNS failure and proxy 403). Every cited item below comes from WebSearch result summaries only, not from the papers' full text. Numbers are quoted as the search summaries gave them, and anything not seen is marked UNVERIFIED. Several items rest on a single secondary source and are flagged where that applies.

## What query-decomposition methods exist, and what gains are reported on multi-hop / multi-facet retrieval?

### Takeaway
Decomposition methods are LLM-driven: least-to-most, self-ask, DecompRC-style span-based splitting, and the LlamaIndex sub-question engine. The most relevant recent retrieval-side result is Ammann et al. (ACL 2025 SRW): decompose with an LLM, retrieve per sub-question, merge, and rerank with a cross-encoder. They report large retrieval gains on MultiHop-RAG and HotpotQA, but the exact figures conflict across summaries. Nothing I found evaluates deterministic conjunction splitting. That comparison is a gap.

### Cited Findings
- Least-to-most prompting uses two stages. A decomposition prompt breaks the question into subproblems. The model then answers them in order, appending each answer to the context for the next, and the original problem is the final subproblem. No training is needed. — [Zhou et al., arXiv 2205.10625 (search summary)](https://arxiv.org/pdf/2205.10625)
- A blog (not verified against the paper) reports SCAN length-generalization accuracy of 16.2% for chain-of-thought and 99.7% for least-to-most. Treat as UNVERIFIED. — [adaline.ai blog](https://www.adaline.ai/blog/least-to-most-prompting)
- Practitioner sources note that early-step mistakes compound in later steps, and that the extra model calls raise cost. — [adaline.ai blog](https://www.adaline.ai/blog/least-to-most-prompting)
- Least-to-most is sequential: later sub-questions depend on earlier answers. That suits multi-hop questions. It is a mismatch for parallel facets like ours, where sub-questions are independent. (This is my reading of the method description, not a source claim.)
- Self-ask (Press et al.) defines the "compositionality gap" as the share of cases where a model answers all sub-questions correctly but still gets the compositional question wrong. In the GPT-3 family the gap does not shrink with scale. Self-ask has the model write and answer follow-up questions before the final answer. Its fixed structure makes it easy to plug in a search engine for the follow-ups. — [Press et al., arXiv 2210.03350 (search summary)](https://arxiv.org/html/2210.03350v3)
- Bamboogle accuracy per a secondary leaderboard (GPT-3 davinci-002): direct prompting 17.6, chain-of-thought 46.4, self-ask 57.6, self-ask + Google Search 60.0. One source only, and the same table has an obviously bad placeholder row, so UNVERIFIED against the paper. — [hyper.ai Bamboogle leaderboard](https://www.hyper.ai/cn/sota/tasks/question-answering/benchmark/question-answering-on-bamboogle)
- DecompRC (Min et al., ACL 2019) decomposes a multi-hop HotpotQA question into single-hop sub-questions that off-the-shelf reading-comprehension models can answer. Sub-question generation is cast as span prediction. About 400 labeled examples were enough to match human-written sub-questions. A global rescoring step scores each full decomposition (sub-questions plus answers) to pick the final answer. — [Min et al. 2019 (search summary)](https://arxiv.org/pdf/1906.02916)
- Ammann, Golde and Akbik (ACL 2025 SRW, pp. 497-507): an LLM splits the question into sub-questions, passages are retrieved for each, and the merged pool is reranked with a cross-encoder. Evaluated on MultiHop-RAG and HotpotQA. Abstract-level claims: MRR@10 +36.7% and answer F1 +11.6% over standard RAG. — [arXiv 2507.00355 / ACL 2025 SRW](https://aclanthology.org/2025.acl-srw.32)
- The same work is summarized differently by a third party as +16.5% Hits@10 on MultiHop-RAG and F1 35.0 on HotpotQA. The two framings conflict, and I could not read the paper's tables. Treat the numbers as UNVERIFIED. Also note MRR@10 +36.7% appears to be a relative gain, with no absolute values seen. — [alphaXiv summary](https://www.alphaxiv.org/overview/2507.00355v1)
- LlamaIndex `SubQuestionQueryEngine` splits a complex query into sub-questions per relevant data source, collects intermediate answers, and synthesizes a final response. The docs example splits a question about a person's life before, during, and after YC into three sub-questions. Construction takes a question generator, response synthesizer, and `QueryEngineTool`s. — [LlamaIndex docs (search summary)](https://developers.llamaindex.ai/python/examples/query_engine/sub_question_query_engine/index.md)
- A 2025 arXiv paper (2508.09755, Lee) decomposes multi-hop questions into single-hop sub-questions and also matches the incoming question against questions pre-generated per document chunk. This is similar to the "question field" design the product already uses. Details not verified. — [papers.cool listing](https://papers.cool/arxiv/2508.09755)

### Inferences
- The product's question ("How can meditation heal suffering and imbibe love, prosperity and success?") is a parallel multi-facet question, not a multi-hop chain. The relevant pattern is "fan out, retrieve per facet, merge" (Ammann et al., LlamaIndex sub-question engine), not sequential least-to-most or self-ask.
- Deterministic splitting on "and"/commas would handle the example's list ("love, prosperity and success") but would mis-split phrases like "peace and quiet" or "body and mind" when they are one concept. No source tested this. I would pair a rule-based candidate split with a cheap check, or use one small-model call that returns a JSON list of facets.
- The "how can meditation heal suffering" part is a shared head. Each facet question should be expanded to carry the head ("meditation" + facet) so retrieval does not lose the topic. This is design reasoning, not a sourced finding.

### Gaps
- No full-text access to the Ammann et al. tables, so the real absolute gains and the effect of the reranking step on its own are unknown.
- No paper found comparing rule-based conjunction splitting to LLM decomposition on retrieval quality.
- No source found on decomposition for spoken-transcript or devotional corpora specifically.

## What does the literature say about multi-span / multi-passage extractive QA and about selecting a diverse, facet-covering set of passages?

### Takeaway
MultiSpanQA shows multi-span answers are a recognized, under-served extractive task and supplies metrics for partial credit, but its spans sit inside one passage. For choosing a set of clips that covers all facets, the classic tools are MMR (relevance minus similarity to already selected items) and facet-aware diversification (xQuAD-style, which scores each result against sub-queries). I could not verify xQuAD details from a source.

### Cited Findings
- MultiSpanQA (Li, Tomko, Vasardani, Baldwin; NAACL 2022, pp. 1250-1260) targets questions whose answers are several non-adjacent spans. Built on Natural Questions, re-annotated; 6,536 multi-span examples. An expanded version adds unanswerable and single-span questions, for over 19,000 examples. The authors propose new metrics for multi-span answers and a model that beat baselines. — [ACL Anthology 2022.naacl-main.90 (search summary)](https://aclanthology.org/2022.naacl-main.90)
- Maximal Marginal Relevance (Carbonell and Goldstein, SIGIR 1998) reduces redundancy while keeping query relevance when reranking documents and selecting passages. It is user-tunable between narrow drill-down and broader sampling. The clearest benefit shown was non-redundant multi-document summaries. — [SIGIR'98 abstract](https://people.eng.unimelb.edu.au/ammoffat/sigir98/abstracts/carbonell.html)
- A 2022 diversification survey describes MMR as a linear combination of relevance and diversity, with diversity as negative maximum similarity to already-selected items, applied as greedy post-processing on already-learned embeddings. — [Result Diversification in Search and Recommendation: A Survey](https://arxiv.org/pdf/2212.14464)
- PyTerrier's dense-retrieval extension ships an MMR re-ranker, so MMR is available off the shelf. — [PyTerrier diversity docs](https://pyterrier.readthedocs.io/en/stable/ext/pyterrier-dr/diversity.html)
- The repo's own CLAUDE.md says retrieval already uses MMR for diversity in the chat graph, and `query_points_groups` caps chunks per parent. That covers diversity between near-duplicate clips but not coverage of facets. (Repo context, not an external source.)

### Inferences
- MMR alone does not guarantee facet coverage. It spreads results apart in embedding space, but two dissimilar clips could both be about "suffering" and none about "prosperity". Facet-aware selection fixes this by assigning the best clip per facet first, then using MMR or a similarity cap to remove clips that are the same passage restated.
- A simple, auditable selection rule for this product: for each facet f, take the top clip c_f by reranker score; accept only if score >= facet threshold; drop a clip if it overlaps (same video, overlapping or contained time range) another accepted clip; if one clip is the best for two facets, serve it once and label both. This is my design proposal, not from a paper. Repo notes say 27% of v8 clips are contained inside another clip of the same video, so overlap de-duplication matters here.
- MultiSpanQA is mainly relevant for its partial-credit metrics idea (score each facet separately), which suggests evaluating "facet coverage" and "per-facet precision" as separate numbers.

### Gaps
- No source verified for xQuAD (Santos, Macdonald, Ounis, ~2010) or Zhai et al. subtopic retrieval; the search for xQuAD returned nothing relevant. Recall from background knowledge only: UNVERIFIED.
- No multi-passage reader paper (e.g. FiD, multi-passage BERT) was retrieved, and those are generative or span readers anyway, not clip-selection methods.
- No source on evaluating facet coverage (alpha-nDCG, subtopic recall) was fetched. UNVERIFIED.

## How do systems detect that a sub-question has no answer in the corpus (unanswerable detection, selective prediction)?

### Takeaway
Raw confidence scores are over-confident on out-of-domain inputs. A separately trained calibrator works better than the base model's probabilities, and a sufficiency check on retrieved context improves precision among answered items. For a clip product the practical analog is a per-facet accept/abstain decision using a reranker or relevance score calibrated on labeled data.

### Cited Findings
- SQuAD 2.0 (Rajpurkar, Jia, Liang, ACL 2018) added over 50,000 crowdworker-written unanswerable questions to the 100,000 in SQuAD 1.1, written to look like answerable ones. A system scoring 86% F1 on SQuAD 1.1 reached only 66% F1 on SQuAD 2.0. — [arXiv 1806.03822 (search summary)](https://arxiv.org/abs/1806.03822)
- Selective QA under domain shift (Kamath, Jia, Liang, ACL 2020): abstention based only on softmax probability does poorly because models are overconfident out of domain. A separate calibrator that predicts whether the QA model is wrong answers 56% of questions at 80% accuracy, versus 48% using the model's probabilities. — [arXiv 2006.09462](https://arxiv.org/pdf/2006.09462)
- Sufficient Context (Joren et al., ICLR 2025): defines when retrieved context suffices to answer. Strong models tend to give a wrong answer rather than abstain when context is insufficient. A selective-generation method that uses sufficiency signals raised the share of correct answers among those given by 2-10% for Gemini, GPT and Gemma. — [ICLR 2025 proceedings](https://proceedings.iclr.cc/paper_files/paper/2025/hash/33dffa2e3d2ab74a783d1a8c292f66d9-Abstract-Conference.html)
- MultiSpanQA's expanded version includes unanswerable questions, so partial-answer / no-answer cases are benchmarked there. — [ACL Anthology 2022.naacl-main.90 (search summary)](https://aclanthology.org/2022.naacl-main.90)

### Inferences
- The repo's existing calibration approach (fixed-sequence Learn-then-Test, 1% risk, at least 299 confident gold items with 0 errors, no profile exists today) applies per facet: each (sub-question, clip) pair is its own accept/abstain decision, so the number of gold labels needed is counted in pairs. The tension: a compound question multiplies decisions, so end-to-end risk grows with the number of facets served. If any served facet can be wrong, per-facet risk must be set lower or the answer labelled per clip. This is my reasoning, not from a source.
- Until a calibrated threshold exists, the honest default for each facet is the repo's current state: serve as "Related, not a direct answer", or say "no recording for this part". Kamath et al. support using a trained calibrator over raw similarity, which matches the repo's rule never to hand-pick a threshold.
- A cheap unanswerability signal that needs no generation: the score gap between the best clip for this facet and the best clip for the unrelated or other facets, plus an answerability YES/NO call (already used in the repo, invariant 22). Sufficient Context supports using a separate sufficiency judgment, but its measured gains are on generative RAG, not clip retrieval.

### Gaps
- No source found on abstention specifically for per-facet or partial-answer decisions (answer some parts, abstain on others).
- Kamath et al.'s calibrator features and the SQuAD 2.0 human-performance numbers were not seen in full text.
- No literature found on conformal / Learn-then-Test applied to multi-facet answers; the multiple-decision risk point above is untested.

## What are the latency and cost trade-offs of decomposition: one extra small-model call vs deterministic splitting?

### Takeaway
I found no primary source with measured decomposition latency. What is sourced: decomposition adds model calls and cost, and sequential methods compound errors. Repo measurements show the pipeline is dominated by LLM calls, with the first-person path already at about 4-6 s uncached. A single parallel decomposition call plus parallel retrieval would add one LLM round trip, not one per facet.

### Cited Findings
- Practitioner sources say least-to-most's extra model calls can increase cost, and early mistakes compound. — [adaline.ai blog](https://www.adaline.ai/blog/least-to-most-prompting)
- Self-ask's follow-up questions can each be sent to a search engine, so one search per sub-question. — [Press et al. (search summary)](https://arxiv.org/html/2210.03350v3)
- Repo measurement (internal, not external): `navigate_and_hyde` merged decomposition, navigation and HyDE into one `asyncio.gather` and cut p95 on comparative queries from 165.4 s to 113.0 s; the CLAUDE.md note says they are independent LLM calls and should not be run serially. First-person uncached latency is about 4-6 s (answerability gate + rerank LLM calls); local retrieval alone is about p50 63 ms / p95 210 ms. (Repo CLAUDE.md, invariants 9, 22, and the R22 note.)
- Repo measurement: `FIRST_PERSON_RELEVANCE_MODEL` scorer needed `max_tokens=1024` and a 12 s budget because the model reasons internally; at 24/256 tokens it returned empty replies. (Repo CLAUDE.md, invariant 24.)

### Inferences
- Deterministic splitting costs about 0 ms but has the false-split problem described above. One small-model decomposition call plus N parallel retrievals adds roughly one model round trip. Given the repo's 4-6 s uncached figure, a reasoning-heavy model could add seconds; a non-reasoning small model with a short JSON output should add much less, but I have no measurement. Measure before choosing.
- Cost-efficient pattern: only call the decomposer when a cheap detector (two or more conjunctions or commas, or question length) flags a likely compound; otherwise take the current single-clip path. Cache by normalized question text (the exact Redis cache already exists).
- Per-facet answerability gate and relevance scoring multiply the existing LLM calls by the facet count. Run them in parallel (the repo notes all sync LLM calls must share one loop via `run_llm_coroutine`) and cap facets (for example 3-4) to bound latency and the rate limit.

### Gaps
- No external benchmark with latency numbers for LLM decomposition versus rule-based splitting.
- Latency of the repo's own decomposer was not measured here; no experiment was run.

## Summary of unresolved items for the report writer
- UNVERIFIED: all SCAN, Bamboogle, and Ammann et al. numbers beyond what is quoted above; xQuAD and subtopic retrieval details; any claim about full-text paper content (full text was not accessible).
- No literature found that directly addresses "one verbatim clip per facet or an honest no-recording" for spoken-teaching corpora; the design above is assembled from adjacent work (sub-question retrieval, diversification, selective prediction) and should be validated on a small gold set of compound questions.
