# Open-work loop (updated 2026-11-28): read this first after any compaction or new session

Goal (owner): Railway healthy and cheap, many concurrent users served, nothing pending, everything documented.
Tests: read `docs/agent/KNOWN_TEST_FAILURES_AND_RUNNING_TESTS.md` before running or fixing any test.
Rule: a row closes only with evidence you ran. Every agent change gets an independent review before it ships. Agents cannot push (the owner pushes); never raise a guard baseline or the exception ceiling (759) without the owner. Scope (owner, 2026-11-27): never edit the `codex/evidence-platform-integration` checkout; work in a worktree on its own branch.

## State: the 2026-11-27 Railway review is MERGED and DEPLOYED
PR 121 merged to `main` as `850b49796` (CI green: PR head `51c5446fd` 9 passed, 0 failed; `main` Lint & Test success). Deployed to the backend by variable change (the backend source is pinned to `commitSha 285f2d4`, so pushes to `main` do NOT auto-deploy it; only celery auto-builds): `bcdee98f` (flag off), then `a5c02f48` with `HEALTHZ_REQUIRE_READY=true`. Both SUCCESS on `850b49796`.

Verified live 2026-11-28 (default domain `askmukthiguru-8119b0e8-production.up.railway.app`):
- `/api/healthz` 200; `/api/capabilities` 200, `ready: true`, `Cache-Control: public, max-age=60`, ETag, conditional GET 304; `/api/health` 200.
- Startup canary ran in production on both containers: 6 warmed, 0 failed, 1,951 ms and 1,141 ms.
- `/api/capabilities` stayed 200 at every sample during the gated rollout.
- First chat after the first deploy: 6.0 s (was 28-29 s before; ONE sample). A second question took 11.2 s (unexplained). Chats served the verbatim path (`first_person_bridge`, grounded, `model_used=None`).
- Memory 2.57 GB now, 2.59 GB hourly average (peak 3.89 GB during the deploy overlap); before the review it averaged 4.8 GB at 2 workers, 2.7 GB at 1.
- `scripts/ops/railway_live_audit.py`: exit 0, no warnings, no critical findings (celery worker aligned to the backend on 2026-11-28: posture `v13_shadow`, collections `first_person_v13_shadow`, scorer `anthropic/claude-haiku-5.5`, set with skipDeploys; the cron picks it up on its next run).
- Backend CI/tests before merge: full suite 15,835 passed, 0 failed, 77 skipped, 1 xfailed.

What shipped (all default-preserving; see ADR 0006 `docs/adr/0006-railway-cost-and-serving-efficiency.md`): scaling audit fixes (health probe cache, capabilities cache+ETag, telemetry consumer, bounded maps, to_thread, lazy sklearn), startup retrieval canary (after readiness), `HEALTHZ_REQUIRE_READY` readiness gate (ON in Railway), opt-in fast tokenizer (OFF), opt-in mmap-prepacked ONNX (OFF), opt-in shared model server (OFF), LLM seams (fixed-cost spend guard for self-hosted providers, `first_person_llm_provider`, opt-in `vllm` provider, scorer routing pins, refreshed cost table), load-test tooling (loopback only), live-config audit script, docs (ADR 0006, blog draft, scaling playbook with Phase 1/Phase 2 plan, self-hosted LLM research, known-test-failures doc).

## Open: owner decisions or actions (an agent cannot do these)
| # | Item | Why / next step |
|---|---|---|
| O1 | DNS: `api.askmukthiguru.com` returns NXDOMAIN though it is configured on the Railway service | add the record at the DNS provider; users cannot reach the app at that name until then |
| O2 | Rotate the HuggingFace token exposed in a reviewer session | huggingface.co/settings/tokens, then `HF_TOKEN` on Railway backend + celery-worker and local `backend/.env` |
| O3 | Delete Railway `first_person_v10` (4,224 pts, Railway-only; you said delete) | needs the Qdrant admin key; snapshot first. Prerequisite done: celery no longer points at v10 |
| O4 | Staged Railway change: add `META_APP_SECRET` to the backend (staged 2026-11-22, value hidden) | NOT applied: without it the WhatsApp webhook rejects every request with 403 in production (fail-closed), so WhatsApp is simply not live. Applying only the secret does nothing useful; also needs `META_APP_ID`, `META_ACCESS_TOKEN`, `META_PHONE_NUMBER_ID` (`docs/whatsapp/META_COEXISTENCE_ONBOARDING_GUIDE.md`) |
| O5 | Make the repo private | the nightly Supabase backup then works; CI minutes will cost money: trim CI first |
| O6 | `FIRST_PERSON_REQUIRE_SPEAKER_VERIFIED`: live false vs repo true | decide |
| O7 | Spend: raise `OPENROUTER_RPM_LIMIT` and caps before 1,000 users (live: 120 RPM, $15/day, $150/month = about 2,900 Haiku chats/day, modelled); resume Railway for the load matrix | see `docs/operations/scaling-playbook-2026-11-27.md` |
| O8 | Product: `useMetrics` shows the previous user's cached metrics for an instant after a user switch if the auth-transition reset does not fire | start with `loading=true` until the session resolves? (test fixed, behaviour unchanged) |
| O9 | Safety: exempt the distress LLM escalation from RPM-limiter waits so its extra recall survives overload (regex floor is unaffected) | needs safety review + owner decision |
| O10 | Human gates: distress/native-speaker/clinician reviews, 299-pair gold labels, faculty invitations, speaker + rights sign-offs, helpline calls | `CLAUDE.md` "Human Operational Next Steps" |
| O11 | Supabase: apply migrations `20261126000100`, `20261126120000`, `20261128053858` to the real project; flip `editorial_persistence_enabled`, `seeker_comprehension_recovery_enabled` | not done by an agent |
| O12 | Celery `CREATE_CONTAINER` failures (deployment `a0d03c30-a3bc-4686-a8e8-a0fced23f188`) | last 3 celery deployments succeeded (2026-11-28); ticket optional |

## Open: engineering, not blocked on the owner
1. **Tokenizer swap stays OFF** until `scripts/ops/verify_fast_tokenizer_in_image.sh` shows 0 skipped on transformers 5.x (needs more than 3 GB free Docker VM memory). Then trial `ONNX_TOKENIZER_BACKEND=tokenizers`.
2. **mmap-prepacked trial** (`ONNX_MMAP_PREPACKED_ENABLED`): baseline 24 h of Railway memory, enable with `ONNX_PREPACKED_CACHE_DIR=/tmp/onnx_prepacked`, pass criteria: embeddings `np.array_equal`, smoke query verbatim, memory at least 200 MB lower in Railway's metric (page-cache billing and x86_64 behaviour UNVERIFIED), no restart loop, boot within budget; rollback = unset. Backend has no volume (ephemeral disk; a 1 GB volume is about $0.15/month if needed).
3. **Model server** real memory/latency numbers (`scripts/ops/measure_model_server.py`, needs 4 GB free); lazy `llmlingua` import (`rag/compressor.py:81`) so the API process stops importing torch.
4. **Load matrix on Railway** (15/30/60 msgs/min for 10 min + a burst of 100 in 5 s) once Railway spend is approved; replaces every MODELLED capacity number. Also record MEASURED tokens/cost per chat.
5. **Open-weight scorer shadow run** through OpenRouter (Phase 1 of the playbook plan) with the scorer pins set (`first_person_scorer_*`), via the registered graded-run machinery. vLLM only if residency, a latency target, or about 30,000 chats/day requires it.
6. **Replace the Llama-3.1-8B distress/classify model** (its card lists Hindi as the only Indic language): safety evaluation first.
7. Gaps found and NOT fixed: with a misconfigured non-default provider, a crisis message that slips past the regex gets the bridge's static decline instead of helplines; `NimService` keeps its own Sarvam/OpenRouter fallbacks; the model-keyed scorer schema branches must be extended deliberately for any new scorer model id.

## Environment risk
Other sessions run `codex-*` compose stacks; the Docker VM is memory-starved (about 0.7-1.8 GB free) and `mukthiguru-backend` was OOM-killed twice on 2026-11-27 by measurement runs. Check `docker stats --no-stream` first; never touch `codex-*` containers or restart `mukthiguru-backend`; use the host venv for tests.
