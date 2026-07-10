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
    ├── index.md       # bundle index (OKF v0.1 reserved)
    ├── log.md         # change log (OKF v0.1 reserved)
    ├── compiled.json  # compiler output (gitignored — regenerate via CLI)
    ├── sri-preethaji/ # Sri Preethaji's teachings (6 entries)
    ├── sri-krishnaji/ # Sri Krishnaji's teachings (2 entries)
    ├── shared/        # Joint / both-teacher teachings (14 entries)
    ├── staging/       # Unreviewed LLM output (excluded from compile)
    └── _scripts/      # Migration and maintenance tooling
```

## Teacher Routing

Each entry carries a `teacher` frontmatter field: `sri-preethaji`, `sri-krishnaji`, or `both`.
The retrieval node (`_okf_match`) detects the guru mentioned in the user's question
and auto-filters to the matching teacher's entries. Questions without a guru reference
return entries from all teachers.

## Seed entries

| File | Teacher | Type | One-line description |
|------|---------|------|----------------------|
| [beautiful_state.md](okf/sri-preethaji/beautiful_state.md) | sri-preethaji | teaching | The two states of being — stressful vs. beautiful — and what keeps suffering alive. |
| [inner_truth_of_suffering.md](okf/sri-preethaji/inner_truth_of_suffering.md) | sri-preethaji | teaching | Sri Krishnaji's insight at Big Bear Lake: all lingering suffering is self-centric thinking. |
| [serene_mind_practice.md](okf/sri-krishnaji/serene_mind_practice.md) | sri-krishnaji | practice | 3-minute Serene Mind practice: breath, emotion, thought direction, flame at eyebrow center. |
| [three_question_meditation.md](okf/sri-preethaji/three_question_meditation.md) | sri-preethaji | practice | Three-question meditation for surfacing state / time / self and returning to the beautiful state. |
| [beautiful_state_glossary.md](okf/shared/beautiful_state_glossary.md) | both | glossary | Definitions of core terms: beautiful state, self-centric thinking, serene mind, connection, presence. |

## Frontmatter contract (OKF v0.1)

```yaml
---
type: teaching           # REQUIRED. One of: teaching | practice | glossary
title: <string>          # human-readable title
source: <string>         # provenance — YouTube video title/URL, book chapter, etc.
teacher: sri-preethaji   # sri-preethaji | sri-krishnaji | both
tags: [<string>, ...]    # optional free-form tags
updated: YYYY-MM-DD      # optional freshness marker
---
```

An entry missing the `type` frontmatter field is rejected by `OKFStore` and
the compiler (raises `ValueError`).

## Compiling

```bash
# from backend/
python -m scripts.okf_compile --rebuild
```

This walks `memory/okf/` recursively (teacher subdirectories), validates
frontmatter, embeds each entry's `title + description` via `EmbeddingService`
(bge-m3), and writes `memory/okf/compiled.json`. The retrieval node loads
`compiled.json` lazily and caches it for the process lifetime.

`staging/` and `_scripts/` are excluded from the recursive walk (see
`okf_store.py` rglob exclusion list).