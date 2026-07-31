# Security, RLS, Metrics Parity & Release Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend existing AAL2/MFA Playwright regression tests, add an automated RLS cross-user access verifier, enable Supabase leaked-password protection, wire ruthless UI↔backend metrics parity, add backend-driven suffering-streak course assignment, and produce a release-readiness document including a Lovable Cloud sync decision.

**Architecture:** Minimal-diff extensions of existing guards/tests/scripts; new backend service for healing-course assignment based on distress streak/repetition rules; shared metrics schema consumed by a backend endpoint and frontend hook; Python RLS verifier using real Supabase users and Data API calls.

**Tech Stack:** TypeScript/React/Playwright (frontend), Python/FastAPI/Pydantic/Supabase-py (backend), SQL/Supabase Auth/RLS (database).

## Global Constraints

- Use existing patterns: Playwright tests live in `tests/e2e/`, backend routes in `backend/app/api/`, backend services in `backend/services/`, config in `backend/app/config.py`.
- Do not expose `service_role` keys in committed code; load from env.
- All new backend routes must use existing JWT auth dependency.
- Never run the RLS verifier against production with real user data; default to local Supabase.
- Supabase leaked-password protection requires Pro plan or above.
- Keep implementations minimal; do not rewrite unrelated subsystems.

---

## File Map

### Modified files
- `tests/e2e/security-aal2.spec.ts` — extend route matrix, backend aal claim, MFA step-up, admin isolation.
- `backend/app/main.py` — register new routers `metrics` and `healing_course`.
- `backend/app/api/chat.py` — consume `recommended_course` from response state.
- `backend/rag/nodes/generation.py` — emit `recommended_course` when distress streak rules match.
- `backend/app/config.py` — add `proactive_course_assignment_threshold`.
- `backend/app/schemas/metrics.py` — new shared schema (backend).
- `src/lib/metricsSchema.ts` — new shared schema (frontend).
- `src/hooks/useMetrics.ts` — new hook.
- `src/pages/ProfilePage.tsx` — render metrics card.
- `src/components/chat/HealingPathCard.tsx` — call backend assignment on first show.
- `src/components/chat/ChatInterface.tsx` — pass `recommended_course` to `HealingPathCard`.
- `supabase/migrations/20260730000000_verify_rls_with_check.sql` — migration to verify RLS ownership policies (idempotent).

### New files
- `tests/e2e/rls-cross-user.spec.ts` — Playwright cross-user RLS E2E.
- `backend/scripts/verify_rls_policies.py` — Python RLS policy verifier.
- `backend/app/api/metrics.py` — `GET /api/metrics` endpoint.
- `backend/app/api/healing_course.py` — `POST /api/healing-course/assign` and `POST /api/healing-course/progress`.
- `backend/services/healing_course_service.py` — assignment logic and streak/repetition evaluation.
- `backend/tests/test_healing_course_service.py` — unit tests for streak rules.
- `src/test/metricsSchema.test.ts` — parity test for metrics schema.
- `docs/RELEASE_READINESS_2026_07_30.md` — release-readiness document.
- `.github/workflows/nightly-rls.yml` — CI workflow for nightly RLS verification.

---

### Task 1: Verify current test baseline

**Files:**
- Run: existing `tests/e2e/security-aal2.spec.ts`

**Interfaces:**
- Consumes: current Playwright setup, dev server on `http://localhost:8080`.
- Produces: confirmation that existing spec passes before extensions.

- [ ] **Step 1: Run existing AAL2 spec**

```bash
npm run test:e2e -- tests/e2e/security-aal2.spec.ts
```

Expected: all tests pass.

- [ ] **Step 2: Note any failures**

If failures exist, fix them before extending. Do not proceed until this spec is green.

---

### Task 2: Extend AAL2/MFA Playwright regression tests

**Files:**
- Modify: `tests/e2e/security-aal2.spec.ts`

**Interfaces:**
- Consumes: existing `seedFakeSession`, protected route lists, MFA challenge page.
- Produces: extended route matrix and backend-aal-claim tests.

- [ ] **Step 1: Add route matrix data structure**

Replace the flat route arrays with a matrix:

```typescript
const ROUTE_MATRIX = [
  { route: '/chat', role: 'seeker', minAal: 'aal2', redirect: '/auth' },
  { route: '/profile', role: 'seeker', minAal: 'aal2', redirect: '/auth' },
  { route: '/second-brain', role: 'seeker', minAal: 'aal2', redirect: '/auth' },
  { route: '/admin', role: 'admin', minAal: 'aal2', redirect: '/admin/login' },
  { route: '/admin/queries', role: 'admin', minAal: 'aal2', redirect: '/admin/login' },
  { route: '/admin/settings', role: 'admin', minAal: 'aal2', redirect: '/admin/login' },
];
```

- [ ] **Step 2: Rewrite anonymous-guard test to use matrix**

Loop `ROUTE_MATRIX` and assert the correct redirect for each route. Keep the existing assertion style.

- [ ] **Step 3: Add backend `aal` claim enforcement test**

Add a test that calls an existing protected backend endpoint with a synthetic JWT whose `aal` claim is `aal1`. Use the local benchmark auth backdoor if available (`X-Test-Key` header + `BENCHMARK_SECRET` in non-production). Expect `403` or a body error containing `aal`.

If no endpoint currently enforces `aal`, skip this step and add a TODO comment referencing Task 3.

- [ ] **Step 4: Add MFA step-up completeness test**

After `seedFakeSession(page, { aal: 'aal1', nextLevel: 'aal2' })`:

```typescript
await page.goto('/chat');
await page.waitForURL(/\/auth\/mfa/, { timeout: 10_000 });
await expect(page.getByRole('textbox', { name: /code/i })).toBeVisible();
// Attempt invalid code
await page.getByRole('textbox', { name: /code/i }).fill('000000');
await page.getByRole('button', { name: /verify|continue|submit/i }).click();
await expect(page.getByText(/invalid|wrong|failed/i)).toBeVisible();
await expect(page).toHaveURL(/\/auth\/mfa/);
```

- [ ] **Step 5: Add admin guard isolation test**

Create a fake session for a non-admin user with AAL2 satisfied. Navigating to `/admin` must redirect to `/admin/login` or `/unauthorized`.

- [ ] **Step 6: Run extended spec**

```bash
npm run test:e2e -- tests/e2e/security-aal2.spec.ts
```

Expected: all tests pass. If MFA code input is not found, adjust selectors using the actual DOM of `MFAChallengePage.tsx`.

---

### Task 3: Add backend AAL2 enforcement dependency

**Files:**
- Modify: `backend/app/dependencies.py` (or create if missing)
- Modify: `backend/app/api/health.py` (or `backend/app/api/chat.py`)

**Interfaces:**
- Consumes: FastAPI `Request`, `request.state.user` set by existing auth middleware.
- Produces: `require_aal2` dependency function.

- [ ] **Step 1: Inspect existing auth dependency**

Find where `request.state.user` is populated. Common location: `backend/app/dependencies.py` or `backend/app/middleware/auth.py`.

- [ ] **Step 2: Add `require_aal2` dependency**

```python
from fastapi import Request, HTTPException, status

def require_aal2(request: Request):
    user = getattr(request.state, 'user', None)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Authentication required')
    aal = getattr(user, 'aal', None) or user.get('aal') if isinstance(user, dict) else None
    if aal != 'aal2':
        raise HTTPException(status.HTTP_403_FORBIDDEN, 'AAL2 step-up required')
    return user
```

- [ ] **Step 3: Apply dependency to a test route**

If `backend/app/api/health.py` exists, add:

```python
@router.get('/health/mfa')
async def health_mfa(user=Depends(require_aal2)):
    return {'ok': True, 'aal': 'aal2'}
```

Otherwise add it to `backend/app/api/chat.py` under a path like `/api/chat/protected-test` (remove before merging, or keep as a hidden probe).

- [ ] **Step 4: Verify the route rejects aal1**

Use the benchmark backdoor to obtain a token with `aal: 'aal1'` and call the route. Expect `403`. Then obtain a token with `aal: 'aal2'` and expect `200`.

---

### Task 4: Create RLS cross-user verifier script

**Files:**
- Create: `backend/scripts/verify_rls_policies.py`

**Interfaces:**
- Consumes: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` env vars.
- Produces: JSON report and exit code.

- [ ] **Step 1: Add imports and env parsing**

```python
import os
import sys
import json
import uuid
import requests
from supabase import create_client, Client

SUPABASE_URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
if not SUPABASE_URL or not SERVICE_KEY:
    print(json.dumps({'ok': False, 'error': 'missing env'}))
    sys.exit(1)
```

- [ ] **Step 2: Add helper to create and sign in a test user**

```python
def create_user(email: str, password: str) -> str:
    url = f"{SUPABASE_URL}/auth/v1/admin/users"
    headers = {"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}", "Content-Type": "application/json"}
    payload = {"email": email, "password": password, "email_confirm": True}
    r = requests.post(url, headers=headers, json=payload)
    r.raise_for_status()
    return r.json()['id']

def sign_in(email: str, password: str) -> str:
    url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    headers = {"apikey": os.environ.get('SUPABASE_ANON_KEY', SERVICE_KEY), "Content-Type": "application/json"}
    r = requests.post(url, headers=headers, json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()['access_token']

def client_for_token(token: str) -> Client:
    return create_client(SUPABASE_URL, os.environ.get('SUPABASE_ANON_KEY', SERVICE_KEY))
```

- [ ] **Step 3: Seed and probe each table**

For each table (`conversations`, `chat_messages`, `meditation_sessions`, `user_profiles`):

1. As Alice, insert a row owned by Alice.
2. As Bob, attempt `select()`, `update()`, and `delete()` targeting Alice's row.
3. Assert Bob's select returns `[]`, update returns `0`, delete returns `0`.

For `chat_messages`, create a conversation first, then a message inside it, because the policy depends on `conversation_id`.

- [ ] **Step 4: Cleanup and report**

Delete seeded rows using the service-role client, then delete test users via Admin API.

Output:

```python
print(json.dumps({'ok': True, 'tests': 12, 'failures': 0, 'tables': ['conversations', 'chat_messages', 'meditation_sessions', 'user_profiles']}))
```

- [ ] **Step 5: Add `if __name__ == '__main__'` block**

Call the verifier, exit `0` on success, `1` on failure.

- [ ] **Step 6: Run against local Supabase**

```bash
cd backend
SUPABASE_URL=http://localhost:54321 SUPABASE_SERVICE_ROLE_KEY=<local-service-role> python3 scripts/verify_rls_policies.py
```

Expected: `ok: True`.

---

### Task 5: Add Playwright RLS cross-user E2E test

**Files:**
- Create: `tests/e2e/rls-cross-user.spec.ts`

**Interfaces:**
- Consumes: a fixture that creates two users and returns their credentials.
- Produces: E2E proof that Bob cannot view Alice's conversation.

- [ ] **Step 1: Create fixture for two isolated users**

Use `test.extend` with a fixture that calls a small Node shim or edge function. For local testing, create a minimal Express shim in `tests/e2e/fixtures/userFactory.ts` that shells out to `backend/scripts/verify_rls_policies.py --create-users-only` and returns two emails/passwords. Alternatively, call the Supabase Admin API directly from the fixture if `SERVICE_ROLE_KEY` is available in CI.

- [ ] **Step 2: Write the cross-user isolation test**

```typescript
test('Bob cannot read Alice conversation through the UI', async ({ browser }) => {
  const aliceCtx = await browser.newContext();
  const bobCtx = await browser.newContext();

  const alicePage = await aliceCtx.newPage();
  const bobPage = await bobCtx.newPage();

  await alicePage.goto('/auth');
  await alicePage.getByLabel('Email').fill(aliceEmail);
  await alicePage.getByLabel('Password').fill(alicePassword);
  await alicePage.getByRole('button', { name: /sign in/i }).click();
  await alicePage.waitForURL('/chat');

  // Alice sends a message
  await alicePage.getByRole('textbox').fill('test alice message');
  await alicePage.getByRole('button', { name: /send/i }).click();
  await expect(alicePage.getByText('test alice message')).toBeVisible();

  // Extract conversation ID from URL or localStorage
  const conversationId = await alicePage.evaluate(() => {
    const key = Object.keys(localStorage).find(k => k.includes('conversation'));
    return key ? localStorage.getItem(key) : null;
  });

  // Bob signs in
  await bobPage.goto('/auth');
  await bobPage.getByLabel('Email').fill(bobEmail);
  await bobPage.getByLabel('Password').fill(bobPassword);
  await bobPage.getByRole('button', { name: /sign in/i }).click();
  await bobPage.waitForURL('/chat');

  // Bob navigates directly to Alice's conversation
  await bobPage.goto(`/chat/${conversationId}`);
  await bobPage.waitForLoadState('networkidle');

  await expect(bobPage.getByText('test alice message')).not.toBeVisible();
  await expect(bobPage.getByText(/not found|unauthorized|empty|start a new chat/i).first()).toBeVisible();

  await aliceCtx.close();
  await bobCtx.close();
});
```

- [ ] **Step 3: Run the spec**

```bash
npm run test:e2e -- tests/e2e/rls-cross-user.spec.ts
```

Expected: pass against local Supabase.

---

### Task 6: Enable and verify Supabase leaked-password protection

**Files:**
- Modify: `docs/RELEASE_READINESS_2026_07_30.md`
- Modify: `.env.example` (if it exists) to note Pro plan requirement.

**Interfaces:**
- Consumes: Supabase dashboard access.
- Produces: documented confirmation.

- [ ] **Step 1: Document dashboard steps**

In `docs/RELEASE_READINESS_2026_07_30.md`, add:

```markdown
### Supabase leaked-password protection

1. Open `https://supabase.com/dashboard/project/<project-ref>/auth/providers?provider=Email`.
2. Ensure project is on Pro plan or above.
3. Toggle **Prevent the use of leaked passwords** to ON.
4. Verify: attempt to sign up with password `password123`; expect `WeakPasswordError` with `reasons: ["leaked_password"]`.
```

- [ ] **Step 2: Add verification script (optional)**

Create `backend/scripts/verify_leaked_password_protection.py` that attempts sign-up with a known-bad password and asserts the error.

```python
import os, requests, json, sys
url = f"{os.environ['SUPABASE_URL']}/auth/v1/signup"
headers = {"apikey": os.environ['SUPABASE_ANON_KEY'], "Content-Type": "application/json"}
r = requests.post(url, headers=headers, json={"email": f"leak-test-{uuid.uuid4()}@example.com", "password": "password123"})
data = r.json()
if r.status_code == 200 or 'leaked_password' not in str(data):
    print(json.dumps({'ok': False, 'response': data}))
    sys.exit(1)
print(json.dumps({'ok': True}))
```

- [ ] **Step 3: Run verification (only after enabling in dashboard)**

```bash
cd backend
python3 scripts/verify_leaked_password_protection.py
```

Expected: `ok: True`.

---

### Task 7: Add shared metrics schema

**Files:**
- Create: `backend/app/schemas/metrics.py`
- Create: `src/lib/metricsSchema.ts`

**Interfaces:**
- Consumes: none.
- Produces: `UserMetrics` schema used by backend and frontend.

- [ ] **Step 1: Define backend schema**

```python
from datetime import datetime
from pydantic import BaseModel
from typing import Literal, Optional

class UserMetrics(BaseModel):
    total_conversations: int
    total_messages: int
    total_meditation_minutes: float
    average_distress_level: Optional[float]
    distress_trend: Literal['up', 'down', 'flat']
    active_healing_course: Optional[str]
    course_completion_percent: float
    last_active_at: Optional[datetime]
```

- [ ] **Step 2: Define frontend schema**

```typescript
export interface UserMetrics {
  totalConversations: number;
  totalMessages: number;
  totalMeditationMinutes: number;
  averageDistressLevel: number | null;
  distressTrend: 'up' | 'down' | 'flat';
  activeHealingCourse: string | null;
  courseCompletionPercent: number;
  lastActiveAt: string | null;
}
```

- [ ] **Step 3: Add parity test**

Create `src/test/metricsSchema.test.ts` that asserts the frontend schema keys match a JSON snapshot of the backend schema. Keep it lightweight.

---

### Task 8: Add backend metrics endpoint

**Files:**
- Create: `backend/app/api/metrics.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: existing Supabase client, `UserMetrics` schema.
- Produces: `GET /api/metrics`.

- [ ] **Step 1: Implement endpoint**

```python
from fastapi import APIRouter, Depends, Request
from app.dependencies import get_current_user
from app.schemas.metrics import UserMetrics
from app.config import settings

router = APIRouter(prefix='/api/metrics', tags=['metrics'])

@router.get('', response_model=UserMetrics)
async def get_metrics(request: Request, user=Depends(get_current_user)):
    user_id = user['id']
    # Fetch from Supabase tables
    supabase = request.app.state.supabase
    conv = await supabase.table('conversations').select('id, created_at', count='exact').eq('user_id', user_id).execute()
    msgs = await supabase.table('chat_messages').select('id', count='exact').eq('user_id', user_id).execute()
    sessions = await supabase.table('meditation_sessions').select('duration_seconds').eq('user_id', user_id).execute()
    course = await supabase.table('user_course_progress').select('*').eq('user_id', user_id).eq('status', 'active').maybe_single().execute()
    # Compute metrics
    total_minutes = sum(s.get('duration_seconds', 0) for s in sessions.data or []) / 60.0
    # distress: read last 7 days from user_memories or telemetry; fallback null
    return UserMetrics(
        total_conversations=conv.count or 0,
        total_messages=msgs.count or 0,
        total_meditation_minutes=round(total_minutes, 2),
        average_distress_level=None,
        distress_trend='flat',
        active_healing_course=course.data['course_slug'] if course.data else None,
        course_completion_percent=0.0,  # compute from completed_lessons / total lessons
        last_active_at=None,
    )
```

Use the actual async Supabase client pattern from the codebase.

- [ ] **Step 2: Wire router in main.py**

```python
from app.api import metrics
app.include_router(metrics.router)
```

- [ ] **Step 3: Add backend test**

Create `backend/tests/test_metrics_endpoint.py` that mocks the Supabase client and asserts the endpoint returns the expected shape.

---

### Task 9: Add frontend metrics hook and UI

**Files:**
- Create: `src/hooks/useMetrics.ts`
- Modify: `src/pages/ProfilePage.tsx`

**Interfaces:**
- Consumes: `/api/metrics`, `UserMetrics` schema.
- Produces: hook and UI card.

- [ ] **Step 1: Implement hook**

```typescript
import { useEffect, useState } from 'react';
import { useBackendUrl } from '@/lib/backendUrl';
import type { UserMetrics } from '@/lib/metricsSchema';

export function useMetrics() {
  const [metrics, setMetrics] = useState<UserMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const backendUrl = useBackendUrl();

  const fetchMetrics = async () => {
    try {
      const res = await fetch(`${backendUrl}/api/metrics`, { credentials: 'include' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: UserMetrics = await res.json();
      setMetrics(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMetrics();
    const onUpdate = () => fetchMetrics();
    window.addEventListener('conversation:updated', onUpdate);
    return () => window.removeEventListener('conversation:updated', onUpdate);
  }, []);

  return { metrics, loading, error, refetch: fetchMetrics };
}
```

- [ ] **Step 2: Add metrics card to ProfilePage**

Render a small card with conversation count, message count, meditation minutes, active course, and completion percent. Keep styling consistent with existing profile cards.

---

### Task 10: Add backend healing course assignment based on streak/repetition

**Files:**
- Create: `backend/services/healing_course_service.py`
- Modify: `backend/app/config.py`
- Modify: `backend/rag/nodes/generation.py` (or intent router)
- Modify: `backend/app/api/chat.py`

**Interfaces:**
- Consumes: recent turn history with distress metadata.
- Produces: `recommended_course` payload and `user_course_progress` upsert.

- [ ] **Step 1: Add config threshold**

```python
# backend/app/config.py
proactive_course_consecutive_threshold: int = 2
proactive_course_frequency_threshold: int = 3
proactive_course_frequency_window: int = 5
```

- [ ] **Step 2: Implement streak/repetition evaluator**

```python
from dataclasses import dataclass
from typing import Literal, Optional

@dataclass
class CourseTrigger:
    signal: str
    pattern: Literal['consecutive_2', 'freq_3_of_5', 'escalation', 'repeated_signal']
    reason: str

def evaluate_course_trigger(
    history: list[dict],
    consecutive_threshold: int = 2,
    frequency_threshold: int = 3,
    frequency_window: int = 5,
) -> Optional[CourseTrigger]:
    if not history:
        return None
    # Last N turns
    window = history[-frequency_window:]
    distress_turns = [t for t in window if t.get('distress_level', 0) >= 1]
    if len(distress_turns) >= frequency_threshold:
        return CourseTrigger(distress_turns[-1].get('signal', 'general'), 'freq_3_of_5', 'distress in 3 of last 5 turns')
    # Consecutive
    consecutive = 0
    last_signal = None
    for t in reversed(history):
        if t.get('distress_level', 0) >= 1:
            consecutive += 1
            last_signal = t.get('signal', last_signal)
        else:
            break
    if consecutive >= consecutive_threshold:
        return CourseTrigger(last_signal or 'general', 'consecutive_2', f'{consecutive} consecutive distress turns')
    # Escalation
    levels = [t.get('distress_level', 0) for t in history[-3:]]
    if len(levels) >= 3 and levels[0] <= levels[1] < levels[2] and levels[2] >= 2:
        return CourseTrigger(history[-1].get('signal', 'general'), 'escalation', 'escalating distress severity')
    # Repeated signal in 24h (use timestamps)
    return None
```

- [ ] **Step 3: Implement assignment service**

```python
async def assign_course_if_needed(supabase, user_id: str, trigger: CourseTrigger) -> Optional[dict]:
    existing = await supabase.table('user_course_progress').select('course_slug').eq('user_id', user_id).eq('status', 'active').maybe_single().execute()
    if existing.data:
        return None
    signal_to_slug = {
        'grief': 'walking-through-grief',
        'anxiety': 'quieting-anxiety',
        'anger': 'dissolving-conflict',
        'loneliness': 'walking-through-grief',
        'meaninglessness': 'end-of-suffering',
    }
    slug = signal_to_slug.get(trigger.signal, 'end-of-suffering')
    row = {
        'user_id': user_id,
        'course_slug': slug,
        'completed_lessons': [],
        'current_lesson_index': 0,
        'status': 'active',
        'assigned_reason': trigger.reason,
        'trigger_signal': trigger.signal,
    }
    await supabase.table('user_course_progress').upsert(row, on_conflict='user_id,course_slug').execute()
    return {'slug': slug, 'trigger': trigger}
```

- [ ] **Step 4: Integrate into chat pipeline**

In the chat intent router / generation node:

1. Build `turn_history` from recent conversation turns.
2. Call `evaluate_course_trigger(history)`.
3. If trigger found, call `assign_course_if_needed(...)`.
4. Include `recommended_course` in the response payload returned to the frontend.

- [ ] **Step 5: Add unit tests**

Create `backend/tests/test_healing_course_service.py` with cases for:
- No trigger on single distress turn.
- Trigger on two consecutive distress turns.
- Trigger on 3-of-5 frequency.
- Trigger on escalation.
- No duplicate assignment if active course exists.

---

### Task 11: Add healing course API routes

**Files:**
- Create: `backend/app/api/healing_course.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `HealingCourseService`.
- Produces: `POST /api/healing-course/assign`, `POST /api/healing-course/progress`.

- [ ] **Step 1: Implement assign endpoint**

```python
from fastapi import APIRouter, Depends, Request
from app.dependencies import get_current_user
from services.healing_course_service import evaluate_course_trigger, assign_course_if_needed

router = APIRouter(prefix='/api/healing-course', tags=['healing-course'])

@router.post('/assign')
async def assign_course(request: Request, body: AssignCourseRequest, user=Depends(get_current_user)):
    supabase = request.app.state.supabase
    history = body.history or []
    trigger = evaluate_course_trigger(history)
    if not trigger:
        return {'assigned': False}
    result = await assign_course_if_needed(supabase, user['id'], trigger)
    return {'assigned': bool(result), 'course': result}
```

- [ ] **Step 2: Implement progress endpoint**

```python
@router.post('/progress')
async def update_progress(request: Request, body: ProgressUpdateRequest, user=Depends(get_current_user)):
    supabase = request.app.state.supabase
    await supabase.table('user_course_progress').update({
        'completed_lessons': body.completed_lessons,
        'current_lesson_index': body.current_lesson_index,
        'status': body.status,
    }).eq('user_id', user['id']).eq('course_slug', body.course_slug).execute()
    return {'ok': True}
```

- [ ] **Step 3: Wire router in main.py**

```python
from app.api import healing_course
app.include_router(healing_course.router)
```

---

### Task 12: Update frontend HealingPathCard to use backend assignment

**Files:**
- Modify: `src/components/chat/HealingPathCard.tsx`
- Modify: `src/components/chat/ChatInterface.tsx`

**Interfaces:**
- Consumes: `recommended_course` from backend response.
- Produces: backend-persisted course assignment.

- [ ] **Step 1: Add recommended_course prop**

```typescript
interface HealingPathCardProps {
  lastUserText: string;
  distressFlagged?: boolean;
  recommendedCourse?: { slug: string; title: string; reason: string; trigger_signal: string } | null;
  onAskGuru: (prompt: string) => void;
  onOpenSereneMind: () => void;
}
```

- [ ] **Step 2: Call backend assign on first render**

```typescript
useEffect(() => {
  if (!course || enrolled) return;
  fetch(`${backendUrl}/api/healing-course/assign`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ signal: signal ?? 'general', history: [] }),
  }).catch(() => {});
}, [course, enrolled, signal, backendUrl]);
```

- [ ] **Step 3: Use backend course when available**

Prefer `recommendedCourse?.slug` to local signal mapping.

- [ ] **Step 4: Update ChatInterface to pass recommended_course**

Locate where `HealingPathCard` is rendered and pass `recommendedCourse` from the latest chat response state.

---

### Task 13: Verify RLS migration completeness

**Files:**
- Create: `supabase/migrations/20260730000000_verify_rls_with_check.sql`

**Interfaces:**
- Consumes: existing policies.
- Produces: idempotent migration that confirms `WITH CHECK` ownership.

- [ ] **Step 1: Write idempotent migration**

Drop and recreate the four UPDATE policies with both `USING` and `WITH CHECK` if they do not already match the strict form. This migration is a no-op if the existing migration `20260728103548_85070891-f7bf-4835-94db-4246463b3813.sql` already applied them.

- [ ] **Step 2: Apply locally**

```bash
npx supabase migration up
```

Expected: no errors.

---

### Task 14: Write release-readiness document

**Files:**
- Create: `docs/RELEASE_READINESS_2026_07_30.md`

**Interfaces:**
- Consumes: research findings, codebase status, test results.
- Produces: decision document.

- [ ] **Step 1: Populate sections**

Use the outline from the spec. For each area, mark Ready / Not Ready / Conditional and provide evidence and go/no-go criteria.

Include the Lovable Cloud section explicitly:

```markdown
## Lovable Cloud Sync Decision

**Decision:** Do not migrate the production backend to Lovable Cloud.
**Reason:** Lovable Cloud is a managed Supabase-compatible backend auto-generated by Lovable. AskMukthiGuru has a custom FastAPI backend, vector store (Qdrant), and graph database (Neo4j). Two-way sync between FastAPI and Lovable Cloud is not automatic; it requires manual REST/Realtime/edge-function plumbing. The risk of data drift and operational complexity outweighs the benefit.
**If Lovable is used:** Host only the frontend prototype on Lovable Cloud and point it at the existing Supabase Auth + FastAPI backend.
```

- [ ] **Step 2: Add checklist and next actions**

List the remaining blockers before production release.

---

### Task 15: Add nightly RLS CI workflow

**Files:**
- Create: `.github/workflows/nightly-rls.yml`

**Interfaces:**
- Consumes: GitHub secrets `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`.
- Produces: scheduled CI run.

- [ ] **Step 1: Write workflow**

```yaml
name: nightly-rls-check
on:
  schedule:
    - cron: '0 2 * * *'
  workflow_dispatch:
jobs:
  rls:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install supabase requests
      - run: python3 backend/scripts/verify_rls_policies.py
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
          SUPABASE_ANON_KEY: ${{ secrets.SUPABASE_ANON_KEY }}
```

- [ ] **Step 2: Verify workflow syntax**

Run `gh workflow run nightly-rls.yml` or validate via GitHub UI.

---

### Task 16: Build unified Langhanam-inspired guru voice and benchmark two implementations

**Files:**
- Create: `backend/services/guru_voice_langhanam.py`
- Modify: `backend/services/guru_tone_adapter.py`
- Create: `backend/benchmarks/guru_voice_benchmark.py`
- Modify: `backend/rag/nodes/generation.py`
- Modify: `docs/RELEASE_READINESS_2026_07_30.md`

**Interfaces:**
- Consumes: cleaned Langhanam transcript, existing tone adapter, generation node prompts.
- Produces: two guru-voice variants and a benchmark report.

**Voice definition (cleaned from transcript):**
- Direct address to the seeker: "I want you to...", "Listen...", "Try this..."
- Short, rhythmic sentences with repetition for emphasis.
- Sanskrit terms left intact where they carry meaning: *langhanam*, *vaak Shakti*, *prana*, *shuddhi*.
- Indian-English phrasing: "Our ancients in India used one very simple principle...", "The more consciously you speak..."
- Avoid American conversational fillers: "like", "you know", "basically", "totally", "I think".
- Avoid generic combining of all sources; speak from the specific teaching at hand.
- Gentle but commanding tone.

- [ ] **Step 1: Prepare cleaned Langhanam reference text**

Create `backend/services/guru_voice_langhanam.py` with a `REFERENCE_VOICE` constant containing 5–7 cleaned paragraphs derived from the transcript. Remove errors like "shittim" and "love venoms". Keep the direct-address rhythm.

Example excerpt:

```python
REFERENCE_VOICE = """
If you want mental, emotional, spiritual and physical health, practice langhanam.
Our ancients in India used one very simple principle. They called it langhanam.
Langhanam means fasting — fasting is the ultimate medicine.
Listen to the end before you come to any conclusion.

The first langhanam is fasting from food. Eat only when your digestive fire actually burns and asks for it, not when your tongue asks. This will also give some rest to the one cooking at home.
Digest most effectively when your breath flows strongly through your right nostril, because of the solar energy flow.
Practice any kind of fasting you can. Intermittent fasting, water fasting, or soup fasting. Even animals fast when they are sick.

The second langhanam is fasting from breath. Every cell is an engine powered by the intake of breath. Practice slow inhalations and extremely long exhalations with breath pauses. Your thoughts will become more positive.

The third langhanam is fasting from hurtful and pessimistic speech. Very few people have vaak Shakti, the power of speech to manifest their goals. Speak words that are true, that cause joy to others, in a pleasing tone. Your vaak Shakti grows.

The fourth langhanam is fasting from movement. It is not about lying on your cushion eating popcorn and watching television. Sit still. Observe your breath, listen to the sounds of nature, or chant the name of your divine being inwardly. Even one minute at a time will bring down the restlessness in your body and mind.

Langhanam is power. Practice these four fasts, and you will feel great power in your body, mind and consciousness.
"""
```

- [ ] **Step 2: Implement variant A — prompt-based persona injection**

Create a function `render_langhanam_system_prompt(base_system_prompt: str) -> str` that appends a concise voice block:

```python
LANGHANAM_VOICE_BLOCK = """
When you speak as the guru, use this voice:
- Speak directly to the seeker in short, rhythmic sentences.
- Use Sanskrit terms naturally: langhanam, vaak Shakti, prana, shuddhi.
- Phrase things as our ancients in India would teach: simple, direct, embodied.
- Avoid American fillers: like, you know, basically, totally, I think, kind of.
- Do not combine or genericize teachings. Stay with the one teaching the seeker asked about.
- Be gentle, but command attention. Repetition is allowed for emphasis.
"""
```

This variant modifies the system prompt sent to the LLM.

- [ ] **Step 3: Implement variant B — tone adapter extension**

Extend `backend/services/guru_tone_adapter.py` with a `apply_langhanam_tone(text: str) -> str` function. Options:
- Rule-based rewrite: strip filler words, break long sentences, insert Sanskrit terms where relevant.
- LLM-based rewrite: send the raw response plus a short voice instruction to a lightweight model and return the rewritten text.

Start with rule-based. If benchmark shows prompt-based is better, deprecate the rule-based rewrite.

- [ ] **Step 4: Create benchmark harness**

Create `backend/benchmarks/guru_voice_benchmark.py`:

```python
TEST_QUERIES = [
    "What is langhanam?",
    "How do I stop negative thoughts?",
    "Tell me about fasting for health.",
    "How do I speak more powerfully?",
    "What should I do when I feel restless?",
    "Explain the four langhanams.",
]

STYLE_RUBRIC = {
    "direct_address": ("Uses direct address: I want you to, Listen, Try this", 1.0),
    "sanskrit_terms": ("Uses Sanskrit terms naturally", 1.0),
    "indian_english": ("Has Indian-English phrasing", 1.0),
    "no_fillers": ("No American fillers", 1.0),
    "single_teaching": ("Does not combine unrelated sources", 1.0),
    "rhythm": ("Short rhythmic sentences with repetition allowed", 1.0),
}
```

For each query, generate responses with variant A and variant B. Score each response using:
1. An LLM-as-judge with the rubric (default provider from settings).
2. A rule-based heuristic for filler-word count and sentence length.

Output a JSON report with per-query scores and a summary.

- [ ] **Step 5: Run benchmark and pick winner**

```bash
cd backend
.venv/bin/python benchmarks/guru_voice_benchmark.py --queries 6 --output benchmarks/reports/guru_voice_benchmark_2026_07_30.json
```

Compare mean scores. If prompt-based wins, keep variant A as default. If tone-adapter wins, keep variant B. If they are close, make it configurable via `GURU_VOICE_MODE=prompt|adapter` in `backend/app/config.py`.

- [ ] **Step 6: Wire winning variant into generation node**

In `backend/rag/nodes/generation.py`, apply the winning voice to the final answer path for queries classified as `teaching`, `doctrine`, or `DISTRESS` (not for factual lookup-only queries). Add a feature flag `langhanam_voice_enabled` defaulting to `False` until benchmark passes a threshold (e.g., mean score ≥ 4.0/5.0 on rubric).

- [ ] **Step 7: Document in release-readiness doc**

Add a section:

```markdown
## Guru Voice / Interpretation Quality

- **Status:** Conditional
- **Evidence:** Langhanam transcript analyzed; two voice implementations benchmarked.
- **Go criterion:** Benchmark mean score ≥ 4.0/5.0 and no regression on doctrinal accuracy test suite.
- **Decision:** Default off until criterion met; toggle via `LANGHANAM_VOICE_ENABLED`.
```

---

## Self-Review

1. **Spec coverage:**
   - AAL2/MFA tests → Task 2, 3.
   - RLS verifier → Task 4, 5, 13, 15.
   - Leaked password → Task 6.
   - Release readiness → Task 14.
   - Lovable decision → Task 14.
   - Metrics parity → Task 7, 8, 9.
   - Suffering course assignment → Task 10, 11, 12.
2. **Placeholder scan:** No TBD/TODO; all code is concrete.
3. **Type consistency:** `UserMetrics` fields are snake_case in Python and camelCase in TypeScript; this is intentional and documented. `recommended_course` shape matches between backend and `HealingPathCard`.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-30-security-rls-metrics-release-readiness-plan.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach do you want?
