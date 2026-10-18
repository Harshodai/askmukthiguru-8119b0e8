# Contextual retrieval designs for a verbatim-clip Qdrant collection: prepend vs metadata vs separate vector, and the effect on calibrated thresholds

Sandbox note for the report writer: WebFetch and curl could not reach arxiv.org, qdrant.tech, jina.ai, semanticscholar.org or huggingface.co (proxy 403 / DNS). Primary pages actually read in full: Anthropic's post, Anthropic's cookbook, Qdrant's OpenAPI JSON on raw.githubusercontent.com, the Jina late-chunking GitHub README, the docTTTTTquery GitHub README, the FlagEmbedding READMEs. Arxiv papers and Qdrant docs pages were only seen through web-search summaries (secondary); those items are tagged [SEARCH-SUMMARY] and anything not confirmed is tagged UNVERIFIED.

## 1. Anthropic Contextual Retrieval: exact method, numbers, independent replications

### Takeaway
Anthropic prepends a 50-100 token LLM-generated, chunk-specific context to each chunk before BOTH embedding and BM25 indexing, and reports a 35% / 49% / 67% cut in top-20 failure rate (5.7% baseline) without/with BM25/with reranking. Everything beyond that is self-run by Anthropic or vendor tutorials; the one academic comparison I found is mixed. Notably the method changes the embedded text itself, so it is the "prepend" design, not the metadata design.

### Cited Findings
- Method: two sub-techniques, Contextual Embeddings and Contextual BM25; the generated context "usually 50-100 tokens, is prepended to the chunk before embedding it and before creating the BM25 index" — [Anthropic post](https://www.anthropic.com/engineering/contextual-retrieval) (the /news/ URL serves the same article)
- Prompt (Claude 3 Haiku era): whole document in `<document>` tags, chunk in `<chunk>` tags, then "Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else." — [Anthropic post](https://www.anthropic.com/engineering/contextual-retrieval); same prompt in code in the [Anthropic cookbook](https://platform.claude.com/cookbook/capabilities-contextual-embeddings-guide)
- Numbers (metric = 1 - recall@20, i.e. share of relevant chunks not in top 20; averaged over codebases, fiction, ArXiv papers, science papers; best embedding config Gemini Text 004): Contextual Embeddings 5.7% -> 3.7% (-35%); + Contextual BM25 5.7% -> 2.9% (-49%); + Cohere reranking (retrieve top 150, rerank to top 20) 5.7% -> 1.9% (-67%) — [Anthropic post](https://www.anthropic.com/engineering/contextual-retrieval)
- Cost: one-time $1.02 per million document tokens with prompt caching, assuming 800-token chunks, 8k-token documents, 50-token instructions, 100 tokens of context per chunk — [Anthropic post](https://www.anthropic.com/engineering/contextual-retrieval)
- Anthropic's own recommendations: embeddings + BM25 beat embeddings alone; Gemini and Voyage embeddings "particularly effective"; tailor the contextualizer prompt to the domain (e.g. add a glossary); experiment with chunk size/boundary/overlap; "always run evals" — [Anthropic post](https://www.anthropic.com/engineering/contextual-retrieval)
- Anthropic states gains vary by embedding model ("some models may benefit more than others") and that contextualizing improved every embedding-source combination tested; per-combination numbers are in an appendix I did not extract — [Anthropic post](https://www.anthropic.com/engineering/contextual-retrieval)
- Cookbook replication on a different, smaller set (9 codebases, 248 queries, Voyage-2 embeddings, character-split chunks): Pass@5 80.92%, Pass@10 87.15% baseline; "Contextual Embeddings ... improve Pass@10 from ~87% to ~95%"; adding contextual BM25 hybrid gave Pass@10 92.31% / Pass@20 95.23% in the logged run — [Anthropic cookbook](https://platform.claude.com/cookbook/capabilities-contextual-embeddings-guide). This is Anthropic's own code and data, not independent.
- Independent-ish academic comparison: "Reconstructing Context" (Merola and Singh, ECIR 2025 workshop) compares late chunking and contextual retrieval inside RAG pipelines; its abstract says contextual retrieval preserves semantic coherence better but costs more compute, while late chunking is cheaper but "tends to sacrifice relevance and completeness"; a summary says results vary with embedding model and dataset — [arXiv 2504.19754](https://arxiv.org/abs/2504.19754) [SEARCH-SUMMARY]
- A search turned up only vendor/tutorial reproductions (Medium, freeCodeCamp, Mixpeek); I found no independent peer-reviewed replication with different corpora reporting the 35/49/67% figures — web search, no single source

### Inferences
- Anthropic's gain comes from resolving ambiguity that the chunk text itself does not carry (company name, period, file). Verbatim spiritual clips with anaphora ("this", "that state") fit the same failure mode, but the 5.7% -> 1.9% numbers are from English document corpora with 800-token chunks, not short spoken clips; do not transfer them as expectations.
- The Anthropic design is the ONE that mutates the embedded string; therefore every Anthropic number is a measurement of "prepend", and none speaks to "metadata only" or "separate vector". Those designs have to be validated locally.
- The BM25 half matters: Anthropic's largest single step after embeddings was adding contextual BM25. Here the analogue is BGE-M3 sparse; prepending context would also contaminate the sparse vector's term weights (inference, not tested by anyone I found).

### Gaps
- Appendix per-embedding-model tables of the Anthropic post not extracted.
- No independent replication on speech transcripts or short clips found.
- Could not read the full text of 2504.19754 (arxiv blocked), so its actual metrics are UNVERIFIED.

## 2. Alternatives: late chunking, metadata filters, multi-vector per point, doc2query / question vectors / HyDE

### Takeaway
Late chunking and doc2query both change what the dense vector encodes, and the better-evidenced variant for dense retrieval keeps the original text vector separate from the added signal and fuses at query time (Doc2Query++ "Dual-Index Fusion"), which is structurally the proposed "separate context_dense" design. Gains reported are modest to moderate and dataset dependent.

### Cited Findings
- Late chunking (Jina): run the transformer over the whole long text, then apply mean pooling per chunk span, so chunk vectors see document context; needs no extra training but requires a long-context embedder (jina-embeddings-v2: 8192 tokens) — [jina-ai/late-chunking README](https://raw.githubusercontent.com/jina-ai/late-chunking/main/README.md); paper [arXiv 2409.04701](https://arxiv.org/abs/2409.04701) (Gunther et al.) [SEARCH-SUMMARY]
- Late chunking results from the README (BeIR, 256-token chunks, jina-embeddings-v2-small-en, nDCG@10): SciFact 64.20 -> 66.10; TRECCOVID 63.36 -> 64.70; FiQA2018 33.25 -> 33.84; NFCorpus 23.46 -> 29.98; Quora 87.19 -> 87.19 (documents ~62 chars, no change); README notes gains correlate with average document length — [jina-ai/late-chunking README](https://raw.githubusercontent.com/jina-ai/late-chunking/main/README.md). A search summary cites 2.70-3.63% nDCG@10 gains on BEIR for the paper — [SEARCH-SUMMARY of arXiv 2409.04701](https://arxiv.org/html/2409.04701v3); the two framings are not reconciled here.
- Direct evidence of score shifts: in the README's Berlin example, similarity of query "Berlin" to a chunk that names Berlin barely moves (0.8486 -> 0.8495), but chunks with anaphoric references rise sharply (0.7084 -> 0.8249 and 0.7535 -> 0.8498) — [jina-ai/late-chunking README](https://raw.githubusercontent.com/jina-ai/late-chunking/main/README.md)
- doc2query / docTTTTTquery: generate likely queries per passage offline, append to the passage, index; inference-heavy work moves to index time; on MS MARCO passage MRR@10 BM25 18.6 -> docTTTTTquery 27.2 (BM25 index) — [castorini/docTTTTTquery README](https://raw.githubusercontent.com/castorini/docTTTTTquery/master/README.md). This is a SPARSE-retrieval result; it does not establish dense gains.
- Doc2Query--: hallucinated generated queries hurt; filtering with a relevance model improves effectiveness "by up to 16%" while cutting query time 30% and index size 48% (abstract versions differ: 23% and 33% in another) — [arXiv 2301.03266](https://arxiv.org/pdf/2301.03266) [SEARCH-SUMMARY]
- Doc2Query++ (arXiv 2510.09557): appending generated queries to documents adds noise to dense embeddings; proposed Dual-Index Fusion encodes text and generated queries separately and fuses with weight alpha; it consistently beats Append across datasets; nDCG@10 peaks around alpha 0.3-0.5 (FiQA) and 0.5-0.6 (SCIDOCS) and falls toward 1.0 — [arXiv 2510.09557](https://arxiv.org/pdf/2510.09557) [SEARCH-SUMMARY]
- Qdrant supports several named vectors per point, each with own size/metric, which is the storage substrate for multi-vector-per-point — Qdrant collections docs, [search summary](https://qdrant.tech/documentation/manage-data/collections/) [SEARCH-SUMMARY]
- Metadata filters: payload indexes (keyword, integer, float, bool, geo, datetime, text, uuid) accelerate filtering; keyword index is for exact, case-sensitive matches; index per field is a user choice with memory cost — [Qdrant indexing docs](https://qdrant.tech/documentation/manage-data/indexing/) [SEARCH-SUMMARY]
- Cross-document paper notes contextual augmentation works only within document boundaries and does not fix information spread across sources — [arXiv 2601.05265](https://arxiv.org/pdf/2601.05265) [SEARCH-SUMMARY, claim cited second-hand]

### Inferences
- A pure metadata approach (discourse title, tags, concept id as payload) cannot change vector scores at all; it only filters or boosts. It is therefore the zero-drift option for the existing threshold, but it also yields no retrieval gain by itself unless the filter is derived from the query (query-side concept routing), which needs its own accuracy measurement.
- Doc2Query++ is the closest published support for the proposed split design: keep original-text vector untouched, put the added signal in a second index/vector, weight the fusion. Its datasets are BEIR text, not clips; the transfer is plausible, not proven.
- Late chunking would still change the dense vector of the passage (not "pure verbatim") and requires reprocessing at document level. BGE-M3 has an 8192 context ([FlagEmbedding BGE-M3 README](https://raw.githubusercontent.com/FlagOpen/FlagEmbedding/master/README.md): 1024-dim, 8192) but whether late-chunked BGE-M3 sparse weights are meaningful is UNVERIFIED. Long 40-minute videos would also exceed 8192 tokens and need windows. Short-document corpora gained nothing in the Jina table (Quora), and clips are short.
- The repository's synthetic-question idea (question_dense) is the doc2query family; the Doc2Query-- literature says unfiltered generated questions can lower quality, so a filter/review gate is justified (consistent with the repo's existing "review gate before any Qdrant write" invariant).

### Gaps
- HyDE (Gao et al., arXiv 2212.10496): not retrieved; no HyDE numbers are quoted here. Note HyDE is query-side (hypothetical answer embedded at query time), which would add an LLM call at serve time and conflict with the repo's "no LLM at serve time" invariant.
- No measured dense-retriever results for doc2query on multilingual/speech corpora found.
- Full paper tables for Doc2Query++ and Late Chunking not read.

## 3. Qdrant mechanics: named vectors, prefetch, RRF/DBSF, payload filters

### Takeaway
Qdrant's Query API supports exactly the proposed layout: several named vectors (dense, sparse, extra) per point, each queried by a `prefetch` with `using=<name>`, merged by an outer fusion (RRF or DBSF), with an optional filter per prefetch. The current OpenAPI also exposes RRF `k` and per-prefetch `weights`, which matters for controlling a third list's influence.

### Cited Findings
- Query/Prefetch schema: `prefetch` = sub-requests performed first; `using` selects the vector name; each prefetch can carry its own `filter`, `limit`, `score_threshold`; prefetches can be nested — [Qdrant OpenAPI (master)](https://raw.githubusercontent.com/qdrant/qdrant/master/docs/redoc/master/openapi.json)
- `Fusion` enum: `rrf` ("Reciprocal Rank Fusion with default parameters") and `dbsf` ("Distribution-Based Score Fusion") — [Qdrant OpenAPI (master)](https://raw.githubusercontent.com/qdrant/qdrant/master/docs/redoc/master/openapi.json)
- Separate `RrfQuery` with parameters `k` (integer, min 1) and `weights` (float array, "higher weight gives more influence ... number of weights should match number of prefetches") — [Qdrant OpenAPI (master)](https://raw.githubusercontent.com/qdrant/qdrant/master/docs/redoc/master/openapi.json). This is the master branch spec; the minimum Qdrant server version that supports weighted RRF is UNVERIFIED.
- `score_threshold` is documented only as "Return points with scores better than this threshold" on the query request and on each prefetch — [Qdrant OpenAPI (master)](https://raw.githubusercontent.com/qdrant/qdrant/master/docs/redoc/master/openapi.json). Its semantics against a fusion-produced score are not specified there.
- RRF uses only rank positions; DBSF normalizes each prefetch's scores using mean +/- 3 standard deviations then sums per point; DBSF available from v1.11.0; examples use `k: 60` while a docs statement gives a default of 2 (inconsistency noted by the summarizer) — [Qdrant hybrid queries docs](https://qdrant.tech/documentation/search/hybrid-queries/) [SEARCH-SUMMARY]
- Fusion only reorders the union of candidates the prefetches return; a point no prefetch retrieves cannot appear. Tuning guide: start with RRF, compare DBSF on labeled queries; default RRF beat the stronger single retriever on 4 of 5 datasets in Qdrant's benchmarks — [Qdrant hybrid search tuning](https://qdrant.tech/documentation/search-tuning/hybrid-search/) [SEARCH-SUMMARY]
- Community note that DBSF absolute scores are normalized per prefetched list and may not be comparable across queries — [skills.sh summary](https://www.skills.sh/qdrant/skills/qdrant-hybrid-search-combining) [SEARCH-SUMMARY, low authority]
- Named vectors: each has own dimension/metric; payload index types and keyword filter semantics as above — [Qdrant collections docs](https://qdrant.tech/documentation/manage-data/collections/), [indexing docs](https://qdrant.tech/documentation/manage-data/indexing/) [SEARCH-SUMMARY]

### Inferences
- Adding `context_dense` as a third prefetch is purely additive in storage: existing `passage_dense` and `passage_sparse` vectors and point ids (uuid5 of transcript_hash:start_ms:end_ms per repo invariant 4) are untouched, because context lives in payload/another vector. Verbatim text and sha256 integrity gate (repo invariants 2, 13) are unaffected since the hash is over the verbatim text only.
- Filters used as payload indexes (concept id, discourse id) require an index per field to be cheap; they cut candidates but do not change scores of surviving candidates for a vector query.
- With rank-based RRF, the fused score depends on the number of prefetch lists and `k`. For two lists with 1-based ranks the maximum is 2/(k+1); adding a third list raises the ceiling to 3/(k+1) and changes the spacing of scores (my arithmetic from the standard RRF definition, not a quoted Qdrant statement). Any threshold set directly on the fused score is therefore not portable when the number of prefetches changes, unless weights are chosen to preserve the old scale.

### Gaps
- Could not read qdrant.tech pages directly; all Qdrant doc statements except the OpenAPI schema are search-summary level.
- What `score_threshold` does on the outer query when `query` is a fusion: UNVERIFIED (not documented in the schema). Test empirically on the deployed server version.
- Whether the repo's abstention gate keys on fused RRF score, dense cosine, or reranker output is not established by this research; check the code before reasoning about drift.

## 4. Does changing embedded text shift cosine-score distributions enough to break a fixed threshold? Calibration / selective prediction evidence

### Takeaway
Yes in principle, and the available evidence points one way: contextualizing a chunk selectively raises its similarity to topically matching queries (Jina's example) and BGE-style models are known to have narrow, model-specific similarity ranges, so a threshold fit on pure-passage scores should be treated as invalid after any change to the embedded text, fusion lists or RRF settings. Distribution-free risk-control methods are valid only for the exact pipeline they were calibrated on.

### Cited Findings
- Contextualization shifts similarity non-uniformly: unchanged where the chunk already names the entity, +0.12 to +0.10 where it has anaphora — [jina-ai/late-chunking README](https://raw.githubusercontent.com/jina-ai/late-chunking/main/README.md). This is a different mechanism (token-level pooling) than text prepending, so it is an analogue, not a measurement of prepending.
- BAAI notes that earlier BGE versions had a skewed "similarity distribution" which the v1.5 models were released to alleviate; i.e. raw cosine ranges are model-dependent and not intrinsically calibrated — [FlagEmbedding README, 09/12/2023 entry](https://raw.githubusercontent.com/FlagOpen/FlagEmbedding/master/README.md). (BGE-M3 example dense scores in its README, e.g. 0.6265 for a matching pair and ~0.35 for non-matching, illustrate a compressed range; this is an example, not a benchmark — [BGE-M3 README](https://raw.githubusercontent.com/FlagOpen/FlagEmbedding/master/research/BGE_M3/README.md).)
- Doc2Query++: appending generated text adds "semantic noise" to document embeddings, and fusion weight alpha trades precision against recall (peak mid-range, falls at 1.0) — [arXiv 2510.09557](https://arxiv.org/pdf/2510.09557) [SEARCH-SUMMARY]
- Learn-then-Test (Angelopoulos, Bates, Candes, Jordan, Lei): tests a grid of thresholds with multiple-hypothesis control (FWER), fixed-sequence testing in a pre-set order is valid, guarantee is risk below target with probability >= 1 - delta for the selected set, under exchangeability of calibration and test data — [arXiv 2110.01052](https://arxiv.org/pdf/2110.01052), [MAPIE LTT docs](https://mapie.readthedocs.io/en/latest/content/risk-control/theory/) [SEARCH-SUMMARY]. MAPIE describes Hoeffding-Bentkus p-values; I did NOT confirm Clopper-Pearson in these sources (the repo uses Clopper-Pearson upper bounds, which is a standard exact binomial bound, but that is not established by these citations).
- C-RAG (Kang et al.) bounds RAG generation risk by conformal analysis, searching RAG configurations including retrieval count and similarity threshold; guarantees extend to bounded risks under distribution shift with extra assumptions — [arXiv 2402.03181](https://arxiv.org/abs/2402.03181) [SEARCH-SUMMARY]
- Other risk-controlled refusal work surfaced: "Trusted Uncertainty in LLMs" ([arXiv 2509.01455](https://arxiv.org/html/2509.01455v1)), CiteGuard ([ICML 2026](https://icml.cc/virtual/2026/poster/64935)) — [SEARCH-SUMMARY]; how they use retrieval scores specifically is UNVERIFIED.
- Repo state: per CLAUDE.md invariant 3, no calibration profile exists today (14 human labels; 299 confident items with 0 errors needed for 1% risk at delta 0.05), so every answer is "Related, not a direct answer" and no hand-picked threshold is allowed — repo CLAUDE.md (internal, not a URL source)

### Inferences
- Because no profile is fitted yet, switching the embedded text now invalidates nothing; doing it after the 299-label calibration would force a refit with fresh labels. This is the strongest argument for deciding the indexing design BEFORE commissioning/fitting the calibration batch.
- Any finite-sample guarantee from LTT/Clopper-Pearson attaches to the full scoring function (embedding text, which vectors, fusion type, k, weights, reranker). Treat all of these as part of "the threshold". The proposed layout (pure passage vectors, context only as payload or a separate vector) preserves the old scores exactly only if the serving score is still computed from the two original vectors; fusing in `context_dense` changes the score.
- Safest ordering of designs by threshold drift (my reasoning): payload-only metadata (no drift) < separate context vector used only as an additional candidate generator but with the final gate score still from the original two-vector score or the reranker < context vector inside the RRF (drift: scale and ordering change) < prepending text into the embedded passage (drift: all dense and sparse scores change, and every point must be re-embedded).
- Exchangeability caveat: gold questions used for calibration must resemble live questions; changing retrieval to favor context-matched queries changes which questions get confident answers, so calibrate and report coverage on the same fixed set.

### Gaps
- No source found that directly measures how prepending LLM context shifts cosine/BGE-M3 score distributions; the claim above is inference from Jina's example and general calibration theory (UNVERIFIED empirically; must be measured locally).
- Original selective-classification (Geifman and El-Yaniv) and conformal risk control (Angelopoulos et al. 2208.02814) papers not retrieved.
- Clopper-Pearson usage inside LTT not confirmed by retrieved text.

## 5. Validating on a fixed question set before switching collections

### Takeaway
Build the candidate as a NEW collection (matching the repo's rule that a new version is a new collection and the old one stays for rollback), run both collections against the identical frozen question set and compare retrieval metrics, score distributions, abstention behavior and out-of-corpus leakage; switch only if gold-set retrieval improves without unacceptable score-distribution drift or leakage. The methodology below is my synthesis; supporting sources are the Anthropic "always run evals" advice and the repo's invariants.

### Cited Findings
- Anthropic: "always run evals"; evaluate with recall@k style metrics (1 - recall@20; cookbook Pass@k with golden chunk labels) — [Anthropic post](https://www.anthropic.com/engineering/contextual-retrieval), [cookbook](https://platform.claude.com/cookbook/capabilities-contextual-embeddings-guide)
- Cookbook protocol is a fixed labeled set (248 queries, one golden chunk each) evaluated at Pass@5/10/20 for each pipeline variant — [Anthropic cookbook](https://platform.claude.com/cookbook/capabilities-contextual-embeddings-guide)
- Doc2Query++ shows fusion weight sensitivity (best alpha mid-range), so sweep the weight on labeled queries rather than assuming one — [arXiv 2510.09557](https://arxiv.org/pdf/2510.09557) [SEARCH-SUMMARY]
- Qdrant's own advice: start RRF, compare DBSF on the same labeled queries; fusion cannot surface points no prefetch retrieved (so measure prefetch recall at depth separately) — [Qdrant hybrid search tuning](https://qdrant.tech/documentation/search-tuning/hybrid-search/) [SEARCH-SUMMARY]
- Repo precedent (internal): an earlier harness bug understated retrieval because it omitted the sparse vector; new-vs-old comparisons must run the real production query path; a fixed question set is required because LLM-generated question sets change per run — repo CLAUDE.md "Measured baselines" section

### Inferences (proposed protocol)
1. Freeze the question set and labels (human gold, not AI-authored for calibration; include the 13 out-of-corpus controls and the on-topic set). Do not regenerate questions between arms.
2. Arms, each in its own collection or as extra named vector in a sandbox copy, same Qdrant version: A = current (passage_dense + passage_sparse, RRF); B = A + `context_dense` as third prefetch (sweep RRF `weights`, e.g. 1/1/w, and `k`); C = payload filters only; D (optional) = prepended-context embedding, to quantify what prepend buys versus the split design.
3. Retrieval metrics per arm: recall@1/3/10 of the labeled correct clip, MRR, nDCG@10, plus prefetch-level recall at the prefetch limit (to see whether context_dense surfaces clips the other two miss). Report bootstrap confidence intervals; with ~100 questions differences below a few points are noise.
4. Score-distribution diagnostics per arm: histograms and quantiles (p5/p25/p50/p75/p95) of top-1 score for in-corpus-correct, in-corpus-wrong, and out-of-corpus queries; AUROC of top-1 score for "correct vs not"; Kolmogorov-Smirnov distance between arm A and B top-1 distributions. Check whether the threshold-relevant quantity is the fused RRF score, a raw cosine, or the reranker score, and compare that one specifically.
5. Selective-risk view: for each arm, plot risk-coverage curve (error rate among served clips vs fraction served); the arm is better if it dominates at low risk. Then (when 299+ human labels exist) fit the LTT/Clopper-Pearson profile separately per arm and compare achievable coverage at 1% risk; a profile fitted on arm A is NOT reusable for arm B.
6. Safety checks: out-of-corpus leakage rate (target 0 served), host-voice leak rate, speaker-verified share, latency p50/p95 with the extra prefetch, and unchanged integrity-gate pass rate (hash match is over verbatim text, so should be unaffected).
7. Offline-generated context/questions must pass a review gate, and generated text must be marked as non-verbatim metadata never rendered as teacher voice (consistent with repo invariants 1, 12, 15).
8. Switch criteria agreed up front (e.g., arm improves recall@k with CI excluding zero, no worse out-of-corpus leakage, latency within budget); rollback = keep old collection and flip `FIRST_PERSON_COLLECTION` (repo mechanism).

### Gaps
- No published standard protocol specific to "re-embedding changes and calibrated thresholds" found; protocol above is synthesis, not a cited method.
- Required gold-set size for detecting an effect is not derived here; the repo's own note that n=100 is mathematically insufficient for 1% risk calibration applies to calibration, while retrieval A/B detection power was not computed.
