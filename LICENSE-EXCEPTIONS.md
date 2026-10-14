# License Policy Exceptions

The repo policy (CLAUDE.md §"Rules for This Repo") requires every
dependency to be open source under Apache 2.0, MIT, or Meta Community.
This file records approved exceptions for packages that do not meet
that policy but are retained for a documented reason.

## Approved exceptions

| Package | Version | License | Reason | Approved |
|---------|---------|---------|--------|----------|
| `@axe-core/playwright` | `^4.12.1` | MPL-2.0 | Only mature Playwright-integrated WCAG 2.1 AA violation checker; no Apache-2.0/MIT drop-in exists that provides equivalent rule coverage. Used by `tests/e2e/a11y-smoke.spec.ts` to gate the release checklist's a11y step. MPL-2.0 is a weak copyleft OSS license (file-level, not viral at project level) — acceptable for a dev-only test dependency that never ships in the production bundle. | 2026-07-28 |
| `axe-core` | `^4.12.1` | MPL-2.0 | Transitive peer of `@axe-core/playwright`; the underlying WCAG rule engine. Same justification — dev-only, never bundled into the shipped app. | 2026-07-28 |
| `easydict` | `1.13` | LGPL-3.0 | Transitive via `lettucedetect → rag-fact-checker`; nothing in the repo imports it directly, and LettuceDetect (`backend/services/lettuce_detect_service.py`) is the NLI faithfulness gate with no Apache-2.0/MIT drop-in. Used unmodified, imported dynamically (a Python `import` is dynamic linking under LGPL; the shipped work is not a derivative of the library). Obligations met: library unmodified, license text ships in its pip metadata, any recipient can swap the package version via pip. Dropping LettuceDetect to clear the gate would silently remove a claimed safety check — the worse trade. | 2026-10-14 |

## Review cadence

Re-evaluate at every major release. If an Apache-2.0/MIT-licensed
alternative with equivalent WCAG 2.1 AA coverage becomes available
(e.g., a Playwright-native a11y checker built on W3C's ACT rules
without axe-core), swap it in and drop the exception.

## Scope

The axe rows above cover **devDependencies only** (the `devDependencies`
block in `package.json`). Neither package is imported by any production
source file under `src/` — they are used exclusively by
`tests/e2e/a11y-smoke.spec.ts` and do not appear in the shipped bundle.

The `easydict` row covers a **runtime** transitive dependency. It is allowed
only because all four hold: (a) unmodified use, (b) dynamic import, (c) no
Apache-2.0/MIT alternative for the parent package's function, (d) the CI
license gate names the allowlist explicitly (`LICENSE_ALLOWLIST` in
`dependency-check.yml`) and refuses any allowlisted name not recorded in
this file. A new runtime exception needs the same four, plus this section
updated — a row alone does not clear the gate.
