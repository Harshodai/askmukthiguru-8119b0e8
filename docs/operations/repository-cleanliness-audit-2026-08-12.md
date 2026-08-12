# Repository Cleanliness Audit — 2026-08-12

**Scope.** This audit distinguishes tracked product source and evidence from disposable build output. It records each material cleanup category observed during the release review, the decision, and the follow-up owner. No production data, credentials, teaching corpus, or deployment configuration was removed.

## Completed safe removals

| Category | Verified condition | Action | Approximate recovered tracked footprint |
|---|---|---:|---:|
| `playwright-screenshots/` | UI test and workflow scripts write this directory as output; no test reads it as a baseline. | Removed and ignored. | 23 MB |
| `work-2f5cc802-84d2-43b2-ab0e-8be79aef9bcb-xCk6Td/` | Unreferenced compiled audio/video work directory. | Removed and ignored. | 4.7 MB |
| `brag-demo-2min.mp4`, `brag-demo-2.5min-master.mp4`, `brag-demo-real-screens.mp4` | Unreferenced legacy rendered demos, superseded by the new demo handoff. | Removed and ignored. | 31 MB |
| `.qoder/settings.json.bak` | Byte-identical backup of the active `.qoder/settings.json`. | Removed and ignored. | 4 KB |
| `dist/`, `playwright-report/`, `test-results/`, `backend/.pytest_cache/` | Ignored local build/test output that is reproducible from the documented commands. | Removed from the local workspace only. | ~7 MB |

> **Guardrail:** “Unreferenced” means absent from tracked application, test, workflow, and documentation text at the audit revision. It does not mean that an artifact is unimportant outside Git; retained or deferred items require an explicit archival decision.

## Retained and scheduled cleanup items

| Priority | Item | Finding | Required resolution |
|---|---|---|---|
| P0 | `book-to-skill` | A gitlink exists at the repository root, but `.gitmodules` contains no declaration. This makes fresh checkout behaviour ambiguous. | Recover a valid submodule declaration and pin, or remove the gitlink after confirming it is unused. |
| P1 | `askmukthiguru-official-launch-demo.mp4` and `video-composition/` | The launch-demo source is still referenced by `scripts/extract_keyframes.py`; the composition project is referenced by capture/verification scripts. | Decide whether the legacy production pipeline remains supported. If not, archive it externally, replace the script reference, and remove the source and generated assets together. |
| P1 | `results/`, `artifacts/db_data_quality_report.json`, and `chat_ui_screenshot.png` | These are tracked research, evidence, or visual-review outputs with no explicit retention manifest. | Add a provenance/retention README; retain only reproducible, decision-relevant artefacts and remove superseded snapshots in a separately reviewed change. |
| P1 | `video-composition/assets/` | Screens, keyframes, audio stems, and validation JSON support the retained legacy production project. | Keep while the production pipeline is supported; otherwise archive the complete source bundle outside Git rather than deleting isolated components. |
| P2 | Local developer environments | `node_modules/` (~599 MB) and `backend/.venv/` (~2.3 GB) are necessary local dependency installations, not repository content. | Recreate with `npm ci` and the backend environment setup when disk space is needed; never commit them. |
| P2 | Generated-report prevention | Existing ignore rules cover `dist/`, Playwright reports, test results, and pytest caches, but not all historical output patterns. | Keep the new ignores for screenshot output, temporary work directories, duplicate backups, and legacy rendered demos; review them when the video pipeline is formally retired. |

## Definition of clean

A clean checkout has no tracked disposable test output, compiled work directories, duplicate editor backups, or superseded rendered demos. Generated output is ignored and reproducible. Retained large assets have an explicit source or pipeline relationship. Any removal that affects an active workflow, a release asset, or research evidence must be carried out in a separate reviewed change with archival confirmation.

## Follow-up completed — book-to-skill removal

The undeclared `book-to-skill` gitlink was removed after verifying that the only tracked dependency was the unreferenced `scripts/generate_all_skills.py` helper. That helper, its Docker exclusion, and the nested external worktree were removed together. No application module, test, CI workflow, deployment configuration, or active documentation path referenced the integration.

## Follow-up completed — generated report separation

Reproducible evaluation reports now default to `artifacts/evaluations/`, which is ignored. The stale tracked evaluation reports, duplicate query-results export, data-quality report, and root-level E2E screenshot were removed. The E2E screenshot test now writes into the Playwright-managed per-test output directory. Retained `results/query_results.json` and `results/The_Four_Sacred_Secrets_structure.json` remain because active tests, documentation, or ingestion scripts reference them.
