# Memory — OKF Index

This directory holds the **Open Knowledge Format (OKF) v0.1** store for
MukthiGuru. OKF entries are markdown files with YAML frontmatter; the single
required field is `type`. Entries are human-auditable and compiled into a
single embedded index (`memory/okf/compiled.json`) that the RAG retrieval node
reads as a third retrieval channel alongside Qdrant and LightRAG.

## Layout

```
memory/
├── AGENTS.md          # this index
├── MEMORY.md          # session-scoped scratch
└── okf/
    ├── *.md           # OKF entries (frontmatter + markdown body)
    └── compiled.json  # compiler output (gitignored — regenerate via CLI)
```

## Seed entries

| File | type | One-line description |
|------|------|----------------------|
| [beautiful_state.md](okf/beautiful_state.md) | teaching | The two states of being — stressful vs. beautiful — and what keeps suffering alive. |
| [inner_truth_of_suffering.md](okf/inner_truth_of_suffering.md) | teaching | Sri Krishnaji's insight at Big Bear Lake: all lingering suffering is self-centric thinking. |
| [serene_mind_practice.md](okf/serene_mind_practice.md) | practice | 3-minute Serene Mind practice: breath, emotion, thought direction, flame at eyebrow center. |
| [three_question_meditation.md](okf/three_question_meditation.md) | practice | Three-question meditation for surfacing state / time / self and returning to the beautiful state. |
| [beautiful_state_glossary.md](okf/beautiful_state_glossary.md) | glossary | Definitions of core terms: beautiful state, self-centric thinking, serene mind, connection, presence. |

## Frontmatter contract (OKF v0.1)

```yaml
---
type: teaching      # REQUIRED. One of: teaching | practice | glossary
title: <string>     # human-readable title
source: <string>    # provenance — YouTube video title/URL, book chapter, etc.
tags: [<string>, ...] # optional free-form tags
# ...any other keys are preserved verbatim
---
```

An entry missing the `type` frontmatter field is rejected by `OKFStore` and
the compiler (raises `ValueError`).

## Compiling

```bash
# from backend/
python -m scripts.okf_compile --rebuild
```

This walks `memory/okf/`, embeds each entry's body with the shared
`EmbeddingService` (bge-m3), and writes `memory/okf/compiled.json` containing
embeddings + summaries + the frontmatter index. The retrieval node loads
`compiled.json` lazily and is cached for the process lifetime.