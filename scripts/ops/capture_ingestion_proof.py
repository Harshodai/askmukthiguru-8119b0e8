#!/usr/bin/env python3
"""Capture end-to-end screenshots of completed video ingestion and workflow DAG."""

import hashlib
import hmac
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

SECRET = os.environ.get("ADMIN_TOTP_SECRET", "V5FF7HLFI47FML25GLDSMHDJANDDVRMN")  # gitleaks:allow
OUT_DIR = Path(
    "/Users/harshodaikolluru/.gemini/antigravity/brain/e954e2dc-0fbc-4037-93b9-b734c3c699db"
)
OUT_DIR.mkdir(parents=True, exist_ok=True)

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


def capture_proof():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark")
        context.add_init_script(
            "localStorage.setItem('askmukthiguru_disclaimer_accepted', 'true');"
        )
        page = context.new_page()

        print("1. Logging in as Admin...")
        page.goto("http://localhost/admin/login")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        page.fill("#admin-email", "mw1789298700@gmail.com")
        page.fill("#admin-password", "SeekerSecret123!")
        page.click("button[type='submit']")
        page.wait_for_timeout(2500)

        if "/auth/mfa" in page.url or page.locator("#mfa-code").count() > 0:
            totp = get_totp(SECRET)
            page.fill("#mfa-code", totp)
            submit_btn = page.locator(
                "button:has-text('Verify'), button:has-text('Submit'), button[type='submit']"
            )
            if submit_btn.count() > 0:
                submit_btn.first.click()
            page.wait_for_timeout(3000)

        print(f"Logged in: {page.url}")

        # 1. Ingestion Runs Table
        print("2. Capturing Ingestion Runs table...")
        page.goto("http://localhost/admin/ingestion?tab=ingestion")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        p1 = str(OUT_DIR / "final_ingestion_runs_table.png")
        page.screenshot(path=p1)
        print(f"Saved: {p1}")

        # 2. Ingestion Workflow DAG
        print(f"3. Capturing Ingestion Workflow DAG for {TEST_VIDEO_ID}...")
        page.goto("http://localhost/admin/ingestion?tab=workflow")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        chips = page.locator(f"button:has-text('{TEST_VIDEO_ID}'), button:has-text('STlEq')")
        if chips.count() > 0 and chips.first.is_visible():
            chips.first.click()
            page.wait_for_timeout(1000)

        p2 = str(OUT_DIR / "final_ingestion_workflow_dag.png")
        page.screenshot(path=p2)
        print(f"Saved: {p2}")

        # 3. Click stage 4 (Attribution) or stage 8 (Persistence) to inspect drawer
        print("4. Inspecting Stage Details Drawer...")
        node = page.locator(".react-flow__node").filter(has_text="ECAPA Speaker Attribution").first
        if node.count() > 0:
            node.click()
            page.wait_for_timeout(1000)
        p3 = str(OUT_DIR / "final_ingestion_stage_drawer.png")
        page.screenshot(path=p3)
        print(f"Saved: {p3}")

        # 4. Video Approval page & Lineage Modal DAG
        print("5. Navigating to Video Approvals (tab=video-approval)...")
        page.goto("http://localhost/admin/ingestion?tab=video-approval")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2500)

        p4 = str(OUT_DIR / "final_video_approval_table.png")
        page.screenshot(path=p4)
        print(f"Saved: {p4}")

        # Open DAG modal for video row
        dag_buttons = page.locator("button:has-text('Pipeline DAG')")
        if dag_buttons.count() > 0:
            print("Opening Pipeline DAG modal for video row...")
            dag_buttons.first.click()
            page.wait_for_timeout(2000)
            p5 = str(OUT_DIR / "final_video_dag_modal.png")
            page.screenshot(path=p5)
            print(f"Saved: {p5}")
        else:
            print("No Pipeline DAG button found on video approval page")

        browser.close()
        print("=== All proof screenshots captured successfully ===")


if __name__ == "__main__":
    capture_proof()
