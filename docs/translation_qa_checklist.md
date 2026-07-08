# Translation QA Checklist (H2.7)

> Purpose: confirm that auto-translation of non-English user input **never blocks** user message rendering or input clearing. Translation must run *after* the user's message is appended to the list and the input box is cleared.

## Background

AskMukthiGuru auto-translates non-English user text to English before sending it to the AI (see `src/hooks/useAutoTranslate.ts` and the submit flow in `src/components/chat/ChatInterface.tsx`).

The contract:

1. User message is appended to the message list (`setMessages([...prev, userMessage])`).
2. Input box is cleared (`setInputValue('')`).
3. **Only then** does `translateToEnglish()` run (an `await` on the MyMemory API, 6s timeout).
4. On failure, the original text is used as a fail-safe — the chat never breaks.

This means translation latency only delays the *AI request*, not what the user sees in their own bubble or the input field.

## Instrumentation

`ChatInterface.handleSubmit` logs a `[Translation] translateToEnglish` console.info after each translation with:
- `ms` — wall-clock duration of the translation call
- `blockedRender` — always `false` (asserts the contract)
- `inputLen` / `outputLen` — to detect no-op or truncated translations

A `[Translation] translateToEnglish failed` console.warn fires on failure with the same shape.

## Test Steps

Run these for **at least one non-English language** (e.g. Hindi `hi`, Telugu `te`, Tamil `ta`) and **English** as a control.

### 1. Render-before-translate (user message visibility)

- [ ] Select a non-English language in the LanguageSelector.
- [ ] Type a message in the selected language and press **Send**.
- [ ] **Expected:** The user's message bubble appears in the chat list **immediately** (in the original language), with no visible delay attributable to translation.
- [ ] **Fail:** If the user bubble only appears after a noticeable pause (i.e. translation blocked the render).

### 2. Input clearing (input not held hostage by translation)

- [ ] With a non-English language selected, type a message and press **Send**.
- [ ] **Expected:** The input textarea is cleared **immediately** on send, before the translation completes.
- [ ] **Fail:** If the typed text remains in the input box while the translation is in flight.

### 3. Translation failure does not break the chat

- [ ] Simulate a translation failure (e.g. block `api.mymemory.translated.net` via DevTools → Network → Block request URL).
- [ ] Send a non-English message.
- [ ] **Expected:** The user bubble appears immediately, the input clears, and the AI still receives a request (using the original untranslated text as a fail-safe). A `[Translation] translateToEnglish failed` warning appears in the console.
- [ ] **Fail:** If the chat hangs, the message is lost, or the AI request is never sent.

### 4. Console instrumentation present

- [ ] Open DevTools → Console.
- [ ] Send a non-English message.
- [ ] **Expected:** A `[Translation] translateToEnglish` info log appears with `ms`, `blockedRender: false`, `inputLen`, `outputLen`.
- [ ] **Fail:** If no such log appears when a non-English language is active, or `blockedRender` is ever `true`.

### 5. English control (no translation overhead)

- [ ] Switch the LanguageSelector back to English.
- [ ] Send a message.
- [ ] **Expected:** No `[Translation]` log appears (translation is inactive for `en`). Render and input clearing are immediate.

### 6. Streaming still works after translation

- [ ] Send a non-English message and wait for the streaming guru response.
- [ ] **Expected:** The streaming response renders token-by-token with no large gaps attributable to the earlier translation. The loading indicator (ThinkingPills) shows while waiting for the first token.

## Regression Notes

- If a future change moves the `translateToEnglish` call **before** the `setMessages`/`setInputValue` calls, this contract breaks — translation would block both the user bubble render and input clearing. The `[Translation]` instrumentation's `blockedRender: false` assertion is the canary; if it ever becomes `true` or the log fires before the user bubble is painted, treat it as a regression.
- The MyMemory API has a 6s timeout (`AbortSignal.timeout(6000)`). Translation must never exceed this; on timeout the fail-safe returns the original text.