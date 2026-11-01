#!/usr/bin/env python3
"""Capture high-resolution screenshots across key surfaces of the AskMukthiGuru application."""

import hashlib
import hmac
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

SECRET = os.environ.get("ADMIN_TOTP_SECRET", "V5FF7HLFI47FML25GLDSMHDJANDDVRMN")  # gitleaks:allow
OUT_DIR = Path("/Users/harshodaikolluru/.gemini/antigravity/brain/e954e2dc-0fbc-4037-93b9-b734c3c699db")
OUT_DIR.mkdir(parents=True, exist_ok=True)

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

def capture_all():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            color_scheme="dark"
        )
        context.add_init_script("localStorage.setItem('askmukthiguru_disclaimer_accepted', 'true');")
        page = context.new_page()

        # 1. Chat Landing Page
        print("1. Capturing Chat Landing Page...")
        page.goto("http://localhost/")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        page.screenshot(path=str(OUT_DIR / "chat_landing_with_gurus.png"))
        print("Saved chat_landing_with_gurus.png")

        # 2. Chat with Guru Teaching and Avatar
        print("2. Sending a query in chat...")
        try:
            input_box = page.locator("textarea").first
            if input_box.is_visible():
                input_box.fill("What is Ekam?")
                page.keyboard.press("Enter")
                print("Waiting for response stream...")
                page.wait_for_timeout(8000)
                page.screenshot(path=str(OUT_DIR / "chat_message_with_guru_avatar_deduped.png"))
                print("Saved chat_message_with_guru_avatar_deduped.png")
        except Exception as e:
            print(f"Chat query capture error: {e}")

        # 3. Profile Page (Sadhana rhythm, Golden Orb visuals)
        print("3. Capturing Profile Page...")
        page.goto("http://localhost/profile")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3000)
        page.screenshot(path=str(OUT_DIR / "profile_journey_golden_orb.png"))
        print("Saved profile_journey_golden_orb.png")

        # 4. Admin Login and Overview
        print("4. Admin login flow...")
        page.goto("http://localhost/admin/login")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        page.fill("#admin-email", "mw1789298700@gmail.com")
        page.fill("#admin-password", "SeekerSecret123!")
        page.click("button[type='submit']")
        page.wait_for_timeout(2500)

        if "/auth/mfa" in page.url:
            print("Entering MFA TOTP code...")
            totp = get_totp(SECRET)
            inputs = page.query_selector_all("input")
            if len(inputs) == 1:
                inputs[0].fill(totp)
            elif len(inputs) == 6:
                for idx, c in enumerate(totp):
                    inputs[idx].fill(c)
            submit_btn = page.query_selector("button[type='submit']")
            if submit_btn:
                submit_btn.click()
            page.wait_for_timeout(3000)

        print("Navigating to Admin Overview...")
        page.goto("http://localhost/admin")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3000)
        page.screenshot(path=str(OUT_DIR / "admin_overview_telemetry.png"))
        print("Saved admin_overview_telemetry.png")

        # 5. Admin Content & OKF Manager
        print("5. Admin Content & OKF Manager...")
        page.goto("http://localhost/admin/content")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3000)
        page.screenshot(path=str(OUT_DIR / "admin_content_teachings.png"))
        print("Saved admin_content_teachings.png")

        # 6. Admin Ingestion Pipeline
        print("6. Admin Ingestion Pipeline...")
        page.goto("http://localhost/admin/ingestion")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3000)
        page.screenshot(path=str(OUT_DIR / "admin_ingestion_pipeline.png"))
        print("Saved admin_ingestion_pipeline.png")

        # 7. Admin RAG Flow
        print("7. Admin RAG Flow...")
        page.goto("http://localhost/admin/rag-flow")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3000)
        page.screenshot(path=str(OUT_DIR / "admin_rag_flow.png"))
        print("Saved admin_rag_flow.png")

        # 8. Admin Evals
        print("8. Admin Evals...")
        page.goto("http://localhost/admin/evals")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3000)
        page.screenshot(path=str(OUT_DIR / "admin_evals_dashboard.png"))
        print("Saved admin_evals_dashboard.png")

        browser.close()
        print("All screenshots successfully captured!")

if __name__ == "__main__":
    capture_all()
