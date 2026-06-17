# Phases 2-4 Delivery Notes

## Phase 2 — Admin Deep Audit
- Full report: [`docs/ADMIN_AUDIT_REPORT.md`](./ADMIN_AUDIT_REPORT.md)
- Headline: **wiring is correct on all 16 admin pages**. The reason metrics "look wrong" is that 14 of 20 source tables are empty in your prod DB. One SQL call fixes the demo state:
  ```sql
  SELECT public.seed_admin_demo();   -- run while authenticated as admin
  ```
- Two minor frontend gaps flagged: `useFeedbackEvents` hook missing; `useAppLogs(requestId)` filter view missing. Add when you start collecting real feedback.
- Real fix path (no demo seed) is in **Recommendation A** of the report — confirm FastAPI `/api/chat` writes `chat_queries`, `chat_responses`, `retrieval_events`, `trace_spans`, and `app_logs` on every turn with a shared `request_id`.

## Phase 3 — Chat UX Polish
Earlier turn already tightened spacing + starter-pill sizing and added `ChatEmptyState` with "Continue last conversation" and "Today's teaching" cards. No additional changes needed for v1; the next high-leverage UX work is reactive streaming token rendering, which is a backend change (already covered in `docs/IMPROVEMENTS_BACKEND.md`).

## Phase 4 — Load Test + Production Hosting

### Load test
- Script: `scripts/benchmarks/smoke.sh` — 50 RPS × 120 s against `/healthz` + 60-req burst against `chat-rate-limit`.
- Doc: [`docs/LOAD_TEST_RESULTS.md`](./LOAD_TEST_RESULTS.md) — acceptance criteria, how to read `hey` output, troubleshooting.
- Run with:
  ```bash
  export PROJECT_REF=fynkjimvuimakgtidvuq
  export ANON_KEY=<publishable key>
  ./scripts/benchmarks/smoke.sh
  ```

### Production hosting (India, cheap)
- Doc: [`docs/PRODUCTION_HOSTING_INDIA.md`](./PRODUCTION_HOSTING_INDIA.md)
- TL;DR pick:
  - Frontend + auth + DB + edge functions + storage → stay on **Lovable Cloud (ap-south-1)**.
  - FastAPI + Qdrant + Redis + Neo4j → **AWS Lightsail Mumbai 4 GB (~$12/mo)**, or **Inservers IN-MID (₹1 600/mo)** if you want INR/GST.
  - LLM → route by language: Indic → `sarvam-m`, everything else → `google/gemini-2.5-flash`. Both via **Lovable AI Gateway** — no self-hosted Sarvam 30B in prod.
  - Total at 10k MAU / 200k turns: **~₹7 300 / mo (~$87)**.
- Full deploy steps + nginx + certbot snippets in the doc.

## Next step you choose
1. Run `SELECT public.seed_admin_demo();` and reload the admin dashboard.
2. Run `scripts/benchmarks/smoke.sh` and paste output to verify p95 < 500 ms.
3. Pick a hosting provider from the comparison table and I'll generate a `docker-compose.prod.yml` + GitHub Actions deploy workflow tailored to it.
