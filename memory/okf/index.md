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
| teaching | [Inner Truth](/inner_truth.md) |
| teaching | [The Inner Truth of Suffering](/inner_truth_of_suffering.md) |
| teaching | [Meditation Practice](/meditation_practice.md) |
| teaching | [Sacred Secrets](/sacred_secrets.md) |
| teaching | [Universal Intelligence](/universal_intelligence.md) |
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
