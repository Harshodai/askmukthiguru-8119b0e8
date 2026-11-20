# Company and research practice survey, 2026-11-20

Method note: every source below was reached through search-result summaries on 2026-11-20. I did not open the full papers or pages, so details are snippet-level. Labels: [SOURCED FACT], [INFERENCE], [RECOMMENDATION].

## 1. LLM-as-judge reranking and its biases

- [SOURCED FACT] Surveys list position bias, verbosity bias, self-preference and format bias as recurring LLM-judge failures. https://arxiv.org/pdf/2412.05579, https://arxiv.org/pdf/2411.15594, https://arxiv.org/pdf/2410.02736 (twelve bias types), https://arxiv.org/pdf/2410.21819 (self-preference). Accessed 2026-11-20.
- [SOURCED FACT] Listwise LLM reranking (RankGPT-style) has context-length limits and positional bias, per a secondary source. https://www.zeroentropy.dev/concepts/listwise-reranking/ (accessed 2026-11-20). I did not retrieve the RankGPT paper itself.
- [INFERENCE] Your pointwise 0-3 scorer sees one clip at a time, so position bias matters less. Self-preference matters if the scorer and the judge share a model family (here the scorer is a Claude model). A 0-3 rubric is also a coarse scale that drifts across prompts.
- [RECOMMENDATION] Never treat judge agreement as ground truth. Use the LLM score only as a feature and ranker, and let human labels set the serving threshold.

## 2. Selective answering with thresholds from human labels

- [SOURCED FACT] Learn-then-Test (Angelopoulos et al.) frames threshold choice as multiple testing with finite-sample risk guarantees. https://arxiv.org/pdf/2110.01052 (accessed 2026-11-20). A 2025 IJCAI paper extends it to ranked retrieval. https://www.ijcai.org/proceedings/2025/1012
- [SOURCED FACT] Selective generation work (SAFER, COIN, CAP) and an EMNLP paper on pairwise LLM judging all require correctness labels, often human ones, and abstain or defer when unsure. https://arxiv.org/pdf/2509.01455v3, https://arxiv.org/html/2506.20178v1, https://proceedings.mlr.press/v304/tayebati26a.html, https://aclanthology.org/2026.emnlp-main.53.pdf (accessed 2026-11-20; snippets only).
- [SOURCED FACT] A 2026 arXiv paper reports impossibility and bound results for certifying LLM outputs with conformal risk control. https://arxiv.org/pdf/2606.29054 (not read; check before relying on it).
- [INFERENCE] The 299-item figure is consistent with the zero-error binomial bound: ln(0.05)/ln(0.99) is about 298.1. It is a sample-size bound, not a quality claim.
- [RECOMMENDATION] Label by risk tier, not randomly. Zero-error with 299 items is expensive, so first label served clips near the threshold (score 2 versus 3), where the cutoff is decided. A relaxed target (for example 5% risk, about 59 zero-error items) is a cheaper interim claim if you state it plainly.

## 3. Hub and duplicate suppression, diversity

- [SOURCED FACT] Qdrant has native MMR as a query parameter (`diversity` in [0,1], `candidates_limit`). Set `candidates_limit` well above `limit`, or MMR has nothing to choose from. LangChain's `lambda_mult` runs the opposite way. https://qdrant.tech/blog/mmr-diversity-aware-reranking/ (accessed 2026-11-20).
- [INFERENCE] MMR diversifies one result list. It does not stop the same hub clip winning across different questions, because it never sees other questions.
- [RECOMMENDATION] Cross-question hubness is a corpus problem. Count per-clip serve frequency across a question set, then down-weight or flag clips served for many unrelated queries. I found no sourced company practice for this exact case. It comes from general retrieval knowledge, so treat it as untested here.

## 4. Conversational query rewriting and topic shift

- [SOURCED FACT] Research frames the task as turning a context-dependent turn into a self-contained query (CONQRR https://arxiv.org/pdf/2112.08558), with topic-switch detection as a step (CHIQ, cited in snippets) and topic shift defined as the gold passage differing from the previous turn (AdaQR https://arxiv.org/pdf/2406.10991). Accessed 2026-11-20.
- [SOURCED FACT] Practitioner blogs suggest embedding distance between turns or topic markers to detect a shift. These are informal sources, for example https://shekhargulati.com/2024/07/17/query-rewriting-in-rag-applications/. A "60% of implementations fail" claim had no source; ignore it.
- [INFERENCE] "Shorter" is not a retrieval query. It is a request to re-serve a different, shorter clip on the same topic.
- [RECOMMENDATION] Classify follow-ups as (a) new topic, (b) continuation needing a rewrite, (c) format request such as "shorter". For (c), reuse the previous retrieval candidates and filter by duration, with no new search.

## 5. Answerability and unanswerable detection

- [SOURCED FACT] Google Research's "sufficient context" work uses an LLM autorater (at least 93% accuracy, prompted Gemini 1.5 Pro) and a small intervention model for selective generation. It also reports that RAG can reduce a model's tendency to abstain. https://research.google/blog/deeper-insights-into-retrieval-augmented-generation-the-role-of-sufficient-context/ (May 14, 2025; accessed 2026-11-20). The SQuAD 2.0 search returned nothing, so I cite no SQuAD source.
- [INFERENCE] Your YES/NO gate reads only the question, so it tests topic coverage, not whether the clip answers. The sufficiency framing (query plus context together) is closer to what you need, and it matches your WEAK-versus-answer failure.
- [RECOMMENDATION] Judge sufficiency on the (question, clip) pair and calibrate it on human labels.

## 6. Grounded-citation products

- [SOURCED FACT] Vertex AI Search check grounding returns a 0-1 support score, optional per-claim scores and citations. The citation threshold defaults to 0.6 and targets latency under 500 ms. https://cloud.google.com/generative-ai-app-builder/docs/check-grounding (accessed 2026-11-20).
- [SOURCED FACT] NotebookLM answers from uploaded sources with inline citations that jump to the passage. Evidence is third-party guides, not Google documentation. For example https://www.zenml.io/llmops-database/source-grounded-llm-assistant-with-multi-modal-output-capabilities (accessed 2026-11-20). One source says citations do not prove the interpretation is correct.
- [SOURCED FACT] Perplexity's help center says each answer has numbered citations. It does not document how sources are ranked. https://hub-prod.perplexity.ai/hub/faq/how-does-perplexity-work (accessed 2026-11-20). Ranking details come from unverified third parties.
- [SOURCED FACT] Glean describes hybrid retrieval (lexical, semantic, knowledge graph), permission-enforced retrieval and citations; performance claims are vendor-reported. https://glean.com/blog/rag-for-llms, https://www.glean.com/blog/glean-information-retrieval (accessed 2026-11-20). No engineering detail on ranking features was found.
- [SOURCED FACT] I found no official "Ask Sadhguru"-style verbatim-clip product. One unofficial GitHub project returns excerpts from his videos: https://github.qingwei-s.workers.dev/desaibhargav/sadhguru (a mirror, unverified, unmaintained status unknown). I found no source on YouTube timestamp search internals.
- [INFERENCE] Every product above cites passages to support generated text. None documents a verbatim-only, abstain-or-serve design, so no company benchmark exists for your exact case. Citation shows provenance, not that the passage answers the question.

## Summary table

| Practice | Applies to verbatim-only? | Why | Cheapest next step |
|---|---|---|---|
| LLM judge as ranker | Yes | Scoring a clip is unchanged | Cross-check scorer against a different model family on 50 clips |
| Bias audit of judge | Yes | Self-preference risk if same family | Compare scores from two judges, count disagreements |
| Human-labelled risk control (LTT) | Yes | Fixes the threshold honestly | Label 60 clips near the cutoff, report a 5% bound |
| Check-grounding score | Partly | Needs generated claims; clip is the evidence | Skip |
| MMR | Partly | Diversifies one list only | Test `candidates_limit` > `limit` on top-k |
| Hub suppression | Yes | Hubs are a corpus issue | Count serves per clip over the question set |
| Query rewriting | Yes | Fixes context-dependent turns | Rewrite only continuations |
| Topic-shift detection | Yes | Prevents stale context | Embedding distance threshold, validate on labelled turns |
| Format follow-up ("shorter") | Yes | Not a retrieval query | Re-rank previous candidates by duration |
| Answerability / sufficiency | Yes | Matches WEAK clips | Prompt on (question, clip), compare to labels |
| Inline citation UI | Partly | Already your whole output | None |
