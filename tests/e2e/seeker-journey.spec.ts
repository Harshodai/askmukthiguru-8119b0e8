import { test, expect } from '@playwright/test';

test.describe('Seeker Journey', () => {
  // 1. Existing Landing to Auth Flow Test (kept intact)
  test('landing page to auth flow', async ({ page }) => {
    // Visit Landing Page
    await page.goto('/');

    // Expect the main hero title to be visible
    await expect(page.locator('h1')).toContainText('Beautiful State');

    // Click Begin Journey
    const beginButton = page.getByRole('link', { name: 'Begin Your Journey →' });
    await beginButton.click();

    // Verify Auth Page Navigation
    await expect(page).toHaveURL(/.*\/auth/);
    await expect(page.locator('h1')).toHaveText('Sign in to AskMukthiGuru');

    // Verify Auth Form
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();

    // Switch to Sign Up
    await page.locator('text=Sign up').click();

    // Full name field should appear
    await expect(page.locator('input[id="fullName"]')).toBeVisible();
  });

  // 2. Comprehensive Multilingual STT/TTS E2E Integration Flow
  test('complete chat session with STT, automatic language detection, and TTS fallback warning', async ({ page }) => {
    // Console log listener for debugging
    page.on('console', msg => console.log(`[BROWSER LOG] [${msg.type()}] ${msg.text()}`));
    page.on('pageerror', err => console.log(`[PAGE ERROR] ${err.message}\n${err.stack}`));
    page.on('request', req => console.log(`[REQUEST] ${req.method()} ${req.url()}`));
    page.on('requestfailed', request => console.log(`[REQUEST FAILED] ${request.url()}: ${request.failure()?.errorText}`));

    // A. Intercept network endpoints to provide mock responses for E2E consistency
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
            preferred_language: 'hi',
            codemix_preference: true,
            topics_of_interest: [],
          }),
        });
      }
    });

    await page.route(/\/api\/speech\/stt/, async (route) => {
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
            transcript: 'నమో గురుజీ',
            language_code: 'te',
          }),
        });
      }
    });

    await page.route(/\/api\/chat\/stream/, async (route) => {
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
          contentType: 'text/event-stream',
          headers: { 'Access-Control-Allow-Origin': '*' },
          body: [
            'event: status\n',
            'data: Thinking\n\n',
            'event: message\n',
            'data: {"content": "ప్రణామం, నేను మీకు సహాయం చేయగలను."}\n\n',
            'event: done\n',
            'data: {"intent": "CASUAL", "citations": [], "meditation_step": 0}\n\n',
            'data: [DONE]\n\n',
          ].join(''),
        });
      }
    });

    await page.route(/\/api\/speech\/tts/, async (route) => {
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
          status: 500,
          contentType: 'application/json',
          headers: { 'Access-Control-Allow-Origin': '*' },
          body: JSON.stringify({
            detail: 'TTS engine voice not found',
          }),
        });
      }
    });

    await page.route(/\/auth\/v1\/user/, async (route) => {
      const request = route.request();
      console.log(`[ROUTE MOCK] auth/v1/user: ${request.method()} ${request.url()}`);
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
          body: JSON.stringify({
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
          }),
        });
      }
    });

    await page.route(/\/auth\/v1\/token/, async (route) => {
      const request = route.request();
      console.log(`[ROUTE MOCK] auth/v1/token: ${request.method()} ${request.url()}`);
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
          body: JSON.stringify({
            access_token: 'mock-access-token',
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
          }),
        });
      }
    });

    await page.route(/\/rest\/v1\/daily_teachings/, async (route) => {
      const request = route.request();
      console.log(`[ROUTE MOCK] daily_teachings: ${request.method()} ${request.url()}`);
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
          body: JSON.stringify([{
            id: 'mock-teaching-id',
            image_url: 'https://example.com/mock-wisdom.jpg',
            caption: 'Live in a beautiful state.',
            created_at: '2026-05-20T00:00:00Z',
            expires_at: null
          }]),
        });
      }
    });

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

    await page.route(/\/rest\/v1\/profiles/, async (route) => {
      const request = route.request();
      console.log(`[ROUTE MOCK] profiles: ${request.method()} ${request.url()}`);
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
          body: JSON.stringify([{
            id: 'mock-user-uuid',
            display_name: 'Test Seeker',
            preferred_language: 'hi',
            theme: 'dark',
            tts_enabled: true,
          }]),
        });
      }
    });

    await page.route(/\/rest\/v1\/conversations/, async (route) => {
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
          body: JSON.stringify([{
            id: 'mock-conversation-id',
            title: 'Mock Conversation',
            created_at: '2026-05-20T00:00:00Z',
            user_id: 'mock-user-uuid',
          }]),
        });
      }
    });

    await page.route(/\/rest\/v1\/chat_messages/, async (route) => {
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

    await page.route(/\/rest\/v1\/guru_memories/, async (route) => {
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

    await page.route(/\/functions\/v1\//, async (route) => {
      const request = route.request();
      const url = request.url();
      if (request.method() === 'OPTIONS') {
        await route.fulfill({
          status: 200,
          headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS, PUT, DELETE',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization, apikey',
          },
        });
      } else if (url.includes('sarvam-stt')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          headers: { 'Access-Control-Allow-Origin': '*' },
          body: JSON.stringify({
            transcript: 'నమో గురుజీ',
            language_code: 'te',
          }),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          headers: { 'Access-Control-Allow-Origin': '*' },
          body: JSON.stringify({ success: true }),
        });
      }
    });

    // B. Setup page initialization listener to mock hardware APIs before page scripts load
    await page.addInitScript(() => {
      // Mock Service Worker to prevent intercept failures in Playwright
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

      // 1. Mock Supabase Authenticated Session (Bypassing real login)
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

      // 2. Mock User Profile with preferred language set to Hindi (hi) and TTS active
      const mockProfile = {
        id: 'mock-user-uuid',
        displayName: 'Test Seeker',
        avatarDataUrl: null,
        bio: 'Searching for inner peace',
        preferredLanguage: 'hi',
        guruTone: 'gentle',
        theme: 'dark',
        ttsEnabled: true,
        ttsRate: 0.9,
        meditationReminders: false,
        reminderTimeMinutes: 420,
        prePracticeLog: {
          counts: { soul_sync: 0, serene_mind: 0, both: 0, none: 0 },
          lastAnswer: null,
          lastAnsweredAt: null,
          history: [],
        },
        createdAt: '2026-05-20T00:00:00.000Z',
        updatedAt: '2026-05-20T00:00:00.000Z',
      };

      localStorage.setItem('sb-ozmjeuqbholoxypfxixb-auth-token', JSON.stringify(mockSession));
      localStorage.setItem('sb-supabase-demo-auth-token', JSON.stringify(mockSession));
      localStorage.setItem('sb-localhost-auth-token', JSON.stringify(mockSession));
      localStorage.setItem('sb-127.0.0.1-auth-token', JSON.stringify(mockSession));
      localStorage.setItem('sb-127-auth-token', JSON.stringify(mockSession));
      localStorage.setItem('askmukthiguru_profile', JSON.stringify(mockProfile));
      
      // Bypasses the PrePracticeGate immediately
      sessionStorage.setItem('askmukthiguru_pre_practice_asked', '1');

      // 3. Mock Web Audio & Microphone recording APIs (MediaRecorder)
      interface MockBlobEvent extends Event {
        data?: Blob;
      }

      class MockMediaRecorder extends EventTarget {
        stream: unknown;
        options: { mimeType?: string } | undefined;
        state: string;
        mimeType: string;
        ondataavailable: ((e: MockBlobEvent) => void) | null = null;
        onstop: (() => void) | null = null;
        static isTypeSupported = () => true;

        constructor(stream: unknown, options?: { mimeType?: string }) {
          super();
          this.stream = stream;
          this.options = options;
          this.state = 'inactive';
          this.mimeType = options?.mimeType || 'audio/webm';
        }

        dispatchEvent(event: Event): boolean {
          const result = super.dispatchEvent(event);
          if (event.type === 'dataavailable' && typeof this.ondataavailable === 'function') {
            try {
              this.ondataavailable(event as MockBlobEvent);
            } catch (e) {
              console.error("Error in ondataavailable:", e);
            }
          }
          if (event.type === 'stop' && typeof this.onstop === 'function') {
            try {
              this.onstop();
            } catch (e) {
              console.error("Error in onstop:", e);
            }
          }
          return result;
        }

        start() {
          this.state = 'recording';
          // Synchronously dispatch dataavailable event so that chunks are populated immediately!
          const event = new Event('dataavailable') as MockBlobEvent;
          event.data = new Blob([new Uint8Array([1, 2, 3])], { type: this.mimeType });
          this.dispatchEvent(event);
        }

        stop() {
          this.state = 'inactive';
          // Synchronously dispatch stop event
          const event = new Event('stop');
          this.dispatchEvent(event);
        }
      }

      window.MediaRecorder = MockMediaRecorder as unknown as typeof MediaRecorder;

      navigator.mediaDevices.getUserMedia = async () => {
        return {
          getTracks: () => [{ stop: () => {} }],
        } as unknown as MediaStream;
      };

      // 4. Mock SpeechSynthesis API on prototype to override read-only properties
      if (typeof SpeechSynthesis !== 'undefined') {
        SpeechSynthesis.prototype.getVoices = () => [];
        SpeechSynthesis.prototype.speak = function (utterance: SpeechSynthesisUtterance) {
          setTimeout(() => {
            if (typeof utterance.onstart === 'function') {
              utterance.onstart();
            }
            setTimeout(() => {
              if (typeof utterance.onend === 'function') {
                utterance.onend();
              }
            }, 100);
          }, 0);
        };
        SpeechSynthesis.prototype.cancel = () => {};
        SpeechSynthesis.prototype.pause = () => {};
        SpeechSynthesis.prototype.resume = () => {};
      }
    });

    // C. Visit `/chat`
    await page.goto('/chat');

    // Print window.location and localStorage to see why it redirected
    const debugInfo = await page.evaluate(() => {
      return {
        url: window.location.href,
        localStorageKeys: Object.keys(localStorage),
        localStorageDemoToken: localStorage.getItem('sb-supabase-demo-auth-token'),
        localStorageProdToken: localStorage.getItem('sb-ozmjeuqbholoxypfxixb-auth-token'),
        sessionStorageKeys: Object.keys(sessionStorage),
      };
    });
    console.log("DEBUG INFO AT START:", JSON.stringify(debugInfo, null, 2));

    // D. Validate Language Hydration (Preferred language from profile is Hindi)
    // The language picker button should display the native name for Hindi: 'हिन्दी'
    const langPickerButton = page.locator('button[aria-haspopup="listbox"]');
    await expect(langPickerButton).toBeVisible();
    await expect(langPickerButton).toContainText('हिन्दी');

    // E. Verify personalized welcome message contains Hindi profile/fallback content
    const firstMessage = page.locator('.message-bubble').first();
    await expect(firstMessage).toBeVisible();

    // Dismiss the Daily Teaching Modal (which pops up automatically upon gated entry)
    const wisdomButton = page.getByRole('button', { name: 'Receive Wisdom' });
    await expect(wisdomButton).toBeVisible();
    await wisdomButton.click();
    await expect(wisdomButton).not.toBeVisible();

    // F. Start speech input (STT Mic streaming)
    const micButton = page.getByRole('button', { name: 'Start voice input' });
    await expect(micButton).toBeVisible();
    await micButton.click();

    // Verify recording states (button should change to Stop recording)
    const activeMicButton = page.getByRole('button', { name: 'Stop recording' });
    await expect(activeMicButton).toBeVisible();

    // Stop recording to trigger API upload
    await activeMicButton.click();

    // Wait for the language detection toast and click "Switch"
    const switchButton = page.getByRole('button', { name: 'Switch' });
    await expect(switchButton).toBeVisible({ timeout: 10000 });
    await switchButton.click();

    // G. Verify STT returned results, populated text area, and automatically switched language to Telugu (te)
    // The language picker button should automatically update to native Telugu: 'తెలుగు'
    await expect(langPickerButton).toContainText('తెలుగు');

    // Verify language change toast notice
    const toastTitle = page.locator('text=🌐 Language Switched').first();
    await expect(toastTitle).toBeVisible();

    // Verify text area is populated with Telugu transcription
    const inputArea = page.locator('textarea');
    await expect(inputArea).toHaveValue(/నమో గురుజీ/);

    // H. Submit message to trigger SSE streaming chat response
    await inputArea.focus();
    await page.keyboard.press('Enter');

    // Verify guru response contains Telugu text streamed from our mock
    const guruResponseBubble = page.locator('.message-bubble').last();
    await expect(guruResponseBubble).toContainText('ప్రణామం, నేను మీకు సహాయం చేయగలను.', { timeout: 15000 });

    // I. Verify graceful fallback warning is displayed on TTS failure
    const errorToastTitle = page.locator('text=Voice Output Notice').last();
    await expect(errorToastTitle).toBeVisible({ timeout: 15000 });
    const errorToastDesc = page.locator("text=Voice output isn't available for Telugu right now. Showing text only.").last();
    await expect(errorToastDesc).toBeVisible({ timeout: 15000 });
  });
});
