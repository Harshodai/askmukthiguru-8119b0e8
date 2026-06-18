# Ruthless Continuation Plan

Three workstreams, executed in one build pass.

## 1. Fix Memory ("guru_memories" missing)

Root cause: `src/lib/memoryApi.ts` and the `memory-embed` edge function reference `guru_memories`, `guru_core_memory`, `guru_session_summaries`, and `chat_sessions`, but none exist in the DB. The `match_user_memories` RPC also points at `public.guru_memories`. Result: "Could not find the table 'public.guru_memories' in the schema cache."

Migration (single transaction):

- `guru_memories` — `user_id`, `content`, `embedding vector(384)`, `source` ('extracted'|'explicit'), `confidence`, `decay_score`, `claim`, timestamps. HNSW index on embedding. RLS: owner-only. GRANTs for `authenticated` + `service_role`.
- `guru_core_memory` — `user_id` UNIQUE, `content` text (≤2048), `updated_at`. RLS owner-only.
- `guru_session_summaries` — `user_id`, `session_id`, `summary`, `created_at`. RLS owner-only.
- `chat_sessions` — `user_id`, `created_at` (used by `getConversations`). RLS owner-only. (Lightweight; conversations table already exists but API expects this name.)
- Recreate `match_user_memories` RPC against the new table (already exists, will re-validate signature).
- Standard GRANT block per project convention (no `anon`).

## 2. Chat empty-state + sample-question alignment

Current issues observed in `ChatInterface.tsx` (lines 1366-1390) and `ChatEmptyState.tsx`:

- Empty-state cards constrained to `max-w-xl` while transcript uses `max-w-3xl` — wasted horizontal space.
- "Continue" card is small/cramped, no visual hierarchy, doesn't feel inviting.
- Starter pills use rigid 3-column grid with `min-h-[48px]` — awkward on tablet, text gets clipped to 2 lines.

Fixes:

- Widen empty-state container to match transcript width (`max-w-3xl`), make "Continue last conversation" the hero card (full-width on top, larger type, preview snippet + 2 message-count chip + relative time), with "Today's Teaching" as secondary card below or side-by-side on `md+`.
- Replace starter pills grid with an asymmetric responsive layout: 1-col mobile, 2-col tablet, 3-col desktop, auto-height, refined typography (font-serif italic accent on first word), subtle gold left-border on hover, no clipping.
- Apply UI-UX-Pro-Max skill principles: clear visual hierarchy, generous whitespace, single primary action per card, motion entrance stagger.
- Token-only styling (ojas/gold + glass), no hardcoded colors.

(Skill repo `nextlevelbuilder/ui-ux-pro-max-skill` — apply its hierarchy/whitespace/contrast heuristics; do not fetch external code, just apply the principles since project memory already encodes the visual system.)

## 3. Pending / partial items closeout

From prior phases, still open:

- **Eval-gate dataset**: extend `backend/evaluation/golden_dataset.json` from placeholder 3 to a real 15-question golden set covering Beautiful State, Serene Mind, distress, citations, refusal.
- **README status badge**: add the `/healthz` shields.io badge to top of `README.md`.
- **Lazy YouTube thumbnails**: convert citation iframes in `ChatMessage` to click-to-load thumbnail (`https://i.ytimg.com/vi/<id>/hqdefault.jpg`) — saves ~250 KB per citation.
- **Fire-and-forget `memory-extract` invoke**: ensure `ChatInterface` write-back to `pending_extractions` uses `void supabase.functions.invoke(...)` without await (verify; patch if still awaited).

## Technical Notes

- Memory tables use `vector(384)` to match `all-MiniLM-L6-v2` already used by `memory-embed`.
- `chat_sessions` is intentionally minimal — just session_id + created_at — since the real conversation data lives in `conversations`/`chat_messages` already.
- All new tables follow the mandatory CREATE→GRANT→RLS→POLICY order.
- No changes to backend Python (FastAPI) — all changes are frontend + edge-function-adjacent SQL.

## Out of scope (deferred)

- Hosting migration to Lightsail Mumbai (waiting on user pick).
- Productionization workflow (waiting on hosting decision).

Ready to build on approval.  
  
Need to work on below as well:  
1. Chat UI should be top notch and you need to refer the skill files present in [https://github.com/nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) repo and also use your intelligence to fix the issues, 

2. Make Sure the experience is world class and top notch in all supported devices