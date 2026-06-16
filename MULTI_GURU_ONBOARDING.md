# MULTI_GURU_ONBOARDING.md — How to add a new guru to the platform

> The architecture is already wired for multi-guru. This doc tells you the
> exact steps to onboard a second guru (e.g. Sadhguru / Isha, Mooji, Adyashanti)
> without touching application code. **The hard part is the corpus, not the code.**

---

## 1. What "multi-guru" means here

Two distinct concepts:

| Concept | What it does | Already in code? |
|---|---|---|
| **Per-user tenancy** | Each user has isolated profile/memory/saved-data | ✅ `services/tenant_context.py` |
| **Per-guru tenancy** | The entire system can be configured to serve a different guru's teachings | 🟡 Partially — corpus & YAML config exist, profile-loader is the next step |

This document focuses on the **per-guru** flow. Onboarding "guru B" means:

  1. A new guru profile config directory.
  2. A new Qdrant collection populated with that guru's corpus.
  3. A new YAML route file (or augmented existing).
  4. A new eval dataset for that guru's tradition.
  5. Optionally a new system-prompt template — usually a swap-in, not a rewrite.

---

## 2. The guru profile directory layout

```
backend/config/gurus/
├── mukthi-guru/                     # active default
│   ├── profile.yaml                 # identity, founders, persona settings
│   ├── doctrine.yaml                # doctrinal markers, refusal patterns
│   ├── router_routes.yaml           # intent routing (same schema as global)
│   ├── prompts.yaml                 # system prompt + casual + distress templates
│   ├── corpus.yaml                  # ingestion config (sources, chunking, qdrant collection)
│   └── eval/
│       └── dataset_v1.yaml          # 50-200 question stratified eval set
│
├── isha-sadhguru/                   # FUTURE
│   ├── profile.yaml
│   └── ...
│
└── _shared/
    ├── crisis_helplines.yaml        # shared across all gurus
    └── safety_patterns.yaml         # safety regex shared across all gurus
```

### profile.yaml — identity contract

```yaml
guru_id: mukthi-guru
display_name: Mukthi Guru
founders:
  - "Sri Preethaji"
  - "Sri Krishnaji"
tradition: "Oneness / Ekam Movement"
founders_pronoun_style: "third_person"   # always speak ABOUT the founders, never AS them
language_default: en
languages_supported: [en, hi, ta, te, hinglish, tanglish]
qdrant_collection: spiritual_wisdom
canonical_sources:
  - "https://www.youtube.com/@OnenessMovement"
  - "https://theonenessmovement.org/manifest"
  - "ekam.org"
forbidden_traditions_to_blend_with:
  - "Buddhist non-self"
  - "Generic Advaita Vedanta"
  - "Neo-Advaita (Tony Parsons et al.)"
  - "Reiki / Pranic Healing"
```

---

## 3. Onboarding a new guru — step by step

### Step 0 (most underestimated): Curate the corpus

Before touching any code, you need:
  - At least 200 transcribed teachings (YouTube transcripts, retreat
    recordings, book chapters, blog posts).
  - Each source must be **explicitly attributed**: who said it, when, in what
    context. Without this, citation correctness collapses.
  - Sources should be in the original language(s) of the teaching where possible
    (Sanskrit terms transliterated, regional language quotes preserved).
  - Quality bar: a follower of the tradition can read any chunk and confidently
    say "yes, this guru taught this". Anything ambiguous → out.

**Rule of thumb**: 1 senior tradition-aware curator for ~2 weeks per guru. You
cannot LLM-summarise this step.

### Step 1: Create the profile directory

```bash
cp -r backend/config/gurus/mukthi-guru backend/config/gurus/<new-slug>
```
Edit every file under the new slug:
  - `profile.yaml` — change identity, founders, language list, Qdrant
    collection name.
  - `doctrine.yaml` — keyword anchors, doctrinal markers, refusal patterns
    specific to this tradition.
  - `router_routes.yaml` — intent utterances tuned for this guru's vocabulary.
  - `prompts.yaml` — system prompt referencing this guru by name.

### Step 2: Ingest the corpus into a new Qdrant collection

```bash
# Choose a unique collection name (config.yaml: qdrant_collection)
export QDRANT_COLLECTION="<new-slug>_wisdom"

# Ingest using the existing pipeline
python -m backend.ingest.pipeline \
  --source-config backend/config/gurus/<new-slug>/corpus.yaml \
  --target-collection "$QDRANT_COLLECTION"
```

The ingestion pipeline (in `backend/ingest/`) already handles:
  - YouTube transcript extraction with multi-language fallback
  - PDF / image OCR (`image_loader.py`)
  - RAPTOR cluster summarisation (`raptor.py`)
  - Contextual chunking with header injection
  - Sparse + dense vector generation
  - Audit & quality control (`auditor.py`, `cleaner.py`, `corrector.py`)

### Step 3: Build the eval set

Copy `backend/evaluation/datasets/mukthi_guru_v1.yaml` to
`backend/config/gurus/<new-slug>/eval/dataset_v1.yaml` and rewrite every
question for the new guru. Minimum:
  - 20 founder biographical
  - 20 core doctrine
  - 30 multilingual
  - 30 adversarial
  - 15 distress
  - 5 crisis
  - 10 temporal
  - 10 capability
  - 10 doctrine traps (where confused with sibling traditions)
  - 50 stratified other

### Step 4: Set the active guru via env

```bash
# backend/.env
ACTIVE_GURU_ID=<new-slug>
```

The `GuruProfile` loader reads this at startup, hydrates the
`SemanticRouter`, the prompts module, the doctrine classifier, and the
retrieval service with the correct config.

### Step 5: Run the eval

```bash
python -m backend.evaluation.eval_runner \
  --endpoint http://localhost:8000 \
  --dataset <new-slug>/dataset_v1 \
  --out-json results/<new-slug>_baseline.json
```

Target: composite ≥0.97 before going live. If lower, iterate on:
  - Retrieval quality (add more corpus, tune chunking)
  - System prompt for the new guru
  - Doctrine YAML keyword anchors

### Step 6: Deploy

You can either:
  - **A/B mode**: run two backend instances, one per guru, route via subdomain
    (mukthi.guruapp.com vs sadhguru.guruapp.com).
  - **Single instance with user-selectable guru**: add `guru_id` to the
    `/api/chat` request body; the orchestrator loads the appropriate
    `GuruProfile` per request. Slight latency overhead (~5 ms profile lookup).

---

## 4. What stays shared across all gurus

These do NOT change per-guru — they are global safety / infrastructure:

- Crisis helpline configuration (`backend/config/gurus/_shared/crisis_helplines.yaml`)
- Safety regex patterns (self-harm, prescription-seeking, manifestation-money)
- HTTP/Qdrant/Redis/Neo4j connection settings
- Auth flow (Supabase / Google OAuth)
- Frontend shell (chat UI, profile, memory) — UI is guru-neutral
- LangGraph pipeline structure
- The LLM judge harness and the 5-dimension rubric

---

## 5. What MUST change per-guru

- Identity in the system prompt (name, founders, lineage)
- Doctrine keyword anchors
- Forbidden tradition cross-blends
- Canonical-source domain whitelist for web search
- Qdrant collection
- Eval dataset
- Refusal style (some gurus want stricter; some want more conversational)

---

## 6. Pre-launch gates for a new guru

Each of these MUST be green before turning a new guru on for real users:

| # | Gate | How to verify |
|---|------|---------------|
| 1 | Corpus is curator-approved | Signed off in writing by the lineage holder or designated curator |
| 2 | Eval composite ≥0.97 | `python -m backend.evaluation.eval_runner --dataset <slug>/dataset_v1` |
| 3 | Crisis-path regression passes | A `crisis_*` query MUST return helplines first |
| 4 | Doctrine-trap regression passes | All `doctrine_*` queries score ≥0.85 on `doctrinal_consistency` |
| 5 | Multilingual regression passes | At least one Hinglish + one regional-language query answered in the same script |
| 6 | Hardcode audit returns empty | `grep` checks from `WHAT_TO_DO.md` §6 |
| 7 | Latency p95 ≤ 8s on the new dataset | Standard SLO |

If any gate fails, do not ship.

---

## 7. Pitfalls I expect you to hit

- **"Just blend two gurus' teachings"** → no. The doctrine_classifier will
  start failing and users lose trust. Run each guru as a sibling instance.
- **"We already have a Sadhguru corpus, ingest it into the existing
  collection"** → no. Cross-doctrine contamination is the most expensive bug
  in this space.
- **"Copy mukthi-guru's eval set and tweak names"** → no. Each guru's eval
  set must test the **traps specific to that lineage** (e.g. for Adyashanti,
  the trap is being mistaken for Eckhart Tolle; for Sadhguru, the trap is
  being mistaken for generic Yoga / Patanjali system).
- **"We can crowdsource the eval from users"** → not initially. Crowd labels
  drift with the population of users; start with curator-labelled gold sets,
  then expand with judged crowd data.

---

## 8. Roadmap for the multi-guru abstraction (not yet shipped)

| Phase | Deliverable | Status |
|---|---|---|
| 1 | YAML schema for guru profile | ✅ Documented in this file |
| 2 | `GuruProfile` loader class | 🟡 To implement |
| 3 | Wire `GuruProfile` into PipelineCoordinator | 🟡 To implement |
| 4 | Per-guru Qdrant collection routing | ✅ `tenant_context.get_tenant_collection()` already supports namespaced collections |
| 5 | Frontend "select guru" UI | 🟡 Defer until guru #2 corpus is ready |

The code lift for items 2 + 3 is ~150 LOC. We deferred it deliberately:
shipping it without a real second guru would mean an untested abstraction.
Add the second guru corpus first, then this scaffolding.
