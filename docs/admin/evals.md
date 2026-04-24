# Evals — golden dataset + regression testing

## Golden questions

Stored in `golden_questions`. Each row:
- `question` — what to ask the assistant
- `expected_answer` — reference answer used by the judge as ground truth
- `expected_sources` — sources that should be retrieved (used for `context_recall`)
- `tags` — for slicing (e.g. `meditation`, `beautiful_state`)
- `active` — only active questions are run

## Regression run

`runEvalSuite(triggered_by)`:
1. Snapshot the active prompt version
2. For each active golden question, call the assistant exactly as a user would
3. Run the same judge (see `backend-integration.md`) over `(question, retrieved_context, answer, expected_answer)`
4. Insert `eval_results`, then `eval_runs.summary`

Triggers:
- `manual` — button on `/admin/evals`
- `prompt_change` — fired when `activatePromptVersion` runs
- `scheduled` — see below

## Scheduling

Until `pg_cron` is confirmed available on Lovable Cloud, use an external
scheduler (cron-job.org, GitHub Actions, EasyCron) hitting:

```
POST /api/public/cron/evals
X-Cron-Signature: <hmac-sha256(body, CRON_SECRET)>
```

The endpoint verifies the HMAC, then runs `runEvalSuite("scheduled")`.

## Regression diff

The `/admin/evals` page shows Δ vs the previous run for `avg_faithfulness`,
`avg_answer_relevancy`, etc. Green ↑ = improvement, red ↓ = regression.
