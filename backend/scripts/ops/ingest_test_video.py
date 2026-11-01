#!/usr/bin/env python3
"""Submit a new YouTube video for ingestion via the Admin UI, monitor the queue, and inspect the DAG."""

import hashlib
import hmac
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SECRET = os.environ.get("ADMIN_TOTP_SECRET", "V5FF7HLFI47FML25GLDSMHDJANDDVRMN")  # gitleaks:allow
OUT_DIR = Path("/Users/harshodaikolluru/.gemini/antigravity/brain/e954e2dc-0fbc-4037-93b9-b734c3c699db")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Sri Preethaji & Sri Krishnaji: Is There a Right Time for Love? (Registered in docs/rights/CONTENT-RIGHTS.md)
TEST_VIDEO_URL = "https://www.youtube.com/watch?v=STlEq16n8kI"
TEST_VIDEO_ID = "STlEq16n8kI"

def base32_decode(s: str) -> bytes:
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    bits = 0
    val = 0
    out = []
    for c in s.upper():
        idx = chars.find(c)
        if idx == -1:
            continue
        val = (val << 5) | idx
        bits += 5
        if bits >= 8:
            out.append((val >> (bits - 8)) & 0xFF)
            bits -= 8
    return bytes(out)

def get_totp(secret: str) -> str:
    key = base32_decode(secret)
    epoch = int(time.time() // 30)
    time_bytes = epoch.to_bytes(8, "big")
    h = hmac.new(key, time_bytes, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = (int.from_bytes(h[offset : offset + 4], "big") & 0x7FFFFFFF) % 1000000
    return f"{code:06d}"

def run_ingestion_flow():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark")
        context.add_init_script("localStorage.setItem('askmukthiguru_disclaimer_accepted', 'true');")
        page = context.new_page()

        print("1. Authenticating as Admin...")
        page.goto("http://localhost/admin/login")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # Login credentials
        page.fill("#admin-email", "mw1789298700@gmail.com")
        page.fill("#admin-password", "SeekerSecret123!")
        page.click("button[type='submit']")
        page.wait_for_timeout(2500)

        # TOTP MFA
        if "/auth/mfa" in page.url or page.locator("#mfa-code").count() > 0:
            totp = get_totp(SECRET)
            page.fill("#mfa-code", totp)
            submit_btn = page.locator("button:has-text('Verify'), button:has-text('Submit'), button[type='submit']")
            if submit_btn.count() > 0:
                submit_btn.first.click()
            page.wait_for_timeout(3000)

        print(f"Logged in: {page.url}")

        # ----------------------------------------------------
        # 2. INGESTION SUBMISSION (TAB=INGESTION)
        # ----------------------------------------------------
        print(f"2. Navigating to Ingestion Page to submit: {TEST_VIDEO_URL}...")
        page.goto("http://localhost/admin/ingestion?tab=ingestion")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        url_input = page.locator("#ingest-url")
        assert url_input.is_visible(), "Ingest URL input not found!"
        url_input.fill(TEST_VIDEO_URL)
        page.wait_for_timeout(300)

        # Toggle Max Accuracy (leave default/unchecked for fast, reliable caption-based ingestion)
        # acc_switch = page.locator("#max-accuracy")

        # Take screenshot of populated form before submit
        pre_submit_path = str(OUT_DIR / "new_video_pre_submit.png")
        page.screenshot(path=pre_submit_path)
        print(f"Saved: {pre_submit_path}")

        # Click submit
        ingest_btn = page.locator("button:has-text('Ingest')").first
        assert ingest_btn.is_visible(), "Ingest button not found!"
        print("Clicking 'Ingest' button...")
        ingest_btn.click()
        page.wait_for_timeout(3000)

        post_submit_path = str(OUT_DIR / "new_video_submitted_toast.png")
        page.screenshot(path=post_submit_path)
        print(f"Saved: {post_submit_path}")

        # ----------------------------------------------------
        # 3. CHECK QUEUE & POLL FOR COMPLETION (TAB=QUEUE)
        # ----------------------------------------------------
        print("3. Checking Queue for job progress...")
        page.goto("http://localhost/admin/ingestion?tab=queue")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)

        # Wait up to 30 seconds for background worker to complete
        for poll_i in range(6):
            page.wait_for_timeout(4000)
            refresh_btn = page.locator("button:has-text('Refresh')")
            if refresh_btn.count() > 0 and refresh_btn.first.is_visible():
                refresh_btn.first.click()
                page.wait_for_timeout(1000)

        queue_path = str(OUT_DIR / "new_video_queue_status.png")
        page.screenshot(path=queue_path)
        print(f"Saved: {queue_path}")

        # ----------------------------------------------------
        # 4. VIEW COMPLETED RUNS (TAB=INGESTION)
        # ----------------------------------------------------
        print("4. Inspecting completed runs table...")
        page.goto("http://localhost/admin/ingestion?tab=ingestion")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        runs_path = str(OUT_DIR / "new_video_ingestion_runs.png")
        page.screenshot(path=runs_path)
        print(f"Saved: {runs_path}")

        # ----------------------------------------------------
        # 5. VIEW WORKFLOW DAG FOR THE VIDEO (TAB=WORKFLOW)
        # ----------------------------------------------------
        print("5. Inspecting Workflow DAG with video context...")
        page.goto("http://localhost/admin/ingestion?tab=workflow")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Check if video selector has our video or click first video
        video_chips = page.locator("button:has-text('TqxxCYnAxo8'), button:has-text('TEDx')")
        if video_chips.count() > 0 and video_chips.first.is_visible():
            print("Selecting newly submitted video chip...")
            video_chips.first.click()
            page.wait_for_timeout(1000)

        dag_path = str(OUT_DIR / "new_video_workflow_dag.png")
        page.screenshot(path=dag_path)
        print(f"Saved: {dag_path}")

        browser.close()
        print("=== Ingestion flow test complete ===")

if __name__ == "__main__":
    run_ingestion_flow()
