# OKF Doctrine Bundle — Change Log

## 2026-07-10 — Teacher subdirectory restructure

- Added `teacher` frontmatter field to every entry (`sri-preethaji`, `sri-krishnaji`, `both`)
- Restructured flat directory into subdirectories by teacher:
  - `sri-preethaji/` (6 entries)
  - `sri-krishnaji/` (2 entries)
  - `shared/` (14 entries)
- Updated `OKFStore` to preserve `teacher` field in `OKFEntry.teacher` property
- Updated `compiler.py` to preserve `teacher` in `compiled.json`
- Updated `_okf_match` in `retrieval.py` to pass `teacher` in metadata and accept filter parameter
- Added teacher routing: query detection of guru name → auto-filters OKF entries to matching teacher
- Updated extraction prompt (`extract_okf_from_stores.py`) to include `teacher` field
- Updated `_write_okf_entry` to write `teacher` in frontmatter
- Updated `_parse_okf_response` to normalise teacher value from LLM output
- Updated `test_okf_doctrine_only.py` to use recursive glob `**/*.md`
