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
`ANTHROPIC_API_KEY`, `BENCHMARK_SECRET`, `CSRF_SECRET`, `EMERGENT_LLM_KEY`,
`JWT_SECRET`, `KRUTRIM_API_KEY`, `NEO4J_PASSWORD`, `OPENROUTER_API_KEY`,
`REDIS_PASSWORD`, `SARVAM_API_KEY`, `SUPABASE_ANON_KEY`, `SUPABASE_KEY`,
`VITE_SUPABASE_PUBLISHABLE_KEY`.
(Non-secret `*_TOKEN`/`*_KEY` vars that are tuning knobs, not credentials:
`ANTHROPIC_EXTENDED_THINKING_BUDGET_TOKENS`, `ANTHROPIC_GATEWAY_MAX_TOKENS`,
`CSRF_TOKEN_TTL`, `LLM_GATEWAY_MAX_TOKENS`, `MAX_TOKENS_PER_REQUEST`,
`TOKENIZERS_PARALLELISM` — verify each is a knob, not a credential, before
skipping.)

> **Rule:** if a var name ends in `_SECRET`, `_KEY` (and is not a model
> name / token-count knob), `_PASSWORD`, or `_TOKEN` (and is not a TTL /
> count), treat it as a credential and rotate it. When in doubt, rotate.

#### D2. Rotation procedures (per service)

- [ ] **D2.1 Supabase** (project `ozmjeuqbholoxypfxixb` — dashboard):
      - **`SUPABASE_KEY` (service_role)** — Settings → API → rotate
        `service_role` key. Update `backend/.env`, `backend/.env.prod`,
        root `.env`. This is the highest-impact rotation — service_role
        bypasses RLS. **Rotate first.**
      - **`SUPABASE_ANON_KEY` / `VITE_SUPABASE_PUBLISHABLE_KEY`** —
        Settings → API → rotate `anon`/publishable key. Update root
        `.env`, `.env.local`, `.env.production`, `backend/.env`,
        `backend/.env.prod`, and Railway service vars.
      - **`JWT_SECRET`** — Settings → API → JWT Settings → rotate. ⚠️ This
        invalidates all existing user sessions (force re-login). Coordinate
        with a maintenance window. Update root `.env`, `backend/.env`,
        `backend/.env.prod`, Railway.
- [ ] **D2.2 Railway** (`resilient-embrace` / `askmukthiguru-8119b0e8`,
      env `production`): for each rotated var, set it via
      `railway variables --kv "KEY=value"` (or dashboard) and redeploy.
      Vars to update after Supabase + provider rotations below:
      `SUPABASE_KEY`, `SUPABASE_ANON_KEY`, `JWT_SECRET`,
      `OPENROUTER_API_KEY`, `NIM_API_KEY`, `SARVAM_API_KEY`,
      `ANTHROPIC_API_KEY`, `KRUTRIM_API_KEY`, `EMERGENT_LLM_KEY`,
      `HF_TOKEN`, `REDIS_PASSWORD`, `NEO4J_PASSWORD`,
      `GOOGLE_CLIENT_SECRET`, `FACEBOOK_CLIENT_SECRET`, `BENCHMARK_SECRET`,
      `CSRF_SECRET`.
- [ ] **D2.3 OpenRouter** — https://openrouter.ai/keys → revoke old key,
      create new → update `OPENROUTER_API_KEY` everywhere + Railway.
- [ ] **D2.4 Sarvam AI** — https://dashboard.sarvam.ai → rotate API key →
      update `SARVAM_API_KEY` everywhere + Railway.
- [ ] **D2.5 NIM** (NVIDIA) — https://build.nvidia.com → rotate → update
      `NIM_API_KEY` everywhere + Railway.
- [ ] **D2.6 Anthropic** — https://console.anthropic.com → rotate →
      update `ANTHROPIC_API_KEY` in `backend/.env.prod` + Railway.
- [ ] **D2.7 Krutrim** — provider dashboard → rotate → update
      `KRUTRIM_API_KEY` in `backend/.env.prod` + Railway.
- [ ] **D2.8 Emergent LLM** — provider dashboard → rotate → update
      `EMERGENT_LLM_KEY` in `backend/.env.prod` + Railway.
- [ ] **D2.9 Hugging Face** — https://huggingface.co/settings/tokens →
      revoke + recreate (read scope is enough) → update `HF_TOKEN`
      everywhere + Railway.
- [ ] **D2.10 Google OAuth** — Google Cloud Console → APIs & Services →
      Credentials → rotate the OAuth client secret → update
      `GOOGLE_CLIENT_SECRET` everywhere + Railway. Also rotate
      `GOOGLE_CLIENT_ID` only if you recreate the client (usually the ID
      is stable; the secret rotates).
- [ ] **D2.11 Facebook OAuth** — Meta for Developers → App Settings →
      rotate client secret → update `FACEBOOK_CLIENT_SECRET` everywhere
      + Railway.
- [ ] **D2.12 Redis** — rotate `REDIS_PASSWORD`: change the Redis config
      (Railway Redis service or local `redis.conf`) and update `REDIS_URL`
      / `REDIS_PASSWORD` everywhere. Restart Redis and all clients.
- [ ] **D2.13 Neo4j** — rotate `NEO4J_PASSWORD`: `ALTER CURRENT USER SET
      PASSWORD FROM 'old' TO 'new'` (or recreate the user) → update
      `NEO4J_PASSWORD` everywhere + Railway.
- [ ] **D2.14 SMTP** (if `SMTP_PASSWORD` is live) — rotate at your SMTP
      provider → update `SMTP_PASSWORD` in `backend/.env`.
- [ ] **D2.15 YouTube OAuth session** (`cookies.txt`) — the file is
      deleted in C4. Sign out of the YouTube account everywhere, then
      re-authenticate the ingestion service (`scripts/` YouTube ingestion)
      with a fresh OAuth token. Confirm the ingestion service resumes
      pulling transcripts under the new token.
- [ ] **D2.16 Benchmark / CSRF / local-only** — `BENCHMARK_SECRET` and
      `CSRF_SECRET`: regenerate (`python3 -c "import secrets;print(secrets.token_urlsafe(32))"`)
      and update everywhere. These are local-only / non-prod guardrails but
      rotate them for hygiene.
- [ ] **D2.17 Keychain** — `KEYCHAIN_PASS` is a local macOS keychain
      password used by dev tooling. Rotate only if you suspect compromise;
      otherwise leave (it is not in any prod env).
- [ ] **D2.18 Ollama** — `OLLAMA_API_KEY` is only a credential if a remote
      Ollama Cloud endpoint is configured (`OLLAMA_BASE_URL` points to a
      non-localhost host). If localhost-only, it is not a remote secret —
      mark it non-credential in the D1 inventory and skip. If a remote
      endpoint is configured, rotate at the Ollama Cloud provider → update
      `OLLAMA_API_KEY` in `backend/.env` + Railway.

### Phase E — Verify

- [ ] **E1.** `bash scripts/security/verify_no_pii_dumps.sh .` → exit 0
      (INV-6 satisfied).
- [ ] **E2.** `git status` shows no dump files (they are gone, not just
      gitignored).
- [ ] **E3.** Backend health: `curl https://<prod>/api/health` returns
      `ready: true` after Railway redeploy with the new secrets.
- [ ] **E4.** Auth smoke test: a real user can sign in (JWT_SECRET
      rotation forced logout; confirm re-login works).
- [ ] **E5.** Chat smoke test: a real query returns doctrine (Supabase
      service_role key works; Qdrant/Neo4j reads succeed).
- [ ] **E6.** Confirm encrypted backups decrypt: `age -d -i
      ~/keys/askmukthiguru-backup.key backups/encrypted/neo4j.dump.age |
      head -c 16 | xxd` produces bytes (not an error).

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
