import { test, expect } from '@playwright/test';

const CONTEXT_ERROR = {
  error: 'Conversation context exhausted',
  error_code: 'conversation_context_exhausted',
  detail: 'This conversation has reached its safe context limit. Start a new chat to continue.',
};

async function dismissOptionalDialog(page: import('@playwright/test').Page) {
  const dialog = page.getByRole('dialog').first();
  if (await dialog.isVisible().catch(() => false)) {
    const skip = dialog.getByRole('button', { name: /skip/i }).first();
    if (await skip.isVisible().catch(() => false)) {
      await skip.click();
    }
  }
}

for (const locale of ['en', 'ur']) {
  test(`context exhaustion preserves work and continues safely (${locale})`, async ({ page }) => {
    await page.addInitScript((lng) => {
      localStorage.clear();
      sessionStorage.clear();
      localStorage.setItem('i18nextLng', lng);
      localStorage.setItem('askmukthiguru_profile.preferredLanguage', lng);
      localStorage.setItem('askmukthiguru_profile', JSON.stringify({
        preferredLanguage: lng,
      }));
      localStorage.setItem('askmukthiguru_consent_v1', 'accepted');
      localStorage.setItem('askmukthiguru_disclaimer_accepted', 'true');
    }, locale);

    await page.route(/\/api\/chat(?:\/[^?]*)?(?:\?.*)?$/, async (route) => {
      const url = route.request().url();
      if (url.includes('/title')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ title: 'Context continuation' }),
        });
        return;
      }
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({ status: 200, headers: { 'Access-Control-Allow-Origin': '*' } });
        return;
      }
      await route.fulfill({
        status: 409,
        contentType: 'application/json',
        headers: { 'Access-Control-Allow-Origin': '*' },
        body: JSON.stringify(CONTEXT_ERROR),
      });
    });

    await page.goto('/chat', { waitUntil: 'domcontentloaded' });
    await dismissOptionalDialog(page);

    const input = page.locator('textarea[data-tour="chat-input"]');
    await expect(input).toBeVisible();

    const draft = locale === 'ur'
      ? 'میں اپنی گفتگو جاری رکھنا چاہتا ہوں'
      : 'I want to continue this conversation';
    await input.fill(draft);

    await page.locator('button[type="submit"]').click();

    const limitTitle = locale === 'ur'
      ? 'گفتگو کی سیاقی حد پوری ہو گئی ہے'
      : 'Conversation context limit reached';
    const continueLabel = locale === 'ur'
      ? 'نئی چیٹ میں جاری رکھیں'
      : 'Continue in a new chat';

    await expect(page.getByText(limitTitle, { exact: true }).first()).toBeVisible({ timeout: 15000 });
    await expect(input).toHaveValue(draft);
    await expect(page.getByRole('button', { name: continueLabel })).toBeVisible();

    const before = await page.evaluate(() => {
      const raw = localStorage.getItem('askmukthiguru_conversations');
      return raw ? JSON.parse(raw).length : 0;
    });

    await page.getByRole('button', { name: continueLabel }).first().click();

    await expect.poll(async () => {
      return page.evaluate(() => {
        const raw = localStorage.getItem('askmukthiguru_conversations');
        return raw ? JSON.parse(raw).length : 0;
      });
    }).toBe(before + 1);

    await expect(input).toHaveValue('');
  });
}
