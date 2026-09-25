"""Human gold-set tooling for the first-person verbatim answer path (B1).

See ../../../docs/agent/B1_gold_set_protocol.md for the review protocol this
package implements. Modules:

- split.py     deterministic video-level held-out split
- sheets.py    blank label-sheet builders (question authoring, relevance
               judging, transcript gold) — never pre-fills a label
- agreement.py Cohen's kappa, confusion matrix, adjudication merge
- metrics.py   precision/coverage/abstention/top-k/wrong-speaker/timestamp
               error/verbatim-mismatch + Clopper-Pearson bound + clustered
               bootstrap, ported from the bake-off scoring.py/scoring_lib.py
"""
