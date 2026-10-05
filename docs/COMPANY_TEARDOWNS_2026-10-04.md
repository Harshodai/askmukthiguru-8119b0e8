# Company Teardowns — Curated-Spiritual Retrieval Stacks (2026-10-04)

Companion to `docs/OKF_WIRING_RESEARCH_2026-10-04.md` (fills its missing company-teardown section).
Method: public sources only (engineering blogs, docs, reputable press). Each company marked **[S]** (sourced fact + URL) vs **[I]** (inference, labelled). No internals guessed as fact.
Our stack for reference: FP verbatim clips (~2,500) + 431 OKF entries + 89k Qdrant corpus + doctrine lexicon; hooks in `backend/rag/nodes/retrieval.py`, `backend/services/memory/okf_store.py`, `backend/app/config.py:1017`, `backend/services/transcript_verbatim.py`, `scripts/eval/run_ragas_eval.py`.

---

## 1. Delphi.ai — creator mind-clones

- **[S]** Retrieve-from: creator-supplied corpus (books, articles, podcasts, videos, courses, docs); clone is only as good as the archive handed in (https://www.delphi.ai/; https://www.assemblyai.com/customers/delphi-customer-story).
- **[S]** Ingest: AssemblyAI transcription + speaker diarization + timestamps + Audio Intelligence; 16× language expansion, 50% faster clone training (AssemblyAI customer story, CTO Sam Spelsberg).
- **[S]** Architecture (Series A post): "Digital Mind Architecture (DMA1)": temporally indexed self-adaptive knowledge graph + serverless AI-first search engine + distributed agent mesh for single-shot high-precision retrieval (https://www.delphi.ai/blog/delphi-raises-16m-series-a-from-sequoia).
- **[S]** Grounding: "responds from your source material, with citations to show where answers come from" (https://www.delphi.ai/); "precise citation feature" linking answers to the **exact second** in referenced YouTube/podcast content (AssemblyAI story, Spelsberg quote).
- **[S]** Curation loop: creator-side — Interview Mode grows the mind by Q&A when no archive exists; Mind Score measures depth-per-topic and prompts creators to add angles (interviews, essays, contrarian takes) (https://www.delphi.ai/blog/interview-mode; https://docs.delphi.ai/advanced/mind-score.md).
- **STEAL:** exact-second source anchoring (timestamp-level citations). Our FP clips already carry transcript offsets — surfacing clip timestamp/ID in the claim→source ledger (R3) is the same pattern at zero architecture cost. Hook: `okf_store.py:274-285` + ledger from R3.
- **Note:** Delphi cites openly; our FP never-cites invariant is deliberately stricter (verbatim as context-only). Keep the invariant; steal the *span-precision*, not the surfacing policy.

## 2. Hallow (+ Magisterium AI engine)

- **[S]** Retrieve-from: 10,000+ audio sessions (prayer, Bible, sleep, chant) + native AI chat trained on Scripture, Catechism, saint writings, papal encyclicals (https://hallow.com/blog/hallow-ai; Play Store listing `app.hallow.android`).
- **[S]** Engine partnership: Hallow's chat feature is powered by Magisterium AI ("it is our engine that provides the faithful answer" — https://www.magisterium.com/blog/church-s-mission-age-ai); English app rolling its own Hallow AI, non-English still Magisterium (https://help.hallow.com/en/articles/13601993-hallow-ai-faq).
- **[S]** Corpus: 23,000+ magisterial docs + 2,300 scholarly works; 33,136 searchable docs; sources mode Auto vs Magisterial-only filter (https://www.magisterium.com/about/why-magisterium-ai; /about/documents).
- **[S]** Grounding: every significant answer carries citations often linked to the **paragraph** in the source doc; "Never take an AI's word on faith alone" (Magisterium why-page). Hallow: references visible in AI responses; AI-labelled tags (https://hallow.com/blog/hallow-ai).
- **[S]** Curation loop: content developed by theology guides, reviewed by senior Church leaders (PhDs, bishops); user-facing inaccurate-answer **report** link feeds back into accuracy work (Play Store listing; Hallow Magisterium FAQ).
- **[S]** Scope guardrail: Hallow AI "cannot provide spiritual direction, hear confessions or write prayers"; Magisterium "not meant for spiritual or moral direction" — full-screen disclaimer, redirect to priests (Hallow AI page + FAQ).
- **STEAL (top-3, #1):** Magisterial/Auto source-mode toggle = our teacher-routing precedent generalized. Add an answer-mode flag (curated-only vs full-corpus) with Magisterial-style filtering by source tier (OKF/FP vs 89k). Maps to R2 cascade floors; hook: `retrieval.py:52-80` + `_okf_match` teacher filter.
- **STEAL:** one-tap inaccurate-answer reporting wired to the curation queue. Cheap R4 addition: log claim→span + user flag into compiler review input.

## 3. AskYourGuide.ai — multi-guru WhatsApp bots

- **[S]** Retrieve-from: per-guru corpora (discourses, books) for 2 B2B spiritual leaders (2.5M+ combined followers); consumer side Sanatan Sangam app, 50+ live temple streams, 11-language support (https://askyourguide.ai/).
- **[S]** Features: bilingual (Hindi/English) AI chatbots + voicebots, AI Guru Voice clones for personalized blessings, video avatars, multilingual outreach via same engine (site).
- **[I]** Grounding: no public citation/verification mechanism found — marketing-led claims ("authentic digital clone"), grant-application stage (pre-seed, seeking seed). Treat voice/idiom fidelity as unverified.
- **REJECT (top-2, #1):** guru-voice cloning + first-person divine voice without source anchoring. GitaGPT post-mortems (§6) show exactly where ungrounded deity-voice leads; our FP never-cites + paraphrase-gate stance is the opposite and must hold. Revisit only with R1-grade verification + explicit consent boundary.
- **STEAL (with caution):** bilingual Hindi/English voicebot delivery as a *presentation* layer on top of already-grounded text (our translation-timeout/fail-open invariant stays; never let voice paraphrase drift from the verified text).

## 4. Perplexity AI — answer engine

- **[S]** Pipeline (official): understand question → live web search → compile insights → numbered inline citations per claim (https://www.perplexity.ai/help-center/en/articles/10352895-how-does-perplexity-work.html).
- **[S]** Pro Search: separates planning from execution — plan steps, per-step queries executed sequentially with prior results passed forward, grouped/filtered docs → LLM synthesis; hover-over-citation snippets (https://www.langchain.com/breakoutagents/perplexity).
- **[S]** Infra: Vespa.ai powers hybrid retrieval — chunk-level spans (not whole docs) fed to LLM; lexical+vector+metadata fusion, cross-encoder late stages, real-time indexing (https://vespa.ai/perplexity).
- **[S]** Citation volume: ~21.87 citations/response, 2.8× ChatGPT; retrieval fires on every query; strongest freshness weighting (Qwairy Q3 2025 via https://www.agentpatterns.ai/geo/how-ai-engines-cite).
- **[S]** Counter-signal: GEO-16 audit found Perplexity citing lower-quality pages (mean G 0.300, 45% citation rate vs Brave 0.727/78%) — volume ≠ quality (https://arxiv.org/html/2509.10762v1).
- **STEAL (top-3, #2):** chunk-level spans as the retrieval unit (only the relevant text span reaches the LLM). Our Qdrant dense already returns chunks; enforce span-trimming before fusion instead of passing whole chunks — precision + context-cost win. Hook: dense-search post step in `retrieval.py`.
- **REJECT (top-2, #2):** freshness-weighted ranking as default. Perplexity's recency bias + GEO-16 quality finding is anti-doctrine: our curated teachings must rank by verification tier and teacher-match, never by recency. Reject time-decay scoring on OKF/FP layers (relevant only to news-like content we don't serve).

## 5. Sri Mandir / AppsForBharat (+ SuperAstro)

- **[S]** Corpus: devotional content platform — 5,000+ ad-free aartis/mantras/bhajans/chalisas + Hindu literature, panchang, 1,000+ temple puja/chadhava network; 30M+ users, 4.5★ (https://appsforbharat.com/; https://srimandir.com/my-kundli/about; Series C ₹175Cr Jun 2025 — Business Standard).
- **[S]** AI surface: SuperAstro AI astrology chat — personalized Q&A grounded in user kundali (birth date/time/place → Lahiri ayanamsa chart), panchang; subscription chat at ₹1 entry (https://superastro.ai/; Play Store `com.afb.superastro`).
- **[S]** Grounding pattern worth noting (adjacent best-in-class, Supastro): compute-then-constrain — full ephemeris-computed chart (NASA JPL, D1–D60, Shadbala, 5-level Vimshottari) BEFORE the LLM speaks; agents debate and report uncertainty when irreconcilable (https://supastro.com/how-it-works; https://supastro.com/ai-astrologer).
- **[I]** Sri Mandir's own faith-Q&A grounding internals are not public; only the deterministic-calculator layer (dosha/nakshatra finders) is verifiable surface.
- **STEAL (top-3, #3):** compute-then-constrain. Our analogue: deterministic layers (lexicon normalize → FP exact-match → OKF teacher filter → quote gate) must resolve BEFORE any generative call, and the generator is constrained to their outputs. This is R2's cascade stated as an ordering invariant. Hooks: `retrieval.py` utils import (ll.35-48), `okf_store.py:168,218`, `config.py:1017`.

## 6. GitaGPT-style apps — post-mortem (what failed)

- **[S]** Builds: ≥5 GPT-3-powered Gita chatbots Jan–Mar 2023 (Vineet's GitaGPT, Garg/Ved Vyas Foundation's bhagavadgita.ai, Sharma's, Sahu's), thin wrappers with no guardrails (https://restofworld.org/2023/chatgpt-religious-chatbots-india-gitagpt-krishna; https://www.thequint.com/explainers/chatgpt-gitagpt-bhagavad-gita-chatbot-india-violence).
- **[S]** Failures: bots condoned killing as dharma-duty; produced casteist/misogynist outputs; praised Modi / dismissed Rahul Gandhi as incompetent — political leakage from base-model priors (CBC 2023-07-06; Rest of World 2023-05-09).
- **[S]** Root cause (expert-quoted): "not trained in a conventional way… retain the generalisation from open AI models… unless extremely diligent about guardrails" (Quint); no AI feedback system; disclaimers ("may not be factually correct") substituted for grounding (CBC; Quint).
- **[S]** Later correction signal: Ved Vyas Foundation's current GitaGPT ships with 20+ scholar commentaries, 5-msg/day cap, and "AI can make mistakes. Verify responses and consult a guru" (https://bhagavadgita.com/gitagpt).
- **Lesson (validates R1+R5):** disclaimers don't ground; only retrieval constraints + eval slices do. Our golden-25 needs the adversarial slice these bots never had (dharma-duty violence probe, political-figure probe, out-of-corpus probe). Hook: `scripts/eval/run_ragas_eval.py` + abstention slice (R5).

## 7. ISKCON srimadgita.com — approved-content badge model

- **[S]** Corpus: complete 700 verses, 18 chapters; per-verse Sanskrit + transliteration + translation + commentary + Quick Answer + self-inquiry questions + linked teachings (e.g. https://www.srimadgita.com/verse/chapter-2-verse-48).
- **[S]** Badge: "ISKCON Approved Content… verified by ISKCON scholars and Sanskrit experts"; BBT-sourced; 75,000+ users, 4.8/5 (https://www.srimadgita.com/official-bhagavad-gita-app).
- **[S]** AI posture: "AI guidance grounded in this verse," offline-first verse DB, per-page app CTA funnels each doctrinal page.
- **[I]** Approval process itself (reviewer roster, cadence, versioning) is not public — badge is a trust claim, not an auditable pipeline.
- **STEAL:** per-answer provenance badge with tier + verse/span pointer ("OKF-verified · FP clip · teacher: X") — the UX translation of our claim→source ledger (R3). Cheap, high trust-per-line.
- **REJECT-adjacent caution:** badge-without-audit-trail. If we badge answers, the badge must resolve to a compiler version + entry hash (`staging/`→compile SLA, R4), not a static marketing claim.

## 8. Medito — nonprofit content pipeline

- **[S]** Corpus: hundreds of guided meditations, sleep stories, courses, breathing exercises; 4.1M+ downloads, 4.9★, 190+ countries; 100% free, no account, AGPL open-source code (https://meditofoundation.org/medito-app; Play Store `meditofoundation.medito`).
- **[S]** Pipeline: content developed with mindfulness researchers + experienced teachers; built by 200+ volunteers; 2024 RCT evidence (Remskar et al.) that regular use boosts wellbeing (Play Store listing; https://meditofoundation.org/).
- **[I]** Exact review gate (acceptance criteria, rejection rate) not public; evidence suggests researcher-informed + volunteer-built rather than formal per-track audit board.
- **STEAL:** evidence-tier content labelling — RCT-backed vs teacher-contributed vs community. Our analogue: tier labels on OKF entries (verbatim-verified / scholar-reviewed / compiler-drafted) surfaced in retrieval priority AND in the provenance badge (§7). Hook: OKF compiler frontmatter + R4 freshness report.
- **STEAL (process):** volunteer+researcher curation at near-zero cost — validates our `staging/` human-review boundary as sufficient without a paid editorial board, provided R5 eval gates hold.

## 9. Insight Timer — UGC + review pipeline

- **[S]** Scale: 300,000–310,000 titles; 20,000 teachers; 50+ languages; 30M community / 10k signups/day; 70-person team, zero ad spend (https://insighttimer.com/about; https://insighttimer.com/).
- **[S]** Review loop: teacher dashboard upload → approval queue with content standards; "most rejections and approval delays happen because content doesn't fully meet our standards" (https://help.insighttimer.com/support/solutions/articles/67000664988-how-long-is-the-approval-process-); best-practices doc mandates audio specs (MP3/128kbps/48kHz), title conventions, categorization (https://help.insighttimer.com/support/solutions/articles/67000664986-best-practices-for-content).
- **[S]** Quality signals: user ratings/reviews per track drive discovery; premium tier (Plus) gates top-1,000 teachers' exclusive tracks (Medium, Aug 2023).
- **[I]** No public per-claim doctrinal verification — gates are production-quality (audio, metadata, categorization), not truthfulness.
- **STEAL:** publish the contributor contract (audio/format/metadata standards + rejection reasons) for our `staging/` curation boundary — R4's SLA doc. Their "best practices for content" page is the template.
- **REJECT (combined into top-2 via §4):** ratings-as-truth. User ratings rank *resonance*, not correctness; a spiritual-answer engine must never let popularity signals override verification tier in ranking. Keep ratings (if ever added) strictly out of the retrieval score path.

---

## Verdicts summary

**Top-3 steals:**
1. Source-mode toggle (Magisterial/Auto → curated-only/full-corpus) — `retrieval.py:52-80`, R2.
2. Chunk-level span trimming before fusion (Vespa/Perplexity pattern) — dense post-step in `retrieval.py`.
3. Compute-then-constrain ordering (deterministic layers resolve before generation) — `retrieval.py` ll.35-48, `okf_store.py:168,218`, `config.py:1017`, R2.

**Top-2 rejects:**
1. Unanchored guru/deity voice cloning (AskYourGuide voice, GitaGPT deity-voice) — hold FP never-cites + quote-gate stance.
2. Freshness-weighted / popularity-weighted ranking on curated layers (Perplexity recency bias; Insight ratings-as-truth) — rank by verification tier + teacher-match only.

**Honorable mentions (steal):** Delphi exact-second span anchoring → FP timestamp in ledger (R3); Hallow one-tap inaccuracy reporting → R4 queue; srimadgita per-answer provenance badge → R3 UX; Medito evidence-tier labels → OKF frontmatter tiers; Insight contributor contract → R4 SLA doc.
