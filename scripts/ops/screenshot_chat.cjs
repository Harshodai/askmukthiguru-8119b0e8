const { chromium } = require('playwright');
const { mkdirSync } = require('fs');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const outputDir = path.join(__dirname, '../../screenshots');
  mkdirSync(outputDir, { recursive: true });

  // Chat page
  await page.goto('http://localhost:80/chat', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: outputDir+'/05-chat.png', fullPage: false });
  console.log('05-chat.png captured');

  const chatText = await page.evaluate(() => document.body.innerText.substring(0, 500));
  console.log('Chat page text:', chatText.substring(0, 200));

  // Go home and click Start Chat
  await page.goto('http://localhost:80/', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(3000);

  const found = await page.evaluate(() => {
    const links = Array.from(document.querySelectorAll('a'));
    const target = links.find(l => l.textContent.includes('Start Chat'));
    if (target) { target.click(); return true; }
    return false;
  });
  if (found) {
    await page.waitForTimeout(5000);
    await page.screenshot({ path: outputDir+'/06-chat-interaction.png', fullPage: false });
    console.log('06-chat-interaction.png captured');
  }

  await browser.close();
  console.log('Done');
})();
