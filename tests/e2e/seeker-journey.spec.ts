import { test, expect } from '@playwright/test';

test.describe('Seeker Journey', () => {
  test('landing page to auth flow', async ({ page }) => {
    // 1. Visit Landing Page
    await page.goto('/');
    
    // Expect the main hero title to be visible
    await expect(page.locator('h1')).toContainText('Mukthi Guru');
    
    // 2. Click Begin Journey
    const beginButton = page.locator('text=Begin Journey');
    await beginButton.click();
    
    // 3. Verify Auth Page Navigation
    await expect(page).toHaveURL(/.*\/auth/);
    await expect(page.locator('h1')).toHaveText('AskMukthiGuru');
    
    // 4. Verify Auth Form
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
    
    // Switch to Sign Up
    await page.locator('text=Sign up').click();
    
    // Full name field should appear
    await expect(page.locator('input[id="fullName"]')).toBeVisible();
  });
});
