#!/usr/bin/env node
/**
 * generate_store_screenshots.cjs
 *
 * Captures mobile-viewport screenshots of the AskMukthiGuru web app for
 * Google Play (1080x1920) and Apple App Store (6.7" iPhone, 1290x2796).
 *
 * Uses the already-installed `playwright` package (see package.json).
 *
 * Usage:
 *   node scripts/ops/generate_store_screenshots.cjs --url http://localhost:8080
 *   node scripts/ops/generate_store_screenshots.cjs --url https://askmukthiguru.lovable.app
 *   node scripts/ops/generate_store_screenshots.cjs --url http://localhost:8080 --out artifacts/store-screenshots --wait 2500
 *
 * Requirements:
 *   - `playwright` npm package installed (it is — ^1.60.0).
 *   - Chromium browser registered: run `npx playwright install chromium` once if missing.
 *
 * Output:
 *   artifacts/store-screenshots/android/{screen}.png   (1080x1920)
 *   artifacts/store-screenshots/iphone/{screen}.png     (1290x2796)
 *
 * Notes:
 *   - Routes that require auth (/chat, /profile) will fall back to the
 *     auth gate. To capture the authenticated state, supply --email and
 *     --password and the script will sign in via the Supabase OAuth form
 *     on /auth before capturing protected screens. If credentials are
 *     omitted, those screens will be captured as-is (auth wall), which is
 *     also a valid store screenshot ("secure login").
 */

const { chromium, devices } = require('playwright');
const path = require('path');
const fs = require('fs');
const os = require('os');

const argv = require('process').argv.slice(2);
function arg(name, fallback) {
  const i = argv.indexOf('--' + name);
  if (i === -1 || i + 1 >= argv.length) return fallback;
  return argv[i + 1];
}
function flag(name) {
  return argv.includes('--' + name);
}

const BASE_URL = arg('url', 'http://localhost:8080');
const OUT_DIR = arg('out', path.join(process.cwd(), 'artifacts', 'store-screenshots'));
const WAIT_MS = parseInt(arg('wait', '2500'), 10);
const EMAIL = arg('email', process.env.AMG_SHOT_EMAIL || '');
// Password is read ONLY from environment variables (never from CLI args, to avoid shell history leaks).
const PASSWORD = process.env.AMG_SHOT_PASSWORD || process.env.AMG_SHOT_PASS || '';
const HELP = flag('help') || flag('h');

if (HELP) {
  console.log(`Usage: node scripts/ops/generate_store_screenshots.cjs --url <URL> [--out <DIR>] [--wait <ms>] [--email <EMAIL>]
  --url     Base URL (default: http://localhost:8080)
  --out     Output dir (default: ./artifacts/store-screenshots)
  --wait    Per-page settle time in ms (default: 2500)
  --email   Optional — sign in before capturing protected screens
Environment:
  AMG_SHOT_EMAIL / AMG_SHOT_PASSWORD — credentials (password env-only, never CLI)
`);
  process.exit(0);
}

const SCREENS = [
  { name: '01-landing', path: '/' },
  { name: '02-auth', path: '/auth' },
  { name: '03-chat', path: '/chat', auth: true },
  { name: '04-practices', path: '/practices' },
  { name: '05-practice-detail', path: '/practices/serene-mind', auth: false },
  { name: '06-profile', path: '/profile', auth: true },
  { name: '07-knowledge-graph', path: '/knowledge-graph' },
  { name: '08-privacy', path: '/privacy' },
  { name: '09-terms', path: '/terms' },
];

const PLATFORMS = [
  {
    name: 'android',
    viewport: { width: 1080, height: 1920 },
    deviceScaleFactor: 1,
    isMobile: true,
    hasTouch: true,
    userAgent:
      'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
  },
  {
    name: 'iphone',
    // 6.7" iPhone (14 Pro Max / 15 Pro Max) — App Store required size.
    viewport: { width: 1290, height: 2796 },
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
    userAgent:
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
  },
];

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

async function trySignIn(page, baseUrl) {
  if (!EMAIL || !PASSWORD) return false;
  console.log(`  → signing in (credentials loaded from env) …`);
  try {
    await page.goto(baseUrl + '/auth', { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(800);
    // Supabase magic-link / password form: try common selectors.
    const emailSel = 'input[type="email"], input[name="email"], input[autocomplete="email"]';
    const passSel = 'input[type="password"], input[name="password"]';
    const emailEl = await page.$(emailSel);
    const passEl = await page.$(passSel);
    if (emailEl && passEl) {
      await emailEl.fill(EMAIL);
      await passEl.fill(PASSWORD);
      const btn = await page.$('button[type="submit"], button:has-text("Sign in"), button:has-text("Log in"), button:has-text("Continue")');
      if (btn) await btn.click();
      await page.waitForTimeout(WAIT_MS);
      return true;
    }
    console.warn('  ⚠ no email/password fields found on /auth — capturing unauthenticated.');
    return false;
  } catch (e) {
    console.warn(`  ⚠ sign-in attempt failed: ${e.message}`);
    return false;
  }
}

async function capturePlatform(browser, platform, baseUrl, outDir) {
  const platformDir = path.join(outDir, platform.name);
  ensureDir(platformDir);
  const context = await browser.newContext({
    viewport: platform.viewport,
    deviceScaleFactor: platform.deviceScaleFactor,
    isMobile: platform.isMobile,
    hasTouch: platform.hasTouch,
    userAgent: platform.userAgent,
    locale: 'en-US',
  });
  const page = await context.newPage();
  let signedIn = false;

  for (const screen of SCREENS) {
    const outPath = path.join(platformDir, `${screen.name}.png`);
    const url = baseUrl + screen.path;
    process.stdout.write(`[${platform.name}] ${screen.name} → ${screen.path} … `);
    try {
      if (screen.auth && !signedIn) {
        signedIn = await trySignIn(page, baseUrl);
      }
      await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
      await page.waitForTimeout(WAIT_MS);
      // Dismiss any obvious modal/overlay if present.
      for (const sel of ['button:has-text("Accept")', 'button:has-text("Got it")', 'button[aria-label="Close"]']) {
        const el = await page.$(sel);
        if (el) { try { await el.click(); await page.waitForTimeout(300); } catch {} }
      }
      await page.screenshot({ path: outPath, type: 'png', fullPage: false });
      const stat = fs.statSync(outPath);
      console.log(`saved ${(stat.size / 1024).toFixed(0)} KB`);
    } catch (e) {
      console.log(`FAILED: ${e.message}`);
    }
  }

  await context.close();
}

(async () => {
  console.log(`AskMukthiGuru store screenshot generator`);
  console.log(`  URL:   ${BASE_URL}`);
  console.log(`  OUT:   ${OUT_DIR}`);
  console.log(`  WAIT:  ${WAIT_MS}ms`);
  console.log(`  AUTH:  ${EMAIL ? 'configured (credentials from env)' : '(none — protected screens will show auth wall)'}`);
  console.log('');

  let browser;
  try {
    browser = await chromium.launch({ headless: true });
  } catch (e) {
    if (e.message && /Executable doesn't exist|playwright install/i.test(e.message)) {
      console.error(`Chromium not found. Run:\n  npx playwright install chromium\nthen re-run this script.`);
      process.exit(0); // graceful — non-blocking
    }
    throw e;
  }

  ensureDir(OUT_DIR);
  for (const platform of PLATFORMS) {
    await capturePlatform(browser, platform, BASE_URL, OUT_DIR);
  }
  await browser.close();
  console.log('\nDone. Screenshots in: ' + OUT_DIR);
})().catch((e) => {
  console.error('Fatal:', e);
  process.exit(1);
});