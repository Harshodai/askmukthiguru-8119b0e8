const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const screensDir = path.join(__dirname, '../video-composition/assets/screens');
if (!fs.existsSync(screensDir)) {
  fs.mkdirSync(screensDir, { recursive: true });
}

async function captureDarkModeScreens() {
  console.log('Capturing ALL AskMukthiGuru app screens in DARK SANCTUARY MODE...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 2,
    colorScheme: 'dark',
  });

  // Inject Dark Mode theme & Auth Session into browser context
  await context.addInitScript(() => {
    localStorage.setItem('theme', 'dark');
    localStorage.setItem('demo_mode', 'true');
    localStorage.setItem('askmukthiguru_onboarded', 'true');
    localStorage.setItem('askmukthiguru_tour_completed', 'true');
    sessionStorage.setItem('auth_explicit_login', 'true');
    document.documentElement.classList.add('dark');
  });

  const page = await context.newPage();

  const screens = [
    { name: 'screen_01_hero', path: '/', scroll: 0, desc: 'Landing Hero in Dark Mode' },
    { name: 'screen_02_how_it_works', path: '/', scroll: 1050, desc: 'How It Works Section in Dark Mode' },
    { name: 'screen_03_auth', path: '/auth', scroll: 0, desc: 'Sign-In Page with Google Login in Dark Mode' },
    { name: 'screen_04_chat', path: '/chat', scroll: 0, desc: 'Grounded RAG Chat Interface in Dark Mode' },
    { name: 'screen_05_serene_mind', path: '/chat?modal=serene-mind', scroll: 0, desc: 'Serene Mind Meditation Practice in Dark Mode' },
    { name: 'screen_06_notebook', path: '/notebooks', scroll: 0, desc: 'Encrypted Study Notebook in Dark Mode' },
    { name: 'screen_07_kg', path: '/knowledge-graph', scroll: 0, desc: '7,601-Node Knowledge Graph in Dark Mode' },
    { name: 'screen_08_profile', path: '/profile?tab=profile', scroll: 0, desc: 'Profile & 14 Languages in Dark Mode' },
    { name: 'screen_09_memory_vault', path: '/profile?tab=memory', scroll: 0, desc: 'Second Brain Vault & Memory Manager in Dark Mode' },
    { name: 'screen_10_privacy', path: '/profile?tab=privacy', scroll: 0, desc: 'Privacy & GDPR Right to Forget in Dark Mode' },
  ];

  const results = [];

  for (const s of screens) {
    console.log(`Capturing ${s.name} (${s.desc}) at http://localhost:8080${s.path}...`);
    const sep = s.path.includes('?') ? '&' : '?';
    await page.goto('http://localhost:8080' + s.path + sep + 'demo=true', { waitUntil: 'networkidle' });
    
    // Ensure dark class is applied to HTML root
    await page.evaluate(() => {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    });

    if (s.scroll > 0) {
      await page.evaluate((sc) => window.scrollTo(0, sc), s.scroll);
    }

    await page.waitForTimeout(s.path.includes('knowledge-graph') ? 4500 : 2000);

    const screenshotPath = path.join(screensDir, `${s.name}.png`);
    await page.screenshot({ path: screenshotPath });

    const currentUrl = page.url();
    const bodyText = await page.innerText('body');
    const isValid = !bodyText.includes('Page not found') && bodyText.length > 200;

    results.push({
      name: s.name,
      path: s.path,
      description: s.desc,
      finalUrl: currentUrl,
      bodyLength: bodyText.length,
      isValid: isValid,
      file: `${s.name}.png`
    });

    console.log(`✓ Saved ${s.name}.png (${isValid ? 'VALID' : 'INVALID'}) -> ${currentUrl}`);
  }

  await browser.close();
  console.log('\n--- Dark Sanctuary Mode Screen Capture Summary ---');
  console.table(results);
  fs.writeFileSync(path.join(screensDir, 'route_validation.json'), JSON.stringify(results, null, 2));
}

captureDarkModeScreens().catch(err => {
  console.error('Capture error:', err);
  process.exit(1);
});
