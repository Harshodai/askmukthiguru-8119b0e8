### L-PINNED-DATASET-BYTES-1 (2026-10-08): a whitespace hook silently broke a sha256-pinned eval dataset
Root cause: commit df6f1fa0 ran pre-commit end-of-file-fixer over backend/evaluation/datasets/first_person_bakeoff_2026-09-25.json, adding one trailing newline. first_person_harness.QUESTIONS_SHA256 pins the exact bytes, so the harness refused to load the question file (test_pinned_question_file_loads_and_has_fixed_denominator failed). The commit message said "JSON content verified identical", which was true for parsed JSON and false for bytes.
Rule: pinned artifacts are byte contracts, not JSON contracts. Formatting hooks exclude backend/evaluation/datasets/. Restored the exact bytes from d1e9d019 rather than re-pinning the hash.
Test: backend/tests/test_first_person_harness.py::test_pinned_question_file_loads_and_has_fixed_denominator (failed before, passes after).

### L-RAIL-SWALLOWS-CRISIS-1 (2026-10-08): a topic block must never hide a crisis
Root cause: InputGuardrailStage runs before DistressStage and deferred only the `self_harm` topic. Every other block (medical_prescription, politics, harmful_pattern, the wellness redirect) was terminal, so "I don't need my meds anymore, everyone would be better off without me" (CRISIS by assess_distress) got only the medical refusal: no check-in, no helplines. WP2's wider medical and party-name patterns made it easier to hit; the class predates WP2.
Rule: on any rail block, assess distress on the texts DistressStage reads (user_msg_en and raw). At SEVERE+ defer, set `guardrail_block_deferred_to_distress`, and DistressStage holds the level at SEVERE+ with no LLM downgrade. The pre-check fails closed (error = defer).
Test: backend/tests/test_guardrail_block_defers_on_distress.py (4 failed before, 6 passed after).
