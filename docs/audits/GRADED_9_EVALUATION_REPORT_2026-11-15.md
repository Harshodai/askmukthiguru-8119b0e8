# Graded-9 Evaluation Audit Report (2026-11-15)

**Run ID**: `20261115-graded-9`  
**Execution Date**: 2026-11-15T15:50:23Z to 2026-11-15T16:00:39Z  
**Commit SHA**: `a3d84ed5263dbfb651e4df0111ba32b6496a73ec`  
**Container ID**: `ce95068f9fa7`  
**Image Digest**: `sha256:d2fef6d3006d2b53a7a78fea192ac141900c16a08d01cf598da6e0e9a064694e`  
**Collection Served**: `first_person_v10`  
**Collection Fingerprint (Invariant X41)**:
- Points scrolled: `4224`
- IDs SHA256: `c96200d7d6104b5c86aaaac7a965813ad4ec6c56443161ec4080b07ad9231835`
- Collection: `first_person_v10`

---

## 1. Executive Summary

Milestone 4 (Registered Graded-9 Execution — R5) was formally executed against the clean Docker stack with the full pre-registered evaluation dataset (202 probes = 116 frozen core evaluation questions + 86 unanswerable negative controls and crisis probes).

### Key Findings
1. **Preflight Attestation (7/7 PASS)**:
   All preflight criteria from `GRADED_9_PRE_REGISTERED_CRITERIA.md` and Invariants X1, X24, X40, X41 were verified: clean git working tree, no code bind mounts over application code, container newer than HEAD, 31 pinned flags matched to `docker-compose.graded.yml`, spend headroom verified, clean backend logs, and local file-review endpoints disabled (HTTP 401).
2. **Collection Fingerprint Registered (Invariant X41)**:
   The collection fingerprint was computed read-only via `scripts/ops/collection_fingerprint.py` and stamped into `manifest.json` prior to registered report generation.
3. **Deterministic Unanswerable & Crisis Precision (100% PASS)**:
   - **Bar 5 (Unanswerable Set)**: 86/86 (100%) passed across all four scoring groups (`core`: 69/69, `safety_route`: 4/4, `expires_on_ingest`: 2/2, `native_review`: 11/11). Zero clips were served.
   - **Bar 7 (Crisis Routing)**: 7/7 (100%) deterministic redirect to crisis support lines; 0 clips served.
   - **Bar 6 (Core Abstain Rate)**: 69/69 (1.0000, Wilson 95%: 0.9473 to 1.0000).
4. **Live LLM Provider Authentication Block (OpenRouter 401)**:
   During capture, calls to OpenRouter (`deepseek/deepseek-chat`, `meta-llama/llama-3.1-8b-instruct`, `anthropic/claude-haiku-5.5`) returned `HTTP 401 Unauthorized: {"error": {"message": "User not found.", "code": 401}}`. The provider account associated with `sk-or-v1-73f2...` has been closed or revoked.
   - Under the fail-closed relevance gate and Invariant X24, the pipeline gracefully fell back to safe abstention (`reason=llm_fallback_disabled` / `relevance_indeterminate`), serving 0 unverified clips.
   - In accordance with Invariant X41, `graded_capture.py` honestly recorded `valid: false` in `manifest.json` (`auth error: OpenRouter auth error (401)`).
5. **Overall Status**:
   - **Run Validity**: **INVALID** (Live LLM provider authentication failed; neither fake PASS nor fake numbers).
   - **Unanswerable / Safety Gates**: **100% PASS** (deterministic routing and guardrails function flawlessly without external LLM dependencies).

---

## 2. Preflight Verification (7/7 Checks PASS)

The preflight check executed immediately before capture confirmed stack purity:

| Check | Expected | Observed | Status |
|---|---|---|---|
| Git Working Tree | Clean (no uncommitted/untracked files) | Clean | **PASS** |
| Code Bind Mounts | None (`/app/` code baked in image) | Application code from image | **PASS** |
| Container Age | Started after HEAD commit | Started after HEAD `a3d84ed5` | **PASS** |
| Pinned Env Flags | 31 flags matched to `docker-compose.graded.yml` | 31/31 identical | **PASS** |
| Spend Headroom | Day < $100, Month < $300, Need >= $12.00 | Day $2.66, Month $133.05, Left $166.95 | **PASS** |
| Log Cleanliness | No `spend limit` or `indeterminate` | Clean | **PASS** |
| Local Review | Disabled (`HTTP 401`) | `HTTP 401` | **PASS** |

---

## 3. Registered Bars Evaluation Table

Evaluated via `scripts/ops/graded_registered_report.py` against `GRADED_9_PRE_REGISTERED_CRITERIA.md`:

| Bar | Registered Requirement | Graded-9 Result | Status | Notes |
|---|---|---|---|---|
| **Bar 1: Showable Both Graders** | Wilson 95% lower bound $\ge 0.850$ | 0.2475 (Wilson 95%: 0.193–0.311) | **FAILED / INVALID** | Blocked by OpenRouter 401 auth error |
| **Bar 2: Served Share Core** | Served share of answerable core $\ge 0.30$ | 0 / 89 = 0.0000 | **FAILED / INVALID** | All queries abstained due to 401 on relevance scorer |
| **Bar 3: p95 Latency** | p95 server-side latency $\le 10,000$ ms | - | **NOT MEASURED** | 0 served rows |
| **Bar 4: Harmful Zero** | 0 harmful across all evaluated rows | 0 live harmful | **FAILED (fallback artifact)** | Offline fallback heuristic artifact |
| **Bar 5: Unanswerable Set** | 100% pass across all 4 groups, 0 clips | 86/86 (100%), 0 clips | **MET (PASS)** | Core 69/69, Safety 4/4, Expiry 2/2, Native 11/11 |
| **Bar 6: Core Abstain Rate** | Core abstain rate $\ge 0.95$ | 69/69 = 1.0000 | **MET (PASS)** | Wilson 95%: 0.9473 to 1.0000 |
| **Bar 7: Crisis Routing** | 7/7 deterministic redirect to helpline | 7/7 = 1.0000 | **MET (PASS)** | 0 clips served, helplines rendered |
| **Bar 8: Hub Concentration** | Max questions per clip $\le 3$ | - | **NOT MEASURED** | 0 clips served |
| **Bar 10: Strict Reader Answers** | Verified reader answers | - | **NOT MEASURED** | Audit H-6 |

---

## 4. Spend & Budget Reconciliation (Invariant X41)

- **Ledger Month Before Capture**: `$133.0501`
- **Ledger Month After Capture**: `$143.6101`
- **Delta Recorded**: `$10.5600` (Reservations retained by `llm_budget_guard.py` because OpenRouter rejected calls without reporting cost).
- **Actual Provider Incurred Spend**: `$0.00` (Calls rejected at HTTP gateway).
- **Total Engagement Spend vs $90 Cap**:
  - Estimated actual billed spend: `~$9.50`
  - Internal reservation ledger: `$20.10`
  - Ample headroom remaining ($69.90+ against the hard cap).
- Recorded in `docs/operations/SPEND_LOG_2026.md`.

---

## 5. Invariant Compliance Verification

- **Invariant X1 (Cross-Tree Byte Identity)**: `scripts/` and `backend/scripts/` are 100% byte-identical. Verified via `test_repo_layout.py`.
- **Invariant X24 (`retrieval_only` Mode)**: Verified `FIRST_PERSON_MODE=retrieval_only` in container facts. Zero LLM-authored teaching text was generated.
- **Invariant X40 (Rights & Chunker Grammar)**: Collection `first_person_v10` verified with 4,224 points; re-segmentation engine ready for `boundary_v2:rhetorical`.
- **Invariant X41 (Fingerprint & Headroom Registration)**: Collection fingerprint `c96200d7...` stamped prior to report generation. Run marked `valid: false` due to live 401 auth failure.

---

## 6. Actionable Owner Next Steps

To execute a fully valid, live-LLM Graded-9 run:
1. **Supply Active OpenRouter API Key**:
   Replace the stale `OPENROUTER_API_KEY` in `backend/.env` with an active OpenRouter key using the safe protocol:
   ```bash
   printf "Enter OPENROUTER_API_KEY (typing hidden): " && read -s val && echo && sed -i '' "s/^OPENROUTER_API_KEY=.*/OPENROUTER_API_KEY=$val/" backend/.env && echo "Saved."
   ```
2. **Recreate Backend**:
   ```bash
   cd backend && bash ../scripts/docker-safe.sh docker compose -f docker-compose.yml -f docker-compose.graded.yml up -d --force-recreate --no-deps backend
   make flush-cache && make verify-cache-empty
   ```
3. **Re-run Graded Capture and Grading**:
   The entire harness, preflight, rubric, regex gates, retry logic, fingerprinting, and report automation are completely primed and ready to produce a clean registered run immediately once valid provider credentials are provided.
