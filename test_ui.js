import { chromium } from 'playwright';
import path from 'path';

async function run() {
  console.log('Launching browser...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  try {
    console.log('Navigating to http://localhost:8080/chat...');
    await page.goto('http://localhost:8080/chat', { waitUntil: 'networkidle' });
    
    // Wait for the sidebar to be visible
    console.log('Waiting for sidebar...');
    await page.waitForSelector('[data-testid="conversation-item"]', { timeout: 10000 }).catch(() => console.log('No conversations found yet, this is expected if new.'));
    
    console.log('Taking screenshot of chat interface...');
    const screenshotPath = 'chat_ui_screenshot.png';
    await page.screenshot({ path: screenshotPath, fullPage: true });
    
    console.log(`Screenshot saved to ${screenshotPath}`);
    
    const hasNewChat = await page.evaluate(() => document.body.innerText.includes('New Chat'));
    console.log(`Contains "New Chat": ${hasNewChat}`);
    
  } catch (err) {
    console.error('Error:', err);
  } finally {
    await browser.close();
  }
}

run();
