# Agent Playbook — driving Mukthi Guru to production

**For the next agent picking this up.** This is the *how*. The *what* lives in:

| Doc | Holds |
|---|---|
| [`RUTHLESS_PRODUCTION_EXECUTION.md`](RUTHLESS_PRODUCTION_EXECUTION.md) | Canonical audit record: fixes R1-R22, backlog B1-B23, live measurements, self-corrections. **Where this file disagrees with it or with the source, they win.** |
| [`../handoff.md`](../handoff.md) | Session narrative, the loop-to-GO table (8 exit criteria), what was tried and failed |
| [`RAG_RUNTIME_DAG.md`](RAG_RUNTIME_DAG.md) | Actual runtime graph, stages dead on the live config, open serialization findings |
| [`../CLAUDE.md`](../CLAUDE.md), [`../backend/CLAUDE.md`](../backend/CLAUDE.md) | Auto-loaded repo constraints. Read before editing |

Read the first two before starting. Don't work from this file's summaries.

## 1. Bring the stack up

```bash
# infra only — leave the host supabase-* containers alone, this project needs them
cd backend && bash ../scripts/docker-safe.sh docker compose up -d qdrant redis neo4j

# backend runs on the HOST (the container OOMs 137 at 6G — B20).
# backend/.env points at Docker-internal hostnames; override for host mode:
REDIS_PW=$(grep -E '^REDIS_PASSWORD=' .env | cut -d= -f2-)
env QDRANT_URL=http://localhost:6333 NEO4J_URI=bolt://localhost:7687 \
    REDIS_URL="redis://:${REDIS_PW}@localhost:6379/0" \
    .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`curl -s localhost:8000/api/health` must show `ready: true`. There is no
`--reload`: **restart after every code change** or you measure the old build.

## 2. Measurement discipline

Every rule below was violated at least once and produced a confident, wrong
finding. They are not style preferences.

1. **Never measure latency while anything else heavy runs on the host.** A
   background `pytest` run inflated one `retrieve_documents` call from ~1s to
   91.5s — embedding inference holds a process-wide `threading.RLock`
   (`services/embedding_service.py:116`). Re-measured clean, the spike vanished.
2. **Never A/B test with concurrent queries.** Same confound: 3 concurrent
   comparative queries made the *improved* build look 25s slower.
3. **Server-side `latency_ms` is authoritative**, not wall clock (which includes
   queue wait and poll granularity).
4. **Fresh anon token per query.** `anon_quota_messages=5`; reuse one and query
   #6 silently 429s. A 429 has no `poll_url` — a harness that counts it as a
   fast success drags the median down ~6x (it did).
5. **Don't nonce-suffix a query meant to hit a short-circuit.** `GREETING_RE` is
   anchored `^...$`, so `"hello (ref 123)"` is not a greeting and pays full
   pipeline cost. That one harness bug produced a bogus "hello costs 6.1s" P0
   that survived two sessions.
6. **Check which implementation is live before patching it.** The live
   provider is `LLM_PROVIDER=openrouter` ⇒ `OpenRouterService`; `sarvam_cloud`
   and `ollama` map to two other separate, non-inheriting classes. A fix
   applied to the wrong one measures as "no improvement" rather than "never
   executed" — this happened twice in one session, once because the provider
   itself changed mid-work. Re-read `backend/.env:7` before trusting any
   provider assumption, including this sentence.
7. **n=1 is a data point, not a percentile.** Label it. Comparative queries vary
   ~10% run to run even isolated.

## 3. Two-way test proof — required for every fix

```bash
git stash push -- <source file(s)>     # remove fix, keep test
.venv/bin/pytest tests/test_x.py -q    # MUST FAIL, for the right reason
git stash pop
.venv/bin/pytest tests/test_x.py -q    # MUST PASS
```

No `pytest-timeout` plugin (`--timeout=` errors). `| tail` swallows exit codes —
use `echo "EXIT=${PIPESTATUS[0]}"`.

Never claim fixed because a test was added. Never silence a failing test. Never
trust a doc over executable truth — several `CLAUDE.md` claims were stale and
are corrected in the audit record.

## 4. Evidence labelling

Every finding carries one: `PROVEN FROM CODE` (file:line) · `MEASURED` ·
`PROVEN FROM LIVE` · `INFERRED` · `REQUIRES LIVE VALIDATION`. When you disprove
an earlier finding — **including your own** — record the correction rather than
deleting the claim. Several findings were escalated wrongly, then walked back
with measurements; that trail is the point.

## 5. Skills, plugins, subagents

Verify by listing dirs if this looks stale.

| Use | What |
|---|---|
| Broad search (>3 queries) | `Explore` subagent; `code-review-graph` / `graphify` / `serena` MCP for symbol lookups (see `CLAUDE.md` → MCP Tooling) |
| Review a change | `ecc:code-reviewer`, `ecc:python-reviewer`, `ecc:fastapi-reviewer`, `ecc:security-reviewer`, `ecc:silent-failure-hunter` |
| Perf | `ecc:performance-optimizer` — but do your own measuring per §2 |
| Tests | `ecc:tdd-guide`, `ecc:pr-test-analyzer`, `ecc:e2e-runner` |
| Docs/codemaps | `ecc:doc-updater`, `/ecc:update-docs` |
| Literature research | `/hyperresearch <query>` (16-step pipeline). Heavy — real research questions only |
| Domain reading | `.agents/skills/`: `rag-made-simple`, `system-design-llm-era`, `designing-data-intensive-apps-2e`, `llms-in-production`, `supabase-postgres-best-practices` |
| Code conventions | `.claude/rules/ecc/common/common-skills.md` — clean-code skills are mandatory here |
| Session hygiene | `/ecc:strategic-compact` at milestones; `/caveman`, `/ponytail` output modes |
| Branch review | `/code-review ultra` — user-triggered and billed; you cannot launch it |

`.claude/skills/mukthiguru-change-control/` is an **empty directory** — a skill
in name only. Don't expect it to do anything.

**Cost matters.** These sessions hit repeated `COST CRITICAL` warnings. Prefer a
targeted `grep` over a subagent fan-out; reading code over re-running a 112s
live query; one clean measurement over three noisy ones.

## 6. When to web search

Do it — this repo's own conclusions have been wrong, and outside evidence is
cheap next to a live LLM round trip. `WebSearch`/`WebFetch` are deferred: load
with `ToolSearch` (`select:WebSearch,WebFetch`) first.

Use it for:

- **Model/technique tradeoffs before changing an architecture decision.** Worked
  example (B23): before proposing `rewrite_query` drop to the fast model, a
  search surfaced Ma et al. 2023
  ([arXiv:2305.14283](https://ar5iv.labs.arxiv.org/html/2305.14283)) — a 770M
  trainable rewriter matched/beat frozen ChatGPT on AmbigNQ/HotpotQA. Reframed
  the change from "risky downgrade" to "the established pattern" — while still
  needing local validation.
- **Library/API behaviour you're about to rely on** — especially `asyncio`
  cancellation, LangGraph join semantics, Qdrant/Neo4j client timeouts. Several
  bugs here are the "the timeout doesn't actually bound a blocking call" family.
- **CVE / dependency checks** (§14 of the original brief — still never run).

Cite what you find, and say plainly when literature supports a hypothesis but
does **not** prove it for this system.

## 7. Where the work stands

Pushed: **R1-R21** (`39a9d4e4`). In the tree: **R22** (latency, verified),
**B23 groundwork** (A/B toggle, no default change), and the **canonical memory**
feature (separate session, now complete).

Latest isolated numbers: p50 **9.7s**, p95 **113.0s** against a <3s target;
greeting path 5ms.

Next, in order:

1. **B23 — now unblocked, and still unmeasured.** The blocker was Sarvam-only:
   `SARVAM_CLOUD_CLASSIFY_MODEL` equalled `SARVAM_CLOUD_MODEL`, so no
   `_generate_fast()` call was actually fast. The deployment has since moved to
   `LLM_PROVIDER=openrouter`, where generation (`deepseek/deepseek-chat`) and
   classify/fast (`meta-llama/llama-3.1-8b-instruct`) are genuinely different
   sizes. `settings.rag_rewrite_query_fast_model` (default `False`) is wired in
   all three provider classes and now has real effect. Nobody has run the
   before/after eval on OpenRouter yet — run it **sequentially** (§2 rule 2)
   before claiming a win.
2. **Why comparative queries never pass verification.** A profiled 112s run
   exhausted `RAG_MAX_REWRITES` and still ended in `handle_fallback`. Latency is
   the symptom; the retrieval/grading failure is the disease. Fix the latter and
   the former may disappear.
3. **B20** — backend Docker OOM 137 (6G limit vs 8.3G host). Blocks the
   documented deploy path.
4. **B16** — nDCG baseline is vacuously 0.0 and reds CI (R20's gate).
5. Brief sections **never run**: §5 model economics, §6 RAG quality eval, §11
   fallback visibility, §12 memory/worker/concurrency, §13 frontend journey,
   §14 dependency/CVE audit.

## 8. Repo rules that override convenience

- **Never commit, branch, or push unless explicitly asked.** Leave changes in
  the working tree.
- **Secrets stay in env vars.** Only `backend/.env.example` is checked in.
- **npm is canonical.** Both `package-lock.json` and `bun.lockb` exist; never
  regenerate the bun lockfile.
- **Never hand-edit generated files or lockfiles.**
- **Another session may be editing this repo concurrently.** Check `git status`
  and `git log` before assuming a change is yours, and commit only files you
  actually touched — an unrelated commit once swept up a half-finished fix and
  left `main` internally broken.
