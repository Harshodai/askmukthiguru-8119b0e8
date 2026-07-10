# Mukthi Guru — Doctrine Bundle

An [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) v0.1 bundle.

**Scope: the teachings of Sri Preethaji and Sri Krishnaji, and nothing else.**

Every concept document in this directory is embedded and injected verbatim into
generated answers by `rag/nodes/retrieval.py:_okf_match`. An entry that is not a
teaching will be cited to a seeker *as* a teaching. Engineering notes, runbooks,
RAG tuning lessons and config postmortems belong in `docs/engineering-notes/`.

## Types

`teaching` · `practice` · `glossary` · `qa` · `reflection`

Enforced by `DOCTRINE_TYPES` in `backend/services/memory/okf_store.py`. Any other
`type` is skipped at load with a warning and never reaches the answer path.

## Concepts

| Type | Concept |
|------|---------|
| teaching | [The Beautiful State](/beautiful_state.md) |
| teaching | [The Inner Truth of Suffering](/inner_truth_of_suffering.md) |
| teaching | [The First Sacred Secret — Live with a Spiritual Vision](/the_first_sacred_secret_live_with_a_spiritual_vision.md) |
| teaching | [Awakening to Compassion](/awakening_to_compassion.md) |
| teaching | [Beautiful State and Health Challenges](/beautiful_state_and_health_challenges.md) |
| teaching | [Beautiful State Practice](/beautiful_state_practice.md) |
| teaching | [Claiming the Inner State](/claiming_the_inner_state.md) |
| teaching | [Connecting to Universal Intelligence](/connecting_to_universal_intelligence.md) |
| teaching | [Experiencing the Divine — Manifest and Unmanifest](/experiencing_the_divine_manifest_and_unmanifest.md) |
| teaching | [Feeling One with Universal Intelligence](/feeling_one_with_universal_intelligence.md) |
| teaching | [Finding Truth in Chaos](/finding_truth_in_chaos.md) |
| teaching | [Gentle Spiritual Awakening](/gentle_spiritual_awakening.md) |
| teaching | [Inner Peace and Consciousness](/inner_peace_and_consciousness.md) |
| teaching | [Inner Truth and Being](/inner_truth_and_being.md) |
| teaching | [Power of Collective Meditation](/power_of_collective_meditation.md) |
| teaching | [Stillness and Inner Truth](/stillness_and_inner_truth.md) |
| teaching | [The Voice That Speaks to You and Guides You](/the_voice_that_speaks_to_you_and_guides_you.md) |
| teaching | [Universal Intelligence](/universal_intelligence.md) |
| teaching | [Universal Intelligence and Oneness](/universal_intelligence_and_oneness.md) |
| practice | [Serene Mind — 3-Minute Practice](/serene_mind_practice.md) |
| practice | [Three-Question Meditation](/three_question_meditation.md) |
| glossary | [Glossary — Core Teachings Vocabulary](/beautiful_state_glossary.md) |

## Lifecycle

```
ingestion → extract_okf(auto_approve=False) → staging/  (unreviewed, never compiled)
                                                  │
                                        admin approve
                                                  ▼
                                            *.md here  →  compile_okf()  →  compiled.json
```

`staging/` is deliberately excluded: `OKFStore.list_entries()` uses a non-recursive
`glob`. Unreviewed, LLM-synthesised doctrine must never reach a seeker.

Reserved filenames per OKF v0.1: `index.md`, `log.md` — no frontmatter, not concepts.
