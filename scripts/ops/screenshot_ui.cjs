const { chromium } = require('playwright');
const { mkdirSync } = require('fs');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const outputDir = path.join(__dirname, '../../screenshots');
  mkdirSync(outputDir, { recursive: true });

  // Collect console errors
  const errors = [];
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text().substring(0, 200)); });

  // 1. Landing page
  await page.goto('http://localhost:80/', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${outputDir}/01-landing.png`, fullPage: false });
  console.log('01-landing.png captured');

  // Check what's visible
  const text = await page.textContent('body').catch(() => '');
  console.log(`Page title: ${await page.title()}`);
  console.log(`Body text length: ${text.length}`);
  console.log(`Console errors: ${errors.length}`);

  // 2. Second shot after JS settles
  await page.screenshot({ path: `${outputDir}/02-loaded.png`, fullPage: false });
  console.log('02-loaded.png captured');

  // 3. Try interacting - find main CTA buttons
  const buttons = await page.$$('button, a[href], [role="button"]');
  console.log(`Interactive elements: ${buttons.length}`);

  // 4. API docs
  await page.goto('http://localhost:8000/docs', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${outputDir}/03-api-docs.png`, fullPage: false });
  console.log('03-api-docs.png captured');

  // 5. Full page landing shot
  await page.goto('http://localhost:80/', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${outputDir}/04-landing-full.png`, fullPage: true });
  console.log('04-landing-full.png captured');

  console.log('\nConsole errors:');
  errors.forEach((e, i) => console.log(`  ${i+1}. ${e}`));

  await browser.close();
  console.log('\nDone - screenshots in screenshots/');
})();
