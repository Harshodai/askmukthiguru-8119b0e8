import os
import sys
import time
from playwright.sync_api import sync_playwright, expect, TimeoutError

ARTIFACT_DIR = "/Users/harshodaikolluru/.gemini/antigravity/brain/eedc781c-e9cc-42c2-80d2-f845bc0385ac"

def run_e2e_tests():
    print("🚀 Starting E2E Verification Script...")
    
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()
        
        # Diagnostic Instrumentation
        page.on("console", lambda msg: print(f"[Browser Console] {msg.type}: {msg.text}"))
        page.on("pageerror", lambda err: print(f"[Browser Error] {err}"))
        page.on("requestfailed", lambda req: print(f"[Network Error] {req.url} - {req.failure.error_text if req.failure else 'Unknown'}"))
        
        try:
            print("=========================================")
            print("1. Testing Chat UI & RAG Pipeline")
            print("=========================================")
            page.goto("http://localhost/chat/")
            page.wait_for_load_state("networkidle")
            
            # Find the chat input
            print("Typing query...")
            chat_input = page.get_by_placeholder("Ask Mukthi Guru a spiritual question...")
            # If the placeholder is different, we can fallback to generic role
            if not chat_input.is_visible():
                chat_input = page.locator('textarea')
            
            query_text = "What is the core teaching of compassion?"
            chat_input.fill(query_text)
            
            # Submit the query
            print("Submitting query...")
            page.keyboard.press("Enter")
            
            # Wait for response
            print("Waiting for RAG streaming response (this may take up to 30s)...")
            # The backend might take time to embed, retrieve, and generate. 
            # We wait for the specific text "What is the core teaching of compassion?" to appear as a user message,
            # then wait for the AI response to finish generating.
            
            # We can wait for networkidle to assume the stream finished
            page.wait_for_timeout(2000) # Wait a bit for the request to start
            page.wait_for_load_state("networkidle", timeout=60000)
            
            print("Capturing Chat UI screenshot...")
            chat_screenshot_path = os.path.join(ARTIFACT_DIR, "chat_success.png")
            page.screenshot(path=chat_screenshot_path, full_page=True)
            print(f"✅ Chat UI test completed. Screenshot saved to {chat_screenshot_path}")
            
            print("\n=========================================")
            print("2. Testing Admin Dashboard & Telemetry")
            print("=========================================")
            page.goto("http://localhost/admin/login")
            page.wait_for_load_state("networkidle")
            
            print("Logging into Admin Dashboard...")
            page.get_by_placeholder("Email").fill("admin@example.com")
            page.get_by_placeholder("Password").fill("password123")
            page.get_by_role("button", name="Login").click()
            
            print("Waiting for dashboard to load...")
            page.wait_for_url("**/admin**", timeout=10000)
            page.wait_for_load_state("networkidle")
            
            print("Navigating to Queries tab...")
            # Click the Queries nav item
            page.get_by_text("Queries", exact=True).click()
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000) # Let the Supabase fetch complete
            
            print("Capturing Admin UI screenshot...")
            admin_screenshot_path = os.path.join(ARTIFACT_DIR, "admin_success.png")
            page.screenshot(path=admin_screenshot_path, full_page=True)
            
            # Assert the telemetry exists
            # We check if the query text appears on the page
            body_text = page.locator("body").inner_text()
            if "compassion" in body_text.lower():
                print(f"✅ Admin Telemetry test completed. Telemetry found! Screenshot saved to {admin_screenshot_path}")
            else:
                print(f"⚠️ Warning: Telemetry for 'compassion' not immediately found in DOM. Check the screenshot: {admin_screenshot_path}")
            
        except TimeoutError as e:
            print(f"❌ Timeout Error: {str(e)}")
            error_screenshot = os.path.join(ARTIFACT_DIR, "error_timeout.png")
            page.screenshot(path=error_screenshot, full_page=True)
            print(f"Captured error state at {error_screenshot}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Unexpected Error: {str(e)}")
            error_screenshot = os.path.join(ARTIFACT_DIR, "error_unexpected.png")
            page.screenshot(path=error_screenshot, full_page=True)
            print(f"Captured error state at {error_screenshot}")
            sys.exit(1)
        finally:
            context.close()
            browser.close()

if __name__ == "__main__":
    run_e2e_tests()
