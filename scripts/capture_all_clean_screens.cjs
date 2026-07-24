const { chromium } = require('playwright');
const path = require('path');

async function captureAllCleanScreens() {
  console.log('🚀 Starting Clean Dark Mode Screen Capture with demo=true URL parameters...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 2,
    colorScheme: 'dark',
  });

  // Setup clean dark mode storage state
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

  const screens = [
    { name: 'screen_01_hero.png', url: 'http://localhost:8080/' },
    { name: 'screen_02_how_it_works.png', url: 'http://localhost:8080/#how-it-works' },
    { name: 'screen_03_wisdom.png', url: 'http://localhost:8080/#wisdom' },
    { name: 'screen_03_auth.png', url: 'http://localhost:8080/auth' },
    { name: 'screen_04_chat.png', url: 'http://localhost:8080/chat?demo=true' },
    { name: 'screen_05_serene_mind.png', url: 'http://localhost:8080/practices/serene-mind' },
    { name: 'screen_07_kg.png', url: 'http://localhost:8080/knowledge-graph' },
    { name: 'screen_06_notebook.png', url: 'http://localhost:8080/notebooks' },
    { name: 'screen_10_privacy.png', url: 'http://localhost:8080/profile?tab=conversations&demo=true' }
  ];

  for (const s of screens) {
    console.log(`📸 Capturing ${s.name} from ${s.url}...`);
    await page.goto(s.url, { waitUntil: 'networkidle' });
    await page.evaluate(() => {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
      // Purge driver.js tour overlays if present
      const popover = document.querySelector('.driver-popover');
      if (popover) popover.remove();
      const overlay = document.querySelector('.driver-overlay');
      if (overlay) overlay.remove();
    });
    await page.waitForTimeout(2500);
    const savePath = path.join(__dirname, '../video-composition/assets/screens', s.name);
    await page.screenshot({ path: savePath });
    console.log(`✓ Saved ${s.name}`);
  }

  await browser.close();
  console.log('🎉 All clean dark screens captured successfully!');
}

captureAllCleanScreens().catch(err => {
  console.error('Capture error:', err);
  process.exit(1);
});
