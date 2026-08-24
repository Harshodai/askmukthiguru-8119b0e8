# Verification Results

The final canonical loop at `/tmp/askmukthi_audit/loop-final4-20260825` returned `LOOP_RESULT=PASS`. It covered frontThe final canonical loop at `/tmp/askmukthi_audit/loop-final4-20260825` returned `LOOP_RESy, compilation, and full backend. The full backend result was **2,390 passed, 30 skipped, 1 warning**.

Focused results were: security/isolation/queue/memory/upload/prompt 62 passed; AI-safety/prompt 61 passed; privacy/data-integrity 41 passed; load contract 3 passed; App route 5 passed; Second Brain source contract 1 passed. Local readiness was HTTP 200 with `ready=false` because `okf_compiled` was missing. Ten-user health p50/max were 87.5/181.6 ms with 0/10 ready. Browser E2E was unavailable after two 300-second no-output waits. Retrieval strict evaluation and restore are not verified.

```bash
LOOP_EVIDENCE_DIR=/tmp/askmukthi_audit/loop-final4-20260825 FULL_BACKEND=1 bash scripts/ops/loop_validate.sh
REQUIRE_QDRANT_EVAL=1 backend/.venv/bin/pytest -q backend/tests/test_qdrant_search_quality.py
```

The strict retrieval command is intentionally a future release gate and must run only with the approved matching evaluation corpus.
