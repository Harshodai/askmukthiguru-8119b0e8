# Segmenting spoken-discourse transcripts into self-contained clips without editing the words

Method note: WebFetch could not resolve any host in this session (getaddrinfo ENOTFOUND for arxiv.org, aclanthology.org, ar5iv). Every finding below therefore comes from WebSearch result summaries, not from reading the full papers. Numbers are copied from those summaries and marked UNVERIFIED where the summary itself flagged them as third-party or I could not see the paper table. A proxy status check was denied by the sandbox and not worked around.

## 1. Discourse/topic segmentation for spoken transcripts, and reported accuracy

### Takeaway
Topic segmentation (TextTiling and its neural successors) finds coarse topic shifts, typically minutes long, and is a poor fit for sentence-level "does this clip open without a dangling referent" decisions. Reported accuracies are dataset-dependent and often weak for the classic unsupervised method, so topic boundaries are a candidate source for clip starts, not a guarantee of self-containedness.

### Cited Findings
- TextTiling (Hearst, ACL 1994) was evaluated against human judgments of major subtopic boundaries on thirteen lengthy texts, not with Pk/WindowDiff. — [Hearst 1994 via search summary](https://arxiv.org/pdf/cmp-lg/9406037)
- Pk (Beeferman et al.) uses a sliding window of size k (half the mean reference segment size). Pevzner and Hearst (Computational Linguistics 28(1), 2002) criticize it: false negatives penalized more than false positives, near-misses over-penalized, sensitivity to segment-size distribution. WindowDiff compares boundary counts inside the window and was proposed to fix this. The Pk description comes from a 2016 secondary paper, not the original. — [Pevzner & Hearst 2002 (ACL Anthology)](https://aclanthology.org/J02-1002/); [secondary summary](https://arxiv.org/pdf/1610.09226)
- On one novel-chapter dataset (Chapter Captor) TextTiling scored Pk 0.587 and WindowDiff 0.714, worse than an equidistant-breaks baseline (0.482 / 0.492); lower is better. This is one atypical dataset, not general TextTiling accuracy. — [Chapter Captor](https://arxiv.org/pdf/2011.04163)
- Koshorek et al. (NAACL 2018) recast segmentation as supervised sentence-level labeling ("does this sentence end a segment") and release Wiki-727k (727,746 Wikipedia articles with table-of-contents boundaries). Their Table 2 reports Pk 22.13 on Wiki-727k (random 53.09); human 14.97 on Wiki-50; GraphSeg 63.56 on Wiki-50. Numbers come from a search summary of the table; lower is better. — [Koshorek et al. 2018](https://aclanthology.org/N18-2075/); [arXiv PDF](https://arxiv.org/pdf/1803.09337)
- Third-party aggregator lists TextTiling Pk 31.7 on Choi's (3-11) and 38.9 on Wiki-50; the aggregator itself is unchecked against original papers. UNVERIFIED. — [wizwand listing](https://www.wizwand.com/paper/68fa5fd21e209131ce9ebf91)
- Spoken-meeting segmentation: Banerjee and Rudnicky adapted TextTiling with speaker-participation overlap and report precision 0.85 / recall 0.59 on unseen meetings. — [Interspeech 2006](https://www.isca-archive.org/interspeech_2006/banerjee06_interspeech.html)
- ASR noise: slides citing Hsueh and Moore report segmentation systems were not significantly worse on ASR output (WER 39.1%) than on reference transcripts; the same slides note Malioutov et al. found method rankings can differ between manual and ASR transcripts. Secondary source (slides); original paper not read. UNVERIFIED. — [Galuščáková slides](https://www.slideshare.net/slideshow/i3-galuscakova/25236216)
- Unsupervised BERT-embedding meeting segmentation (BertSeg, a TextTiling variant using utterance embeddings) and a hierarchical large-transcript method (TreeSeg) exist; no accuracy numbers extracted. — [arXiv 2106.12978](https://arxiv.org/pdf/2106.12978); [TreeSeg](https://arxiv.org/html/2407.12028v1)
- Spotify's PODTILE: fine-tuned encoder-decoder that jointly generates chapter boundaries and titles for podcast transcripts averaging about 16,000 tokens; inputs get episode title, description and previous chapter titles as context; reported 11% ROUGE improvement over the strongest baseline in intrinsic evaluation; chapter titles help sparse retrieval. No Pk/F1 seen. — [PODTILE, arXiv 2410.16148](https://arxiv.org/abs/2410.16148)
- A 2025 thesis compares TextTiling, LLM semantic-similarity thresholding and a BIO-label transformer on manually annotated podcast transcripts (F1, Pk, WindowDiff) and reports deep representations beat the classical baseline; numbers not extracted. — [Webis thesis](https://downloads.webis.de/theses/papers/chaitanya-valaboju_2025.pdf)

### Inferences
- Topic-level segmenters output boundaries at minute-scale granularity; our need is clip-level (sub-minute) starts, so they are most useful as a coarse constraint (do not cross a topic boundary when extending backward) rather than the boundary generator.
- Because Whisper already supplies sentence timestamps, the supervised "sentence ends segment?" formulation (Koshorek) maps directly onto our unit of choice: a binary decision per sentence boundary. It only ever selects boundaries, which satisfies the no-edit rule.
- Pk/WindowDiff measure agreement with human topic boundaries and would not detect an orphan "this". They are the wrong primary metric for our goal.

### Gaps
- No TextTiling/neural segmenter accuracy on spoken religious/philosophical talks or on Whisper output specifically was found.
- Exact Pk figures for TextTiling on spoken lectures (Malioutov and Barzilay) not retrieved.
- PODTILE boundary-level metrics (not ROUGE) not seen.

## 2. Anaphora/coreference-aware chunking: detecting unresolved openers and extending backward

### Takeaway
Pronoun/demonstrative-at-chunk-start detection is straightforward with heuristics, and coreference models can confirm whether the antecedent lies outside the clip. The published RAG work I found mostly resolves or rewrites pronouns (which we cannot do), but one chunk-quality metric counts entity-pronoun pairs split across a boundary, which is exactly a boundary-only measure.

### Cited Findings
- "References Completeness" (RC) in the Adaptive Chunking paper (LREC 2026) counts how often an entity and its pronoun fall on opposite sides of a chunk boundary, using the Maverick coreference model; English only. Other metrics there: Intrachunk Cohesion, Document Contextual Coherence, Block Integrity, Size Compliance. RC's exact formula was not seen; description is from a search summary. Answer correctness reported rising to 72% from 62-64% with their chunking selection. — [Adaptive Chunking, arXiv 2603.25333](https://arxiv.org/abs/2603.25333); [LREC page](https://aclanthology.org/2026.lrec-1.903/)
- CLAP resolves pronouns to antecedents inside each chunk and generates pseudo-queries from the resolved chunk; reports up to 20.68 absolute nDCG@10 gain (BEIR/MS MARCO, mostly sparse retrievers). It rewrites text, so the method is not usable as-is; only the motivation transfers. — [CLAP, arXiv 2508.06941](https://arxiv.org/pdf/2508.06941)
- Another 2025 study reports coreference resolution helps RAG, with smaller models gaining more (details not read). — [arXiv 2507.07847](https://arxiv.org/html/2507.07847v1); [Jang et al., ACL SRW 2025](https://preview.aclanthology.org/setup/2025.acl-srw.27)
- Maverick (ACL 2024) is a compact coreference model (about 500M parameters) claiming state-of-the-art CoNLL-2012 with far less memory and 170x faster inference than prior SOTA; an aggregator lists CoNLL-2012 F1 83.6 for one variant, marked unverified. — [Maverick, ACL 2024](https://aclanthology.org/2024.acl-long.722); [aggregator](https://sotaverified.org/papers/2407-21489)
- Decontextualization (Choi et al., TACL 2021) names coreference resolution, global scoping and bridging anaphora among the phenomena that make a sentence non-stand-alone, and notes some sentences need title/subtitle information. — [Choi et al. 2021](https://aclanthology.org/2021.tacl-1.27)
- Demonstrative pronouns ("this", "that") are more often tied to discourse-level antecedents (clauses, whole sentences, larger fragments) than definite descriptions are, which entity-centric coreference models handle poorly. — [Artstein & Poesio](https://publishup.uni-potsdam.de/files/947/artstein_poesio.pdf); [Recasens, AnCora study](https://dspace.ut.ee/bitstream/10062/7367/1/Recasens.pdf)

### Inferences
- For sentence-initial "Yes, this ..." / "These are ...", the antecedent is usually an event, clause or whole prior sentence (discourse deixis), so a standard NP coreference model will often not link it. A lexical rule (sentence-initial this/these/that/those/it/they/such, optionally after "yes/so/and/but/now") is probably the more reliable detector, with a coreference model as a secondary check.
- Boundary-only repair: if the first sentence has an orphan opener, move the start back one sentence (repeat up to N times, stop at topic/speaker boundary or length cap); if no clean start exists within the cap, skip the clip. This preserves verbatim words by construction.
- Moving a start back can introduce a new orphan opener in the newly included sentence; the check must loop.
- A host/interviewer question immediately before the clip is a hazard: extending backward may pull in non-teacher speech (relevant to the project's speaker allowlist).

### Gaps
- No source found giving the typical sentence distance between a sentence-initial "this" and its antecedent in spoken discourse.
- Did not find any paper that does boundary-only, antecedent-preserving clip extension on audio; the approach above is my design inference.
- Coreference model accuracy on ASR/spoken text (disfluencies, no punctuation) not found.

## 3. Complete-thought / proposition-level chunking: rewrite or choose boundaries?

### Takeaway
Dense X Retrieval's propositions are produced by rewriting (decontextualizing), so they cannot be used for the served text, though the paper's granularity findings still guide what unit to index. Boundary-only alternatives are semantic chunking and sentence-level boundary classifiers, plus index-side context that is never shown as quote.

### Cited Findings
- Dense X Retrieval (Chen et al., EMNLP 2024) defines propositions as atomic, distinct-factoid, self-contained expressions; indexing by propositions significantly outperforms passages in retrieval, and for QA under a fixed word budget the largest gain over passages appears around 100-200 words (about 10 propositions, 5 sentences or 2 passages). — [arXiv 2312.06648](https://arxiv.org/abs/2312.06648); [ACL Anthology](https://preview.aclanthology.org/setup/2024.emnlp-main.845)
- Propositions are self-contained by rewriting, e.g. resolving "the tower" to "Pisa Tower" and pronouns to entity names. — [Dense X, HTML](https://arxiv.org/html/2312.06648v3) (as summarized in search results)
- Propositionizer: a secondary community write-up says GPT-4 produced paragraph-to-proposition pairs (over 40,000) used to fine-tune Flan-T5-Large. UNVERIFIED; paper's own three principles not confirmed. — [community write-up](https://scrapbox.io/nishio/Dense_X_Retrieval:_What_Retrieval_Granularity_Should_We_Use%3F)
- Decontextualization is likewise a rewriting task (edits to make a sentence stand alone, trained on Wikipedia). — [Choi et al. 2021](https://aclanthology.org/2021.tacl-1.27)
- Contextual Retrieval (Anthropic): prepending a short generated context (secondary sources: 50-100 tokens) to each chunk before embedding/BM25 cut top-20 retrieval failures by 35% (embeddings only: 5.7% to 3.7%), 49% (embeddings plus BM25: 5.7% to 2.9%), and 67% with reranking; internal benchmarks, not independent. The context is used for indexing, not shown as the passage. — [Anthropic](https://anthropic.com/news/contextual-retrieval)
- PODTILE feeds neighbouring chapter titles as input context while only outputting boundaries and titles. — [PODTILE](https://arxiv.org/abs/2410.16148)

### Inferences
- Index/serve split: it is compatible with the verbatim rule to attach LLM-generated context or questions to a clip for retrieval only (Anthropic style), while the served audio/transcript remains the unedited span. This is an inference about design, and it interacts with the project's existing rule that offline LLM output needs a review gate before any Qdrant write.
- An LLM can be used as a boundary judge (output: "does this clip stand alone?" yes/no, or the index of the best start sentence) rather than a rewriter, consistent with the project's ranking-selector-only rule.
- "Complete thought" for sentence-level start/end selection can be framed as two checks: start has no unresolved referent or dependent connective; end is not on a trailing conjunction or mid-clause.

### Gaps
- Dense X's three proposition principles and Propositionizer details not confirmed from the paper.
- No paper found that evaluates a boundary-only (non-rewriting) variant of proposition chunking.
- Semantic-chunking (embedding-similarity splitting) literature not searched in detail; no accuracy figure collected.

## 4. Clip-length tradeoffs for spoken answers

### Takeaway
I found no controlled evidence on ideal length of a spoken verbatim clip for comprehension; retrieval literature gives a 100-200 word sweet spot for text units, and marketing sources give conflicting clip-length advice. Length target must be set empirically on this product.

### Cited Findings
- Retrieval: Dense X finds the largest gain of fine-grained units over passages at roughly 100-200 words of retrieved context. This is for text QA with a fixed word budget, not human listening. — [arXiv 2312.06648](https://arxiv.org/abs/2312.06648)
- Search for controlled clip-length comprehension studies returned none. Practitioner guidance: one source says 30-90 seconds provides enough context while sustaining attention; another says 5-15 minutes; neither cites research. — [Rizzle blog](https://rizzle.com/blog/post/what-is-the-ideal-length-of-a-clip-and-why-is-it-important); [Swell AI blog](https://www.swellai.com/blog/how-to-clip-a-podcast-segment)
- Survey data on whole educational podcasts (medical residents) found preferences for 5-15 or 15-30 minute episodes; relates to episodes, not clips. — [PMC5476404](https://pmc.ncbi.nlm.nih.gov/articles/PMC5476404)
- Project invariants already set a rolling 18-25 s target for a diagnosis-plus-solution window and a 15-word minimum (from the repo's CLAUDE.md, internal, not an external source).

### Inferences
- At typical speaking rates (assumption, not sourced: around 120-160 words per minute) the 100-200 word range corresponds to roughly 45-90 s, which overlaps the practitioner 30-90 s guidance; treat as a hypothesis to test, not a finding.
- Any length cap interacts with the backward-extension repair: a cap that is too tight forces more skips. Track skip rate per cap.

### Gaps
- No peer-reviewed evidence on comprehension or satisfaction versus spoken-clip length; needs an in-product A/B or rater study.

## 5. How to measure clip self-containedness

### Takeaway
Use cheap deterministic proxies at scale (orphan-opener rate, split-reference rate) and a small human "stands alone" rating to validate them. Topic-segmentation metrics (Pk, WindowDiff) are not appropriate for this goal.

### Cited Findings
- A boundary-split-reference metric already exists: References Completeness (entity-pronoun pairs separated by a chunk boundary, via Maverick). — [arXiv 2603.25333](https://arxiv.org/abs/2603.25333)
- Decontextualization defines a human-annotation protocol for whether a sentence can be understood alone, and a follow-up paper reuses it with labels yes / no / title. — [Choi et al. 2021](https://aclanthology.org/2021.tacl-1.27); [Learning to Reject, arXiv 2301.09044](https://arxiv.org/pdf/2301.09044)
- Pk and WindowDiff measure topic-boundary agreement and have known biases. — [Pevzner & Hearst 2002](https://aclanthology.org/J02-1002/)

### Inferences
Proposed metric set (my design, not from a source):
1. Orphan-opener rate: share of served clips whose first word(s), after stripping fillers/connectives ("yes", "so", "and", "now", "well"), is a demonstrative or personal pronoun without an in-clip antecedent. Target near zero after repair; measure before/after on the live collection.
2. Dangling-connective rate: clips starting with "but/so/because/which" or ending on a trailing conjunction.
3. Cross-boundary reference rate: coreference-linked pairs where the mention is in the clip and the antecedent is outside (RC-style); compute only for entity mentions, and rely on rule 1 for discourse deixis.
4. Human "stands alone" rating (yes / needs preceding sentence / no) on a stratified sample, with at least two raters and agreement reported; use it to estimate precision and recall of the automatic detector, since the detector is itself a classifier. Use an unrepaired-clip control group to measure the gain from repair.
5. Repair side-effects: skip rate, mean clip length change, host-speech leak rate after extending backward.
6. Rater sample size is an open design choice; no sourced guidance found.

### Gaps
- No published benchmark labels "clip stands alone" for spoken talks; one would have to be created.
- No source for the expected base rate of orphan openers in ASR sentence-segmented talks; must be measured on the project's own data.
