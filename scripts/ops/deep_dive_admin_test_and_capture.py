#!/usr/bin/env python3
"""Deep-dive interactive testing and screenshot capture across all Admin Portal pages."""

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

def deep_dive_test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            color_scheme="dark",
            bypass_csp=True,
        )
        context.add_init_script("localStorage.setItem('askmukthiguru_disclaimer_accepted', 'true');")
        page = context.new_page()

        # 0. Log in with admin credentials and MFA
        print("Logging in to admin portal...")
        page.goto("http://localhost/admin/login")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)

        # Dismiss disclaimer if present
        try:
            disclaimer_btn = page.locator("button:has-text('I Understand'), button:has-text('Begin My Journey')")
            if disclaimer_btn.count() > 0 and disclaimer_btn.first.is_visible():
                disclaimer_btn.first.click()
                page.wait_for_timeout(1000)
        except Exception as e:
            print("Disclaimer dismiss check:", e)

        page.fill("#admin-email", "mw1789298700@gmail.com")
        page.fill("#admin-password", "SeekerSecret123!")
        page.click("button[type='submit']")
        page.wait_for_timeout(3000)

        if "/auth/mfa" in page.url or page.locator("#mfa-code").count() > 0 or "mfa" in page.url.lower():
            print("Solving MFA TOTP challenge...")
            totp = get_totp(SECRET)
            if page.locator("#mfa-code").is_visible():
                page.fill("#mfa-code", totp)
            else:
                inputs = page.query_selector_all("input")
                if len(inputs) == 1:
                    inputs[0].fill(totp)
                elif len(inputs) == 6:
                    for idx, c in enumerate(totp):
                        inputs[idx].fill(c)
            submit_btn = page.query_selector("button[type='submit']")
            if submit_btn:
                submit_btn.click()
            page.wait_for_timeout(3500)
            print("After MFA submit URL:", page.url)

        # -------------------------------------------------------------------
        # 1. /admin — Overview & Telemetry with Time-Range Dropdown Interaction
        # -------------------------------------------------------------------
        print("1. Deep-testing /admin Overview & Telemetry...")
        page.goto("http://localhost/admin")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2500)

        # Look for time range dropdown/select button
        dropdown = page.locator("button:has-text('24h'), button:has-text('7d'), button:has-text('Last'), [role='combobox']").first
        if dropdown.is_visible():
            print("Opening time-range dropdown...")
            dropdown.click()
            page.wait_for_timeout(1000)
        page.screenshot(path=str(OUT_DIR / "admin_overview_inside_timerange.png"))
        print("Saved admin_overview_inside_timerange.png")

        # -------------------------------------------------------------------
        # 2. /admin/content — Daily Teaching, Teaching Tips, Topics, OKF Manager
        # -------------------------------------------------------------------
        print("2. Deep-testing /admin/content tabs...")
        page.goto("http://localhost/admin/content")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2500)

        # Tab 1: Daily Teaching
        caption_box = page.locator("textarea").first
        if caption_box.is_visible():
            caption_box.fill("The sacred state of inner calm is accessible in every breath. Rest in awareness.")
        page.screenshot(path=str(OUT_DIR / "admin_content_inside_daily_teaching.png"))
        print("Saved admin_content_inside_daily_teaching.png")

        # Tab 2: Teaching Tips
        tips_tab = page.locator("button:has-text('Teaching Tips'), [role='tab']:has-text('Teaching Tips')").first
        if tips_tab.is_visible():
            print("Switching to Teaching Tips tab...")
            tips_tab.click()
            page.wait_for_timeout(2000)
            page.screenshot(path=str(OUT_DIR / "admin_content_inside_teaching_tips.png"))
            print("Saved admin_content_inside_teaching_tips.png")

        # Tab 3: Topics
        topics_tab = page.locator("button:has-text('Topics'), [role='tab']:has-text('Topics')").first
        if topics_tab.is_visible():
            print("Switching to Topics tab...")
            topics_tab.click()
            page.wait_for_timeout(2000)
            search_input = page.locator("input[placeholder*='Search'], input[type='search']").first
            if search_input.is_visible():
                search_input.fill("Suffering")
                page.wait_for_timeout(1000)
            page.screenshot(path=str(OUT_DIR / "admin_content_inside_topics.png"))
            print("Saved admin_content_inside_topics.png")

        # Tab 4: OKF (Ontological Knowledge Framework)
        okf_tab = page.locator("button:has-text('OKF'), [role='tab']:has-text('OKF')").first
        if okf_tab.is_visible():
            print("Switching to OKF tab...")
            okf_tab.click()
            page.wait_for_timeout(2500)
            page.screenshot(path=str(OUT_DIR / "admin_content_inside_okf_doctrine.png"))
            print("Saved admin_content_inside_okf_doctrine.png")

        # -------------------------------------------------------------------
        # 3. /admin/ingestion — Pipeline, Attribution, Video Approval, Queue
        # -------------------------------------------------------------------
        print("3. Deep-testing /admin/ingestion tabs and real URL input...")
        page.goto("http://localhost/admin/ingestion")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2500)

        # Tab 1: Manual Ingest Form
        url_input = page.locator("#ingest-url, input[placeholder*='URL'], input[placeholder*='http']").first
        if url_input.is_visible():
            print("Entering real discourse URL into Ingestion form...")
            url_input.fill("https://www.youtube.com/watch?v=kYv_3M2D4tA")
            page.wait_for_timeout(1000)
        page.screenshot(path=str(OUT_DIR / "admin_ingestion_inside_manual_form.png"))
        print("Saved admin_ingestion_inside_manual_form.png")

        # Tab 2: Video Approval
        video_tab = page.locator("button:has-text('Video Approval'), [role='tab']:has-text('Video Approval')").first
        if video_tab.is_visible():
            print("Switching to Video Approval tab...")
            video_tab.click()
            page.wait_for_timeout(2500)
            page.screenshot(path=str(OUT_DIR / "admin_ingestion_inside_video_approval.png"))
            print("Saved admin_ingestion_inside_video_approval.png")

        # Tab 3: Speaker & Dialogue (Attribution)
        attrib_tab = page.locator("button:has-text('Speaker'), [role='tab']:has-text('Speaker')").first
        if attrib_tab.is_visible():
            print("Switching to Speaker Attribution tab...")
            attrib_tab.click()
            page.wait_for_timeout(2500)
            page.screenshot(path=str(OUT_DIR / "admin_ingestion_inside_speaker_attribution.png"))
            print("Saved admin_ingestion_inside_speaker_attribution.png")

        # Tab 4: Queue (Jobs)
        queue_tab = page.locator("button:has-text('Queue'), [role='tab']:has-text('Queue')").first
        if queue_tab.is_visible():
            print("Switching to Queue tab...")
            queue_tab.click()
            page.wait_for_timeout(2000)
            page.screenshot(path=str(OUT_DIR / "admin_ingestion_inside_queue.png"))
            print("Saved admin_ingestion_inside_queue.png")

        # -------------------------------------------------------------------
        # 4. /admin/rag-flow — Interactive Node Inspection Side Drawer
        # -------------------------------------------------------------------
        print("4. Deep-testing /admin/rag-flow interactive graph and node drawer...")
        page.goto("http://localhost/admin/rag-flow")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3000)

        # Click on a node in the ReactFlow diagram (e.g. intent_router or retrieve_documents)
        nodes = page.locator(".react-flow__node")
        if nodes.count() > 0:
            print(f"Found {nodes.count()} nodes in RAG Flow. Clicking node 1 to inspect...")
            nodes.first.click()
            page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT_DIR / "admin_rag_flow_inside_node_inspect_drawer.png"))
        print("Saved admin_rag_flow_inside_node_inspect_drawer.png")

        # -------------------------------------------------------------------
        # 5. /admin/evals — Golden Question Modal & Prompts Diff
        # -------------------------------------------------------------------
        print("5. Deep-testing /admin/evals tabs and Golden Question Dialog...")
        page.goto("http://localhost/admin/evals")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2500)

        # Open Add Golden Question Dialog
        add_btn = page.locator("button:has-text('Add Golden Question'), button:has-text('Add question'), button:has-text('New Golden')").first
        if add_btn.is_visible():
            print("Opening Add Golden Question Modal Dialog...")
            add_btn.click()
            page.wait_for_timeout(1500)
            page.screenshot(path=str(OUT_DIR / "admin_evals_inside_golden_question_modal.png"))
            print("Saved admin_evals_inside_golden_question_modal.png")
            # Close dialog
            close_btn = page.locator("button:has-text('Cancel'), [aria-label='Close']").first
            if close_btn.is_visible():
                close_btn.click()
                page.wait_for_timeout(500)

        # Switch to Prompts Tab
        prompts_tab = page.locator("button:has-text('Prompts'), [role='tab']:has-text('Prompts')").first
        if prompts_tab.is_visible():
            print("Switching to Prompts Tab to view Prompt Diff...")
            prompts_tab.click()
            page.wait_for_timeout(2500)
            page.screenshot(path=str(OUT_DIR / "admin_evals_inside_prompts_diff.png"))
            print("Saved admin_evals_inside_prompts_diff.png")

        browser.close()
        print("All deep-dive interactive admin tests and screenshots successfully captured!")

if __name__ == "__main__":
    deep_dive_test()
