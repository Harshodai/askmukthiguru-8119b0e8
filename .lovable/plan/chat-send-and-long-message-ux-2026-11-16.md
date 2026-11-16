# Chat send and long-message UX

## Build
- Simplify the active-chat view after sending by removing nonessential consent/promotional clutter while retaining AI disclosure, safety support, quota state, stop, queue, and retry controls.
- Make long drafts easier to manage by removing the custom textarea scroll slider, aligning the visible textarea height limit with its auto-resize limit, and relying on native scrolling.
- Improve long-message layout with robust wrapping, readable line lengths, and small, purposeful message/send transitions.
- Respect the existing reduced-motion setting and preserve streaming checkpoints, focus recovery, queue behavior, attachments, voice, and language controls.

## Technical details
- Reuse existing React, Framer Motion, semantic design tokens, and chat components; no new dependency or backend changes.
- Add focused tests for long text wrapping, composer scroll affordances, active-chat clutter, and existing send/retry states where coverage is absent.
- Validate with targeted chat tests, build telemetry, and phone/tablet/desktop preview checks.