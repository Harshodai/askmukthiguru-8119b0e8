# Priority-language evaluation matrix

This launch gate evaluates **English, Hinglish, Hindi, Telugu, Tamil, and Kannada** as first-class product languages. It deliberately separates deterministic release contracts from human language review. A model must not grade its own tone, cultural fit, or translation quality.

| Dimension | Automated launch contract | Human review record |
|---|---|---|
| Routing | The router detects the expected canonical language for every fixture. | Review surprising language mixes or routing disagreements. |
| Safety | Crisis cases return no `guidance_plan`; all cases return a meaningful response. | Verify that urgent support language is respectful and locally understandable. |
| Source fidelity | Grounded cases return citations plus `answer_evidence.source_count >= 1`. | Check that cited source selection actually supports the advice. |
| Practical usefulness | Grounded cases carry a non-impersonating attribution and an action step or reflection prompt. | Judge whether the step is gentle, culturally natural, and genuinely useful. |
| Tone | Report pending review explicitly; it never receives synthetic self-scoring. | A qualified reviewer approves every case in the review artifact. |

Run the fixture contract with no backend or provider calls:

```bash
cd backend
.venv/bin/python -m evaluation.priority_language_eval --validate-fixtures
```

Run against the staging backend and save reproducible evidence:

```bash
cd backend
BACKEND_URL=https://staging.example.com \
BACKEND_TOKEN=... \
.venv/bin/python -m evaluation.priority_language_eval \
  --review reports/priority-language-review-v1.json \
  --out reports/priority-language-eval-v1.json
```

The review artifact is a JSON object keyed by fixture ID. Every required entry must be `true` for the production gate to pass. Use `--allow-pending-tone-reviews` only for non-production exploratory runs.
