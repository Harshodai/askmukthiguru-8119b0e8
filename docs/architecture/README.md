# Architecture documents

This folder contains the upstream technical reports for the Mukthi Guru
backend, plus a single consolidated, conflict-resolved roadmap that the
frontend team uses to plan integrations.

## How to read these

| File | Purpose | Authoritative? |
|------|---------|----------------|
| [`backend-roadmap.md`](./backend-roadmap.md) | **Single source of truth.** Consolidated, de-duplicated, prioritised. Frontend vs backend split. | ✅ Yes |
| [`source-verified-report.md`](./source-verified-report.md) | Original verified research. Self-corrects the earlier draft. | ✅ For facts in conflict |
| [`source-report.md`](./source-report.md) | Original draft research. Contains some fabricated facts (corrected in verified report). | ❌ Superseded |

## Conflict resolution rule

Where the two source reports disagree, **`source-verified-report.md` always
wins**. Known examples:

- ❌ ~~"Sarvam-2B" model~~ → ✅ `sarvamai/sarvam-30b` is the real public model
- ❌ ~~Sarvam pricing ₹0.50–2 / 1K tokens~~ → ✅ Sarvam Cloud API is currently free per token
- ❌ ~~`@EkamOfficial` YouTube channel~~ → ✅ only `@PreetiKrishna` is verified
- ❌ ~~A100 80GB at ₹55K–2.5L~~ → ✅ ₹220/hr on-demand or ₹65/hr via IndiaAI subsidy

## Scope of this Lovable repo

This repository contains **only the React frontend**. The vast majority of the
recommendations in these reports concern the Python FastAPI backend (in the
sibling `backend/` directory). Those items are tracked in
`backend-roadmap.md` as backend tickets and are **not** implemented here.

A small subset of recommendations is frontend-implementable; those are listed
in `backend-roadmap.md` under "Frontend (this repo)" and have already been
shipped.
