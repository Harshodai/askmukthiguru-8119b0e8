# Frontend hosting fact sheet

Written 2026-11-06 from repository files only (static read, NEW-LOV-07). Nothing here was checked against a live host, Vercel, Lovable or Railway. Items marked UNKNOWN need the owner.

## Short answer

- Which host serves production traffic: **UNKNOWN**. The repository holds evidence for two hosts and does not say which one is live.
- Railway (the backend) is stopped by owner decision until the local clean-sweep passes (CLAUDE.md, Gotchas). So every build below that points at the Railway URL reaches no running backend today.

## Evidence in the repository

| Fact | Where | What it shows |
|---|---|---|
| `PUBLIC_APP_URL = https://askmukthiguru.lovable.app` | `src/lib/domain.ts:17` | The app names a Lovable-hosted address as its public URL. |
| `vercel.json` sets `VITE_BACKEND_URL` to the Railway production URL and adds security headers | `vercel.json` | A Vercel config exists. Whether a Vercel project is connected is UNKNOWN. |
| `.env.production` sets the same `VITE_BACKEND_URL` | `.env.production:3` | Any production-mode Vite build, on any host, embeds the Railway URL unless it is overridden. |
| Prod hostnames are `askmukthiguru.com`, `www.askmukthiguru.com` and the Railway host | `src/lib/backendUrl.ts` (`PROD_HOSTNAMES`) | Only these hosts resolve to the Railway URL by hostname. The Lovable address is not in the list. |
| Docker frontend image is built with mock Supabase values for scanning only | `.github/workflows/build-deploy.yml` (frontend build step) | The CI image is not a deploy artifact. |

## Backend URL by build

Resolution order in `src/lib/backendUrl.ts`: `VITE_BACKEND_URL` if set, else the Railway URL on an exact prod hostname, else an empty string (relative `/api`, or dev localhost).

| Build | `VITE_BACKEND_URL` it gets | Reaches a running backend today |
|---|---|---|
| Vercel (if connected) | Railway URL, from `vercel.json` `env` | No (Railway stopped). Whether it is connected: UNKNOWN. |
| Lovable preview | UNKNOWN. Lovable's build env is not in this repo. If it runs a production-mode build it embeds the `.env.production` value; if a dev build, it falls back to an empty string. | UNKNOWN |
| Lovable publish (`askmukthiguru.lovable.app`) | UNKNOWN, same reason. The hostname is not in `PROD_HOSTNAMES`, so it depends on the build-time variable. | UNKNOWN |
| Custom domain `askmukthiguru.com` | Railway URL by hostname, even with no env var. Which host serves this domain: UNKNOWN. | No (Railway stopped) |
| Local dev (`npm run dev`) | `http://localhost:8000` through the Vite proxy (`vite.config.ts`) | Only with a local backend |
| Native (Capacitor) | None unless `VITE_BACKEND_URL` is set or `VITE_NATIVE_BACKEND=prod`; otherwise calls fail closed | No by default |

## What the owner needs to confirm

1. Which host serves `askmukthiguru.com` today (Vercel, Lovable, other).
2. Whether `lovable.app` is still used by real visitors or only for previews.
3. The build variables set in the Lovable project and the Vercel project (names only; do not paste keys).

When these are known, replace each UNKNOWN above and delete this paragraph.

## Related

- Backend deploy source of truth: `.railway/railway.ts` and `docker-compose.prod.yml`.
- Lovable edit rules: `src/CLAUDE.md`, "Lovable edits".
- Review of the Lovable write path: `audits/audit-output-2026-11-04/specifications/LOVABLE_SYNC_PATH_REVIEW.md`.
