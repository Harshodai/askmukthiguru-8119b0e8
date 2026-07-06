import { chromium } from 'playwright';
import { mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const outDir = join(dirname(__filename), '..', 'playwright-report', 'ui-explore');
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
  const data = await res.json();
  const { access_token, expires_at, expires_in, refresh_token, token_type, user } = data;
  if (!access_token || !refresh_token) {
    throw new Error(`Supabase signup did not return active session tokens. Response: ${JSON.stringify(data)}`);
  }
  return { email, access_token, expires_at, expires_in, refresh_token, token_type, user };
}

async function screenshot(page, name) {
  await page.screenshot({ path: join(outDir, `${name}.png`), fullPage: false });
}

async function dismissOverlays(page) {
  // Cookie consent
  const cookie = page.locator('div[role="dialog"][aria-label="Cookie consent"] button', { hasText: 'Accept' }).first();
  if (await cookie.isVisible().catch(() => false)) await cookie.click();
  // Serene Mind modal
  const sereneClose = page.locator('div[role="dialog"][aria-label="Serene Mind meditation"] button[aria-label="Close"]').first();
  if (await sereneClose.isVisible().catch(() => false)) await sereneClose.click();
  // Guided meditation flow
  const guidedClose = page.locator('div[role="dialog"][aria-label="Guided meditation"] button[aria-label="Close"]').first();
  if (await guidedClose.isVisible().catch(() => false)) await guidedClose.click();
  await page.waitForTimeout(200);
}

const session = await createSession();
console.log('Created session for', session.email);

const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const logs = [];

  page.on('console', (msg) => {
    const line = `[${msg.type()}] ${msg.text()}`;
    logs.push(line);
    console.log(line);
  });
  page.on('pageerror', (err) => {
    const line = `[PAGEERROR] ${err.message}`;
    logs.push(line);
    console.log(line);
  });

  await page.goto(`${BASE}/chat`, { waitUntil: 'commit' });
  await page.evaluate((sess) => {
    const payload = JSON.stringify({
      access_token: sess.access_token,
      expires_at: sess.expires_at,
      expires_in: sess.expires_in,
      refresh_token: sess.refresh_token,
      token_type: sess.token_type,
      user: sess.user,
    });
    localStorage.setItem('sb-127-auth-token', payload);
    sessionStorage.setItem('askmukthiguru_pre_practice_asked', '1');
  }, session);

  await page.reload({ waitUntil: 'networkidle' });
  await dismissOverlays(page);
  await screenshot(page, '01-chat-ready');

  const questions = [
    'What is the Beautiful State, and how do I begin?',
    "I'm feeling overwhelmed — help me find calm",
    'Share a teaching from Sri Preethaji on suffering',
  ];

  const timings = [];
  const startAll = Date.now();

  for (let i = 0; i < questions.length; i++) {
    const q = questions[i];
    const qStart = Date.now();
    console.log(`Asking (${i + 1}/${questions.length}): ${q}`);
    await dismissOverlays(page);

    const textarea = page.locator('textarea[aria-label="Your message"]').first();
    await textarea.fill(q);
    await page.click('button[aria-label="Send message"]');

    const thinking = page.locator('[data-testid="thinking-pills"]').first();
    try {
      await thinking.waitFor({ state: 'visible', timeout: 5000 });
      await thinking.waitFor({ state: 'hidden', timeout: 120000 });
    } catch (e) {
      console.log('Thinking indicator did not behave as expected:', e.message);
    }

    const lastGuru = page.locator('[data-message-id]:has(.prose)').last();
    await lastGuru.waitFor({ state: 'visible', timeout: 120000 }).catch(() => {});
    await page.waitForTimeout(1500);

    const elapsed = Date.now() - qStart;
    timings.push({ question: q, elapsed_ms: elapsed });
    console.log(`  answered in ${elapsed}ms`);
    await screenshot(page, `02-answer-${i + 1}`);
  }

  const total = Date.now() - startAll;
  console.log(`Total UI session time: ${total}ms`);
  await screenshot(page, '03-final');

  const report = { email: session.email, url: page.url(), total_ms: total, timings, log: logs.slice(-200) };
  const fs = await import('fs/promises');
  const reportPath = join(outDir, 'report.json');
  await fs.writeFile(reportPath, JSON.stringify(report, null, 2));
  console.log('Report saved to', reportPath);
  console.log(JSON.stringify(report, null, 2));
} finally {
  await browser.close();
}
