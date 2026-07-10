# Mukthi Guru — Doctrine Bundle

An [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) v0.1 bundle.

**Scope: the teachings of Sri Preethaji and Sri Krishnaji, and nothing else.**

Every concept document here is embedded and injected verbatim into
generated answers by `rag/nodes/retrieval.py:_okf_match`. An entry that is not a
teaching will be cited to a seeker *as* a teaching. Engineering notes, runbooks,
RAG tuning lessons and config postmortems belong in `docs/engineering-notes/`.

## Types

`teaching` · `practice` · `glossary` · `qa` · `reflection`

Enforced by `DOCTRINE_TYPES` in `backend/services/memory/okf_store.py`.

## Teacher Routing

Each entry carries a `teacher` frontmatter field: `sri-preethaji`, `sri-krishnaji`, or `both`.
At query time, the retrieval node detects the guru mentioned in the user's question
and filters OKF entries to match. Questions without a guru reference return entries
from all teachers (shared + both).

| Subdirectory | Meaning | Entry count |
|---|---|---|
| `sri-preethaji/` | Teachings delivered by Sri Preethaji | 6 |
| `sri-krishnaji/` | Teachings delivered by Sri Krishnaji | 2 |
| `shared/` | Joint teachings or compiled glossary | 14 |

## Concepts

### Sri Preethaji

| Type | Concept |
|------|---------|
| teaching | [The Beautiful State](sri-preethaji/beautiful_state.md) |
| teaching | [The Inner Truth of Suffering](sri-preethaji/inner_truth_of_suffering.md) |
| teaching | [Experiencing the Divine — Manifest and Unmanifest](sri-preethaji/experiencing_the_divine_manifest_and_unmanifest.md) |
| teaching | [The First Sacred Secret — Live with a Spiritual Vision](sri-preethaji/the_first_sacred_secret_live_with_a_spiritual_vision.md) |
| teaching | [The Voice That Speaks to You and Guides You](sri-preethaji/the_voice_that_speaks_to_you_and_guides_you.md) |
| practice | [Three-Question Meditation](sri-preethaji/three_question_meditation.md) |

### Sri Krishnaji

| Type | Concept |
|------|---------|
| teaching | [Awakening to Compassion](sri-krishnaji/awakening_to_compassion.md) |
| practice | [Serene Mind — 3-Minute Practice](sri-krishnaji/serene_mind_practice.md) |

### Shared (both teachers)

| Type | Concept |
|------|---------|
| teaching | [Beautiful State and Health Challenges](shared/beautiful_state_and_health_challenges.md) |
| teaching | [Beautiful State Practice](shared/beautiful_state_practice.md) |
| teaching | [Claiming the Inner State](shared/claiming_the_inner_state.md) |
| teaching | [Connecting to Universal Intelligence](shared/connecting_to_universal_intelligence.md) |
| teaching | [Feeling One with Universal Intelligence](shared/feeling_one_with_universal_intelligence.md) |
| teaching | [Finding Truth in Chaos](shared/finding_truth_in_chaos.md) |
| teaching | [Gentle Spiritual Awakening](shared/gentle_spiritual_awakening.md) |
| teaching | [Inner Peace and Consciousness](shared/inner_peace_and_consciousness.md) |
| teaching | [Inner Truth and Being](shared/inner_truth_and_being.md) |
| teaching | [Power of Collective Meditation](shared/power_of_collective_meditation.md) |
| teaching | [Stillness and Inner Truth](shared/stillness_and_inner_truth.md) |
| teaching | [Universal Intelligence](shared/universal_intelligence.md) |
| teaching | [Universal Intelligence and Oneness](shared/universal_intelligence_and_oneness.md) |
| glossary | [Glossary — Core Teachings Vocabulary](shared/beautiful_state_glossary.md) |

## Lifecycle

```
ingestion → extract_okf(auto_approve=False) → staging/  (unreviewed, never compiled)
                                                  │
                                        admin approve
                                                  ▼
                       sri-preethaji/  sri-krishnaji/  shared/
                                                  │
                                          compile_okf()
                                                  │
                                                  ▼
                                            compiled.json
```

The `staging/` directory and `_scripts/` are excluded from the recursive glob.
`OKFStore.list_entries()` uses `glob("*.md")` (non-recursive by design — subdirectories
are explicit doctrine, `staging/` is unreviewed). When the subdirectory layout was
introduced, the test `_CONCEPT_FILES` was updated to `glob("**/*.md")` to match.

Reserved filenames per OKF v0.1: `index.md`, `log.md` — no frontmatter, not concepts.

## Frontmatter Contract

```yaml
---
type: teaching       # required — one of: teaching, practice, glossary, qa, reflection
title: "The Title"   # required
description: "..."   # recommended — embedded for semantic match
source: "..."        # required — provenance URL
teacher: "sri-preethaji"  # recommended — sri-preethaji | sri-krishnaji | both
tags: [tag1, tag2]   # optional
updated: "2026-07-10"  # recommended — freshness tracking
---
```
