# Known test failures, flakes, and how to run the suite

**Read this before running tests or "fixing" a red test.** Last verified 2026-11-27 on the integrated branch `chore/railway-live-audit-2026-11-27`: full backend suite on the host = **15,773 passed, 1 failed, 77 skipped, 1 xfailed, 2 deselected** in 346 s. Add a row when you find a new one, with evidence; delete a row when it is fixed.

Rules: never weaken, delete or skip a test to make it green. Never raise a guard baseline or the exception ceiling (759) without the owner. Before blaming your change for a red test, rerun it on clean `origin/main` in a temporary worktree (`git worktree add --detach <dir> origin/main`, then remove it).

## How to run

```bash
cd backend && .venv/bin/python -m pytest -p no:cacheprovider -q          # full suite, ~6 min on the host
cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_x.py   # one file
npm test -- --run                                                        # frontend (vitest)
```

- Use a **single `-q`**. `-q -q` suppresses pytest's summary line (passed/failed counts), which hid the result once.
- Use the **host venv** (`backend/.venv/bin/python`). Do not run the full suite or model-loading tests inside Docker while the Docker VM has little free memory: on 2026-11-27 measurement runs OOM-killed `mukthiguru-backend` twice (VM had 0.7 to 1.8 GB free, swap empty, other sessions' `codex-*` stacks running). Check `docker stats --no-stream` first; never touch `codex-*` containers or restart `mukthiguru-backend`.
- Run ruff **from `backend/` with relative paths** (CI pins ruff 0.15.13). Running it from the repo root with absolute paths produced garbage output.
- In **zsh**, an unquoted `$VAR` holding several paths is NOT split into arguments. Use `$(cat list.txt)` or an array.
- Start long runs with `run_in_background` and wait for the process; a launcher shell exiting is not the suite finishing.
- Commits run an i18n parity pre-commit hook. If it fails on stale locale keys, run `npm run i18n:sync`; a new UI key must be added to `src/locales/en.json` first. Never `--no-verify`.

## Expected skips (not failures)

- 6 cases in `tests/test_fast_tokenizer_equivalence_2026_11_27.py`: the host venv has `transformers` 4.57.6 and serving uses 5.19, so the 5.x cases skip. Closing this needs the in-image run: `scripts/ops/verify_fast_tokenizer_in_image.sh` (refuses below 3 GB free VM memory).
- 6 cases in `tests/test_model_server_equivalence.py`: they need the real models and only run in the backend image.

## Known failing or flaky tests

| Test | What happens | Evidence (2026-11-27) | What to do |
|---|---|---|---|
| `tests/test_first_person_async_lane.py::test_c20_async_lane_does_not_starve_the_executor` | Load-sensitive timing flake: asserts no asyncio slow-callback warning ("Executing … took 0.126 seconds", threshold 0.1 s). | Clean `origin/main`: passed 1 of 2 runs, failed 1 of 2. Integrated branch: failed 3 of 3 alone and once in the full run, with other sessions' Docker stacks loading the host; passed in an earlier full run. | Treat as a flake on a loaded host. Rerun when the machine is quiet. Do not "fix" by raising the threshold without the owner. |
| `tests/test_flashrank_rerank.py::test_rerank_with_flashrank` | `assert len(results) == 2` gets 1: the reranker threshold (0.1) filtered one doc ("Keeping top-1, score 0.0122"). | Fails on clean `origin/main` locally and with either `ONNX_TOKENIZER_BACKEND` value when run alone; passed inside one full-suite run (order/state dependent). CI status of this test was not checked. | Pre-existing; not caused by the tokenizer or scaling changes. Investigate separately. |
| `tests/test_contradiction_resolver.py::TestGenerateAnswerMetadataPropagation::test_generate_answer_propagates_conflict_metadata` | Order-dependent: failed once inside a ~890-test batch. | Passes alone (18 passed). | Run it alone to confirm before treating as a regression; likely shared state with another test. |
| `tests/test_metrics_reachability.py` | Reports "checked 0 files" when run from a git worktree under `.claude/`, because it skips paths containing `.claude/`. | Seen by the scaling-audit agent in `.claude/worktrees/…`. | Run it from the main checkout or a worktree outside `.claude/`. |
| `tests/test_supabase_types_lint.py` | Fails if `src/integrations/supabase/types.ts` lists a table with no migration. | The out-of-band production table `user_brain_keys_archive_20261119` (archived wrapped keys) is re-added whenever types are regenerated from prod. | Remove that block from `types.ts`. Do not add a migration for it. |
| `tests/test_guru_literal_scan.py::test_baseline_matches_the_tree` and `scripts/guards/guru_literal_guard.py` | Fail when `scripts/guards/guru_literal_baseline.txt` is stale ("now 0, baseline 1" for `src/pages/ChatPage.tsx` and `src/pages/guides/SereneMindPracticePage.tsx` on some branches). | Seen on agent worktrees branched from older commits; PR 121 lowered the baseline from 574 to 572. | Lower the baseline to match (never raise it). |
| Frontend `i18n-sync` / `i18nKeysInEnglish` vitest tests | Fail on a stale or missing locale key. | Brevo changes used 11 keys with no `en.json` entry. | Add the keys to `src/locales/en.json`, then `npm run i18n:sync`. |

## Guards that must stay green

`scripts/guards/config_lint.py`, `scripts/guards/exception_ratchet.py` (ceiling 759), `scripts/guards/pipeline_order_guard.py`, `backend/tests/test_settings_guards.py`, `backend/tests/test_repo_layout.py`.
