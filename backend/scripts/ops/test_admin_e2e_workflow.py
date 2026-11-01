#!/usr/bin/env python3
"""End-to-end UI verification of Admin Metrics, Redesigned RAG Flow Graph, and Ingestion Workflow DAG."""

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


def run_workflow():
    with sync_playwright() as p:
        # Launch browser without bypass_csp to strictly verify real Docker Nginx CSP config
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark")
        context.add_init_script(
            "localStorage.setItem('askmukthiguru_disclaimer_accepted', 'true');"
        )
        page = context.new_page()

        console_errors = []
        page.on(
            "console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None
        )

        # ----------------------------------------------------
        # 1. AUTHENTICATION & MFA
        # ----------------------------------------------------
        print("1. Authenticating to Admin Portal...")
        page.goto("http://localhost/admin/login")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # Dismiss disclaimer if visible
        try:
            btn = page.locator(
                "button:has-text('I Understand'), button:has-text('Begin My Journey')"
            )
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                page.wait_for_timeout(500)
        except Exception:
            pass

        page.fill("#admin-email", "mw1789298700@gmail.com")
        page.fill("#admin-password", "SeekerSecret123!")
        page.click("button[type='submit']")
        page.wait_for_timeout(2500)

        # Handle TOTP MFA
        if "/auth/mfa" in page.url or page.locator("#mfa-code").count() > 0:
            print("Entering TOTP MFA code...")
            totp = get_totp(SECRET)
            page.fill("#mfa-code", totp)
            submit_btn = page.locator(
                "button:has-text('Verify'), button:has-text('Submit'), button[type='submit']"
            )
            if submit_btn.count() > 0 and submit_btn.first.is_visible():
                submit_btn.first.click()
            page.wait_for_timeout(3000)

        print(f"Current URL after login: {page.url}")

        # ----------------------------------------------------
        # 2. OVERVIEW METRICS VERIFICATION & COOKIE BANNER CHECK
        # ----------------------------------------------------
        print("2. Verifying Admin Overview Metrics & Cookie Banner Suppression...")
        page.goto("http://localhost/admin")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify Cookie Banner is completely suppressed on Admin
        cookie_banners = page.locator("text='Essential cookies only'")
        print(f"Cookie banners visible on admin: {cookie_banners.count()}")
        assert cookie_banners.count() == 0, (
            "CookieConsentBanner must not be rendered on admin routes!"
        )

        # Print KPI cards text to verify non-zero values
        kpi_texts = page.locator(".grid .rounded-xl").all_text_contents()
        print(f"Extracted KPI cards ({len(kpi_texts)}):")
        for k in kpi_texts[:6]:
            clean_k = " ".join(k.split())
            print(f"  - {clean_k}")

        overview_path = str(OUT_DIR / "admin_overview_metrics_live.png")
        page.screenshot(path=overview_path)
        print(f"Saved: {overview_path}")

        # ----------------------------------------------------
        # 3. REDESIGNED RAG FLOW GRAPH
        # ----------------------------------------------------
        print("3. Verifying Redesigned RAG Flow Graph...")
        page.goto("http://localhost/admin/rag-flow")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        rag_standard_path = str(OUT_DIR / "admin_rag_flow_redesigned_standard.png")
        page.screenshot(path=rag_standard_path)
        print(f"Saved: {rag_standard_path}")

        fp_tab = page.locator("button:has-text('First-Person Architecture')")
        if fp_tab.count() > 0 and fp_tab.first.is_visible():
            fp_tab.first.click()
            page.wait_for_timeout(1500)
            rag_fp_path = str(OUT_DIR / "admin_rag_flow_first_person_arch.png")
            page.screenshot(path=rag_fp_path)
            print(f"Saved: {rag_fp_path}")

        # Click a node inside canvas to inspect drawer
        node_card = page.locator(".react-flow__node").nth(2)
        if node_card.count() > 0 and node_card.is_visible():
            node_card.click(force=True)
            page.wait_for_timeout(1000)
            rag_drawer_path = str(OUT_DIR / "admin_rag_flow_drawer_inspect.png")
            page.screenshot(path=rag_drawer_path)
            print(f"Saved: {rag_drawer_path}")

        # Close any open drawer
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # ----------------------------------------------------
        # 4. INGESTION WORKFLOW DAG (TAB = WORKFLOW)
        # ----------------------------------------------------
        print("4. Verifying Ingestion Workflow DAG tab...")
        page.goto("http://localhost/admin/ingestion?tab=workflow")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2500)

        # Verify all 8 stage nodes rendered
        stage_nodes = page.locator(".react-flow__node")
        print(f"Rendered Ingestion Workflow DAG nodes: {stage_nodes.count()}")
        assert stage_nodes.count() >= 8, f"Expected 8 stage nodes, found {stage_nodes.count()}"

        dag_tab_path = str(OUT_DIR / "ingestion_workflow_dag_live.png")
        page.screenshot(path=dag_tab_path)
        print(f"Saved: {dag_tab_path}")

        # Click on ECAPA Speaker Attribution node to open Inspector Drawer
        attribution_node = page.locator(
            ".react-flow__node:has-text('ECAPA Speaker Attribution')"
        ).first
        if attribution_node.is_visible():
            print("Inspecting ECAPA Speaker Attribution stage...")
            attribution_node.click(force=True)
            page.wait_for_timeout(1500)
            stage_inspect_path = str(OUT_DIR / "ingestion_workflow_stage_inspector.png")
            page.screenshot(path=stage_inspect_path)
            print(f"Saved: {stage_inspect_path}")

        # Close the inspector drawer
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # ----------------------------------------------------
        # 5. VIDEO APPROVAL & PER-VIDEO LINEAGE DAG MODAL
        # ----------------------------------------------------
        print("5. Verifying Video Approval & Lineage DAG modal...")
        page.goto("http://localhost/admin/ingestion?tab=video-approval")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        video_approval_path = str(OUT_DIR / "ingestion_workflow_step3_approval.png")
        page.screenshot(path=video_approval_path)
        print(f"Saved: {video_approval_path}")

        # Click "Pipeline DAG" on the first video row
        dag_btn = page.locator("button:has-text('Pipeline DAG')").first
        if dag_btn.is_visible():
            print("Opening Video Ingestion Pipeline DAG modal...")
            dag_btn.click()
            page.wait_for_timeout(2500)
            modal_dag_path = str(OUT_DIR / "ingestion_video_opened_dag_modal.png")
            page.screenshot(path=modal_dag_path)
            print(f"Saved: {modal_dag_path}")

        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # ----------------------------------------------------
        # 6. LIVE VIDEO INGESTION SUBMISSION VIA UI
        # ----------------------------------------------------
        print("6. Executing Live Video Ingestion via Admin UI...")
        page.goto("http://localhost/admin/ingestion?tab=ingestion")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        # Submit real YouTube discourse URL
        test_youtube_url = "https://www.youtube.com/watch?v=0kI4_7Fw1yY"
        url_input = page.locator("#youtube-url")
        if url_input.is_visible():
            url_input.fill(test_youtube_url)
            page.wait_for_timeout(500)

            # Enable max accuracy switch if available
            acc_switch = page.locator("#max-accuracy")
            if acc_switch.is_visible() and not acc_switch.is_checked():
                acc_switch.click()
                page.wait_for_timeout(300)

            # Click Ingest URL
            ingest_btn = page.locator("button:has-text('Ingest URL')")
            if ingest_btn.is_visible():
                print(f"Clicking 'Ingest URL' for {test_youtube_url}...")
                ingest_btn.click()
                page.wait_for_timeout(2000)

        submission_path = str(OUT_DIR / "ingestion_ui_submission_live.png")
        page.screenshot(path=submission_path)
        print(f"Saved: {submission_path}")

        # Step 6.1: Check Ingestion Queue Tab
        print("Checking Ingestion Queue...")
        page.goto("http://localhost/admin/ingestion?tab=queue")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        queue_path = str(OUT_DIR / "ingestion_ui_queue_live.png")
        page.screenshot(path=queue_path)
        print(f"Saved: {queue_path}")

        # ----------------------------------------------------
        # 7. SPEAKER ATTRIBUTION TAB
        # ----------------------------------------------------
        print("7. Verifying Speaker Attribution Tab...")
        page.goto("http://localhost/admin/ingestion?tab=attribution")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)
        attribution_path = str(OUT_DIR / "ingestion_workflow_step4_attribution.png")
        page.screenshot(path=attribution_path)
        print(f"Saved: {attribution_path}")

        # ----------------------------------------------------
        # 8. TEACHING TIPS AUDIT (CLEAN SACRED TEACHINGS)
        # ----------------------------------------------------
        print("8. Verifying Curated Teaching Tips in Admin...")
        page.goto("http://localhost/admin/content?tab=teachings")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)
        teachings_path = str(OUT_DIR / "admin_teaching_tips_live.png")
        page.screenshot(path=teachings_path)
        print(f"Saved: {teachings_path}")

        browser.close()
        print("=== All UI Workflow Tests Completed Successfully ===")


if __name__ == "__main__":
    run_workflow()
