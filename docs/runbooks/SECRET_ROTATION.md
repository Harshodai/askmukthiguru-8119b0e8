# Runbook: Secret Rotation & PII Dump Remediation (CRIT-6)

> **Status:** Code-deliverable scope shipped (pre-commit hooks + this runbook
> + INV-6 verification script). The manual ops actions below are **yours to
> execute** — an automated agent cannot delete files from your main checkout
> or rotate keys in external services. This runbook is the checklist.

## Purpose

The working tree of the main checkout holds unencrypted PII dumps and live
secrets that are gitignored (never committed) but present on disk. This is
a P0 operational finding. The code shipped with this runbook prevents
*regression* (re-adding dumps / large files / committed secrets); this
runbook drives the *remediation* of the current exposure.

## Scope of code shipped (already done, for context)

| Deliverable | File | What it does |
|---|---|---|
| T6 — large-files hook | `.pre-commit-config.yaml` (`check-added-large-files --maxkb=500`) | Blocks staging any file > 500 KB. PII dumps are 36 MB / 11 MB / 43 KB / 300 KB — all gitignored, this is the size backstop. |
| T7 — dump detector | `scripts/security/check_no_pii_dumps.sh` | Fails if `neo4j.dump`, `supabase_dump.sql`, `redis_dump.rdb`, `cookies.txt`, or `public_schema_dump.sql` is present in the working tree. Never deletes — only reports. |
| T7 — pre-commit local hook | `.pre-commit-config.yaml` (`local` repo, `check-no-pii-dumps`) | Runs the detector on every commit. Bypassable with `--no-verify`; CI step is the enforcement backstop. |
| INV-6 — verification gate | `scripts/security/verify_no_pii_dumps.sh` + CI step in `.github/workflows/lint-test.yml` (`pre-commit-check` job, `INV-6` step) | Canonical INV-6 caller. CI fails if any forbidden dump is in the checkout. |

All code deliverables are **additive** — revert the commit to remove them.

---

## Manual ops checklist (USER executes)

Tick each box as you complete it. Do not skip ordering — secrets rotation
must happen before old dumps are deleted (so services stay live).

### Phase A — Inventory (read-only, no changes)

- [ ] **A1.** Confirm the dump files exist in your **main checkout root**
      (not the worktree). Expected:
      - `neo4j.dump` (~36 MB) — full Neo4j graph (user ontology, possibly memories)
      - `supabase_dump.sql` (~11 MB) — full Supabase SQL (auth.users, profiles, guru_memories)
      - `redis_dump.rdb` (~43 KB) — Redis snapshot (session/cache state)
      - `cookies.txt` (~300 KB) — active YouTube OAuth session cookie
      - `The_Four_Sacred_Secrets.pdf` (~2.8 MB) — scrubbed from git history 2026-08-01, still on disk
      - `public_schema_dump.sql` (if present) — public schema SQL
- [ ] **A2.** Confirm all are gitignored: `git check-ignore -v neo4j.dump
      supabase_dump.sql redis_dump.rdb cookies.txt The_Four_Sacred_Secrets.pdf`.
      Every path must print a matching `.gitignore` line. If any is **not**
      ignored, stop and add it to `.gitignore` before continuing.
- [ ] **A3.** Run the INV-6 gate to confirm current exposure:
      `bash scripts/security/verify_no_pii_dumps.sh .` — expect FAIL (exit 1)
      with the list of present dumps.

### Phase B — Backup encryption setup (T2 — pick ONE option)

You must encrypt the existing backups before deleting the root copies. Pick
either `age` (recommended, simplest) or S3 SSE-KMS (if you already use AWS).

- [ ] **B1 (option age).** Install `age`:
      - macOS: `brew install age`
      - Linux: `apt install age` or download from https://github.com/FiloSottile/age/releases
- [ ] **B2 (option age).** Generate an `age` keypair **outside the repo**:
      `age-keygen -o ~/keys/askmukthiguru-backup.key` and store the
      **private key in 1Password** (or your KMS / password manager — never
      in the repo, never in `backups/`). Note the **recipient** (public key)
      string printed by `age-keygen`.
- [ ] **B3 (option age).** Create the encrypted target:
      `mkdir -p backups/encrypted` (this path is gitignored under
      `backups/`). Confirm `git check-ignore backups/encrypted` matches.
- [ ] **B1' (option S3 SSE-KMS).** Create an S3 bucket with a KMS key
      (CMK) dedicated to backups. Note the bucket ARN and key ARN. Configure
      bucket policy to deny unencrypted (`x-amz-server-side-encryption: aws:kms`)
      PUTs. Use `aws s3 cp --sse aws:kms --sse-kms-key-id <KEY_ARN>` for
      uploads. Skip B2/B3 (age path) if you chose this option.

### Phase C — Move dumps to encrypted storage, then delete root copies (T1/T3/T4)

- [ ] **C1.** Encrypt each dump into `backups/encrypted/` (age path):
      ```bash
      for f in neo4j.dump supabase_dump.sql redis_dump.rdb public_schema_dump.sql; do
        [ -f "$f" ] && age -r <RECIPIENT_PUBKEY> -o "backups/encrypted/$f.age" "$f"
      done
      ```
      (S3 path: `aws s3 cp --sse aws:kms --sse-kms-key-id <KEY_ARN> neo4j.dump s3://<bucket>/neo4j.dump` etc.)
- [ ] **C2.** Verify each encrypted artifact decrypts back to a byte-identical
      original before deleting the plaintext:
      `age -d -i ~/keys/askmukthiguru-backup.key backups/encrypted/neo4j.dump.age | cmp - neo4j.dump`
      (Repeat for each.) All must report identical (no `differ` output).
- [ ] **C3.** Only after C2 passes for every dump: delete the root plaintext
      copies:
      ```bash
      rm -f neo4j.dump supabase_dump.sql redis_dump.rdb public_schema_dump.sql
      ```
- [ ] **C4.** Delete `cookies.txt` (active session — no backup needed, it
      is an OAuth credential, not data):
      ```bash
      rm -f cookies.txt
      ```
- [ ] **C5.** `The_Four_Sacred_Secrets.pdf`: per `CONTENT-RIGHTS.md` the
      rights basis is **unconfirmed**. If you cannot confirm a rights basis
      (CC license / direct arrangement / fair-use academic commentary) with
      Ekam Science Foundation / OneWorld Academy, **delete the on-disk
      copy**:
      ```bash
      rm -f The_Four_Sacred_Secrets.pdf
      # and from data/private/ if a copy lives there
      rm -f data/private/The_Four_Sacred_Secrets.pdf
      ```
      If rights are confirmed, instead move it to `data/private/` (gitignored
      via `*.pdf`) and record the basis in `CONTENT-RIGHTS.md`.
- [ ] **C6.** Re-run INV-6: `bash scripts/security/verify_no_pii_dumps.sh .`
      — expect **OK (exit 0)**. If it still fails, a dump remains; find and
      remediate it.

### Phase D — Rotate every secret (T5)

The dumps in `supabase_dump.sql` and `redis_dump.rdb` exposed live secrets.
Treat every secret-bearing env var as compromised and rotate it. The
inventory below lists **variable names only** (never values) — look up each
value in your local `.env` / `backend/.env` / `backend/.env.prod` to know
what to rotate.

#### D1. Secret inventory (variable names, by file)

**Root `.env`** — secret-bearing vars:
`BENCHMARK_SECRET`, `FACEBOOK_CLIENT_SECRET`, `GOOGLE_CLIENT_SECRET`,
`HF_TOKEN`, `JWT_SECRET`, `KEYCHAIN_PASS`, `NEO4J_PASSWORD`, `NIM_API_KEY`,
`OLLAMA_API_KEY`, `OPENROUTER_API_KEY`, `REDIS_PASSWORD`, `SARVAM_API_KEY`,
`SUPABASE_ANON_KEY`, `SUPABASE_KEY`.
(Non-secret tuning vars in this file: `MAX_TOKENS_PER_REQUEST`,
`TOKENIZERS_PARALLELISM`, `CORS_ORIGINS`, etc. — no rotation needed.)

**`.env.local`** — secret-bearing vars:
`VITE_SUPABASE_PUBLISHABLE_KEY` (publishable, low-risk, but rotate if
Supabase anon key is rotated). Non-secret: `VITE_BACKEND_URL`,
`VITE_GOOGLE_CLIENT_ID`, `VITE_SUPABASE_URL`, `VITE_USE_NATIVE_OAUTH`.

**`.env.mobile`** — no secrets (`VITE_BACKEND_URL` only).

**`.env.production`** — secret-bearing vars:
`VITE_SUPABASE_PUBLISHABLE_KEY`. Non-secret: `VITE_ALLOW_MOCK`,
`VITE_BACKEND_URL`, `VITE_GOOGLE_CLIENT_ID`, `VITE_SUPABASE_PROJECT_ID`,
`VITE_SUPABASE_URL`.

**`backend/.env`** — secret-bearing vars (superset of root `.env` plus):
`SMTP_PASSWORD`. Also: `BENCHMARK_SECRET`, `FACEBOOK_CLIENT_SECRET`,
`GOOGLE_CLIENT_SECRET`, `HF_TOKEN`, `JWT_SECRET`, `KEYCHAIN_PASS`,
`NEO4J_PASSWORD`, `NIM_API_KEY`, `OLLAMA_API_KEY`, `OPENROUTER_API_KEY`,
`REDIS_PASSWORD`, `SARVAM_API_KEY`, `SUPABASE_ANON_KEY`, `SUPABASE_KEY`.

**`backend/.env.prod`** — secret-bearing vars (production):
`ANTHROPIC_API_KEY`, `ANON_SESSION_HMAC_SECRET`, `BENCHMARK_SECRET`, `CSRF_SECRET`,
`EMERGENT_LLM_KEY`, `JWT_SECRET`, `KRUTRIM_API_KEY`, `NEO4J_PASSWORD`,
`NIM_API_KEY`, `OPENROUTER_API_KEY`, `QDRANT_API_KEY`, `REDIS_PASSWORD`,
`SARVAM_API_KEY`, `SUPABASE_ANON_KEY`, `SUPABASE_KEY`, `SUPABASE_SERVICE_KEY`,
`VITE_SUPABASE_PUBLISHABLE_KEY`.
- `HF_TOKEN` — only if Hugging Face gated-model downloads are enabled; otherwise mark as **not configured**.
- `GOOGLE_CLIENT_SECRET` / `FACEBOOK_CLIENT_SECRET` — only if the respective OAuth provider is enabled in Supabase Auth; otherwise mark as **not configured**.
(Non-secret `*_TOKEN`/`*_KEY` vars that are tuning knobs, not credentials:
`ANTHROPIC_EXTENDED_THINKING_BUDGET_TOKENS`, `ANTHROPIC_GATEWAY_MAX_TOKENS`,
`CSRF_TOKEN_TTL`, `LLM_GATEWAY_MAX_TOKENS`, `MAX_TOKENS_PER_REQUEST`,
`TOKENIZERS_PARALLELISM` — verify each is a knob, not a credential, before
skipping.)

> **Rule:** if a var name ends in `_SECRET`, `_KEY` (and is not a model
> name / token-count knob), `_PASSWORD`, or `_TOKEN` (and is not a TTL /
> count), treat it as a credential and rotate it. When in doubt, rotate.

#### D2. Rotation Procedures & Dependency Ordering

Rotate secrets in the following strict dependency order. **Stage 1 stores do not all support native zero-downtime dual-credential rotation** — apply the provider-specific overlap plan below to avoid service interruption.

```
[Stage 1: Databases & Stores]  -->  [Stage 2: Backend Core Auth]  -->  [Stage 3: Upstream AI APIs]  -->  [Stage 4: Frontend / Clients]
(Postgres, Redis, Neo4j, Qdrant)    (JWT, Anon HMAC, CSRF, Service)      (Sarvam, OpenRouter, NIM)         (SSO, Publishable Keys)
```

- [ ] **D2.1 Databases & Persistence (Stage 1) — overlap/rollback plan:**
      - **Supabase keys** (rotate in this order; the rotation model differs between the two key families):
        1. **`SUPABASE_SERVICE_KEY`** (service_role, highest privilege) — Supabase dashboard: Project Settings → API → Project API keys → regenerate **service role** key. This key bypasses RLS; keep it backend-only.
           - Update in `backend/.env.prod` and Railway production variables **only**.
           - Verify backend writes still succeed (`/api/health`, one admin/RPC write) before revoking the old service key.
        2. **`SUPABASE_KEY`** (service_role alias used by backend scripts/tests) — same service role key as above, or a dedicated service role copy if scripts need isolation.
           - Update in root `.env`, `backend/.env`, `backend/.env.prod`, plus any one-off scripts (`scripts/ops/prune_retention.py`, `backend/scripts/seed_admin.py`, `backend/scripts/verify_rls_policies.py`).
           - **Note:** `SUPABASE_SERVICE_KEY` is the preferred production name; `SUPABASE_KEY` is the legacy fallback. Rotate both to the same new value unless you deliberately maintain separate roles.
        3. **`SUPABASE_ANON_KEY`** (publishable/anon key, public-facing) — Supabase dashboard: Project Settings → API → Project API keys → regenerate **anon/public** key.
           - Update in frontend `.env.*` (`VITE_SUPABASE_PUBLISHABLE_KEY`), root `.env`, `backend/.env`, `backend/.env.prod`, and all Supabase Edge Functions (`supabase/functions/*/index.ts`) that create a `SupabaseClient` with `Deno.env.get("SUPABASE_ANON_KEY")`.
           - **Rebuild and redeploy the frontend** — the new bundle embeds the key (`VITE_SUPABASE_PUBLISHABLE_KEY` is baked in at build time). Purge CDN/browser caches or set cache-busting headers so clients fetch the new bundle; reload/restart alone is insufficient.
           - This invalidates existing anon-signed requests; clients pick up the new key only from the freshly served bundle.
        - **Legacy JWT-based keys (anon/service_role JWTs signed by the JWT secret) vs. new publishable/secret key model** — branch on what your project uses:
          - **Legacy JWT-based keys** (`SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`, `SUPABASE_KEY` as JWTs): regenerating the JWT secret (D2.2) **immediately invalidates ALL existing API keys and user sessions** — there is **no overlap or rollback window** for these keys. Rotate them in a maintenance window: update all env files + Railway variables, redeploy backend, and expect all users to re-login. Do not plan a coexistence period for legacy keys.
          - **New publishable/secret key model** (`VITE_SUPABASE_PUBLISHABLE_KEY` + dashboard-managed secret keys): these **can coexist** — create the new publishable+secret pair, update clients, verify, then revoke the old pair. Keep coexistence/rollback guidance **only** for this model.
      - **Redis `REDIS_PASSWORD`** — If your Redis provider supports dual-password rotation (e.g. ElastiCache user rotation or Redis ACL with two active passwords), add the new password as a secondary auth credential first; otherwise plan a short maintenance window.
        - Update `REDIS_PASSWORD` and rebuild `REDIS_URL` in backend env.
        - Restart backend/workers **after** the Redis service accepts the new password.
        - Remove the old password from Redis ACL/config only after verification with the new credentials: `redis-cli -a '<NEW_PASSWORD>' ping` must return `PONG` (or pass an application health probe that authenticates with the new `REDIS_URL`).
        - Before removing the old credential, monitor for authentication failures over a soak period (e.g. Redis `AUTH` failure logs / `INFO commandstats` for `auth_cmd_fail`, or backend error logs) — any failures mean a client still holds the old credential; do not delete it until auth failures are zero.
        - *Rollback:* if the new password is rejected, revert `REDIS_URL` to the old value and restart; Redis still accepts the old password until you explicitly delete it.
      - **Neo4j `NEO4J_PASSWORD`** — `ALTER CURRENT USER SET PASSWORD` **does not** support overlapping active passwords (it replaces the password; the old one stops working immediately). Choose one of:
        1. **Separate user:** create a new user with the new password (`CREATE USER <new-user> SET PASSWORD '<new>'` + grants), point `NEO4J_USER`/`NEO4J_PASSWORD` env at it, restart backend, verify, then `DROP USER <old-user>` once stable.
        2. **Maintenance window:** stop traffic, run `ALTER CURRENT USER SET PASSWORD FROM 'old' TO 'new'`, update `NEO4J_PASSWORD` in env, restart backend.
        - Verify bolt connection logs show no auth errors (or `cypher-shell -a bolt://<host>:7687 -u <user> -p '<new>' RETURN 1` succeeds).
        - *Rollback:* revert env to old password and restart if the new password fails — but note the old password is only valid until the `ALTER` runs; after that, rollback requires changing the password back (or restoring the separate-user path).
      - **Qdrant `QDRANT_API_KEY`** — Qdrant Cloud does not support overlapping API keys on the same cluster. Plan a brief maintenance window or rotate during low-traffic period.
        - Generate new key in Qdrant cloud console → update `QDRANT_API_KEY` in backend env → restart backend → verify `/api/health` reports Qdrant ready.
        - *Rollback:* if the new key is mis-typed, immediately restore the old `QDRANT_API_KEY` and restart; the old key remains valid until explicitly deleted in Qdrant Cloud.
        - Delete the old Qdrant key in console only after 5 minutes of clean metrics / zero `401` responses.

- [ ] **D2.2 Backend Core Auth & Session Secrets (Stage 2):**
      - **`ANON_SESSION_HMAC_SECRET`** — Generate high-entropy 32-byte hex string:
        `python3 -c "import secrets; print(secrets.token_hex(32))"`
        Update `ANON_SESSION_HMAC_SECRET` in `backend/.env.prod` and Railway service vars.
        *Note:* Existing anonymous session tokens will be invalidated; anonymous users will automatically receive a new signed session on their next visit.
      - **`JWT_SECRET`** — Supabase dashboard: Settings → API → JWT Settings → rotate.
        ⚠️ Invalidates all active user login sessions (forces re-login). Coordinate with a maintenance window.
        Update `JWT_SECRET` in root `.env`, `backend/.env`, `backend/.env.prod`, Railway.
      - **`CSRF_SECRET` & `BENCHMARK_SECRET`** — Regenerate:
        `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
        Update `CSRF_SECRET` and `BENCHMARK_SECRET` in backend env.

- [ ] **D2.3 Upstream AI & LLM Provider Keys (Stage 3):**
      - **Sarvam AI** (`SARVAM_API_KEY`) — https://dashboard.sarvam.ai → generate new key → update backend env → revoke old key after verification.
      - **OpenRouter** (`OPENROUTER_API_KEY`) — https://openrouter.ai/keys → create new key → update backend env → delete old key.
      - **NVIDIA NIM** (`NIM_API_KEY`) — https://build.nvidia.com → generate new API key → update backend env.
      - **Anthropic / Krutrim / Emergent** (`ANTHROPIC_API_KEY`, `KRUTRIM_API_KEY`, `EMERGENT_LLM_KEY`) — rotate in respective consoles.
      - **Hugging Face** (`HF_TOKEN`) — https://huggingface.co/settings/tokens → generate read-token → update backend env.

- [ ] **D2.4 Frontend & Client Credentials (Stage 4):**
      - **Supabase Anon / Publishable Key** (`SUPABASE_ANON_KEY` / `VITE_SUPABASE_PUBLISHABLE_KEY`) — rotate in Supabase dashboard → update frontend `.env.*` and backend env.
      - **Google / Meta OAuth** (`GOOGLE_CLIENT_SECRET`, `FACEBOOK_CLIENT_SECRET`) — rotate in Google Cloud Console / Meta Developer Portal → update backend env.

- [ ] **D2.5 Railway Deployment:**
      For production deployment on Railway, update variables through the **Railway dashboard** (Project → Service → Variables) or another verified secret-input mechanism. **Do not paste secrets into shell commands** such as CLI arguments with inline values; shell history and process lists can leak them.
      Redeploy the service and monitor logs for zero startup errors.

### Phase E — Post-Rotation Scans & Verification

- [ ] **E1.** Verification script: `bash scripts/security/verify_no_pii_dumps.sh .` → exit 0 (INV-6).
- [ ] **E2.** Secret leakage scan with GitLeaks:
      `gitleaks detect --source . --verbose` (confirm no plaintext secrets committed).
- [ ] **E3.** Backend health check:
      `curl -f https://<prod>/api/health` → `{"status": "ok", "ready": true}`
      `curl -f https://<prod>/api/health/mfa` → `{"status": "ok"}`
- [ ] **E4.** Anonymous session token generation check:
      `curl -X POST https://<prod>/api/auth/anon-session` → `{"token": "anon_..."}`
- [ ] **E5.** Auth smoke test: User sign-in with email/password and Google OAuth.
- [ ] **E6.** RAG chat query smoke test: Send a question to `/api/chat` and verify 200 OK with citations.
- [ ] **E7.** Prometheus metrics check:
      `curl -f https://<prod>/api/metrics` → verify metrics scraped with 0 authentication errors.
- [ ] **E8.** Confirm encrypted backups decrypt: decrypt to a temporary file
      **first** so a decryption failure fails the check (`age -d` exit code is
      propagated, unlike the piped version):
      `age -d -i ~/keys/askmukthiguru-backup.key -o /tmp/backup.dec backups/encrypted/neo4j.dump.age && head -c 16 /tmp/backup.dec | xxd && rm -f /tmp/backup.dec`
      produces bytes (not an error); the `&&` chain stops on any failure.

---

## Cross-references

- **`CONTENT-RIGHTS.md`** — rights basis for `The_Four_Sacred_Secrets.pdf`
  (unconfirmed as of 2026-08-01; deletion path documented in C5).
- **`CREDENTIALS_GUIDE.md`** → "Mobile App Credentials" — separate mobile
  signing + push creds (keystore, `google-services.json`, APNs `.p8`); out
  of scope for this runbook unless those were in a dump (they were not).
- **`docs/INCIDENT_RESPONSE.md`** — credential-exposure scenario runbook
  (broader incident process; this file is the CRIT-6 specific procedure).
- **`.gitignore`** — dump files and `.env*` are already ignored; verify
  with `git check-ignore` per A2.
- **Pre-commit hooks** — `.pre-commit-config.yaml` (T6 large-files +
  T7 dump detector). Revert the CRIT-6 commit to remove both.
- **INV-6 gate** — `scripts/security/check_no_pii_dumps.sh` (impl) +
  `scripts/security/verify_no_pii_dumps.sh` (caller) + CI step in
  `.github/workflows/lint-test.yml` (`pre-commit-check` job).

## Rollback

The code deliverables are additive. To remove the hooks:
`git revert <CRIT-6 commit>`. The dump files and rotated secrets are
**not** reversible by revert — once you delete a dump it is gone (you have
an encrypted backup), and once you rotate a key the old key is dead at the
provider. Confirm Phase B (encrypted backup) before Phase C (delete).
