const { chromium } = require('playwright');
const { mkdirSync, existsSync } = require('fs');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 }
  });
  const page = await context.newPage();
  
  const outputDir = path.join(__dirname, '../../screenshots');
  mkdirSync(outputDir, { recursive: true });

  console.log('Starting screenshot sweep...');

  // 1. Sign up/Sign in
  await page.goto('http://localhost:80/chat', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);

  // If redirected to login, register a test user
  const isLoginPage = await page.locator('text=Sign in to AskMukthiGuru').count() > 0;
  if (isLoginPage) {
    console.log('On login page, toggling to Sign Up...');
    // Click "Sign up" toggle button
    await page.click('button:has-text("Sign up")');
    await page.waitForTimeout(1000);

    const email = `sweep-test-${Date.now()}@example.com`;
    console.log(`Creating test user with email: ${email}`);

    await page.fill('input#fullName', 'Harshodai');
    await page.fill('input#email', email);
    await page.fill('input#password', 'seekerpassword123!');
    await page.click('button[type="submit"]');
    
    // Wait for auth redirect / session load
    await page.waitForTimeout(6000);
  }

  // 2. Capture Chat Welcome Page
  console.log('Capturing Chat Welcome page...');
  await page.screenshot({ path: `${outputDir}/05-chat-welcome.png`, fullPage: true });

  // Dismiss cookie banner and "Before we begin" dialog if they are visible
  await page.waitForSelector('button:has-text("Accept")', { timeout: 5000 }).catch(() => {});
  await page.click('button:has-text("Accept")').catch(() => {});

  await page.waitForSelector('button:has-text("Skip for now")', { timeout: 5000 }).catch(() => {});
  await page.click('button:has-text("Skip for now")').catch(() => {});
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${outputDir}/05b-chat-welcome-dismissed.png`, fullPage: true });
  console.log('05b-chat-welcome-dismissed.png captured');

  // 3. Send a message to verify RAG and thinking pills
  console.log('Sending message to general assistant...');
  await page.fill('textarea', 'What is the Beautiful State?');
  await page.click('button[aria-label="Send message"]');
  
  // Capture thinking state immediately
  await page.waitForTimeout(1000);
  await page.screenshot({ path: `${outputDir}/06-chat-thinking.png`, fullPage: false });
  console.log('06-chat-thinking.png captured');

  // Wait for RAG response to stream completely
  console.log('Waiting for response stream...');
  await page.waitForTimeout(20000);
  await page.screenshot({ path: `${outputDir}/07-chat-response.png`, fullPage: true });
  console.log('07-chat-response.png captured');

  // 4. Capture Practices Page
  console.log('Navigating to Practices page...');
  await page.goto('http://localhost:80/practices', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${outputDir}/08-practices.png`, fullPage: true });
  console.log('08-practices.png captured');

  // 5. Capture Profile Page
  console.log('Navigating to Profile page...');
  await page.goto('http://localhost:80/profile', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${outputDir}/09-profile.png`, fullPage: true });
  console.log('09-profile.png captured');

  // 6. Capture Terms Page
  console.log('Navigating to Terms page...');
  await page.goto('http://localhost:80/terms', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${outputDir}/10-terms.png`, fullPage: true });
  console.log('10-terms.png captured');

  // 7. Capture Privacy Page
  console.log('Navigating to Privacy page...');
  await page.goto('http://localhost:80/privacy', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${outputDir}/11-privacy.png`, fullPage: true });
  console.log('11-privacy.png captured');

  // 8. Capture Serene Mind Modal and its Tabs
  console.log('Navigating back to Chat page to verify Serene Mind tabs...');
  await page.goto('http://localhost:80/chat', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);
  await page.click('button:has-text("Skip for now")').catch(() => {});

  console.log('Opening Serene Mind modal...');
  await page.fill('textarea', 'open serene mind');
  await page.click('button[aria-label="Send message"]');
  await page.waitForSelector('[role="dialog"]', { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(1000);

  // Take screenshot of Breathe Tab
  console.log('Capturing Breathe Tab...');
  await page.screenshot({ path: `${outputDir}/12-serene-mind-breathe.png` });

  // Click Audio Tab
  console.log('Clicking Audio Tab...');
  await page.click('button[role="tab"]:has-text("Audio")').catch(() => {});
  await page.waitForTimeout(1000);
  await page.screenshot({ path: `${outputDir}/13-serene-mind-audio.png` });

  // Click Video Tab
  console.log('Clicking Video Tab...');
  await page.click('button[role="tab"]:has-text("Video")').catch(() => {});
  await page.waitForTimeout(1000);
  await page.screenshot({ path: `${outputDir}/14-serene-mind-video.png` });

  // Close the modal
  await page.click('button[aria-label="Close"]').catch(() => {});

  await browser.close();
  console.log('Screenshot sweep complete.');
})();
