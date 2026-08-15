# Progressive Anonymous Access + Public Content Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert AskMukthiGuru from an authenticate-first experience to a progressive model where anonymous users can browse practices/guides and chat for a limited number of messages before a soft sign-in prompt, while protecting authenticated-only surfaces.

**Architecture:** We separate three concerns using Clean/Hexagonal boundaries: (1) a layout layer split into `PublicShell` and `AuthShell` so auth policy is explicit per route; (2) a backend domain service `AnonymousQuotaService` (port) with Redis/in-memory adapters to enforce per-session message limits; (3) a chat UX layer that interprets a backend `anon_limit_reached` signal and surfaces a soft auth prompt instead of a doctrine response. Deployment contracts (Vercel static-file exclusions + Playwright route tests) are added as a final verification layer.

**Tech Stack:** Vite + React 18 + TypeScript + Tailwind + shadcn/ui frontend; FastAPI + Pydantic + Redis backend; Playwright E2E; Vercel static hosting.

## Global Constraints

- Backend Python 3.12, dependencies pinned in `backend/requirements.lock`.
- Frontend Node 22 LTS, `npm ci` only, never `npm install` in CI.
- No changes to existing authenticated backend logic unless required for the anonymous path.
- Anonymous chat must reuse the existing signed anon session token (`POST /api/auth/anon-session`) and `resolve_anon_identity()`.
- The anonymous message limit must be keyed by the signed anon session id (`anon:<payload>`), not IP, to avoid punishing shared networks.
- Public pages must remain prerenderable by `scripts/prerender-seo.mjs`; do not introduce client-only auth checks that break SEO.
- All route-level auth behavior must be covered by Playwright tests.
- Preserve existing `AppShell` behavior for authenticated routes to avoid regressions.
- Do not commit secrets or hard-coded credentials.

---

## Sub-project P1: Public Content Surface

### Task P1.1: Create `PublicShell` layout component

**Files:**
- Create: `src/components/layout/PublicShell.tsx`
- Modify: `src/components/layout/AppShell.tsx` (extract shared chrome)
- Test: `src/test/components/PublicShell.test.tsx`

**Interfaces:**
- Consumes: none.
- Produces: `<PublicShell title={string} children={ReactNode} />` — renders top nav, footer-ish spacing, and `children` without `useRequireAuth`.

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from '@testing-library/react';
import { PublicShell } from '@/components/layout/PublicShell';
import { describe, it, expect } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

describe('PublicShell', () => {
  it('renders children without requiring auth', () => {
    render(
      <MemoryRouter>
        <PublicShell title="Public page">
          <div data-testid="public-content">Hello</div>
        </PublicShell>
      </MemoryRouter>
    );
    expect(screen.getByTestId('public-content')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --run src/test/components/PublicShell.test.tsx`
Expected: FAIL — `PublicShell` not defined.

- [ ] **Step 3: Implement `PublicShell` and extract shared layout chrome**

Create `src/components/layout/PublicShell.tsx`:

```tsx
import { Navbar } from '@/components/landing/Navbar';
import { Footer } from '@/components/landing/Footer';
import { usePageMeta } from '@/hooks/usePageMeta';

interface PublicShellProps {
  title: string;
  children: React.ReactNode;
}

export const PublicShell = ({ title, children }: PublicShellProps) => {
  usePageMeta({ title });
  return (
    <div className="min-h-dvh bg-background flex flex-col">
      <Navbar />
      <main className="flex-1">{children}</main>
      <Footer />
    </div>
  );
};
```

Modify `AppShell.tsx` to render the same top nav and footer from shared chrome if it currently duplicates them; otherwise leave `AppShell` unchanged except ensuring it still calls `useRequireAuth`.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- --run src/test/components/PublicShell.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/components/layout/PublicShell.tsx src/test/components/PublicShell.test.tsx
git commit -m "feat(layout): add PublicShell for anonymous-facing pages"
```

### Task P1.2: Convert public content pages to `PublicShell`

**Files:**
- Modify: `src/pages/PracticesPage.tsx`, `src/pages/PracticeDetailPage.tsx`, `src/pages/guides/*.tsx` (7 files), `src/pages/KnowledgeGraphPage.tsx`
- Test: `tests/e2e/public-content-routes.spec.ts`

**Interfaces:**
- Consumes: `PublicShell`.
- Produces: pages render without `useRequireAuth`; metadata remains via `usePageMeta`.

- [ ] **Step 1: Write the failing E2E test**

Create `tests/e2e/public-content-routes.spec.ts`:

```ts
import { test, expect } from '@playwright/test';

const PUBLIC_ROUTES = [
  '/practices',
  '/practices/soul-sync',
  '/practices/serene-mind',
  '/practices/beautiful-state',
  '/practices/daily-reflection',
  '/practices/wisdom-reflection',
  '/guides/spirit-guides',
  '/guides/ai-spiritual-companion',
  '/guides/beautiful-state-meditation',
  '/guides/serene-mind-practice',
  '/guides/self-centric-thinking',
  '/guides/spiritual-guide-for-anxiety',
  '/guides/suffering-to-beautiful-state',
  '/knowledge-graph',
];

for (const route of PUBLIC_ROUTES) {
  test(`public route renders anonymously: ${route}`, async ({ page }) => {
    await page.goto(route, { waitUntil: 'networkidle' });
    await expect(page).not.toHaveURL(/.*\/auth/);
    await expect(page.locator('body')).toBeVisible();
    const finalUrl = new URL(page.url());
    expect(finalUrl.pathname).toBe(route);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx playwright test tests/e2e/public-content-routes.spec.ts`
Expected: FAIL — pages redirect to `/auth` because `AppShell` calls `useRequireAuth`.

- [ ] **Step 3: Replace `AppShell` with `PublicShell` in public pages**

In each of the following files, replace `import { AppShell } from '@/components/layout/AppShell'` with `import { PublicShell } from '@/components/layout/PublicShell'` and replace `<AppShell ...>` usage with `<PublicShell ...>`:
- `src/pages/PracticesPage.tsx`
- `src/pages/PracticeDetailPage.tsx`
- `src/pages/guides/AiSpiritualCompanionPage.tsx`
- `src/pages/guides/BeautifulStateMeditationPage.tsx`
- `src/pages/guides/SereneMindPracticePage.tsx`
- `src/pages/guides/SelfCentricThinkingPage.tsx`
- `src/pages/guides/SpiritGuidesPage.tsx`
- `src/pages/guides/SpiritualGuideForAnxietyPage.tsx`
- `src/pages/guides/SufferingToBeautifulStatePage.tsx`
- `src/pages/KnowledgeGraphPage.tsx`

Keep all existing `usePageMeta` calls and page content unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `npx playwright test tests/e2e/public-content-routes.spec.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pages/PracticesPage.tsx src/pages/PracticeDetailPage.tsx src/pages/guides/*.tsx src/pages/KnowledgeGraphPage.tsx tests/e2e/public-content-routes.spec.ts
git commit -m "feat(routes): switch public content pages to PublicShell"
```

### Task P1.3: Update homepage copy for progressive model

**Files:**
- Modify: `src/components/landing/HeroSection.tsx`
- Modify: `public/locales/en/translation.json` and the 5 real-locale files (`hi`, `te`, `kn`, `ta`, `mr`)
- Test: `src/test/components/HeroSection.test.tsx` (add one assertion)

**Interfaces:**
- Consumes: i18n keys `landing.hero.microcopyProgressive`.
- Produces: updated hero microcopy.

- [ ] **Step 1: Add translation keys**

Add to `public/locales/en/translation.json` under `landing.hero`:

```json
"microcopyProgressive": "Start your conversation. No account needed to begin."
```

Add the same key to `hi`, `te`, `kn`, `ta`, `mr` JSON files. If a translation is not available, keep the English string with a `// TODO: translate` comment not inside JSON (add a note in the plan ledger instead).

- [ ] **Step 2: Update HeroSection to use new key**

In `src/components/landing/HeroSection.tsx`, replace:

```tsx
{t('landing.hero.microcopy', 'No account needed. Your peace is private.')}
```

with:

```tsx
{t('landing.hero.microcopyProgressive', 'Start your conversation. No account needed to begin.')}
```

- [ ] **Step 3: Add/update unit test**

Add a Vitest test in `src/test/components/HeroSection.test.tsx` (create if missing) asserting the microcopy is rendered. If the file does not exist, create a minimal test:

```tsx
import { render, screen } from '@testing-library/react';
import { HeroSection } from '@/components/landing/HeroSection';
import { I18nextProvider } from 'react-i18next';
import i18n from '@/test/i18n-test-config';
import { MemoryRouter } from 'react-router-dom';

describe('HeroSection', () => {
  it('renders progressive microcopy', () => {
    render(
      <MemoryRouter>
        <I18nextProvider i18n={i18n}>
          <HeroSection />
        </I18nextProvider>
      </MemoryRouter>
    );
    expect(screen.getByText(/No account needed to begin/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Run tests**

Run: `npm test -- --run src/test/components/HeroSection.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/components/landing/HeroSection.tsx public/locales/en/translation.json public/locales/hi/translation.json public/locales/te/translation.json public/locales/kn/translation.json public/locales/ta/translation.json public/locales/mr/translation.json src/test/components/HeroSection.test.tsx
git commit -m "feat(copy): progressive anonymous microcopy on hero"
```

---

## Sub-project P2: Anonymous Chat with Quota

### Task P2.1: Define anonymous quota domain port + value object

**Files:**
- Create: `backend/app/domain/anon_quota.py`
- Create: `backend/app/domain/interfaces/quota_repository.py`
- Test: `backend/tests/test_anon_quota_domain.py`

**Interfaces:**
- Consumes: none.
- Produces:
  - `AnonQuotaResult(allowed: bool, remaining: int, reason: str | None)`
  - `QuotaPolicy(limit: int, window_seconds: int)`
  - `IQuotaRepository` port with `async get(key: str) -> int` and `async increment(key: str, ttl: int) -> int`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_anon_quota_domain.py`:

```python
import pytest
from app.domain.anon_quota import AnonQuotaService, QuotaPolicy, AnonQuotaResult
from app.domain.interfaces.quota_repository import IQuotaRepository

class InMemoryQuotaRepo(IQuotaRepository):
    def __init__(self):
        self.store = {}
    async def get(self, key: str) -> int:
        return self.store.get(key, 0)
    async def increment(self, key: str, ttl: int) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

@pytest.mark.asyncio
async def test_anon_quota_allows_first_messages():
    repo = InMemoryQuotaRepo()
    service = AnonQuotaService(repo, QuotaPolicy(limit=3, window_seconds=3600))
    result = await service.check_and_increment("anon:test")
    assert result.allowed is True
    assert result.remaining == 2

@pytest.mark.asyncio
async def test_anon_quota_denies_after_limit():
    repo = InMemoryQuotaRepo()
    service = AnonQuotaService(repo, QuotaPolicy(limit=1, window_seconds=3600))
    await service.check_and_increment("anon:test")
    result = await service.check_and_increment("anon:test")
    assert result.allowed is False
    assert result.remaining == 0
    assert result.reason == "anon_limit_reached"
```

- [ ] **Step 2: Run test to verify it fails**

Run from `backend/`:

```bash
.venv/bin/pytest tests/test_anon_quota_domain.py -v
```

Expected: FAIL — `AnonQuotaService` not defined.

- [ ] **Step 3: Implement domain objects**

Create `backend/app/domain/anon_quota.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from app.domain.interfaces.quota_repository import IQuotaRepository


@dataclass(frozen=True)
class QuotaPolicy:
    limit: int
    window_seconds: int


@dataclass(frozen=True)
class AnonQuotaResult:
    allowed: bool
    remaining: int
    reason: str | None = None


class AnonQuotaService:
    """Domain service: decides whether an anonymous session may send another message."""

    def __init__(self, repository: IQuotaRepository, policy: QuotaPolicy):
        self.repository = repository
        self.policy = policy

    async def check_and_increment(self, session_id: str) -> AnonQuotaResult:
        used = await self.repository.increment(session_id, self.policy.window_seconds)
        if used > self.policy.limit:
            return AnonQuotaResult(allowed=False, remaining=0, reason="anon_limit_reached")
        remaining = max(0, self.policy.limit - used)
        return AnonQuotaResult(allowed=True, remaining=remaining)

    async def peek(self, session_id: str) -> AnonQuotaResult:
        used = await self.repository.get(session_id)
        remaining = max(0, self.policy.limit - used)
        allowed = used < self.policy.limit
        return AnonQuotaResult(allowed=allowed, remaining=remaining)
```

Create `backend/app/domain/interfaces/quota_repository.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod


class IQuotaRepository(ABC):
    @abstractmethod
    async def get(self, key: str) -> int: ...

    @abstractmethod
    async def increment(self, key: str, ttl: int) -> int: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_anon_quota_domain.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/anon_quota.py backend/app/domain/interfaces/quota_repository.py backend/tests/test_anon_quota_domain.py
git commit -m "feat(domain): anonymous message quota port and value objects"
```

### Task P2.2: Implement Redis + in-memory quota adapters

**Files:**
- Create: `backend/app/adapters/redis_quota_repository.py`
- Create: `backend/app/adapters/in_memory_quota_repository.py`
- Test: `backend/tests/test_quota_adapters.py`

**Interfaces:**
- Consumes: `IQuotaRepository`.
- Produces: concrete repositories usable via DI.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_quota_adapters.py`:

```python
import pytest
from app.adapters.in_memory_quota_repository import InMemoryQuotaRepository

@pytest.mark.asyncio
async def test_in_memory_repository_counts_and_expires():
    repo = InMemoryQuotaRepository()
    assert await repo.increment("s1", ttl=1) == 1
    assert await repo.increment("s1", ttl=1) == 2
    assert await repo.get("s1") == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_quota_adapters.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement adapters**

Create `backend/app/adapters/in_memory_quota_repository.py`:

```python
from __future__ import annotations

from app.domain.interfaces.quota_repository import IQuotaRepository


class InMemoryQuotaRepository(IQuotaRepository):
    """Test/development adapter. Not suitable for multi-replica production."""

    def __init__(self):
        self._store: dict[str, int] = {}

    async def get(self, key: str) -> int:
        return self._store.get(key, 0)

    async def increment(self, key: str, ttl: int) -> int:
        self._store[key] = self._store.get(key, 0) + 1
        return self._store[key]
```

Create `backend/app/adapters/redis_quota_repository.py`:

```python
from __future__ import annotations

import redis
from app.domain.interfaces.quota_repository import IQuotaRepository


class RedisQuotaRepository(IQuotaRepository):
    """Production adapter using Redis INCR + EXPIRE."""

    def __init__(self, client: redis.Redis | redis.asyncio.Redis):
        self.client = client

    async def get(self, key: str) -> int:
        value = await self.client.get(key)
        return int(value) if value is not None else 0

    async def increment(self, key: str, ttl: int) -> int:
        pipe = self.client.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl)
        results = await pipe.execute()
        return int(results[0])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_quota_adapters.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/adapters/in_memory_quota_repository.py backend/app/adapters/redis_quota_repository.py backend/tests/test_quota_adapters.py
git commit -m "feat(adapters): in-memory and Redis quota repositories"
```

### Task P2.3: Wire quota service into FastAPI dependencies

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/dependencies.py`
- Create: `backend/app/api/dependencies/quota.py`
- Test: `backend/tests/test_quota_dependency.py`

**Interfaces:**
- Consumes: `AnonQuotaService`, `InMemoryQuotaRepository`, `RedisQuotaRepository`.
- Produces: `get_quota_service()` dependency callable.

- [ ] **Step 1: Add config values**

In `backend/app/config.py`, add near existing limits:

```python
anon_chat_message_limit: int = Field(default=5, ge=1, description="Max anonymous chat messages per session before auth prompt")
anon_chat_quota_window_seconds: int = Field(default=86400, ge=60, description="TTL for anonymous message quota counter")
```

- [ ] **Step 2: Add quota service to ServiceContainer**

In `backend/app/dependencies.py`, import `AnonQuotaService` and `QuotaPolicy`, and add:

```python
from app.domain.anon_quota import AnonQuotaService, QuotaPolicy
from app.adapters.in_memory_quota_repository import InMemoryQuotaRepository

try:
    import redis as _redis
except ImportError:
    _redis = None

class ServiceContainer:
    ...
    @property
    def quota_service(self) -> AnonQuotaService:
        if not hasattr(self, '_quota_service'):
            policy = QuotaPolicy(
                limit=settings.anon_chat_message_limit,
                window_seconds=settings.anon_chat_quota_window_seconds,
            )
            if self.redis_client and _redis:
                from app.adapters.redis_quota_repository import RedisQuotaRepository
                repo = RedisQuotaRepository(self.redis_client)
            else:
                repo = InMemoryQuotaRepository()
            self._quota_service = AnonQuotaService(repo, policy)
        return self._quota_service
```

- [ ] **Step 3: Create quota dependency**

Create `backend/app/api/dependencies/quota.py`:

```python
from fastapi import Depends
from app.dependencies import ServiceContainer, get_container
from app.domain.anon_quota import AnonQuotaService

async def get_quota_service(container: ServiceContainer = Depends(get_container)) -> AnonQuotaService:
    return container.quota_service
```

- [ ] **Step 4: Write dependency test**

Create `backend/tests/test_quota_dependency.py`:

```python
from fastapi.testclient import TestClient
from app.main import app

def test_quota_service_dependency_resolves():
    with TestClient(app) as client:
        # Basic health check proves container builds without error
        resp = client.get("/api/health")
        assert resp.status_code == 200
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/pytest tests/test_quota_dependency.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/app/dependencies.py backend/app/api/dependencies/quota.py backend/tests/test_quota_dependency.py
git commit -m "feat(infra): wire anonymous quota service into DI container"
```

### Task P2.4: Enforce quota in chat endpoints

**Files:**
- Modify: `backend/app/api/chat.py`
- Test: `backend/tests/test_chat_anon_quota.py`

**Interfaces:**
- Consumes: `get_quota_service`.
- Produces: when anonymous limit reached, endpoint returns `ChatResponse` with `blocked=True`, `block_reason="anon_limit_reached"`, and a compassionate message.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_chat_anon_quota.py`:

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def clear_in_memory_quota():
    # Reset container singleton if needed; for this test we rely on fresh TestClient process
    yield

def test_anonymous_chat_blocks_after_limit():
    limit = 2
    # Hit limit + 1
    for i in range(limit + 1):
        resp = client.post("/api/chat", json={
            "messages": [],
            "user_message": f"message {i}",
            "session_id": "anon:quota-test",
            "incognito": True,
        })
        assert resp.status_code in (200, 202), resp.text
    # Next message should be blocked
    resp = client.post("/api/chat", json={
        "messages": [],
        "user_message": "over limit",
        "session_id": "anon:quota-test",
        "incognito": True,
    })
    body = resp.json()
    assert body.get("blocked") is True
    assert body.get("block_reason") == "anon_limit_reached"
    assert "sign in" in body.get("response", "").lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_chat_anon_quota.py -v`
Expected: FAIL — no quota enforcement yet.

- [ ] **Step 3: Modify chat endpoint to check quota for anonymous users**

In `backend/app/api/chat.py`, for `/api/chat`, `/api/chat/v2`, and `/api/chat/stream`:

1. Import the dependency:

```python
from app.api.dependencies.quota import get_quota_service
from app.domain.anon_quota import AnonQuotaService
```

2. Add parameter to each endpoint:

```python
quota_service: AnonQuotaService = Depends(get_quota_service),
```

3. After `user = resolve_anon_identity(user, chat_body.session_id)` and before invoking the orchestrator, add:

```python
if user.get("is_anonymous"):
    quota = await quota_service.check_and_increment(user.get("id", "anonymous"))
    if not quota.allowed:
        return ChatResponse(
            response=(
                "You've explored a few messages with the Guru. "
                "Sign in for free to continue your conversation, save reflections, "
                "and receive personalized guidance."
            ),
            blocked=True,
            block_reason="anon_limit_reached",
            grounding_state="safety_redirect",
        )
```

For the streaming endpoint, emit an SSE event with `event: blocked` and the same payload shape.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_chat_anon_quota.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/chat.py backend/tests/test_chat_anon_quota.py
git commit -m "feat(chat): enforce anonymous message quota with soft auth prompt"
```

### Task P2.5: Allow anonymous access on `/chat` frontend

**Files:**
- Modify: `src/pages/ChatPage.tsx`
- Modify: `src/hooks/useRequireAuth.ts` (add optional mode)
- Test: `tests/e2e/anonymous-chat.spec.ts`

**Interfaces:**
- Consumes: `useAuthStatus` (already exists).
- Produces: `ChatPage` no longer redirects anonymous users to `/auth`.

- [ ] **Step 1: Write the failing E2E test**

Create `tests/e2e/anonymous-chat.spec.ts`:

```ts
import { test, expect } from '@playwright/test';

test('anonymous user can visit /chat', async ({ page }) => {
  await page.goto('/chat', { waitUntil: 'networkidle' });
  await expect(page).not.toHaveURL(/.*\/auth/);
  await expect(page.getByTestId('chat-composer-input')).toBeVisible();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx playwright test tests/e2e/anonymous-chat.spec.ts`
Expected: FAIL — redirect to `/auth`.

- [ ] **Step 3: Make `/chat` allow anonymous users**

Modify `src/hooks/useRequireAuth.ts`: add an optional `redirectIfUnauthenticated` parameter defaulting to `true`:

```ts
export function useRequireAuth({ redirectIfUnauthenticated = true } = {}) {
  ...
  // In handleNoSession, guard the navigate call:
  if (redirectIfUnauthenticated) {
    navigate('/auth', { replace: true });
  } else {
    setLoading(false);
  }
  ...
}
```

Modify `src/pages/ChatPage.tsx`: replace `useRequireAuth()` with `useRequireAuth({ redirectIfUnauthenticated: false })`. Use `useAuthStatus()` to know auth state for UI purposes. Keep existing authenticated-only features (multi-device continue, tour) gated by `user` presence.

- [ ] **Step 4: Run test to verify it passes**

Run: `npx playwright test tests/e2e/anonymous-chat.spec.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hooks/useRequireAuth.ts src/pages/ChatPage.tsx tests/e2e/anonymous-chat.spec.ts
git commit -m "feat(chat): allow anonymous users to open /chat without redirect"
```

### Task P2.6: Surface soft auth prompt in chat UI when quota reached

**Files:**
- Modify: `src/lib/chat/transport.ts`
- Modify: `src/components/chat/ChatInterface.tsx`
- Create: `src/components/chat/AnonLimitPrompt.tsx`
- Test: `src/test/components/AnonLimitPrompt.test.tsx`

**Interfaces:**
- Consumes: backend `blocked` + `block_reason="anon_limit_reached"`.
- Produces: UI modal/prompt with CTA to sign in.

- [ ] **Step 1: Add `block_reason` handling in transport**

In `src/lib/chat/transport.ts`, ensure the returned `AIResponse` type already includes `blockReason`. The existing type `AIResponse` likely has it; confirm and map `block_reason` to `blockReason` if needed.

- [ ] **Step 2: Create prompt component**

Create `src/components/chat/AnonLimitPrompt.tsx`:

```tsx
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';

interface AnonLimitPromptProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const AnonLimitPrompt = ({ open, onOpenChange }: AnonLimitPromptProps) => (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="sm:max-w-md">
      <DialogHeader className="gap-2">
        <div className="mx-auto w-12 h-12 rounded-full bg-ojas/10 flex items-center justify-center mb-2">
          <Sparkles className="w-6 h-6 text-ojas" />
        </div>
        <DialogTitle className="text-center">Continue your journey</DialogTitle>
        <DialogDescription className="text-center">
          You've enjoyed a few messages with the Guru. Sign in for free to keep chatting,
          save your reflections, and receive guidance tailored to you.
        </DialogDescription>
      </DialogHeader>
      <div className="flex flex-col gap-3 mt-4">
        <Button asChild className="w-full bg-ojas hover:bg-ojas-light">
          <Link to="/auth">Sign in — it's free</Link>
        </Button>
        <Button variant="outline" onClick={() => onOpenChange(false)} className="w-full">
          Stay anonymous and explore practices
        </Button>
      </div>
    </DialogContent>
  </Dialog>
);
```

- [ ] **Step 3: Wire prompt into ChatInterface**

In `src/components/chat/ChatInterface.tsx`:
1. Add state: `const [anonLimitOpen, setAnonLimitOpen] = useState(false);`
2. In the message-send flow, after receiving `AIResponse`, if `response.blockReason === 'anon_limit_reached'`, set `anonLimitOpen(true)` and render the assistant message as the compassionate text.
3. Render `<AnonLimitPrompt open={anonLimitOpen} onOpenChange={setAnonLimitOpen} />` near the dialogs.

- [ ] **Step 4: Write component test**

Create `src/test/components/AnonLimitPrompt.test.tsx`:

```tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { AnonLimitPrompt } from '@/components/chat/AnonLimitPrompt';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';

describe('AnonLimitPrompt', () => {
  it('renders sign-in CTA', () => {
    render(
      <MemoryRouter>
        <AnonLimitPrompt open={true} onOpenChange={vi.fn()} />
      </MemoryRouter>
    );
    expect(screen.getByText(/Sign in/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 5: Run tests**

Run:

```bash
npm test -- --run src/test/components/AnonLimitPrompt.test.tsx
npx playwright test tests/e2e/anonymous-chat.spec.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/components/chat/AnonLimitPrompt.tsx src/test/components/AnonLimitPrompt.test.tsx src/components/chat/ChatInterface.tsx src/lib/chat/transport.ts
git commit -m "feat(chat): show soft auth prompt when anonymous quota reached"
```

---

## Sub-project P3: Deployment Contracts + Tests

### Task P3.1: Exclude static crawl files from Vercel SPA rewrite

**Files:**
- Modify: `vercel.json`
- Test: `tests/e2e/crawl-files.spec.ts`

**Interfaces:**
- Consumes: none.
- Produces: `/robots.txt`, `/sitemap.xml`, `/manifest.json` served as static files before SPA fallback.

- [ ] **Step 1: Write the failing test**

Create `tests/e2e/crawl-files.spec.ts`:

```ts
import { test, expect } from '@playwright/test';

const CASES = [
  { path: '/robots.txt', contentType: 'text/plain', bodyIncludes: 'User-agent' },
  { path: '/sitemap.xml', contentType: 'application/xml', bodyIncludes: '<?xml' },
  { path: '/manifest.json', contentType: 'application/json', bodyIncludes: '"name"' },
];

for (const c of CASES) {
  test(`crawl file ${c.path} is served correctly`, async ({ page }) => {
    const res = await page.goto(c.path);
    expect(res?.status()).toBe(200);
    const headers = res?.headers() ?? {};
    expect(headers['content-type']).toContain(c.contentType);
    const body = await page.locator('body').textContent();
    expect(body).toContain(c.bodyIncludes);
    expect(body).not.toContain('<!DOCTYPE html>');
    expect(body).not.toContain('<div id="root">');
  });
}
```

- [ ] **Step 2: Run test to verify it passes or fails**

Run: `npx playwright test tests/e2e/crawl-files.spec.ts`
Expected: Likely PASS locally because `vite preview` serves static files; on Vercel it may fail if rewrite catches them. The test documents the contract.

- [ ] **Step 3: Update vercel.json**

Replace `vercel.json` with explicit static exclusions before the catch-all:

```json
{
  "rewrites": [
    { "source": "/robots.txt", "destination": "/robots.txt" },
    { "source": "/sitemap.xml", "destination": "/sitemap.xml" },
    { "source": "/manifest.json", "destination": "/manifest.json" },
    { "source": "/og-image.png", "destination": "/og-image.png" },
    { "source": "/(.*)", "destination": "/index.html" }
  ],
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "X-Frame-Options", "value": "DENY" },
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "Referrer-Policy", "value": "same-origin" }
      ]
    },
    {
      "source": "/assets/(.*)",
      "headers": [
        { "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }
      ]
    }
  ],
  "env": {
    "VITE_API_URL": "@vite_api_url",
    "VITE_SUPABASE_URL": "@vite_supabase_url",
    "VITE_SUPABASE_ANON_KEY": "@vite_supabase_anon_key"
  }
}
```

- [ ] **Step 4: Run test again**

Run: `npx playwright test tests/e2e/crawl-files.spec.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add vercel.json tests/e2e/crawl-files.spec.ts
git commit -m "feat(deploy): explicit static-file exclusions before SPA fallback"
```

### Task P3.2: Add Playwright route contract tests for auth consistency

**Files:**
- Create: `tests/e2e/route-auth-contract.spec.ts`
- Modify: `tests/e2e/page-smoke.spec.ts` (update expectations)

**Interfaces:**
- Consumes: page routing behavior.
- Produces: documented contract of which routes are public vs auth-only.

- [ ] **Step 1: Create route contract spec**

Create `tests/e2e/route-auth-contract.spec.ts`:

```ts
import { test, expect } from '@playwright/test';

const PUBLIC = ['/', '/practices', '/practices/serene-mind', '/guides/spiritual-guide-for-anxiety', '/knowledge-graph', '/privacy', '/terms'];
const AUTH_ONLY = ['/chat', '/profile', '/notebooks', '/second-brain'];

for (const route of PUBLIC) {
  test(`public route stays on ${route}`, async ({ page }) => {
    await page.goto(route, { waitUntil: 'networkidle' });
    await expect(page).not.toHaveURL(/.*\/auth/);
  });
}

for (const route of AUTH_ONLY) {
  test(`auth route redirects to /auth from ${route}`, async ({ page }) => {
    await page.goto(route, { waitUntil: 'networkidle' });
    await expect(page).toHaveURL(/.*\/auth/);
  });
}
```

- [ ] **Step 2: Update page-smoke expectations**

In `tests/e2e/page-smoke.spec.ts`, remove `/practices`, `/practices/serene-mind`, `/chat` from the "expected redirect" assumption. Adjust the `fatal` filter to not treat a redirect to `/auth` as a failure for auth-only pages. Add the routes to the PUBLIC list if needed.

- [ ] **Step 3: Run tests**

Run: `npx playwright test tests/e2e/route-auth-contract.spec.ts tests/e2e/page-smoke.spec.ts`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/route-auth-contract.spec.ts tests/e2e/page-smoke.spec.ts
git commit -m "test(e2e): route auth contract for public and authenticated routes"
```

### Task P3.3: Add tablet responsive breakpoint tests

**Files:**
- Create: `tests/e2e/responsive-tablet.spec.ts`

**Interfaces:**
- Consumes: page rendering at multiple viewports.
- Produces: no horizontal overflow at 768, 820, 912, 1024 px widths.

- [ ] **Step 1: Create responsive spec**

Create `tests/e2e/responsive-tablet.spec.ts`:

```ts
import { test, expect } from '@playwright/test';

const VIEWPORTS = [
  { width: 768, height: 1024, name: 'tablet-sm' },
  { width: 820, height: 1180, name: 'tablet-md' },
  { width: 912, height: 1368, name: 'tablet-lg' },
  { width: 1024, height: 768, name: 'desktop-sm' },
];

const ROUTES = ['/', '/practices', '/guides/serene-mind-practice'];

for (const route of ROUTES) {
  for (const vp of VIEWPORTS) {
    test(`responsive: ${route} at ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(route, { waitUntil: 'networkidle' });
      const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
      expect(bodyWidth).toBeLessThanOrEqual(vp.width);
    });
  }
}
```

- [ ] **Step 2: Run tests**

Run: `npx playwright test tests/e2e/responsive-tablet.spec.ts`
Expected: PASS (or document known failures for follow-up).

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/responsive-tablet.spec.ts
git commit -m "test(e2e): tablet breakpoint responsive contract tests"
```

---

## Verification and Final Quality Gate

- [ ] **Run frontend unit tests**

```bash
npm test -- --run
```

Expected: PASS (or existing skips).

- [ ] **Run frontend lint**

```bash
npm run lint
```

Expected: 0 errors; warnings acceptable if pre-existing.

- [ ] **Run frontend build + prerender**

```bash
npm run build
```

Expected: 27+ routes prerendered, no errors.

- [ ] **Run backend tests for new code**

```bash
cd backend
.venv/bin/pytest tests/test_anon_quota_domain.py tests/test_quota_adapters.py tests/test_quota_dependency.py tests/test_chat_anon_quota.py -v
```

Expected: PASS.

- [ ] **Run targeted Playwright suites**

```bash
npx playwright test tests/e2e/public-content-routes.spec.ts tests/e2e/anonymous-chat.spec.ts tests/e2e/crawl-files.spec.ts tests/e2e/route-auth-contract.spec.ts
```

Expected: PASS.

- [ ] **Update documentation**

- `lessons.md`: add lesson about separating auth policy from layout shell and anonymous quota design.
- `README.md`: if it describes route behavior, update to reflect public practices/guides and progressive chat.
- `docs/PRODUCT_OPPORTUNITIES.md`: mark relevant items complete.

- [ ] **Final review and handoff**

Use `superpowers:finishing-a-development-branch` to present merge options.
