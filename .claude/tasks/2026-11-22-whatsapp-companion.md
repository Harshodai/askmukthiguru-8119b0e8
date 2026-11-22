# WhatsApp companion follow-up — approval pending

Implementation plan: `.lovable/plan.md`. Current-branch evidence: `docs/plans/2026-11-21-whatsapp-direct-research.md`, 2026-11-22 follow-up.

1. Confirm Meta app, use-case eligibility and supported coexistence path before any number action. Reason: phone-app continuity and India eligibility cannot be inferred from ownership.
2. Repair existing linking/Profile privacy flow, with unchecked optional consents and fresh two-channel proof. Reason: current defaults conflict with explicit-consent requirements; forwarded links must not bind accounts.
3. Route verified linked identity through existing trusted teaching services. Reason: current unsigned public chat request does not carry the linked profile.
4. Persist opt-out/reset/handoff and durable inbound/outbound state. Reason: confirmations and API acceptance must match stored outcomes, including restart recovery.
5. Add concise WhatsApp menus and ordinary text entry; preserve language, exact quotes and source links. Reason: familiar navigation without pretending WhatsApp can mirror the website UI.
6. Add focused regressions, run dependency-complete tests in CI/test image, and verify authenticated linking/Profile on devices. Then perform authorized real receiving/reply/delivery/readback/unlink test. Reason: mocks and source inspection cannot establish live operation.

No implementation, production deployment, number migration, credential change, message send or spend in this planning pass. Meta setup and human-help destination remain external dependencies. Update task outcomes after approval.