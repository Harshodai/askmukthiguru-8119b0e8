# Presentation patterns for quote-first / verbatim answers (headings, points, citations, timestamps)

Method caveat (read first): WebFetch failed with DNS errors (getaddrinfo ENOTFOUND) for every domain (nngroup.com, arxiv.org, developers.google.com). A curl fallback was blocked by the sandbox policy and I did not try to work around it. Every finding below therefore comes from WebSearch result summaries of the named pages, not from reading the full pages. Treat quoted wording as the search tool's paraphrase unless shown in quotation marks, and re-verify numbers against the primary page before they go into a report. Anything I could not source is marked UNVERIFIED or sits under Gaps.

## 1. How do Ask Sadhguru, Delphi.ai, Perplexity, YouTube/Google "key moments" and podcast tools present quoted answers and timestamps?

### Takeaway
Only the Google/YouTube timestamp mechanics and Perplexity's numbered-citation pattern are verifiable from official pages. For Ask Sadhguru and Delphi I found no public documentation of answer layout, so their presentation is UNVERIFIED. Nothing found shows any product that shows verbatim teacher clips with a ▶ link inside an AI-framed multi-clip answer, so this app has no verified direct precedent to copy.

### Cited Findings
- Google's Video structured-data docs offer two key-moment mechanisms. Clip markup lets the publisher set each segment's start time, end time and a label to display, and Google prioritizes manually identified key moments. SeekToAction lets Google find moments automatically and needs a URL parameter that starts playback at a given second (example `?t=30`). — [Google Search Central: Video structured data](https://developers.google.com/search/docs/data-types/video)
- For YouTube-hosted videos, the same Google docs say timestamps and labels can be given in the YouTube description, so SeekToAction markup is unnecessary there. — [Google Search Central: Video structured data](https://developers.google.com/search/docs/data-types/video)
- Pattern implied by Clip markup: every moment is a labelled pair (a human-readable title plus a start/end offset), not a bare time. — [Google Search Central: Video structured data](https://developers.google.com/search/docs/data-types/video)
- YouTube chapters: the first timestamp must be 00:00, at least three timestamps are needed in ascending order, minimum chapter length is 10 seconds, and creator-entered chapters override auto-generated ones. Chapters appear at the bottom of the player and take their titles from the description. — [YouTube Help: Video Chapters](https://support.google.com/youtube/answer/9884579?hl=en)
- Perplexity: each answer includes numbered citations linking to the original sources; users hover to preview or click through. Trust labels such as Government, Academic and Trusted are shown. Each answer section displays the sources pulled for that section. Help pages also note that responses are generated with AI and may contain mistakes. — [Perplexity Help Center: How does Perplexity work?](https://www.perplexity.ai/help-center/en/articles/10352895-how-does-perplexity-work); [Perplexity: Getting started](https://www.perplexity.ai/hub/getting-started); [Perplexity Enterprise: Queries](https://www.perplexity.ai/enterprise/videos/an-introduction-to-queries)
- Delphi: the product page says a Digital Mind's answers are based on the creator's own source material and include references to where the information came from. It does not say how references are formatted, whether they show timestamps, or whether text is quoted or paraphrased. — [Delphi embed page](https://embed.delphi.ai/)
- Ask Sadhguru: it appears to be a feature inside Isha's Miracle of Mind app (launched Feb 2025). A June 2025 Isha press release claims training on 50,000+ hours of teachings. I found no source stating answers are verbatim, how they are laid out, or whether they carry citations or timestamps. — [GlobeNewswire press release, June 2025](https://www.globenewswire.com/news-release/2025/06/06/3095288/0/en/Isha-Foundation-s-Meditation-App-Surpasses-ChatGPT-s-Launch-Pace-Signals-Global-Demand-for-Digital-Stillness.html)
- Isha also showed a conversational AI avatar of Sadhguru on hologram units at Mahashivratri 2026; reports describe responses as "aligned with" his teachings, not his own words. — [IT Brief](https://itbrief.in/story/ai-hologram-of-sadhguru-debuts-at-mahashivratri-fest), [GlobeNewswire Feb 2026](https://www.globenewswire.com/news-release/2026/02/20/3242096/0/en/sadhguru-presents-innovative-ai-hologram-tech-at-massive-event.html)
- Podcast tools (third-party write-ups only, no official docs found): Snipd creates a timestamped highlight with audio clip plus transcript text, and answers episode questions concisely with a link to the audio clip; its Obsidian export includes transcript, AI summary, personal notes and a direct playback link. Readpodcast AI shows a scrolling transcript with speaker separation and clickable timestamps. HappyScribe's tool lets users search transcripts and jump to exact timestamps. PodText offers a timestamped searchable transcript. — [AI Indigo Snipd tutorial](https://aiindigo.com/tutorials/getting-started-with-snipd-transform-passive-listening-into-active-knowledge), [Creati: Readpodcast AI](https://creati.ai/ai-tools/readpodcast-ai/), [GoTranscript on HappyScribe](https://gotranscript.com/public/happyscribe-makes-podcast-quotes-searchable-in-minutes), [Product Hunt: PodText](https://www.producthunt.com/products/podtext)
- Separate note from a Snipd review: snip start/end can be imprecise with noisy audio, and speaker labels on 3+ speaker shows should be spot-checked. — [AI Indigo Snipd review](https://aiindigo.com/blog/turning-podcasts-into-knowledge-a-2026-review-of-snipd)

### Inferences
- Reusable, verified building blocks: (a) a short human-readable label plus a time offset per moment (Clip/YouTube chapters); (b) numbered markers tied to a source list with hover or click preview (Perplexity); (c) per-section source lists rather than one pile at the bottom (Perplexity Enterprise).
- Because each of our clips is itself the source, the "citation" can sit directly on the clip (speaker, video title, mm:ss, ▶) instead of a numbered footnote.
- The 10-second minimum chapter length and the 3-timestamp minimum on YouTube are platform rules for chapters, not guidance for clip length; do not treat them as design targets for clips.

### Gaps
- No public documentation found for Ask Sadhguru answer layout, Delphi citation format, or whether either shows timestamps. Needs hands-on inspection of the products (UNVERIFIED).
- No official docs found for Snipd, Listen Notes or Podscribe; podcast findings are third-party.
- No product found that interleaves verbatim clips with clearly labelled AI framing.

## 2. Research on trust and comprehension with quotes vs paraphrase, inline citations and source attribution (HCI)

### Takeaway
Evidence consistently shows that visible citations raise trust, sometimes even when the citations are wrong, and that citations often fail to support the sentence they sit on. I found no study directly comparing verbatim quotation against paraphrase for comprehension or trust, so the quote-vs-paraphrase question is a gap. Citation presentation (hover card vs sidebar) measurably changes verification behaviour.

### Cited Findings
- Audit of four generative search engines (Bing Chat, NeevaAI, perplexity.ai, YouChat): only 51.5% of generated sentences were fully supported by citations, and only 74.5% of citations supported their sentence. The authors also warn fluent, confident tone can make answers seem more trustworthy than they are. Published at Findings of EMNLP 2023, not CHI. — [Liu, Zhang, Liang, arXiv 2304.09848](https://arxiv.org/abs/2304.09848)
- Preregistered randomized experiment, U.S.-representative sample: reference links and citations significantly increased trust in generative AI even when incorrect or hallucinated; highlighting uncertainty reduced willingness to trust and share. — [Human Trust in AI Search: A Large-Scale Experiment, arXiv 2504.06435](https://arxiv.org/abs/2504.06435v1)
- A 303-person randomized trial reported that participants who actually checked citations rated answers as less trustworthy (reported via a secondary review, not the paper itself). — [Moonlight review of "Citations and Trust in LLM Generated Responses"](https://www.themoonlight.io/fr/review/citations-and-trust-in-llm-generated-responses)
- 2026 arXiv study of source-transparency design compared hover cards, a sidebar and listings: hover cards supported on-demand verification during the task; an aligned sidebar mitigated information-overload effects, with sidebar users scoring higher on critical thinking as citation density rose. — [Seeing to Think? arXiv 2601.14611](https://arxiv.org/html/2601.14611v1)
- A CHI 2026-era paper on generative AI search result design and information adoption exists (findings not visible to me). — [ACM DL 10.1145/3786304.3787937](https://dl.acm.org/doi/10.1145/3786304.3787937)
- Copilot-style information-seeking study: trust was often misplaced in favour of ease of use and seemingly perfect answers in chat. — [Can You Tell Me? arXiv 2601.11284](https://arxiv.org/pdf/2601.11284)
- Wharton experiments (1,372 participants): 73% accepted a confident but incorrect AI answer (secondary report). — [Stacker](https://stacker.com/stories/ai/two-thirds-workers-dont-always-check-what-ai-tells-them-half-think-theyd-be-responsible)

### Inferences
- Citation-as-trust-signal cuts both ways: for this app, whose clips ARE the source, a ▶ link next to the exact words is a stronger provenance cue than an AI footnote, but the "citation lifts trust regardless of accuracy" result means a visible attribution must be backed by real relevance (the app's "Related, not a direct answer" label is the right counterweight).
- Placement of provenance matters (hover card vs sidebar). For clip answers, an always-visible attribution line on each clip avoids hover-only discovery on mobile (this is an inference; the hover-vs-sidebar study does not test clip UIs).
- A reader who cannot tell where framing ends and teacher speech begins cannot calibrate trust, which supports strict visual separation (see section 4).

### Gaps
- No CHI/CSCW study found that compares verbatim quote versus paraphrase for trust or comprehension. Searching "quotation vs paraphrase" gave nothing relevant (not found).
- Could not read the full text of the ACM generative-search-design paper.
- Why users call multi-clip answers "AI-generated" or "split" has no direct study; the cause is likely stitching cues and no connective structure (hypothesis, UNVERIFIED).

## 3. Readability guidance for structured answers (NN/g)

### Takeaway
NN/g's long-standing finding is that web readers scan: meaningful subheadings, front-loaded keywords, bulleted lists and short paragraphs improve usability. Numbers date from 1997-era studies but have been reconfirmed in later NN/g material.

### Cited Findings
- 79% of test users always scanned new pages; 16% read word-by-word (original 1997 study). — [NN/g: How Users Read on the Web](https://www.nngroup.com/articles/how-users-read-on-the-web/)
- Recommended scannable-text techniques: keywords, meaningful subheadings, bullet lists, one idea per paragraph, conclusions first. When three writing improvements were combined on one site, usability was measured at 124% better. — [NN/g: Concise, SCANNABLE, and Objective](https://www.nngroup.com/articles/concise-scannable-and-objective-how-to-write-for-the-web/), [NN/g: How Users Read on the Web](https://www.nngroup.com/articles/how-users-read-on-the-web/)
- Users read more closely when highly motivated or interested; scanning is the default, not the only mode. — [NN/g: Website Reading: It (Sometimes) Does Happen](https://www.nngroup.com/articles/website-reading/)
- F-shaped pattern is a rough, general shape, not a uniform pixel-perfect behaviour. — [NN/g: F-Shaped Pattern, Misunderstood](https://www.nngroup.com/articles/f-shaped-pattern-reading-web-content/)
- Bulleted-list tips: roughly equal item length, numbers only when order or count matters (testing showed people thought they had to do every numbered step), parallel phrasing, avoid repeating the same opening words, clear lead-in, consistent punctuation, vertical lists best for 3+ items. — [NN/g: 7 Tips for Presenting Bulleted Lists](https://www.nngroup.com/articles/presenting-bulleted-lists/)
- For long bullets, bold the key term at the start. — [NN/g: 5 Formatting Techniques for Long-Form Content](https://www.nngroup.com/articles/formatting-long-form-content/)
- Headings/lists should start with the information-carrying words (university editorial guide echoing NN/g). — [Newcastle University readability guide](https://www.ncl.ac.uk/design-system/ux/editorial/readability/)

### Inferences
- Our editable layer (headings, lead-in, per-clip labels) is exactly what NN/g says carries scanning: a one-line own-text lead-in with the answer's gist, then clip cards each led by a short topic label (bold, written by us, clearly ours), then the quote.
- Do not put teacher text into bullets that imply paraphrase; use block-quote style cards. Bullets are for our own framing (e.g. "What these clips cover").
- Parallel structure across clip cards (speaker, source, time, ▶) satisfies NN/g's parallelism and equal-length advice without touching quote wording.
- Numbers on clip cards would imply sequence (NN/g numbered-list finding); use numbering only if the clips are genuinely ordered, otherwise no numbers or use the speaker/time as the identifier.

### Gaps
- No NN/g study found specifically on AI chat answers or on quotation blocks. The 70% bulleted-list-examined figure circulating online was not confirmed against NN/g; do not use it.
- Did not read the full NN/g pages (fetch failed); details come from search summaries.

## 4. Patterns for labelling AI-written framing versus quoted source text

### Takeaway
I found no authoritative guideline in this search specific to separating machine framing from quoted text. What is verifiable is general: Google's recommendation-not-requirement stance on labelling AI content, Perplexity's standing "generated with AI, may contain mistakes" notice, and per-section source lists. The concrete patterns below are design proposals (inference), not documented standards.

### Cited Findings
- Google's 2023 stance relayed in an event recap: labelling AI-generated images via IPTC metadata is recommended but not required; labelling text as AI-generated was not required. — [Relevant Audience recap](https://www.relevantaudience.com/seo/google-ai-content-guidance-manual-fact-check/) (secondary, and a 2024 announcement of C2PA-based labels in Search supersedes parts of it per [Entrepreneur India](https://india.entrepreneur.com/?p=2099); sources conflict on timing)
- Perplexity keeps a generic notice that responses are AI-generated and may contain mistakes, and attributes sources per answer section. — [Perplexity Help Center](https://www.perplexity.ai/help-center/en/articles/10352895-how-does-perplexity-work)
- Uncertainty highlighting reduces trust and willingness to share even when content is right, so a label that signals uncertainty has a cost the team should weigh. — [arXiv 2504.06435](https://arxiv.org/abs/2504.06435v1)
- Google's PAIR People + AI Guidebook has an explainability/trust chapter; I could not retrieve its text on attribution or labelling. — [PAIR Guidebook summary](https://www.exploreaiethics.com/tools/people-ai-guidebook/)

### Inferences (design proposals, UNVERIFIED as established standards)
- Two visually distinct registers: our framing in plain body text with a small fixed tag (e.g. "Guide note"), teacher words inside a block-quote card with a left rule, speaker name, source title and time. Never mix registers within a sentence.
- Keep the connective tissue minimal and meta (what the next clip addresses), not doctrinal; one-sentence lead-in plus short topic label per clip, to read as curated rather than generated.
- Put a single consistent line on each card: speaker, video title, start time with ▶. A per-card line mirrors Perplexity's per-section sources and YouTube's label+time moments.
- Use one answer-level honesty line (e.g. "Related, not a direct answer" when uncalibrated) rather than hedging on every card, to avoid the uncertainty-trust penalty on each clip.
- Avoid first-person framing text in the guide's voice that could be mistaken for the teacher's (repo constraint: framing must be clearly ours; no impersonation).
- Avoid joining clips with transitions that merge them into one flowing paragraph; that is likely what makes multi-clip answers feel "split yet AI-written". Treat as hypothesis to A/B test.

### Gaps
- No peer-reviewed study found on labelling AI framing versus quoted text.
- No documentation found on how Delphi or Ask Sadhguru distinguish generated text from source text.
- The 2024 Google labelling claim comes from secondary outlets; check Google's official announcement before citing.
