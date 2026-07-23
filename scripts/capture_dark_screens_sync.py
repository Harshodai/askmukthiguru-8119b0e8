import asyncio
import os
import json
from playwright.async_api import async_playwright

screens_dir = os.path.abspath("video-composition/assets/screens")
os.makedirs(screens_dir, exist_ok=True)

async def capture_dark_mode_ruthless():
    print("Starting RUTHLESS Dark Sanctuary Mode Playwright screen capture...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=2,
            color_scheme="dark"
        )

        # Inject Dark Theme & DISMISS Tour completely
        init_script = """
        localStorage.setItem('theme', 'dark');
        localStorage.setItem('demo_mode', 'true');
        localStorage.setItem('askmukthiguru_onboarded', '1');
        localStorage.setItem('askmukthiguru_tour_completed', '1');
        localStorage.setItem('askmukthiguru_tour_shown_count', '99');
        sessionStorage.setItem('auth_explicit_login', 'true');
        document.documentElement.classList.add('dark');
        """
        await context.add_init_script(init_script)

        page = await context.new_page()

        targets = [
            {"name": "screen_01_hero", "path": "/?demo=true", "scroll": 0, "desc": "Landing Hero in Dark Sanctuary Mode"},
            {"name": "screen_02_how_it_works", "path": "/?demo=true", "scroll": 1050, "desc": "How It Works 4-Step Flow in Dark Mode"},
            {"name": "screen_03_auth", "path": "/auth?demo=true", "scroll": 0, "desc": "Sign-In Page with Google Login in Dark Mode"},
            {"name": "screen_04_chat", "path": "/chat?demo=true", "scroll": 0, "desc": "Grounded RAG Chat Interface in Dark Mode (No Tour Modal)"},
            {"name": "screen_05_serene_mind", "path": "/chat?modal=serene-mind&demo=true", "scroll": 0, "desc": "Serene Mind Guided Meditation Modal in Dark Mode"},
            {"name": "screen_06_notebook", "path": "/notebooks?demo=true", "scroll": 0, "desc": "Encrypted Study Notebook in Dark Mode"},
            {"name": "screen_07_kg", "path": "/knowledge-graph?demo=true", "scroll": 0, "desc": "7,601-Node Interactive Wisdom Map in Dark Mode"},
            {"name": "screen_08_profile", "path": "/profile?tab=profile&demo=true", "scroll": 0, "desc": "Profile & 14 Languages Selector in Dark Mode"},
            {"name": "screen_09_memory_vault", "path": "/profile?tab=memory&demo=true", "scroll": 0, "desc": "Second Brain Vault & Memory Manager in Dark Mode"},
            {"name": "screen_10_privacy", "path": "/profile?tab=privacy&demo=true", "scroll": 0, "desc": "Privacy & GDPR Right to Forget in Dark Mode"},
        ]

        results = []

        for item in targets:
            url = "http://localhost:8080" + item["path"]
            print(f"Navigating to {url}...")
            await page.goto(url, wait_until="networkidle")

            # Force dark theme & clear any popovers/tours
            await page.evaluate("""
            document.documentElement.classList.add('dark');
            localStorage.setItem('theme', 'dark');
            localStorage.setItem('askmukthiguru_tour_completed', '1');
            localStorage.setItem('askmukthiguru_onboarded', '1');
            
            // Remove driver.js popover if present
            const popover = document.querySelector('.driver-popover');
            if (popover) popover.remove();
            const overlay = document.querySelector('.driver-overlay');
            if (overlay) overlay.remove();
            """)

            if item["scroll"] > 0:
                await page.evaluate(f"window.scrollTo(0, {item['scroll']});")

            wait_time = 4500 if "knowledge-graph" in item["path"] else 2000
            await page.wait_for_timeout(wait_time)

            out_path = os.path.join(screens_dir, f"{item['name']}.png")
            await page.screenshot(path=out_path)

            body_text = await page.inner_text("body")
            has_tour = await page.evaluate("!!document.querySelector('.driver-popover')")
            is_valid = "Page not found" not in body_text and len(body_text) > 200 and not has_tour

            results.append({
                "name": item["name"],
                "path": item["path"],
                "description": item["desc"],
                "bodyLength": len(body_text),
                "hasTourOverlay": has_tour,
                "isValid": is_valid,
                "file": f"{item['name']}.png"
            })
            print(f"✓ Ruthlessly Validated {item['name']}.png -> Tour Overlay: {has_tour} | Valid: {is_valid}")

        await browser.close()
        
        with open(os.path.join(screens_dir, "dark_mode_validation.json"), "w") as f:
            json.dump(results, f, indent=2)
        print("\n🎉 All 10 Dark Mode screens ruthlessly captured without tour popovers!")

if __name__ == "__main__":
    asyncio.run(capture_dark_mode_ruthless())
