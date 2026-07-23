const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const assetsDir = path.join(__dirname, '../video-composition/assets/screens');
if (!fs.existsSync(assetsDir)) {
  fs.mkdirSync(assetsDir, { recursive: true });
}

async function captureRealScreens() {
  console.log('Launching Playwright Chrome for high-res app screenshots...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 2, // 4K retina quality
  });

  const page = await context.newPage();

  // 1. Landing Hero
  console.log('1. Capturing Landing Hero (http://localhost:8080/)...');
  await page.goto('http://localhost:8080/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(assetsDir, 'screen_01_hero.png') });

  // 2. How It Works Section
  console.log('2. Capturing How It Works Section...');
  await page.evaluate(() => window.scrollTo(0, 1100));
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(assetsDir, 'screen_02_how_it_works.png') });

  // 3. Sample Wisdom Section
  console.log('3. Capturing Sample Wisdom / Wisdom & Insights Section...');
  await page.evaluate(() => window.scrollTo(0, 1900));
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(assetsDir, 'screen_03_wisdom.png') });

  // 4. Chat Interface
  console.log('4. Capturing Chat Interface (http://localhost:8080/#/chat)...');
  await page.goto('http://localhost:8080/#/chat', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(assetsDir, 'screen_04_chat.png') });

  // 5. Knowledge Graph
  console.log('5. Capturing Knowledge Graph (http://localhost:8080/#/knowledge-graph)...');
  await page.goto('http://localhost:8080/#/knowledge-graph', { waitUntil: 'networkidle' });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: path.join(assetsDir, 'screen_05_kg.png') });

  // 6. Spirit Guides Page
  console.log('6. Capturing Spirit Guides (http://localhost:8080/#/guides)...');
  await page.goto('http://localhost:8080/#/guides', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(assetsDir, 'screen_06_guides.png') });

  // 7. Study Notebook
  console.log('7. Capturing Study Notebook (http://localhost:8080/#/notebook)...');
  await page.goto('http://localhost:8080/#/notebook', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(assetsDir, 'screen_07_notebook.png') });

  // 8. Profile Page / Memory Manager
  console.log('8. Capturing Profile / Memory Manager (http://localhost:8080/#/profile)...');
  await page.goto('http://localhost:8080/#/profile', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(assetsDir, 'screen_08_profile.png') });

  await browser.close();
  console.log('🎉 All real app screen captures completed successfully!');
}

captureRealScreens().catch(err => {
  console.error('Error capturing real app screens:', err);
  process.exit(1);
});
