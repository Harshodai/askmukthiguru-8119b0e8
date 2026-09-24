# Chat Enter Fix and Public UI Journey Audit

## Goal
Fix the confirmed chat composer defects, then finish the remaining frontend-only user journey audit across web, Android-sized, and iOS-sized layouts.

## 1. Fix chat keyboard submission
- Remove the duplicate plain-Enter submit path from `ChatInterface`; let the installed AI Elements `PromptInputTextarea` own Enter-to-submit and Shift+Enter-to-newline.
- Keep page-specific keyboard behavior only for Up-arrow recall and preserve IME composition safety for CJK and Indic input.
- Preserve Cmd/Ctrl+Enter shortcut, message queueing while streaming, attachments, and the Send button.
- Add regression tests proving Enter submits exactly once, Shift+Enter does not submit, and composition Enter does not submit.

## 2. Fix textarea hit area
- Make the full visible prompt area focus the textarea without intercepting footer controls, menus, attachments, or the submit button.
- Remove conflicting minimum-height styling and establish one stable multiline text area with a 44px minimum touch target.
- Verify direct clicks near the visible top, center, and lower text region all place focus in the textarea.

## 3. Finish public user journey audit
- Test landing sections and navigation, practices and practice details, knowledge graph/wisdom map, notebooks, Second Brain signed-out state, guides, auth/reset, privacy, terms, and not-found behavior.
- Exercise real visible controls where frontend-only behavior is available; treat unavailable backend responses separately from UI failures.
- Check phone and desktop layouts for overlap, horizontal overflow, unreachable controls, focus order, 44px targets, safe areas, and coherent return-to-chat navigation.
- Confirm toolbar consolidation remains correct on fresh local storage and does not regress when an older conversation is restored.

## 4. Validation
- Run focused composer, IME, toolbar, and mobile viewport tests, followed by the full frontend test/lint/typecheck/build gates.
- Run Playwright from clean browser contexts with service workers cleared and local storage isolated.
- Capture evidence for Enter send, Shift+Enter newline, direct textarea focus, fresh toolbar menu, and every public route at phone and desktop widths.
- Record authenticated Profile as externally blocked unless a managed test session becomes available; do not weaken auth or create bypasses.

## Technical notes
- Frontend-only scope. No backend, database, authentication-policy, spiritual-answer, or deployment changes.
- Reuse installed AI Elements and existing design tokens. No new dependency.
- Existing toolbar consolidation stays intact.
