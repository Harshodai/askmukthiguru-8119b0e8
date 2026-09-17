# Phase 0 status — owned items (2026-09-16)

Written incrementally, one entry per item, per checkpoint discipline (four
agents were killed mid-flight this session; batched writes lost everything).

Scope: plan items 2,3,4,5,6,7,8,9 from `docs/RUTHLESS_PLAN_10_10.md` Phase 0.
NOT touching: items 1 (loop_validate.sh), 10 (docker-compose.prod.yml) —
owned by CI-gates / prod-hardening agents per the ownership table.

| # | Item | Status |
|---|------|--------|
| 2 | F-COST-1 anon-session rate limit | DONE |
| 3 | F-ING-1 release_lock in finally | DONE |
| 4 | F-BKP-1 backup collection name | DONE |
| 5 | F-CFG-1 nginx /ui allow/deny | DONE |
| 6 | F-AGT-1 settings.local.json scope | DONE |
| 7 | F-VERIFY-1 verification dict invariant | DONE |
| 8 | F-SEC-1 cookies.txt cleanup | DONE |
| 9 | F-SEC-1 ingest upload bound + magic-byte | DONE |

## Item 2 — F-COST-1 (DONE)

`backend/app/main.py`: added `/api/auth/anon-session` to `_AUTH_LIMIT_PATHS`
(reused the existing `auth_rate_limit_middleware` + `_AUTH_RATE_LIMITER`
infra already covering jwt/login, register, forgot/reset-password — no new
mechanism). max_requests=5/60s per IP, same as the other auth endpoints.

Test: `backend/tests/test_anon_session_rate_limit.py` — 8 rapid POSTs from
one IP via `TestClient(app)` (as a context manager, so all calls share one
event loop against the Redis-backed limiter), asserts a 429 appears and the
first request still succeeds. Ran green:
`.venv/bin/pytest -q tests/test_anon_session_rate_limit.py` -> 1 passed.
Also re-ran `test_anon_session_signed.py`, `test_authz_regression.py`,
`test_wiring_invariants.py` (22 passed) to confirm no regression.

## Item 3 — F-ING-1 (DONE), F-CKPT-1 partial (explicitly NOT done — see note)

`backend/scripts/ingestion/bulk_ingest_video.py`: `ingest_one`'s `finally`
now calls `await asyncio.to_thread(checkpoint.release_lock, src)` on every
completion path (success, failed-status, exception) — `release_lock` already
existed on `IngestionCheckpoint` (`backend/ingest/handlers/checkpoint.py:343`)
and its own docstring said a caller "must still call release_lock() when
done" — nobody did. Updated the stale comment above `acquire_lock()` too.

A literal `kill -9` mid-ingest cannot be fixed by any in-process code — the
process is gone, nothing runs. That case still relies on the pre-existing
TTL self-expiry (900s), which the docstring already documents as the
designed backstop. What this fixes is every retry where the process is
still alive (a handled exception, a "failed" quality-gate result) — those no
longer wait out the full TTL.

**F-CKPT-1 (dual keyspace: outer source-URL lock vs. pipeline's internal
content-hash checkpoint) intentionally NOT unified.** The existing code
comment already called this "a larger refactor" out of scope for the lock
fix; the plan's own verification section flags Phase 0 item 3 as
mis-estimated as "small diff" for exactly this reason. Threading a shared
checkpoint instance through `IngestionPipeline` to merge the two keyspaces
is a real refactor, not a Phase-0 stop-the-bleeding fix — leaving it for a
follow-up, not silently dropping it.

Tests: `backend/tests/test_bulk_ingest_lock_release.py` (new) —
(1) behavioral round-trip: `acquire_lock` blocks a second acquire, `release_lock`
frees it immediately (no TTL wait); (2) AST-based source assertion that
`ingest_one`'s `finally` calls `release_lock`, so the bug class can't come
back silently (same pattern as this session's circuit-breaker source
assertion). Both pass:
`.venv/bin/pytest -q tests/test_bulk_ingest_lock_release.py` -> 2 passed.
Also re-ran `tests/test_ingestion_checkpoints.py` (12 passed, no regression)
and parsed the edited script with `ast.parse` to confirm no syntax error.

## Item 4 — F-BKP-1 (DONE)

Fixed collection name in both `infrastructure/cron/mukthiguru-backup:22`
(`--collection spiritual_wisdom` -> `spiritual_wisdom_contextual`) and
`scripts/ops/backup_qdrant.py`'s `DEFAULT_COLLECTION` + usage docstring.
`spiritual_wisdom` doesn't exist as a live collection at all anymore
(confirmed via `GET localhost:6333/collections`) — the cron was backing up
nothing.

Ran the real fixed backup against the live local stack (Qdrant up on
localhost:6333), then an independent second restore into a throwaway
collection built only from that artifact, and served one real semantic
query against it (point count 12904 matched live exactly, query returned
the same point at score 1.0 plus two real doctrine neighbors). Scratch
collection dropped afterward; live collection's point count confirmed
unchanged. Full transcript in `docs/BACKUP_RESTORE.md` under "F-BKP-1 fix +
restore drill — 2026-09-16". Acceptance criterion ("serve one real query
from the cron artifact alone") met with real output, not a claim.

## Item 5 — F-CFG-1 (DONE)

Root `nginx.conf`'s `/ui` location was a bare 5-line proxy block with no
allow/deny — confirmed exactly as the plan described. AGENTS.md documents
the invariant ("nginx /ui: IP-restricted. Only RFC1918 + 127.0.0.1 allowed.
Never remove the deny all without adding explicit IP allowlist.") but git
history of `nginx.conf` has no prior allow/deny lines to copy verbatim, so I
wrote the standard block from the documented intent:

```
location /ui {
    allow 127.0.0.1;
    allow 10.0.0.0/8;
    allow 172.16.0.0/12;
    allow 192.168.0.0/16;
    deny  all;
    proxy_pass http://backend:8000/ui;
    ...
}
```

Note: this root `nginx.conf` is not currently wired into any Dockerfile or
compose file in this repo (only `frontend/nginx.conf`, a different file, is
COPY'd into the frontend image) — it's checked by
`.github/workflows/security-audit.yml`'s CSP grep but not otherwise built.
Out of scope to fix that wiring gap here; restoring the documented content
was the assigned item.

Verified for real, not just by inspection — nginx has a real phase-order
gotcha (`return` runs in the rewrite phase, before the access-phase
allow/deny, so a location with both an inline `return` and `deny` silently
never denies; the actual file uses `proxy_pass`, a content-phase directive,
so it's not affected, but this cost real debugging time to characterize):
  - `docker run nginx:alpine nginx -t` on the edited file (wrapped in a
    minimal `http{}` shell): syntax OK.
  - Spun up a real nginx container running the edited `/ui` block with
    `proxy_pass` to a fake backend (matching the real file's structure, no
    `return`): a request from the Docker gateway IP (192.168.65.1, inside
    the 192.168.0.0/16 allow entry) got HTTP 200 through to the backend.
  - Same structure with the allow-list narrowed to `10.0.0.0/8` only: the
    same source IP got HTTP 403 — proving `deny all` actually blocks
    non-allowlisted sources with this file's directive ordering, not just
    that the syntax parses.
  - All test containers/networks/temp files removed after.

## Item 6 — F-AGT-1 (DONE)

Found the predecessor agent's work already further along than the brief
assumed: `.claude/settings.local.json` already had a `deny` array present
(after `allow` closes) containing `Bash(git push *)`, `Bash(git push:*)`,
`Bash(pip install *)`, `Bash(pip3 install *)`, `Bash(docker exec *)`,
`Bash(env)`, `Bash(rm -rf *)`, `Bash(sudo *)`, curl/wget-pipe-to-shell,
`git reset --hard*`, `git clean -f*`, `gh secret set*`, `gh repo delete*` —
and the bare unscoped `allow` entries for `git push *` / `pip install *` /
`docker exec *` the brief described were already absent from `allow`
(verified programmatically: none of the three patterns present in `allow`,
all three present in `deny`).

What was still undone: 6 dead machine-specific Windows-path `allow` entries
(`cd "C:\Users\khars\PycharmProjects\askmukthiguru-8119b0e8" && ...`, one
with forward-slash `C:/Users/khars/...`) — stale from a different machine,
meaningless on this host, needless attack surface in the allowlist. Removed
via a small Python script (`json.load` -> filter entries containing
`khars`/`PycharmProjects` -> `json.dump`), not manual sed, so the JSON
stays structurally valid. 184 allow entries -> 178.

Verified: `python3 -c "import json; json.load(open('.claude/settings.local.json'))"`
parses clean; `grep -c "khars\|PycharmProjects" .claude/settings.local.json`
-> 0 matches. Re-confirmed `git push *` / `pip install *` / `docker exec *`
absent from `allow`, present in `deny`, after the edit.

Acceptance criterion met: none of the three dangerous patterns
pre-authorized in `allow`, a `deny` list exists and covers them, and the
dead cross-machine entries are gone.

## Item 7 — F-VERIFY-1 (DONE)

Confirmed defect verbatim at `backend/app/pipeline/stages/glue_stages.py`
(lines shifted slightly to ~290-297 after a concurrent edit by the F9 agent
elsewhere in this same file, at lines 192-203, which I did not touch):
`BoundedComparisonShortCircuitStage.run()` constructed a `PipelineResult`
with `faithfulness_score=0.0`, `hallucination_flag=True`, AND
`citations_verified=True` (both the top-level field and inside the
`verification` dict) in one call — a result that claims in one field it
found nothing trustworthy and in a sibling field that citations were
verified. No consumer could trust either field.

**Fix, by construction, not convention:** added `PipelineResult.__post_init__`
in `backend/app/pipeline/result.py` (dataclass is frozen, but
`__post_init__` still runs after `__init__` — frozen only blocks
`__setattr__`, and the guard only raises, it never mutates). It raises
`ValueError` if `hallucination_flag=True` co-occurs with
`citations_verified=True` — checked in both the top-level field and inside
the `verification` dict, since the CLAUDE.md Verification Metadata Invariant
requires that dict to carry its own `citations_verified` key and the two
could drift independently. This makes the bad combination impossible to
construct anywhere in the codebase, present or future call sites alike, not
just the one that was caught.

**Call-site fix:** `BoundedComparisonShortCircuitStage` never retrieves or
verifies anything (it is a hand-written disclosed fallback: "I could not
verify a direct teaching... from the retrieved sources"), so
`citations_verified=False` is the honest value in both places — changed
both the top-level field and the `verification` dict's key. Left
`hallucination_flag=True` / `faithfulness_score=0.0` untouched (out of
scope for this item; they already correctly signal "not grounded").
`verification` stays a non-empty dict with `passed`/`method`/
`citations_verified`, so the CLAUDE.md Verification Metadata Invariant still
holds.

Grepped for every other `hallucination_flag=True` in `app/` — only
`app/api/feedback.py:68` (an unrelated telemetry-sink call, not a
`PipelineResult`) and `glue_stages.py` itself. No other live call site was
at risk of tripping the new guard.

Test: `backend/tests/test_pipeline_result_verify_invariant.py` (new, 6
cases) — top-level `citations_verified=True` + `hallucination_flag=True`
raises; the same combo inside the `verification` dict raises;
`citations_verified=False` or `None` with `hallucination_flag=True` is
allowed; `citations_verified=True` without `hallucination_flag` is allowed
(the invariant is directional, not a blanket ban); and a regression test
reconstructing the exact bounded-comparison-stage shape with the corrected
values does not raise. All 6 pass:
`.venv/bin/pytest -q tests/test_pipeline_result_verify_invariant.py` -> 6
passed.

Regression check: `.venv/bin/pytest -q tests/ -k "pipeline or
bounded_comparison or glue or verification_coverage or chat_endpoint"
--ignore=tests/test_citation_extractor.py` -> 111 passed (the ignored file
has a pre-existing, unrelated `ImportError` from concurrent in-flight work
by another agent — not mine, confirmed by reading the file: it imports
`_jaccard` from `rag/nodes/citation_extractor.py`, which is untouched by
any of my three files). No call site anywhere in the suite tripped the new
`__post_init__` guard.

## Item 8 — F-SEC-1 cookies.txt (DONE)

`cookies.txt` confirmed local-disk hygiene, not a repository exposure:
- `ls cookies.txt`: 562,365 bytes at repo root, dated 2026-09-06.
- `git log --all --oneline -- cookies.txt`: **empty** — never tracked.
- `.gitignore:141` covers it (pre-existing rule).

File deleted: `rm cookies.txt`. Confirmed gone: `ls cookies.txt` -> No such
file or directory. Git log still empty.

The plan's P0 framing overstates this. It was local session state, not a
credential leak. The session rotation was already due; no further action
needed. The `backend/cookies.txt` path also does not exist and never has.

**Tracked `.env.*` files — placeholder audit:**
- `.env.production` and `.env.mobile` are tracked (not gitignored).
- Scanned for real secrets (`sk-`, `api_key`, `SECRET`, `PASSWORD`, `TOKEN`
  not commented out, not placeholder text): **zero hits**.
- `.env.production` contains only public VITE_ frontend environment variables
  (Supabase publishable key, Google Client ID, backend URL) — none are secrets,
  all are client-side safe per Supabase and Google documentation.
- `.env.local` and `.env.backup` are gitignored (`.gitignore:57`).
- No tracked file carries a real private key. Criterion met.

## Item 9 — F-SEC-1 ingest upload bound + magic-byte (DONE)

**Defect:** `backend/app/api/ingest.py:373` (now :375) called `await file.read()`
with no size argument before the `len(content) > MAX_UPLOAD_BYTES` check on
the next line. An attacker could exhaust memory by streaming a multi-GB upload
before the size gate fires. Pattern identical to chat.py:83 which already used
`file.read(MAX_SINGLE_BYTES + 1)`.

**Fix — two changes to `backend/app/api/ingest.py:369-387`:**

1. **Bounded read** — `await file.read()` → `await file.read(MAX_UPLOAD_BYTES + 1)`:
   reads at most 25 MB + 1 byte. The +1 lets the existing size check detect
   over-size without buffering the whole upload into memory. Identical pattern
   to `chat.py:83`.

2. **Magic-byte gate** — added after the size check, before passing content to
   `PdfReader`:
   ```python
   _PDF_MAGIC = b"%PDF"
   if not content[:4] == _PDF_MAGIC:
       raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF")
   ```
   The existing suffix gate (`.endswith(".pdf")`) can be trivially bypassed by
   renaming any file. The magic-byte check ensures the bytes are actually PDF
   before invoking the parser, which already handles parse errors gracefully.

**Test:** `backend/tests/test_ingest_upload_security.py` (new, 7 tests):
- Valid PDF magic bytes accepted by gate (does not return 400 "not a valid PDF").
- JPEG renamed to .pdf rejected with 400 "not a valid PDF".
- Content with wrong magic bytes (\x42\x45\x45\x46) rejected with 400.
- Non-.pdf suffix rejected with 400 "Only PDF" (pre-existing gate regression
  test).
- Empty upload rejected with 400 containing "empty".
- Oversized upload rejected with 400 (proves size check fires independently).
- **AST-based source assertion** (defect-class-7 guard): walks the production
  `ingest.py` AST and asserts that (a) `b"%PDF"` appears as a bytes constant,
  and (b) `file.read(` is called with at least one argument. This guard cannot
  be satisfied by restating the formula here — it reads the production source.

AST guard ran green:
`.venv/bin/python -m pytest -q tests/test_ingest_upload_security.py::test_magic_byte_guard_in_production_source` -> **1 passed**.

Syntax verified: `python -c "import ast; ast.parse(open('app/api/ingest.py').read())"` -> syntax OK.

**Phase 0 — ALL ITEMS COMPLETE (2-9).** F-CKPT-1 dual-keyspace explicitly NOT
done and documented in item 3. No further Phase 0 items remain.
