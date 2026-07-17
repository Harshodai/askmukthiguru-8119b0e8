import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load session state if it exists (allows testing production/authenticated pages easily)
const sessionFile = path.resolve(__dirname, '../../playwright-session.json');
const hasSession = fs.existsSync(sessionFile);
if (hasSession) {
  test.use({ storageState: sessionFile });
  console.log('[UI REGRESSION] Found playwright-session.json, loading authenticated browser state...');
} else {
  console.log('[UI REGRESSION] No playwright-session.json found, running as anonymous user...');
}

class VisualRegressionTracker {
  private page: any;
  private stepNumber = 0;
  private outputDir = path.resolve(__dirname, '../../playwright-screenshots');

  constructor(page: any) {
    this.page = page;
    if (!fs.existsSync(this.outputDir)) {
      fs.mkdirSync(this.outputDir, { recursive: true });
    } else {
      // Clean up previous screenshots to avoid mixing runs
      const files = fs.readdirSync(this.outputDir);
      for (const file of files) {
        if (file.endsWith('.png')) {
          fs.unlinkSync(path.join(this.outputDir, file));
        }
      }
    }
  }

  private getStepName(description: string) {
    this.stepNumber++;
    const formattedNum = String(this.stepNumber).padStart(3, '0');
    const sanitized = description.toLowerCase().replace(/[^a-z0-9_]+/g, '_').replace(/(^_+|_+$)/g, '');
    return `${formattedNum}_${sanitized}.png`;
  }

  async capture(description: string) {
    const filename = this.getStepName(description);
    const filepath = path.join(this.outputDir, filename);
    await this.page.screenshot({ path: filepath, fullPage: true });
    console.log(`[UI REGRESSION] Captured: ${filename} - ${description}`);
  }

  async clickAndScreenshot(selector: string | any, description: string) {
    const locator = typeof selector === 'string' ? this.page.locator(selector) : selector;
    try {
      await locator.waitFor({ state: 'visible', timeout: 3000 });
      await locator.click({ force: true });
      await this.page.waitForTimeout(1500); // Wait for transitions/animations to settle
      await this.capture(description);
    } catch (err) {
      console.log(`[UI REGRESSION] Skipping click action: ${description} (Element not clickable/visible)`);
    }
  }

  async typeAndScreenshot(selector: string | any, text: string, description: string) {
    const locator = typeof selector === 'string' ? this.page.locator(selector) : selector;
    try {
      await locator.waitFor({ state: 'visible', timeout: 3000 });
      await locator.fill(text);
      await this.page.waitForTimeout(500);
      await this.capture(description);
    } catch (err) {
      console.log(`[UI REGRESSION] Skipping type action: ${description} (Element not fillable/visible)`);
    }
  }

  async navigateAndScreenshot(url: string, description: string) {
    try {
      const resp = await this.page.goto(url);
      if (!resp || !resp.ok()) {
        throw new Error(`Navigation to ${url} returned ${resp ? resp.status() : 'no response'}`);
      }
      await this.page.locator('body').waitFor({ state: 'visible', timeout: 5000 });
      await this.page.waitForTimeout(2000); // Wait for page hydration
      await this.capture(description);
    } catch (err) {
      console.log(`[UI REGRESSION] Navigation failed to: ${url} (Error: ${err.message})`);
      throw err;
    }
  }
}

test.describe('E2E Visual Regression Suite - All Pages & safe Actions', () => {
  test('Capture step-by-step screenshots of all pages & buttons', async ({ page }) => {
    const tracker = new VisualRegressionTracker(page);
    test.setTimeout(240000);
    await page.setViewportSize({ width: 1280, height: 800 });

    // Step 1: Navigate to Home/Landing
    await tracker.navigateAndScreenshot('/', 'landing_page_load');

    // Click CTAs on landing page
    const ctaButton = page.locator('a[href="/chat"], button:has-text("Start"), button:has-text("Chat")').first();
    if (await ctaButton.isVisible()) {
      await tracker.clickAndScreenshot(ctaButton, 'landing_cta_clicked');
    }

    // Direct page list (public pages)
    const publicPages = [
      { path: '/chat', desc: 'chat_page' },
      { path: '/practices', desc: 'practices_list' },
      { path: '/practices/soul-sync', desc: 'practices_soul_sync' },
      { path: '/practices/serene-mind', desc: 'practices_serene_mind' },
      { path: '/practices/beautiful-state', desc: 'practices_beautiful_state' },
      { path: '/practices/daily-reflection', desc: 'practices_daily_reflection' },
      { path: '/guides/spirit-guides', desc: 'guides_spirit_guides' },
      { path: '/guides/ai-spiritual-companion', desc: 'guides_ai_companion' },
      { path: '/guides/beautiful-state-meditation', desc: 'guides_beautiful_state' },
      { path: '/guides/serene-mind-practice', desc: 'guides_serene_mind' },
      { path: '/guides/self-centric-thinking', desc: 'guides_self_centric_thinking' },
      { path: '/guides/spiritual-guide-for-anxiety', desc: 'guides_anxiety' },
      { path: '/guides/suffering-to-beautiful-state', desc: 'guides_suffering_to_beautiful' },
      { path: '/auth', desc: 'auth_page' },
      { path: '/privacy', desc: 'privacy_policy' },
      { path: '/terms', desc: 'terms_of_service' }
    ];

    // Visit every public page & check for overlays
    for (const item of publicPages) {
      await tracker.navigateAndScreenshot(item.path, `${item.desc}_load`);

      // Dismiss cookie consent or daily teaching popups on every page load
      const cookieAccept = page.locator('button:has-text("स्वीकृत"), button:has-text("Accept"), button:has-text("Agree")').first();
      if (await cookieAccept.isVisible()) {
        await tracker.clickAndScreenshot(cookieAccept, `${item.desc}_dismiss_cookie_consent`);
      }

      const wisdomButton = page.locator('[data-testid="receive-wisdom-button"], button:has-text("Receive Wisdom"), button:has-text("Wisdom")').first();
      if (await wisdomButton.isVisible()) {
        await tracker.clickAndScreenshot(wisdomButton, `${item.desc}_dismiss_daily_teaching`);
      }

      const closeTour = page.locator('button:has-text("टूर छोड़ें"), button:has-text("Close tour"), button:has-text("Skip tour")').first();
      if (await closeTour.isVisible()) {
        await tracker.clickAndScreenshot(closeTour, `${item.desc}_skip_tour`);
      }

      // Safe interactive element clicks on specific pages
      if (item.path === '/chat') {
        const inputArea = page.locator('textarea[placeholder*="Ask"], textarea[placeholder*="अपने"], textarea').first();
        if (await inputArea.isVisible()) {
          await tracker.typeAndScreenshot(inputArea, 'How do I live in a beautiful state?', 'chat_type_query');
          
          const sendButton = page.locator('button[type="submit"], button:has(svg.lucide-send)').first();
          if (await sendButton.isVisible()) {
            await tracker.clickAndScreenshot(sendButton, 'chat_submit_query');
            // Wait for response streaming to finish
            await page.waitForTimeout(5000);
            await tracker.capture('chat_response_completed');
          }
        }
      }

      if (item.path.startsWith('/practices/')) {
        // Look for practice navigation tabs / detail elements
        const startBtn = page.locator('button:has-text("Start"), button:has-text("तैयार"), button:has-text("प्रारंभ")').first();
        if (await startBtn.isVisible()) {
          await tracker.clickAndScreenshot(startBtn, `${item.desc}_click_start`);
        }
      }
    }

    // Step 3: Admin Console Routes
    const adminPages = [
      { path: '/admin', desc: 'admin_dashboard' },
      { path: '/admin/self-check', desc: 'admin_self_check' },
      { path: '/admin/monitoring', desc: 'admin_monitoring' },
      { path: '/admin/telemetry', desc: 'admin_telemetry' },
      { path: '/admin/auth-latency', desc: 'admin_auth_latency' },
      { path: '/admin/topics', desc: 'admin_topics' },
      { path: '/admin/jobs', desc: 'admin_jobs' },
      { path: '/admin/logs', desc: 'admin_logs' },
      { path: '/admin/triggers', desc: 'admin_triggers' },
      { path: '/admin/prompts', desc: 'admin_prompts' },
      { path: '/admin/feedback', desc: 'admin_feedback' },
      { path: '/admin/alerts', desc: 'admin_alerts' },
      { path: '/admin/retrieval', desc: 'admin_retrieval' },
      { path: '/admin/knowledge-graph', desc: 'admin_knowledge_graph' },
      { path: '/admin/ingestion', desc: 'admin_ingestion' },
      { path: '/admin/quality', desc: 'admin_quality' },
      { path: '/admin/evals', desc: 'admin_evals' },
      { path: '/admin/admins', desc: 'admin_admins_list' },
      { path: '/admin/auth-diagnostics', desc: 'admin_auth_diagnostics' },
      { path: '/admin/daily-teaching', desc: 'admin_daily_teaching' },
      { path: '/admin/tts-verification', desc: 'admin_tts_verification' }
    ];

    if (hasSession) {
      console.log('[UI REGRESSION] Running Admin Panel E2E regression check...');
      for (const item of adminPages) {
        await tracker.navigateAndScreenshot(item.path, `${item.desc}_load`);

        // Click safe tabs, filters, and refresh buttons if they exist
        const refreshBtn = page.locator('button:has(svg.lucide-refresh-cw), button:has-text("Refresh"), button:has-text("Reload")').first();
        if (await refreshBtn.isVisible()) {
          await tracker.clickAndScreenshot(refreshBtn, `${item.desc}_refresh_clicked`);
        }

        const tabBtn = page.locator('button[role="tab"], [role="tablist"] button').first();
        if (await tabBtn.isVisible()) {
          await tracker.clickAndScreenshot(tabBtn, `${item.desc}_tab_switched`);
        }
      }
    } else {
      console.log('[UI REGRESSION] Skipping Admin Console checks because no playwright-session.json is configured.');
    }

    console.log('[UI REGRESSION] End-to-end multi-route regression completed.');
  });
});
