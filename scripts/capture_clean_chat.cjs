const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

async function captureCleanChat() {
  console.log('Capturing CLEAN screen_04_chat.png with tour disabled...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 2,
    colorScheme: 'dark',
  });

  await context.addInitScript(() => {
    localStorage.setItem('theme', 'dark');
    localStorage.setItem('demo_mode', 'true');
    localStorage.setItem('askmukthiguru_onboarded', '1');
    localStorage.setItem('askmukthiguru_tour_completed', '1');
    localStorage.setItem('askmukthiguru_tour_shown_count', '99');
    sessionStorage.setItem('auth_explicit_login', 'true');
    document.documentElement.classList.add('dark');
  });

  const page = await context.newPage();

  // Navigate to Chat
  console.log('Navigating to http://localhost:8080/chat?demo=true...');
  await page.goto('http://localhost:8080/chat?demo=true', { waitUntil: 'networkidle' });
  
  await page.evaluate(() => {
    document.documentElement.classList.add('dark');
    localStorage.setItem('theme', 'dark');
    
    // Explicitly remove any popovers from DOM if any exist
    const popover = document.querySelector('.driver-popover');
    if (popover) popover.remove();
    const overlay = document.querySelector('.driver-overlay');
    if (overlay) overlay.remove();
  });

  await page.waitForTimeout(2500);

  const screenshotPath = path.join(__dirname, '../video-composition/assets/screens/screen_04_chat.png');
  await page.screenshot({ path: screenshotPath });

  const hasPopover = await page.evaluate("!!document.querySelector('.driver-popover')");
  console.log(`✓ Saved CLEAN screen_04_chat.png to ${screenshotPath}`);
  console.log(`✓ Driver Popover Present: ${hasPopover} (Must be false)`);

  await browser.close();
}

captureCleanChat().catch(err => {
  console.error('Capture error:', err);
  process.exit(1);
});
