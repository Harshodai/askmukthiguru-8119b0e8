# How AskMukthiGuru works now—and how the editorial teaching system should work

AskMukthiGuru already has several pieces of the editor-style system you described. The main missing capability is a reliably verified, coherent **set of teachings across videos**. Adding Memgraph or another LLM alone will not produce that capability.

Your requirement is a useful editorial product: search the archive, locate relevant moments, preserve complete thoughts, remove unrelated or harmful context, order complementary evidence, keep the teachers’ words intact, and show exactly where each teaching came from. The design must preserve that whole requirement even when the first implementation step is small.

**Inspection basis:** repository source at baseline Git HEAD `41752e0c`, inspected 2026-11-01/02, plus your attached research. This is not a live production benchmark. The local stack was rebuilt and its safe flags/imports were verified; production configuration, a successful live-Qdrant teaching response, and comparative answer-quality measurements remain unverified. The full default backend suite was later run locally: 12,256 passed, 21 skipped, 3 deselected, 1 xfailed.

**Implementation update (2026-11-02):** a shared typed evidence-policy slice has now been added and wired across the legacy, context-harness, compound, and exact-cache safety paths. Compound speaker-verification and disabled-relevance gaps were also addressed. `make docker-rebuild-web` completed and the backend imported the new pipeline/policy. Focused policy regressions and the full default backend suite passed; the provider-backed live-Qdrant case was excluded pending a dedicated $0.25-capped test key. These results validate the exercised code paths, not answer-quality improvement.

## 1. What already exists in the code

### First-person requests have a real route-to-pipeline path

The first-person graph node calls `run_first_person_bridge`, and the bridge invokes `FirstPersonPipeline.execute` through `asyncio.to_thread`. This is actual request wiring, not merely a module with tests. The bridge currently requests up to three clips. Crisis, topic, serving-contract, cache, and evidence decisions surround that path.

Source: `backend/rag/nodes/first_person.py:46–65`; `backend/app/pipeline/stages/first_person_bridge.py:827–850`; `backend/services/first_person_pipeline.py:3101–3290`.

### Typed evidence already exists

`SourceSpan` and the parent/context types are not generic clip dictionaries. They already carry immutable source-span IDs, parent IDs, word coordinates, timestamps, transcript and per-span hashes, speaker roles, completeness/boundary status, rights state, topics/facets, and verification provenance. The model rejects unknown payload fields with `extra="forbid"`.

Therefore, a future `TeachingUnit` should start as an editorial view over these existing records, not a competing source-of-truth schema. Add genuinely missing policy annotations through a versioned contract after checking consumers. Do not rename IDs or write invented fields into historical points.

Source: `backend/domain/first_person_context.py:1–245`.

### Context reconstruction is already implemented

The harness can select a single span or a parent context, check speaker/rights/hash/completeness, verify citations, and reconstruct answer text from stored spans. The pipeline also contains parent-window enrichment and cross-parent antecedent stitching. Adjacent same-video/speaker citations can be merged.

That means q056/q061 are not problems with no boundary machinery. They are problems where existing structural rules and annotations may not capture the necessary meaning consistently. A grammatical sentence, a metadata flag, and a complete answer are different things.

Source: `backend/services/first_person_context_harness.py:620–739`; `backend/services/first_person_pipeline.py:2196–2363`, `3470–3575`; relevant lessons include `L-CROSS-PARENT-ANTECEDENT-STITCHING-1` and `L-CONSECUTIVE-CITATION-CLUBBING-1`.

### Memgraph is already used in two different ways

First, optional concept expansion asks the graph for one-hop neighbors, then runs an additional concept-filtered retrieval and appends new parents after the original vector candidates. This path is bounded; the implementation defaults to eight neighbors and a 1.5-second graph budget. Its source default and verified local-container setting are false.

Second, the context serving branch conditionally calls `fetch_doctrine_subgraph` and passes the resulting descriptions/relationships to QuoteWeaver—but only when `first_person_mode == "hybrid"`. That is graph context supplied to an editorial LLM path. It is not a demonstrated final checker that the answer solves the question.

The doctrine fetch returns text descriptions and adjacent relationship names with a result limit. The inspected query does not return source-span evidence IDs, rights decisions, verification state, or a claim-support ledger. Its output must not be promoted to source-certified teaching merely because it came from Memgraph. The rebuilt local service is `retrieval_only`, so this hybrid-only graph-to-QuoteWeaver path is currently inactive.

**Verified local posture after rebuild:** `IS_PRODUCTION=false`, `FIRST_PERSON_MODE=retrieval_only`, context harness/terminal/enrichment/graph expansion off, and the owner-only local-review flag on. Memgraph is running as a healthy service, but it is not acting as an LLM “brain” or final answer checker in the current first-person response path.

Source: `backend/services/first_person_graph_expansion.py:93–138`; `backend/services/first_person_pipeline.py:2310–2363`, `3639–3702`; `backend/rag/kg_expansion.py:300–337`.

### Multi-clip selection and editorial scaffolding are partly present

The optional compound-query branch retrieves a broad candidate pool, scores question parts, prefers distinct video IDs, and renders selected clips. However, it scores only the first three available clips for each part. It also becomes unavailable when the terminal context-harness posture is active.

The optional context selector accepts only retrieved span IDs. Unknown IDs are rejected; generated prose is not used as teaching. QuoteWeaver can produce bounded scaffolding in hybrid mode while formatting teaching text from stored clips and applying an assertion gate.

These are useful foundations, but they do not prove corpus-wide facet recall, balanced two-teacher coverage, or editorial set sufficiency. “Several clips can be rendered” is not the same as “the best complementary clips were found and collectively answer the question.”

Source: `backend/services/first_person_pipeline.py:3267–3278`, `5059–5248`; `backend/services/first_person_context_selector.py:1–158`; `backend/services/quote_weaver.py:1369–1511`.

### Existing safety and completeness rules are duplicated

The legacy and compound branches independently apply allowlist/blocklist, violence, and unsolicited self-harm filtering. The harness imports private standalone regexes from the pipeline. That coupling is exactly the architectural issue your research identified.

The source audit found that the context worker did not mirror the legacy/compound unsolicited-self-harm filter, and its standalone checks omitted dangling question tails. The new shared policy now applies query-context safety in the harness and rechecks the assembled window; the context standalone policy now includes the dangling-tail detector. Focused regressions and the full default backend suite now pass for the tested policy paths. The live answerability/relevance provider and cross-video editorial selector were not exercised, so these results do not certify a successful teaching answer.

Another concrete risk is the hybrid weaver adapter’s `c.get("speaker_verified", True)`. That is an unsafe missing-field default under the repository invariant, even if upstream metadata normally supplies the field. Record and test it; do not silently fix or enable anything during planning.

Source: `backend/services/first_person_pipeline.py:3487–3511`, `3681`, `4206–4228`, `5130–5147`; `backend/services/first_person_context_harness.py:275–303`.

## 2. What the system does not yet prove

It does not yet prove that a broad request such as “What is love?” finds the needed complementary moments from the relevant indexed videos. It does not prove that the selected clips cover the question’s facets rather than repeat one broad theme. It does not prove that contradictions, contextual qualifiers, event dependencies, and host turns are handled consistently across every route.

The harness can return `context_sufficiency="sufficient"` after deterministic gates. That field is useful structural output, but it is not an independently calibrated semantic judgment over an editorial set spanning several videos. The current answerability call in the compound branch receives the question, not a claim-to-evidence proof for the final selected set.

Nor does a source hash prove rights, speaker identity, or timestamp accuracy. The per-span hash proves text integrity relative to the recorded artifact. Video playback and source-coordinate replay, rights-register joins, speaker evidence, and editorial review remain separate checks.

Source: `backend/services/first_person_context_harness.py:705–735`; `backend/services/first_person_pipeline.py:5163–5196`; `backend/domain/first_person_context.py:9–18`.

## 3. How “What is love?” should work after the full design

### Step 1: understand this question without adding unsupported requirements

The planner identifies a definition request with no single teacher named. It may consider definition, connection, inner experience, and distinction from attachment as candidate facets. These are retrieval hypotheses—not assertions that the gurus taught those facets, and not a requirement to fill every section.

If the user asks “What did Preethaji say about love?”, Krishnaji cannot be substituted to fill a gap. If both teachers are requested but verified evidence exists for only one, report that limitation rather than fabricate balance.

### Step 2: search the eligible indexed archive

Qdrant retrieves a bounded pool of candidate moments across the relevant videos. The system searches the index, not raw media at request time. It must report the corpus/build searched, not falsely claim every raw video was exhaustively read for this request.

Candidate expansion can use lexical terms, semantic similarity, approved concept tags, and optional graph neighbors. Each route still enforces source eligibility. No graph hit, backup export, or OKF summary gets to bypass the evidence gate.

### Step 3: recover complete source thoughts

Each candidate resolves to its stored `SourceSpan` and parent/continuation context. The smallest valid context window is added to resolve “this,” “he or she,” a list continuation, or an unfinished rhetorical question. Added words must be stored source words, not LLM-completed sentences.

If necessary context is unavailable, belongs to an unverified host, exceeds the allowed window, or fails rights/integrity checks, exclude the candidate. Do not make it grammatical by rewriting the teacher.

### Step 4: apply candidate-level judgment

The semantic evaluator considers the query, exact unit text, necessary context, and provenance-backed graph facts. It returns structured dimensions such as directness, supported facets, event dependence, safety context, and uncertainty.

Code—not the LLM’s Boolean answer—checks rights, speaker verification, source hashes, coordinates, permitted graph IDs, and policy versions. Benign relationship questions must not receive unsolicited self-harm content. Explicit self-harm questions still follow the independently approved safety route; matching the topic does not automatically permit a harmful clip.

### Step 5: select a coherent set

The selector should prefer a direct definition, then genuinely complementary evidence where available. It should reject near-duplicates and avoid manufacturing a connection between two clips that merely share a word.

Diversity cannot override directness or safety. Include both gurus when the request and evidence support it, but do not impose a two-teacher quota on every answer. Respect differences between perspectives instead of merging them into one attributed voice.

### Step 6: verify the set, not just its members

Ask whether the chosen set answers the actual question, contains unresolved dependencies, leaves material facets unsupported, or creates a misleading contrast. Return `supported`, `partial`, `conflicted`, or `insufficient` with reasons.

A second LLM call can contribute to that assessment, but two calls are not independent certification. Calibrate against human labels and held-out examples. Unanswerability evaluation must measure both unsafe over-answering and unnecessary refusal.[7] [8]

### Step 7: render evidence in a permissible mode

The default production first-person mode remains `retrieval_only`: exact source excerpts and attribution, with directness/grouping in metadata or UI—not an invented guru paragraph.

The longer-term editorial mode may add short, visibly labelled synthesis outside source excerpts. This requires a **separate product and serving-contract decision**. It is not permitted simply because a field is named `editorial_synthesis`; the inspected production guard rejects hybrid first-person mode.

The same approved set can produce an edit decision list with chapter, source ID, in/out coordinates, speaker, selection reason, and explicit discontinuities. Rendering a video is downstream work. Republishing permission must be separately checked; permission to retrieve or display clips is not automatically permission to publish a compilation.

Source for the current production boundary: `backend/services/first_person_release.py:84–129`.

## 4. How others solve parts of this problem

### VideoRAG: archive indexing and cross-video retrieval

VideoRAG combines graph-driven textual knowledge with multimodal retrieval. Its LongerVideos benchmark covers cross-video understanding, and the repository exposes both algorithm code and a desktop application. The repository also notes that generation scores can fluctuate.[1]

This supports offline archive processing and retrieval—not feeding thousands of videos into one request. It does not establish exact guru attribution, licensed compilation rights, clinical safety, or verbatim quote reliability for this project. Borrow the architecture and test protocol; do not replace this repository wholesale.

### TwelveLabs: locating moments in an indexed video collection

The documented search API supports visual, audio, and transcription search, with lexical/semantic transcription matching. Results contain video ID, start/end seconds, and rank. A search request operates within one index.[2]

This is a real commercial example of “find the moment.” It is not evidence that ranked moments automatically form a complete teaching answer. Treat it as a capability reference; adopting a commercial service would require privacy, cost, rights, and repository-policy review.

### Descript: editable, transcript-linked clip creation

Descript’s documented Create clips feature scans a composition for self-contained short cuts, accepts topic/goal criteria, and creates separate editable compositions. The documented workflow includes human review and editing.[3]

This demonstrates practical text-linked clipping. It does not claim exhaustive archive-wide question answering or doctrinal fidelity. Clip engagement and answer sufficiency are different optimization objectives.

### EditDuet: assembly and iterative critique

EditDuet uses an Editor and Critic over a non-linear timeline. The reported work specifically focuses on producing B-roll over an existing A-roll sequence, not reconstructing source-faithful spiritual explanations from thousands of talks.[4]

The transferable idea is a reviewable edit plan and iterative correction. The non-transferable assumption is that a critic’s satisfaction proves evidence truth or rights clearance.

### GraphRAG examples: relationships after retrieval

Qdrant’s official example stores matching chunk IDs in the vector and graph stores, retrieves vector seeds, and then fetches nearby relationships. Its final prompt uses graph context to generate an answer.[5]

That validates composition of retrieval and relationship expansion. The tutorial is not a production blueprint for this application: it does not supply the required rights-register enforcement, speaker provenance, source-word replay, or calibrated abstention. Microsoft’s GraphRAG documentation similarly describes specialized search modes and the need for responsible evaluation.[6]

## 5. What Phase 0–1 changes—and what it cannot change

Phase 0 makes existing behavior inspectable: a bounded failure taxonomy, route-to-policy inventory, named regression fixtures, and separate counts for genuine evidence rejection versus provider timeout, malformed output, budget exhaustion, or unavailable infrastructure. The source audit and implementation review are complete for this slice. After the user authorized validation, the focused suite passed 209 tests, with the live-Qdrant integration intentionally deselected; the full repository suite was not run.

The initial Phase 1 code slice adds an internal frozen `EvidenceDecision` and shared standalone/query-context policy, routes safety through the legacy, context-harness, compound, and exact-cache paths, and pins the new policy and answer-length/speaker settings in the cache fingerprint. It also closes the compound speaker-verification and relevance-kill-switch gaps. It does **not** yet unify every integrity, rights, speaker, or answerability gate behind one candidate adapter, nor does it add a multi-video evidence-set selector. It reuses `SourceSpan`, the existing harness and crisis rails, and the current cache contract; no graph schema, model, corpus, or public response format was introduced.

**This is necessary root architecture, but not sufficient semantic repair.** Renaming regexes inside an engine does not solve discourse understanding, contextual harm, or multi-video sufficiency. Those require source-backed annotations, trained/calibrated semantic judgment, human labels, and editorial set selection in the later phases.

The full research-backed design stays in the plan. The narrower starting scope limits implementation risk; it does not remove the product requirement.

## 6. Production-oriented does not mean deploy now

A production-oriented design needs safe failure modes, not just more filters. Optional graph failure may preserve already valid primary evidence. Missing rights, unverifiable speaker claims, hash mismatch, and unresolved required dependencies must not become successful evidence. Provider failure must be measured separately from an honestly unanswerable question.

Policy changes must invalidate policy-dependent exact cache entries without deleting unrelated Redis namespaces. New payload fields must round-trip through actual consumers. Graph/vector writes need reconciliation because they are not one transaction. Revocation must reach first-person retrieval, general retrieval, media, derived artifacts, and affected caches.

Cleanup remains an independent lifecycle process: inventory, identify authoritative copies, map superseded IDs, preserve regression and audit artifacts, test restores, then obtain scoped deletion approval. Existing staging, compiled OKF, source media, snapshots, and audit folders are not disposable because they are old or large.

Implementation changes were made locally on 2026-11-02. Python 3.12 syntax compilation, the regex safety check, and `git diff --check` passed; the corpus publication guard was not run because it requires explicit corpus/audit/output paths. The focused regression suite passed 209 tests, with one live-Qdrant integration deselected. After the no-data-loss frontend/backend rebuild, one cold/incognito local chat sample reached the first-person route but abstained with zero citations because the fail-closed OpenRouter budget guard made answerability indeterminate; the candidates were discarded and reranking/scoring skipped. Read-only metadata showed the legacy collection was green with 1,801 points, which does not prove a relevant love passage exists. No budget counter was reset, no limit or gate was changed, and no Qdrant write, alias change, deployment, or public-release action occurred. No pre-change response exists for an A/B comparison, and no “best answer” quality claim is supported. Full findings are in the [local validation report](first_person_local_validation_2026-11-02.md).

## References

[1]: https://github.com/HKUDS/VideoRAG "VideoRAG repository and cross-video benchmark"
[2]: https://docs.twelvelabs.io/docs/guides/search "TwelveLabs video search guide"
[3]: https://help.descript.com/repurpose/create-clips-from-your-content "Descript Create Clips documentation"
[4]: https://arxiv.org/html/2509.10761v1 "EditDuet video editing research"
[5]: https://qdrant.tech/documentation/examples/graphrag-qdrant-neo4j/ "Qdrant GraphRAG implementation example"
[6]: https://microsoft.github.io/graphrag/ "Microsoft GraphRAG documentation"
[7]: https://aclanthology.org/2025.acl-long.415/ "UAEval4RAG unanswerability evaluation"
[8]: https://aclanthology.org/2024.eacl-demo.16/ "RAGAS retrieval augmented generation evaluation"
