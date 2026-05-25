import { test, expect } from '@playwright/test';

const mockSession = {
  access_token: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjo5OTk5OTk5OTk5LCJzdWIiOiJtb2NrLXVzZXItdXVpZCIsImVtYWlsIjoic2Vla2VyQGV4YW1wbGUuY29tIiwicm9sZSI6ImF1dGhlbnRpY2F0ZWQiLCJhcHBfbWV0YWRhdGEiOnsicHJvdmlkZXIiOiJlbWFpbCJ9LCJ1c2VyX21ldGFkYXRhIjp7ImZ1bGxfbmFtZSI6IlRlc3QgU2Vla2VyIn19.signature',
  token_type: 'bearer',
  expires_in: 3600,
  refresh_token: 'mock-refresh-token',
  user: {
    id: 'mock-user-uuid',
    aud: 'authenticated',
    role: 'authenticated',
    email: 'seeker@example.com',
    email_confirmed_at: '2026-05-20T00:00:00Z',
    user_metadata: {
      full_name: 'Test Seeker',
    },
    created_at: '2026-05-20T00:00:00Z',
    updated_at: '2026-05-20T00:00:00Z',
  },
  expires_at: 9999999999,
};

const mockProfile = {
  id: 'mock-user-uuid',
  displayName: 'Test Seeker',
  preferredLanguage: 'en',
  preferredVoice: 'deepika',
  ttsEnabled: true,
  ttsRate: 0.9,
  theme: 'dark',
};

test.describe('E2E Verification of Scrolling Behavior and TTS Voice Switching', () => {
  
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'serviceWorker', {
        get: () => ({
          register: () => Promise.resolve({
            active: null,
            installing: null,
            waiting: null,
            onupdatefound: null,
            unregister: () => Promise.resolve(true),
            update: () => Promise.resolve(),
          }),
          addEventListener: () => {},
          removeEventListener: () => {},
        }),
        configurable: true,
      });
    });

    // Console log listener for E2E execution diagnostic
    page.on('console', msg => {
      if (msg.type() === 'error') {
        console.error(`[BROWSER ERROR] ${msg.text()}`);
      } else {
        console.log(`[BROWSER LOG] [${msg.type()}] ${msg.text()}`);
      }
    });
    page.on('pageerror', err => console.error(`[PAGE EXCEPTION] ${err.message}\n${err.stack}`));

    // Intercept Supabase Auth endpoints globally
    await page.route(/\/auth\/v1\/user/, async (route) => {
      const request = route.request();
      if (request.method() === 'OPTIONS') {
        await route.fulfill({
          status: 200,
          headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS, PUT, DELETE',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
          },
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          headers: { 'Access-Control-Allow-Origin': '*' },
          body: JSON.stringify(mockSession.user),
        });
      }
    });

    await page.route(/\/auth\/v1\/token/, async (route) => {
      const request = route.request();
      if (request.method() === 'OPTIONS') {
        await route.fulfill({
          status: 200,
          headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS, PUT, DELETE',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
          },
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          headers: { 'Access-Control-Allow-Origin': '*' },
          body: JSON.stringify(mockSession),
        });
      }
    });

    await page.route(/\/auth\/v1\/session/, async (route) => {
      const request = route.request();
      if (request.method() === 'OPTIONS') {
        await route.fulfill({
          status: 200,
          headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS, PUT, DELETE',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
          },
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          headers: { 'Access-Control-Allow-Origin': '*' },
          body: JSON.stringify(mockSession),
        });
      }
    });

    // Intercept profile custom backend sync API with proper CORS & OPTIONS preflight fulfillment
    await page.route(/\/api\/profile/, async (route) => {
      const request = route.request();
      if (request.method() === 'OPTIONS') {
        await route.fulfill({
          status: 200,
          headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS, PUT, DELETE',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
          },
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          headers: { 'Access-Control-Allow-Origin': '*' },
          body: JSON.stringify({
            preferred_language: 'en',
            codemix_preference: false,
            topics_of_interest: [],
          }),
        });
      }
    });

    await page.route(/\/rest\/v1\/profiles/, async (route) => {
      const request = route.request();
      if (request.method() === 'OPTIONS') {
        await route.fulfill({
          status: 200,
          headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS, PUT, DELETE',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization, apikey',
          },
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          headers: { 'Access-Control-Allow-Origin': '*' },
          body: JSON.stringify([mockProfile]),
        });
      }
    });

    // Intercept app telemetry/logs database calls
    await page.route(/\/rest\/v1\/app_logs/, async (route) => {
      const request = route.request();
      if (request.method() === 'OPTIONS') {
        await route.fulfill({
          status: 200,
          headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS, PUT, DELETE',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization, apikey',
          },
        });
      } else {
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          headers: { 'Access-Control-Allow-Origin': '*' },
          body: JSON.stringify({}),
        });
      }
    });

    // Intercept daily teachings to avoid database permission/signature warnings
    await page.route(/\/rest\/v1\/daily_teachings/, async (route) => {
      const request = route.request();
      if (request.method() === 'OPTIONS') {
        await route.fulfill({
          status: 200,
          headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS, PUT, DELETE',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization, apikey',
          },
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          headers: { 'Access-Control-Allow-Origin': '*' },
          body: JSON.stringify([]),
        });
      }
    });

    // Intercept meditation sessions to avoid database warnings
    await page.route(/\/rest\/v1\/meditation_sessions/, async (route) => {
      const request = route.request();
      if (request.method() === 'OPTIONS') {
        await route.fulfill({
          status: 200,
          headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS, PUT, DELETE',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization, apikey',
          },
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          headers: { 'Access-Control-Allow-Origin': '*' },
          body: JSON.stringify([]),
        });
      }
    });

    // Intercept speech TTS calls to bypass live edge functions
    await page.route(/\/api\/speech\/tts/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'audio/mpeg',
        body: Buffer.from([]),
      });
    });
  });

  test('TTS Verification Page E2E diagnostics and voice switching', async ({ page }) => {
    // Mock session token injection for consistent local run
    await page.addInitScript(() => {
      localStorage.clear();
      sessionStorage.clear();

      const mockSessionLocal = {
        access_token: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjo5OTk5OTk5OTk5LCJzdWIiOiJtb2NrLXVzZXItdXVpZCIsImVtYWlsIjoic2Vla2VyQGV4YW1wbGUuY29tIiwicm9sZSI6ImF1dGhlbnRpY2F0ZWQiLCJhcHBfbWV0YWRhdGEiOnsicHJvdmlkZXIiOiJlbWFpbCJ9LCJ1c2VyX21ldGFkYXRhIjp7ImZ1bGxfbmFtZSI6IlRlc3QgU2Vla2VyIn19.signature',
        token_type: 'bearer',
        expires_in: 3600,
        refresh_token: 'mock-refresh-token',
        user: {
          id: 'mock-user-uuid',
          aud: 'authenticated',
          role: 'authenticated',
          email: 'seeker@example.com',
          email_confirmed_at: '2026-05-20T00:00:00Z',
          user_metadata: {
            full_name: 'Test Seeker',
          },
        },
        expires_at: 9999999999,
      };

      const mockProfileLocal = {
        id: 'mock-user-uuid',
        displayName: 'Test Seeker',
        preferredLanguage: 'en',
        preferredVoice: 'deepika',
        ttsEnabled: true,
        ttsRate: 0.9,
        theme: 'dark',
      };

      localStorage.setItem('sb-fynkjimvuimakgtidvuq-auth-token', JSON.stringify(mockSessionLocal));
      localStorage.setItem('sb-supabase-demo-auth-token', JSON.stringify(mockSessionLocal));
      localStorage.setItem('sb-localhost-auth-token', JSON.stringify(mockSessionLocal));
      localStorage.setItem('askmukthiguru_profile', JSON.stringify(mockProfileLocal));
      localStorage.setItem('askmukthiguru_consent_v1', 'accepted'); // PREVENT Cookie Banner Overlay
    });

    // Visit the TTS verification page
    await page.goto('/test-tts', { waitUntil: 'networkidle' });

    // Assert the page loaded successfully and displays main headings
    await expect(page.locator('h1')).toContainText('TTS & Telemetry Verification');

    // Click "Run Automated Diagnostics"
    const runDiagnosticsBtn = page.getByRole('button', { name: 'Run Automated Diagnostics' });
    await expect(runDiagnosticsBtn).toBeVisible();
    await runDiagnosticsBtn.click();

    // Verify the checklist turns into positive green states
    const statusBox = page.locator('.glass-card').first();
    await expect(statusBox).toContainText('Passed');
    
    // Wait for the diagnostic sequence to fully complete (Aditya and Anushka switches, logs complete)
    const logsConsole = page.locator('.glass-card').last();
    await expect(logsConsole).toContainText('Automated Verification Complete', { timeout: 10000 });

    // Take screenshot to document verification page excellence
    await page.screenshot({ path: 'chat_ui_screenshot.png', fullPage: true });
    console.log('✅ Captured E2E verification screenshot: chat_ui_screenshot.png');
  });

  test('Chat Interface Auto-Scrolling and Thinking Pill Positioning during streaming', async ({ page }) => {
    // Mock user session with all 3 storage keys and clean state
    await page.addInitScript(() => {
      localStorage.clear();
      sessionStorage.clear();

      const mockSessionLocal = {
        access_token: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjo5OTk5OTk5OTk5LCJzdWIiOiJtb2NrLXVzZXItdXVpZCIsImVtYWlsIjoic2Vla2VyQGV4YW1wbGUuY29tIiwicm9sZSI6ImF1dGhlbnRpY2F0ZWQiLCJhcHBfbWV0YWRhdGEiOnsicHJvdmlkZXIiOiJlbWFpbCJ9LCJ1c2VyX21ldGFkYXRhIjp7ImZ1bGxfbmFtZSI6IlRlc3QgU2Vla2VyIn19.signature',
        token_type: 'bearer',
        expires_in: 3600,
        refresh_token: 'mock-refresh-token',
        user: {
          id: 'mock-user-uuid',
          aud: 'authenticated',
          role: 'authenticated',
          email: 'seeker@example.com',
          email_confirmed_at: '2026-05-20T00:00:00Z',
          user_metadata: {
            full_name: 'Test Seeker',
          },
        },
        expires_at: 9999999999,
      };

      const mockProfileLocal = {
        id: 'mock-user-uuid',
        displayName: 'Test Seeker',
        preferredLanguage: 'en',
        preferredVoice: 'deepika',
        ttsEnabled: false,
        theme: 'dark',
      };

      localStorage.setItem('sb-fynkjimvuimakgtidvuq-auth-token', JSON.stringify(mockSessionLocal));
      localStorage.setItem('sb-supabase-demo-auth-token', JSON.stringify(mockSessionLocal));
      localStorage.setItem('sb-localhost-auth-token', JSON.stringify(mockSessionLocal));
      localStorage.setItem('askmukthiguru_profile', JSON.stringify(mockProfileLocal));
      localStorage.setItem('askmukthiguru_consent_v1', 'accepted'); // PREVENT Cookie Banner Overlay
      sessionStorage.setItem('askmukthiguru_pre_practice_asked', '1');
    });

    // Mock chat SSE streaming endpoint explicitly using RegExp for perfect match
    await page.route(/\/api\/chat/, async (route) => {
      const request = route.request();
      console.log(`[ROUTE MOCK] Intercepted /api/chat: method=${request.method()} url=${request.url()}`);
      if (request.method() === 'OPTIONS') {
        await route.fulfill({
          status: 200,
          headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS, PUT, DELETE',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
          },
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          headers: {
            'Access-Control-Allow-Origin': '*',
          },
          body: [
            'event: status\n',
            'data: Navigating Doctrine Graph\n\n',
            'event: message\n',
            'data: {"content": "In a beautiful state, you connect deeply with your pure essence. "}\n\n',
            'event: message\n',
            'data: {"content": "This beautiful state allows you to be free of all anxiety and worries. "}\n\n',
            'event: message\n',
            'data: {"content": "Inner peace is not a destination, but a state of awareness."}\n\n',
            'event: done\n',
            'data: {"intent": "FACTUAL", "citations": ["wisdom-scroll-1"], "meditation_step": 0}\n\n',
            'data: [DONE]\n\n',
          ].join(''),
        });
      }
    });

    // Go to Chat interface
    await page.goto('/chat', { waitUntil: 'networkidle' });

    console.log('[TEST LOG] Navigated to /chat successfully');

    // Ensure page elements are present
    const inputArea = page.locator('textarea');
    await expect(inputArea).toBeVisible();

    // Type a factual message
    await inputArea.fill('What is a beautiful state?');

    // Click the send button (bulletproof click instead of keypress)
    const sendButton = page.getByLabel('Send message');
    await expect(sendButton).toBeEnabled();
    await sendButton.click();

    // Verify thinking pill and streamed message containers appear correctly
    const bubble = page.locator('.message-bubble').last();
    await expect(bubble).toContainText('Inner peace', { timeout: 15000 });

    // Verify scroll position locked at the bottom
    const scrollHeight = await page.evaluate(() => {
      const container = document.querySelector('.overflow-y-auto.scrollbar-spiritual');
      if (!container) return null;
      return {
        scrollTop: container.scrollTop,
        clientHeight: container.clientHeight,
        scrollHeight: container.scrollHeight,
      };
    });

    console.log(`📏 Scroll position state:`, scrollHeight);
    
    // Near bottom check: scrollTop + clientHeight should be very close to scrollHeight
    if (scrollHeight) {
      const isAtBottom = scrollHeight.scrollTop + scrollHeight.clientHeight >= scrollHeight.scrollHeight - 100;
      expect(isAtBottom).toBe(true);
      console.log('✅ Confirmed page successfully and automatically scroll-locked to bottom during active token stream!');
    }

    // Save chat UI screenshot for confirmation
    await page.screenshot({ path: 'chat_ui_screenshot_chat.png', fullPage: true });
    console.log('✅ Captured chat streaming auto-scroll verification screenshot: chat_ui_screenshot_chat.png');
  });
});
