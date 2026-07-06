import { chromium, devices } from 'playwright';
import { mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const outDir = join(dirname(__filename), '..', 'playwright-report', 'ui-sending');
mkdirSync(outDir, { recursive: true });

const BASE = 'http://localhost';
const ANON_KEY = 'sb_publishable_ACJWlzQHlZjBrEguHvfOxg_3BJgxAaH';

async function createSession() {
  const email = `agent-ui-${Date.now()}@example.com`;
  const password = 'AgentPass123!';
  const res = await fetch('http://127.0.0.1:54321/auth/v1/signup', {
    method: 'POST',
    headers: { apikey: ANON_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(`Supabase signup failed: ${res.status} ${await res.text()}`);
  const { access_token, expires_at, expires_in, refresh_token, token_type, user } = await res.json();
  return { access_token, expires_at, expires_in, refresh_token, token_type, user };
}

async function capture(page, name) {
  await page.screenshot({ path: join(outDir, `${name}.png`), fullPage: false });
}

async function dismissOverlays(page) {
  const cookie = page.locator('div[role="dialog"][aria-label="Cookie consent"] button', { hasText: 'Accept' }).first();
  if (await cookie.isVisible().catch(() => false)) await cookie.click();
  const sereneClose = page.locator('div[role="dialog"][aria-label="Serene Mind meditation"] button[aria-label="Close"]').first();
  if (await sereneClose.isVisible().catch(() => false)) await sereneClose.click();
  await page.waitForTimeout(200);
}

const session = await createSession();
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();

await page.goto(`${BASE}/chat`, { waitUntil: 'commit' });
await page.evaluate((sess) => {
  localStorage.setItem('sb-127-auth-token', JSON.stringify({
    access_token: sess.access_token, expires_at: sess.expires_at, expires_in: sess.expires_in,
    refresh_token: sess.refresh_token, token_type: sess.token_type, user: sess.user,
  }));
  sessionStorage.setItem('askmukthiguru_pre_practice_asked', '1');
}, session);
await page.reload({ waitUntil: 'networkidle' });
await dismissOverlays(page);

const q = 'What is the Beautiful State, and how do I begin?';
await page.locator('textarea[aria-label="Your message"]').first().fill(q);
await page.click('button[aria-label="Send message"]');

await capture(page, '00-just-sent');
await page.waitForTimeout(800);
await capture(page, '01-thinking-appears');
await page.waitForTimeout(2000);
await capture(page, '02-thinking-active');

const thinking = page.locator('[data-testid="thinking-pills"]').first();
try {
  await thinking.waitFor({ state: 'hidden', timeout: 120000 });
} catch {}
await page.waitForTimeout(500);
await capture(page, '03-answer-arrived');

await browser.close();
console.log('Screenshots saved to', outDir);
