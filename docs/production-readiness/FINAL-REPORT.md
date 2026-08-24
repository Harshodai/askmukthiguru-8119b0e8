# AskMukthiGuru Ruthless Productionization — Final Report

**Date:** 2026-08-21
**Scope:** Local checkout `Harshodai/askmukthiguru-8119b0e8`
**Deployment action:** None. No production deployment, push, secret rotation, or destructive third-party operation was performed.

## Verdict

> **NOT READY FOR PRODUCTION**

The local application gates are green, but release is blocked by unresolved backend dependency vulnerabilities and unverified staging/production evidence. The smallest next action is to create a dependency-upgrade branch, resolve the `pip-audit` findings while rerunning the backend/RAG gates, then run credentialed staging checks with `BACKEND_E2E=true`, RLS probes, backup/restore, migration rollback, and cross-browser security coverage.

## Executive summary

This pass materially hardened the repository without replacing working architecture. Confirmed defects were fixed in health JSON serialization, citation remapping fixtures, BM25 regression policy, regex scanning, local E2E backend selection, stale service-worker isolation, accessibility contrast, ARIA relationships, keyboard interaction, bundle-budget measurement, protected-route smoke behavior, and MFA/security test contracts. The full backend suite, frontend unit suite, typecheck, lint, build, bundle, Chromium accessibility, browser smoke, and final prelaunch gates now pass.

The release decision remains deliberately conservative. `pip-audit` reports known vulnerabilities in the locked backend dependency set; live backend chat/meditation round trips were intentionally not claimed because `BACKEND_E2E=true` was not enabled; the final AAL2 run was Chromium-only; and RLS, backup/restore, migration rollback, production deployment smoke, and real provider verification were not executed in this local pass.

## Changes implemented

| Area | Verified change |
|---|---|
| Health and reliability | Normalized optional-service flags, provider names, cache telemetry, queue depth, backpressure counters, and graph warmup values before JSON encoding. Preserved truthful `ready` versus `status=degraded` semantics. |
| External web search | Documented the fixed DuckDuckGo origin invariant around the bounded fallback request so Bandit passes without accepting user-controlled schemes or hosts. |
| Citation and retrieval | Strengthened citation-diversity fixtures and aligned the BM25 fixture with the documented standard/deep retrieval policy. |
| Regex security | Excluded virtual-environment layouts and handled invalid source encodings safely. |
| Browser isolation | Blocked service workers in Playwright so stale cached bundles cannot mask source fixes. |
| Accessibility | Added the real `sidebar-panel` target for `aria-controls`; fixed chat-sidebar, cookie-consent, footer, and auth contrast; added persistent link styling; converted the practice preview to a keyboard-operable button. |
| E2E contracts | Used the labelled chat composer, dismissed the pre-practice gate explicitly, required `BACKEND_E2E=true` for live provider journeys, accepted intentional auth redirects, and limited AAL2 identity checks to routes that actually require authentication. |
| Quality gates | Added `npm run typecheck`; changed the bundle gate to measure eager/core JS separately from lazy route and locale code; removed an ambiguous Tailwind easing utility. |
| Durable engineering memory | Added release-gate lessons to `lessons.md` and preserved the dated baseline evidence. |

## Verification matrix

| Gate | Result | Evidence |
|---|---:|---|
| Frontend typecheck | **VERIFIED** | `npm run typecheck` exit 0. |
| Frontend lint | **VERIFIED** | Exit 0; 39 warnings, 0 errors. |
| Frontend unit/component tests | **VERIFIED** | 87 files passed, 1 skipped; 506 tests passed, 6 skipped. |
| Frontend build/prerender | **VERIFIED** | Exit 0; 28 routes prerendered. |
| Bundle budget | **VERIFIED** | Eager/core 1.32 MB < 3 MB; total 4.47 MB < 5 MB; largest chunk 462.11 KB < 800 KB. |
| Backend pytest | **VERIFIED** | 2,336 passed, 30 skipped, 1 warning in 238.63 seconds. |
| Bandit | **VERIFIED** | Exit 0; no medium/high findings. |
| Regex safety | **VERIFIED** | Exit 0; no unbounded nested-quantifier literals in runtime Python. |
| Git diff hygiene | **VERIFIED** | `git diff --check` exit 0. |
| Frontend npm audit | **VERIFIED** | 0 vulnerabilities. |
| Page smoke | **VERIFIED** | 14 passed. |
| Accessibility smoke | **VERIFIED** | 8 passed, including meditation flow. |
| Google auth flow | **VERIFIED** | 4 passed. |
| Session/auth flow | **VERIFIED** | 4 passed. |
| Prelaunch sweep | **VERIFIED** | 10 passed. |
| Full regression | **VERIFIED with explicit skips** | 6 passed, 2 skipped because live backend assertions require `BACKEND_E2E=true`. |
| AAL2 security, Chromium | **VERIFIED with explicit skips** | 5 passed, 2 skipped for preview-only source access and the unimplemented backend AAL claim endpoint. |
| Backend dependency audit | **NOT VERIFIED / BLOCKED** | `pip-audit` exited 1. The requirements-file run reported 36 known vulnerabilities across 16 packages; the lockfile audit also exited 1. |
| Live provider chat | **NOT VERIFIED** | Requires staging/production-like services and explicit `BACKEND_E2E=true`. |
| Cross-browser AAL2 matrix | **NOT VERIFIED** | No final green Firefox/WebKit/mobile rerun was claimed. |
| Direct local health | **VERIFIED as degraded** | `/api/health` returned `ready: true`, `status: degraded` because optional OCR was unavailable; `/api/healthz` returned alive. |

## Independent red-team findings

The red-team pass identified that static Vite previews could return HTML 200 responses for `/api/*`, causing false-positive backend readiness and false-negative chat tests. Live provider assertions now require explicit opt-in. It also identified that the AAL2 suite treated anonymous `/chat` as identity-protected even though the product supports anonymous chat with quotas and rate controls. AAL2 coverage now targets `/profile`, `/second-brain`, and admin routes, while anonymous chat remains covered by its own policy tests.

Accessibility failure injection found a real orphaned ARIA relationship, contextual contrast failures in shared overlays/sidebar states, and a keyboard-inaccessible practice control. These were fixed rather than suppressed. The final axe run reports zero serious/critical violations on the audited routes and meditation state.

## Remaining blockers and risks

| Priority | Status | Risk | Next action |
|---|---|---|---|
| P0 | **Open** | Backend dependency lock has known vulnerabilities, including findings affecting Transformers, LangChain/LangGraph packages, `cryptography`, `pyarrow`, `litellm`, `dspy`, `datasets`, `gptcache`, and related packages. | Upgrade in compatibility batches on a dedicated branch; rerun pytest, Bandit, pip-audit, and RAG evaluation after each batch. |
| P0 | **Open** | Real backend chat and meditation round trips were not verified. | Run staging with `BACKEND_E2E=true`, valid auth/test fixtures, reachable Qdrant/Neo4j/Redis/LLM, and latency/error evidence. |
| P1 | **Open** | Cross-browser AAL2 coverage remains unverified. | Rerun the suite across Firefox, WebKit, and mobile projects in CI/staging. |
| P1 | **Open** | RLS cross-user probes, backup/restore drill, migration rollback, and deployment smoke were not executed. | Run the existing RLS, backup-drill, migration-revert, and deployment-verification workflows with required staging secrets. |
| P1 | **Open** | Lint is green but retains 39 warnings, including React Hook dependency and Fast Refresh export warnings. | Triage hook-dependency warnings first, then split non-component exports. |
| P2 | **Open** | Local deep health is degraded only because optional OCR is unavailable. | Confirm OCR policy and alert only on critical readiness loss. |
| P2 | **Open** | Jaeger export was unavailable during pytest but did not block application tests. | Verify staging telemetry endpoints and ensure export failure cannot block requests. |

## Deployment and rollback recommendation

Do not deploy the current checkout as-is. After dependency remediation and staging verification, deploy through the existing repository workflow. Capture the commit SHA, migration state, dependency lock hash, liveness/deep-health responses, and browser artifacts before opening traffic.

For rollback, restore the last known-good image or commit, avoid automatic destructive down-migrations, and preserve forward-compatible migration state unless the migration-revert workflow proves safety. Verify `/api/healthz`, `/api/health`, anonymous/authenticated routes, queue health, and latency/error dashboards before reopening traffic.

## Reproducible commands

```bash
npm run typecheck
npm run lint
npm run test -- --reporter=dot
npm run build
npm run bundle:check
SKIP_BUILD=1 scripts/prelaunch.sh

backend/.venv/bin/python -m pytest backend/tests -q
backend/.venv/bin/ruff check backend
backend/.venv/bin/bandit -r backend -c backend/.bandit -ll
backend/.venv/bin/python scripts/security/check_regex_safety.py
backend/.venv/bin/pip-audit -r backend/requirements.lock --desc
CI=1 npx playwright test --project=chromium tests/e2e/security-aal2.spec.ts
```

## Changed-file inventory

`backend/app/api/health.py`, `backend/services/web_search_service.py`, `backend/tests/test_citation_marker_remap.py`, `backend/tests/test_task3.py`, `lessons.md`, `package.json`, `playwright.config.ts`, `scripts/check-bundle-budget.mjs`, `scripts/security/check_regex_safety.py`, `src/admin/pages/CachePage.tsx`, `src/components/chat/DesktopSidebar.tsx`, `src/components/common/CookieConsentBanner.tsx`, `src/components/landing/Footer.tsx`, `src/pages/AuthPage.tsx`, `src/pages/PracticeDetailPage.tsx`, `tests/e2e/a11y-smoke.spec.ts`, `tests/e2e/full-regression.spec.ts`, `tests/e2e/page-smoke.spec.ts`, `tests/e2e/prelaunch-sweep.spec.ts`, and `tests/e2e/security-aal2.spec.ts`, plus the `docs/production-readiness/` evidence directory.
