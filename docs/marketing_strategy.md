# Marketing Strategy — Stub

> **Status**: Placeholder. Marketing is not a current priority.
> This doc captures ideas for future reference. Implementation deferred until product-market fit is validated and chat UX is stable.

## Waitlist Strategy

Collect pre-launch signups to build an audience before public launch.

- **Endpoint**: `POST /api/waitlist` (placeholder, returns 501)
- **Fields**: email (required), name (optional)
- **Future**: invite tiers, referral tracking, Stripe integration, email drip campaign

## Daily Wisdom Newsletter

Daily email delivering a teaching excerpt from the corpus.

- **Concept**: Automated pipeline selects a daily passage → LLM generates a short reflection → sent via email provider (Resend / SendGrid / AWS SES)
- **Requires**: content curation pipeline, subscriber management, unsubscribe handling, sending domain + DKIM setup
- **Not started** — deferred until ingestion is complete
