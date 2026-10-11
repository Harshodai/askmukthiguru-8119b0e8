# gold_set_v1: human labels for the first-person clip route

Built 2026-10-11 against Qdrant collection `first_person_v8` (1,801 points). **No labels are
filled in.** Every question is AI-written (`synthetic: true`). The CLAUDE.md invariant 3 still
holds: no threshold may be fitted on AI-authored labels.

## What is in the package

| file | for whom | what |
|---|---|---|
| `questions.jsonl` | owner | Line 1 is a header. Then 205 questions: 150 on-topic (14 themes, forms `what_is / why / how_do_i / statement / keyword / yes_no / translit`, 12 in Hindi, Tamil or Telugu transliteration), 40 out-of-corpus decoys (`ooc`) and 15 adversarial probes. `real_seeker_text` is a blank column: fill it to replace a question with a real seeker's wording, or append rows with `synthetic: false`. |
| `pairs.csv` | owner | 505 rows. Each on-topic question has its top-3 retrieved clips (450 rows). Each decoy or adversarial question has its retrieval top-1 (55 rows). Order is shuffled with seed `20261011`. `assignment` is A (202), B (202) or A+B overlap (101, 20%). |
| `annotator_A.csv`, `annotator_B.csv` | annotators | 303 rows each, with blank label columns. These are the only files annotators get. |
| `pairs_scores.csv` | owner / scripts | System scores per `pair_id`: `dense_cosine`, `rrf_score`, ranks, `rail_blocked`/`rail_reason`, `shown_by`. **Never give this to annotators**, because seeing ranks biases labels. |
| `LABELING_GUIDE.md` | annotators | The rubric, worked examples (AI-labelled, marked as illustrations only), the protocol, and a wellbeing note. |
| `build_pairs.py` | owner | Regenerates the sheets. Read-only against Qdrant, and runs host-side. |
| `score_gold.py` | owner | Kappa, agreement, confusion and disagreements on the two filled sheets, then exports the adjudicated `labels_human.jsonl`. |
| `fit_threshold.py` | owner | Fits the 1%-risk threshold with `backend/evaluation/gold/calibrator.py` (reused unchanged). |
| `test_gold_tools.py` | CI | pytest on synthetic data. |

Retrieval is the production path, reused from `.work/autoresearch_fp/build_cache.py`:
- `encode_single_full`, then `search_hybrid(limit=80, dedup_limit=40)` with the teacher filter;
- then the integrity gate and the content-quality gate. The CQ gate is ON in production, so clips that fail it can never be served.

The serve-time LLM answerability and relevance gates were **not** run. Decoy and adversarial rows therefore show the clip the system would show *if those gates let it through*.

## Workflow

1. **Hand out** `annotator_A.csv` to one annotator and `annotator_B.csv` to the other, each with `LABELING_GUIDE.md`. Optionally, replace weak synthetic questions first by filling `real_seeker_text`, then re-run
   `cd backend && .venv/bin/python3 ../evals/gold_set_v1/build_pairs.py`.
2. **Score agreement**:
   `backend/.venv/bin/python3 evals/gold_set_v1/score_gold.py A_filled.csv B_filled.csv`.
   - Target: kappa >= 0.6 on every dimension.
   - If kappa is below that, re-brief the annotators on the guide and relabel the overlap before going further.
3. **Adjudicate**. A third person fills the `adj_*` columns of `disagreements.csv`. Then re-run with
   `--adjudicated disagreements.csv` to export `labels_human.jsonl`.
4. **Double-label the positives.** Every exported row that is SHOW-worthy (relevance >= 2, complete, no risk, speaker yes) but has `n_annotators: 1` gets a second label before it is used in step 5. One person's error rate is above 1%.
5. **Fit**:
   `backend/.venv/bin/python3 evals/gold_set_v1/fit_threshold.py --labels labels_human.jsonl --unit top1 --min-annotators 2 --profile-out profile.json`.
   - It prints `insufficient labels` (exit 2) below the 299-item zero-error minimum.
   - It prints `no operating point` (exit 3) if no threshold clears the bound. Note: rail-blocked decoy/adversarial rows count as errors even though production never serves them (conservative, not unsafe).

## Effort (2 annotators)

| task | estimate |
|---|---|
| Labelling, at about 1.5-2 min per row (read the text, listen to the first 10 s, decide) | 303 rows each, so **8-10 h per annotator, 16-20 h in total** |
| Adjudication, at about 30 disagreements x 2 min | **about 1 h** |
| Second labels for single-labelled positives (step 4), at about 60-100 rows | **about 2-3 h** |

Total: **about 20-24 annotator-hours.**

## What it unlocks, and what it does not

- **Unlocked: honest precision.** The human-measured precision of today's top-1 and top-3, per theme. This replaces the AI-judged numbers in `.work/autoresearch_fp/`.
- **Unlocked: inter-annotator agreement.** This tells you whether the rubric is learnable at all, and how far the AI judge sits from humans: compare `labels_human.jsonl` with `.work/autoresearch_fp/labels.jsonl`.
- **Unlocked: decoy and adversarial false-show rate** at retrieval level.
- **Not unlocked: a 1% calibration profile.** The served unit is the top-1 clip per question, and this package has only 205 top-1 items, below the 299 minimum. Worse, the AI judge put only **6 of 29** top-1 clips at SHOW (about 21%), and the selected set must hold at least 299 *correct* items with zero errors. At that base rate you need roughly **1,450+ labelled top-1 questions**, and more if scores separate imperfectly. `--unit pair` reaches 505 items, but a pair-fitted threshold must not be shipped against a top-1 serving rule. Treat v1 as the seed and the rubric test. Direct answers (`is_direct_answer=True`) stay off until a later, larger set passes `fit_threshold.py`.

## Retrieval observations from the build

- **Dense cosine separates poorly.** Median top-1 cosine is 0.653 for on-topic questions, 0.597 for decoys (max 0.700) and 0.654 for adversarial probes, so a cosine-only threshold would admit many decoys.
- **Clips repeat.** There are 273 distinct clips across 505 rows, and the most-repeated clip appears 13 times. Speakers are skewed: Krishnaji 358 rows, Preethaji 147.
- **Possible crisis-rail false positive.** "I feel empty inside even though I have everything" (q010) trips the crisis rail. Production would redirect it, not answer. It is still labelled here.
