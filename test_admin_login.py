from playwright.sync_api import sync_playwright

def test_admin_login():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Log console and errors
        page.on("console", lambda msg: print(f"CONSOLE [{msg.type}]: {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        
        print("Navigating to admin login...")
        page.goto('http://localhost/admin/login', wait_until='networkidle')
        
        print("Filling in credentials...")
        page.fill('input[type="email"]', 'kharshaengineer@gmail.com')
        page.fill('input[type="password"]', 'Admin@123456')
        
        print("Clicking submit...")
        page.click('button[type="submit"]')
        
        # Wait a bit to see what happens
        page.wait_for_timeout(3000)
        
        print(f"Final URL: {page.url}")
        
        # Check if there's any alert/error displayed
        alerts = page.locator('.bg-destructive\\/5').all_inner_texts()
        if alerts:
            print(f"UI Error displayed: {alerts}")
            
        # Try to navigate to /admin directly
        print("Checking if we can access /admin directly...")
        page.goto('http://localhost/admin', wait_until='networkidle')
        print(f"URL after direct access: {page.url}")
        
        browser.close()

if __name__ == "__main__":
    test_admin_login()
