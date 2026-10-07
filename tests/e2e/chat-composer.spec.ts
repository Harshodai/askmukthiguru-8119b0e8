import { test, expect } from '@playwright/test';
import { dismissSafetyDisclaimer } from './support';

test.describe('Chat composer — keyboard and controls', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.clear();
      sessionStorage.clear();
      localStorage.setItem('askmukthiguru_tour_completed', '1');
      localStorage.setItem('askmukthiguru_consent_v1', 'rejected');
    });
    await page.route('**/api/**', (r) => r.abort());
    await page.route('**/realtime/v1/**', (r) => r.abort());
    await page.route('**/supabase.co/**', (r) => r.abort());
    await page.goto('/chat', { waitUntil: 'domcontentloaded' });
    await dismissSafetyDisclaimer(page);
  });

  test('Enter submits the message and clears the textarea', async ({ page }) => {
    const textarea = page.getByRole('textbox', { name: /your message/i });
    await expect(textarea).toBeVisible();
    await textarea.fill('test message');
    await textarea.press('Enter');
    await expect(textarea).toHaveValue('');
  });

  test('Shift+Enter inserts a newline without submitting', async ({ page }) => {
    const textarea = page.getByRole('textbox', { name: /your message/i });
    await expect(textarea).toBeVisible();
    await textarea.fill('line one');
    await textarea.press('Shift+Enter');
    const val = await textarea.inputValue();
    expect(val).toContain('line one');
    expect(val).toContain('\n');
    await expect(textarea).not.toHaveValue('');
  });

  test('Enter during IME composition does not submit', async ({ page }) => {
    const textarea = page.getByRole('textbox', { name: /your message/i });
    await expect(textarea).toBeVisible();
    await textarea.fill('composition');
    await page.evaluate(() => {
      const ta = document.querySelector('textarea') as HTMLTextAreaElement;
      if (!ta) return;
      ta.dispatchEvent(new CompositionEvent('compositionstart', { bubbles: true }));
      const ev = new KeyboardEvent('keydown', {
        key: 'Enter', code: 'Enter', keyCode: 229,
        bubbles: true, cancelable: true, isComposing: true,
      });
      ta.dispatchEvent(ev);
    });
    await expect(textarea).not.toHaveValue('');
  });

  test('click near top of visible prompt area focuses textarea', async ({ page }) => {
    const form = page.locator('form[aria-label]').first();
    await expect(form).toBeVisible();
    const box = await form.boundingBox();
    expect(box).not.toBeNull();
    await page.mouse.click(box!.x + box!.width / 2, box!.y + 14);
    const textarea = page.getByRole('textbox', { name: /your message/i });
    await expect(textarea).toBeFocused();
  });

  test('click in centre of prompt area focuses textarea', async ({ page }) => {
    // The form spans textarea + toolbar footer; clicking the form's vertical
    // centre lands on toolbar buttons. We click the textarea's own centre
    // to verify that the prompt hit-area correctly focuses the input.
    const textarea = page.getByRole('textbox', { name: /your message/i });
    await expect(textarea).toBeVisible();
    const box = await textarea.boundingBox();
    expect(box).not.toBeNull();
    await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2);
    await expect(textarea).toBeFocused();
  });

  test('toolbar shows exactly one Plus (more actions) button on fresh localStorage', async ({ page }) => {
    const plusBtn = page.getByRole('button', { name: /more actions/i });
    await expect(plusBtn).toHaveCount(1);
    const langBtn = page.getByRole('button', { name: /selected language/i });
    await expect(langBtn).toHaveCount(1);
    const sendBtn = page.getByRole('button', { name: /send message/i });
    await expect(sendBtn).toBeDisabled();
  });

  test('toolbar structure is preserved when an older conversation is restored', async ({ page }) => {
    await page.addInitScript(() => {
      const conv = [{
        id: 'legacy-conv-id',
        startedAt: '2026-01-01T00:00:00.000Z',
        updatedAt: '2026-01-01T00:00:00.000Z',
        preview: 'Old conversation',
        messageCount: 1,
        messages: [{
          id: 'msg-1', role: 'guru',
          content: 'Welcome back.', timestamp: '2026-01-01T00:00:00.000Z',
        }],
      }];
      localStorage.setItem('askmukthiguru_conversations', JSON.stringify(conv));
      localStorage.setItem('askmukthiguru_current_conversation', 'legacy-conv-id');
    });
    await page.reload({ waitUntil: 'domcontentloaded' });
    await dismissSafetyDisclaimer(page);
    await expect(page.getByRole('button', { name: /more actions/i })).toHaveCount(1);
    await expect(page.getByRole('button', { name: /send message/i })).toBeDisabled();
  });
});
