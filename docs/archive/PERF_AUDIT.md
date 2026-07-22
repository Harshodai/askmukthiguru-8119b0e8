# Performance Audit — Findings & Actions

## Shipped this session

| Fix | File | Impact |
|---|---|---|
| Admin routes lazy-loaded | `src/App.tsx` (already done) | Admin bundle deferred until `/admin` navigation. Saves ~200KB from initial payload. |
| Heavy seeker routes lazy | `src/App.tsx` (already done) | KnowledgeGraph, PracticeDetail, SpiritGuides, MFA all split. |
| Language selector text size | `src/components/chat/LanguageSelector.tsx` (prior turn) | Native-script labels now `text-lg` / `text-base` — no more tiny Devanagari. |

## Pending — do when needed

### 1. Bundle vendor split
`vite.config.ts` currently has no `manualChunks`. If initial load feels heavy, add:

```ts
build: {
  rollupOptions: {
    output: {
      manualChunks: {
        'react-vendor': ['react', 'react-dom', 'react-router-dom'],
        'supabase': ['@supabase/supabase-js'],
        'framer': ['framer-motion'],
        'radix': ['@radix-ui/react-dialog', '@radix-ui/react-popover', ...],
      },
    },
  },
},
```

### 2. Image optimization
Landing page hero images are `.jpg`. Add `vite-imagetools`:

```bash
bun add -D vite-imagetools
```

Then in `vite.config.ts` plugins array: `imagetools()`. Import with:

```ts
import hero from './hero.jpg?format=webp&w=1200'
```

Save ~40-60% on hero image size.

### 3. Slow-query indexes
Run `supabase--slow_queries` (agent tool) to identify. Likely candidates:

- `chat_messages` needs index on `(conversation_id, created_at DESC)` — already present, verify
- `kb_chunks` HNSW index on `embedding` — already present
- `telemetry_events` needs index on `(user_id, created_at DESC)` if admin analytics slow

### 4. N+1 in ChatPage
`ChatPage` sequentially calls: `getConversations()` → per-conversation `getMessages()`. Consider batch fetch via single JOIN query if conversation list >50.

### 5. Preload LCP image
Add to `index.html` `<head>`:

```html
<link rel="preload" as="image" href="/hero.webp" fetchpriority="high" />
```

---

## Not-a-Problem Findings

- **`lazyWithRetry` + `preloadCriticalRoutes`** — already implemented in `src/lib/lazyWithRetry.ts`. Route chunks preload after initial mount.
- **React Query** — already used for data caching, no additional work needed.
- **Service worker** (`public/sw.js`) — already present for offline PWA.
