# AskMukthiGuru — Release Checklist

Every publish goes through this gate. Nothing ships until the automated
column is green **and** every manual item is initialled.

## 1. Automated gate — one command

```bash
scripts/prelaunch.sh
# or, against production:
BASE_URL=https://askmukthiguru.lovable.app scripts/prelaunch.sh
```

`scripts/prelaunch.sh` runs, in order, and short-circuits on the first red:

| # | Step                | What it guards                                            |
|---|---------------------|-----------------------------------------------------------|
| 1 | `npm run build`     | TS errors, bundler errors, prerender failures             |
| 2 | `vitest --run`      | Component and lib-layer contracts                         |
| 3 | `page-smoke`        | Every route mounts without a fatal console error          |
| 4 | `a11y-smoke`        | axe-core: no serious/critical WCAG 2.1 AA violations on `/`, `/auth`, `/chat`, `/profile`, `/practices`, meditation flow, `/knowledge-graph` |
| 5 | `google-auth-flow`  | No One Tap double-prompt; post-login redirect contract    |
| 6 | `session-auth`      | Protected routes bounce anonymous users to `/auth`        |
| 7 | `prelaunch-sweep`   | Scroll + click every safe control on every critical route |
| 8 | `full-regression`   | Chat round-trip, KG, second-brain, mobile, backend health |

Exit code 0 = safe to publish. Non-zero = do not publish.

On failure, Playwright retains a screenshot, a video, and a full trace
under `test-results/` for **failed Playwright tests only** (plus the HTML
report in `playwright-report/`). Build failures (`npm run build`), unit
test failures (`vitest --run`), and suites skipped via short-circuit
(`scripts/prelaunch.sh` exits on the first red step) do not produce
Playwright media — only the spec that actually failed a Playwright run
leaves artifacts. In CI these are uploaded by
`.github/workflows/prelaunch-gate.yml`; locally, replay a trace with
`npx playwright show-trace test-results/<dir>/trace.zip`.

### CI

`.github/workflows/prelaunch-gate.yml` runs this exact script on every PR
targeting `main` and on every push to `main`. It seeds a disposable Supabase
test user when `SUPABASE_SERVICE_ROLE_KEY` is present, and always uploads the
report + failure artifacts.


### Optional: seed a disposable test user before the run

```bash
SUPABASE_URL=https://<project>.supabase.co \
SUPABASE_SERVICE_ROLE_KEY=... \
TEST_USER_EMAIL=preflight+$(date +%s)@example.com \
TEST_USER_PASSWORD='Preflight123!@#XY' \
scripts/prelaunch.sh
```

The script POSTs to the Supabase admin API with `email_confirm=true` and
exports `PLAYWRIGHT_TEST_USER_EMAIL` / `_PASSWORD` for authenticated specs.
Delete the user afterwards from Supabase Studio or the admin API.

## 2. Manual verification — journeys automation cannot cover

Initial each row. Do **not** initial without actually running the flow.

### Auth

- [ ] Google sign-in on desktop: **exactly one** popup, lands on the page
      the user originated from (e.g. bounced from `/profile` → back to `/profile`)
- [ ] Google sign-in on iOS Safari
- [ ] Google sign-in on Android Chrome
- [ ] Forgot password: email arrives within 60s, link opens `/reset-password`,
      new 12-char password is accepted, old rejected
- [ ] Password minimum length is 12 (regression check for `weak_password_policy`)
- [ ] Sign-out clears the Supabase session and bounces to `/`

### Chat

- [ ] Anonymous chat round-trip: message sent, streaming response arrives, no
      "connection issue" fallback
- [ ] Signed-in chat: conversation persists, appears in sidebar on refresh
- [ ] Slash-command menu opens with `/` and inserts a command
- [ ] TTS reads a response aloud; STT records a message
- [ ] Language selector switches UI; response arrives in the selected language

### Meditation

- [ ] Serene Mind: Preethaji audio plays; on network throttle, Web Speech TTS
      fallback kicks in without breaking the step timer
- [ ] Video link opens the correct YouTube practice
- [ ] Meditation session persists to profile (Insights tab shows +1)

### Knowledge & second brain

- [ ] `/knowledge-graph` renders the Obsidian-style force-directed graph,
      drag + zoom work, close button (top-right ✕) returns to previous page
- [ ] `/second-brain` empty state hero renders for a new user
- [ ] Add a note → refresh → note persists

### Profile

- [ ] Hero tile, stats, sparklines render at 375, 768, 1280 CSS px
- [ ] Delete-my-account flow ends at a clean signed-out state (staging only)

### Admin

- [ ] `/admin/login` accepts admin credentials, non-admin credentials are
      rejected with a visible error
- [ ] `/admin/self-check` renders green for at least one healthy backend

### Mobile shell (only when a Capacitor build ships)

- [ ] Google OAuth deep link (`com.askmukthiguru.app://auth-callback`) returns
      to the app and completes sign-in
- [ ] Push notification round-trip: register device → send test push → banner shows

## 3. Pre-publish hygiene

- [ ] `handoff.md` updated with the current turn's state
- [ ] `mem://index.md` reflects any new project decisions
- [ ] Security scan re-run: no NEW high/critical findings
- [ ] No secrets in the diff (`rg -n 'sk-|SUPABASE_SERVICE_ROLE'` returns nothing new)
- [ ] `robots.txt` and `sitemap.xml` still list only intended routes

## 4. Publish

Only after 1–3 are green.

## 5. Post-publish smoke (within 10 min)

- [ ] `BASE_URL=https://askmukthiguru.lovable.app scripts/prelaunch.sh SUITES="page-smoke google-auth-flow"`
- [ ] Manually load the landing page in a fresh incognito window
- [ ] Send one anonymous chat message and confirm the response
- [ ] Check Railway logs for a spike in 5xx or "Vector dimension" errors
      (see CLAUDE.md → "Embedding dimension contract")

## Ponytail note

`prelaunch.sh` reuses existing specs — `page-smoke`, `full-regression`,
`session-auth` — and adds only `google-auth-flow` and `prelaunch-sweep`,
because those two are the failure modes recent regressions actually hit.
No fixtures, no page-object framework, no CI runner rewrite. Grow the
suite by adding one spec file at a time and appending it to `DEFAULT_SUITES`.
