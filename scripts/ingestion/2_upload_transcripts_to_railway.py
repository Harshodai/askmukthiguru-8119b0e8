#!/usr/bin/env python3
"""
Mukthi Guru — Phase 2: Upload Local Transcripts to Railway
==============================================================
Reads every .md transcript file written by Phase 1
(1_fetch_transcripts_local.py) — or by scripts/ingestion/extract_transcripts.py,
same output format — and forwards each one to the Railway backend's
POST /api/ingest/raw-text, which runs the rest of the pipeline there: chunk,
embed, Qdrant, RAPTOR, LightRAG, OKF.

Setup:
  1. Run Phase 1 first (or extract_transcripts.py) so .md files exist in
     scripts/ingestion/transcripts/.
  2. Get your admin access token: log into askmukthiguru.lovable.app as
     admin, open browser DevTools -> Application -> Local Storage ->
     the "sb-<project-ref>-auth-token" key -> copy the "access_token" field
     out of that JSON value. Tokens expire in ~1h — this phase is fast
     (network POSTs, not scraping), so one token is normally enough for a
     full run; re-export and re-run (resumable) if it isn't.
  3. export MUKTHI_ADMIN_TOKEN="<paste it here>"

Run:
  python3 scripts/ingestion/2_upload_transcripts_to_railway.py              # all fetched .md files
  python3 scripts/ingestion/2_upload_transcripts_to_railway.py --limit 3    # first 3, for testing

State (resumable): scripts/ingestion/upload_state.json tracks which video
IDs were already forwarded, so re-running only sends the new/failed ones.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import httpx
except ImportError:
    print("Missing dependency: pip install -r scripts/ingestion/requirements-local-fetch.txt")
    sys.exit(1)

TRANSCRIPTS_DIR = Path(os.environ.get("MUKTHI_TRANSCRIPTS_DIR", str(Path(__file__).resolve().parent / "transcripts")))
CORPUS_DIR = Path(os.environ.get("MUKTHI_CORPUS_DIR", str(Path(__file__).resolve().parent / "corpus")))
STATE_DIR = Path(os.environ.get("MUKTHI_STATE_DIR", str(Path(__file__).resolve().parent)))
STATE_FILE = STATE_DIR / "upload_state.json"
RECONCILIATION_LEDGER_FILE = STATE_DIR / "reconciliation_ledger.json"
API_BASE = os.environ.get("MUKTHI_API_BASE", "https://api.askmukthiguru.com").rstrip("/")
ADMIN_TOKEN = os.environ.get("MUKTHI_ADMIN_TOKEN", "")

_FIELD_RE = re.compile(r"^\*\*([^:]+):\*\*\s*(.+)$")


def parse_transcript_item(path_or_dir: Path) -> Optional[dict]:
    """Parses transcript item from either a .md projection or a corpus directory."""
    if path_or_dir.is_dir():
        # Read from corpus directory
        q_file = path_or_dir / "quality_report.json"
        t_file = path_or_dir / "transcript.md"
        m_file = path_or_dir / "manifest.json"
        if not (q_file.exists() and t_file.exists()):
            return None
        try:
            q_data = json.loads(q_file.read_text())
            m_data = json.loads(m_file.read_text()) if m_file.exists() else {}
        except Exception:
            return None

        # Filter strictly for trusted / trusted_after_review
        quality_state = q_data.get("quality_state", "needs_review")
        if quality_state not in ["trusted", "trusted_after_review"]:
            return None

        return parse_transcript_md(t_file)
    else:
        return parse_transcript_md(path_or_dir)


def parse_transcript_md(path: Path) -> Optional[dict]:
    """Parses the `# Title` / `**Field:** value` / `## Transcript` format."""
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  [warn] Could not read {path}: {e}")
        return None

    lines = raw.splitlines()
    title = ""
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
            break

    fields: dict[str, str] = {}
    for line in lines:
        m = _FIELD_RE.match(line.strip())
        if m:
            fields[m.group(1).strip().lower()] = m.group(2).strip()

    video_id = fields.get("video id", "").strip("`") or path.stem
    url = fields.get("url", "") or f"https://www.youtube.com/watch?v={video_id}"
    speaker = fields.get("speaker", "Sri Preethaji & Sri Krishnaji")
    quality_state = fields.get("quality state", "trusted")
    pipeline_version = fields.get("pipeline version", "2.0.0")
    artifact_manifest_hash = fields.get("artifact manifest hash", "").strip("`")
    transcript_hash = fields.get("transcript hash", "").strip("`")

    # Hard gate: Reject untrusted quality states
    if quality_state not in ["trusted", "trusted_after_review"]:
        return None

    marker = "## Transcript"
    idx = raw.find(marker)
    if idx == -1:
        return None
    text = raw[idx + len(marker):].strip()
    if not text or text == "_No transcript available._":
        return None

    # Compute idempotency key
    import hashlib
    canonical_payload = json.dumps({
        "pipeline_version": pipeline_version,
        "transcript_hash": transcript_hash,
        "video_id": video_id,
    }, sort_keys=True)
    idempotency_key = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()

    return {
        "video_id": video_id,
        "url": url,
        "title": title or video_id,
        "speaker": speaker,
        "text": text,
        "quality_state": quality_state,
        "pipeline_version": pipeline_version,
        "artifact_manifest_hash": artifact_manifest_hash,
        "transcript_hash": transcript_hash,
        "idempotency_key": idempotency_key,
    }


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"done": {}, "failed": {}}


def save_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_FILE)


def load_reconciliation_ledger() -> list[dict]:
    if RECONCILIATION_LEDGER_FILE.exists():
        try:
            return json.loads(RECONCILIATION_LEDGER_FILE.read_text())
        except Exception:
            pass
    return []


def save_reconciliation_record(record: dict) -> None:
    ledger = load_reconciliation_ledger()
    ledger.append(record)
    tmp = RECONCILIATION_LEDGER_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(ledger, indent=2))
    tmp.replace(RECONCILIATION_LEDGER_FILE)


def poll_job_status(
    client: httpx.Client,
    job_id: str,
    api_base: str = API_BASE,
    admin_token: str = ADMIN_TOKEN,
    max_timeout_s: float = 600.0,
) -> tuple[str, dict]:
    """Bounded exponential polling of Celery ingestion job status.

    Returns:
        (terminal_state, last_status_response)
    """
    start_t = time.time()
    interval = 2.0
    backoff_factor = 1.5
    max_interval = 30.0

    while time.time() - start_t < max_timeout_s:
        try:
            resp = client.get(
                f"{api_base}/api/ingest/status/{job_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
                timeout=15.0,
            )
            if resp.status_code in (401, 403):
                return "auth_failed", {"error": "unauthorized"}
            if resp.status_code == 200:
                data = resp.json()
                celery_state = (data.get("status") or "").upper()
                if celery_state in ["SUCCESS", "COMPLETED"]:
                    return "success", data
                elif celery_state in ["FAILURE", "FAILED", "REVOKED"]:
                    return "failure", data
                # PENDING or STARTED: continue polling
        except Exception as e:
            # Network blip — continue polling
            pass

        time.sleep(interval)
        interval = min(max_interval, interval * backoff_factor)

    return "timeout", {"error": f"Polling timed out after {max_timeout_s}s"}


def forward_to_railway(
    client: httpx.Client,
    item: dict,
    api_base: str = API_BASE,
    admin_token: str = ADMIN_TOKEN,
) -> dict:
    resp = client.post(
        f"{api_base}/api/ingest/raw-text",
        json={
            "text": item["text"],
            "source_url": item["url"],
            "title": item["title"],
            "speaker": item.get("speaker", "Sri Preethaji & Sri Krishnaji"),
            "tags": ["general"],
            "max_accuracy": True,
            "quality_state": item.get("quality_state", "trusted"),
            "transcript_hash": item.get("transcript_hash"),
            "artifact_manifest_hash": item.get("artifact_manifest_hash"),
            "pipeline_version": item.get("pipeline_version", "2.0.0"),
            "idempotency_key": item.get("idempotency_key"),
        },
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=45,
    )
    resp.raise_for_status()
    return resp.json()


def upload_batch_to_railway(
    items_to_upload: list[Path],
    api_base: str = API_BASE,
    admin_token: str = ADMIN_TOKEN,
    delay: float = 0.5,
    poll_completion: bool = True,
) -> tuple[int, int, int, bool]:
    """Upload a batch of trusted transcripts with idempotency and reconciliation polling."""
    state = load_state()
    ok_count = 0
    fail_count = 0
    skip_count = 0
    token_expired = False

    with httpx.Client() as client:
        for i, path in enumerate(items_to_upload):
            item = parse_transcript_item(path)
            if not item:
                print(f"[{i + 1}/{len(items_to_upload)}] [skip] {path.name}: untrusted or unparseable")
                skip_count += 1
                continue

            video_id = item["video_id"]
            if video_id in state["done"]:
                print(f"[{i + 1}/{len(items_to_upload)}] [skip] {video_id} already uploaded")
                skip_count += 1
                continue

            print(f"[{i + 1}/{len(items_to_upload)}] Uploading {item['title']} (Speaker: {item.get('speaker')})")
            max_retries = 3
            uploaded = False
            for attempt in range(max_retries):
                try:
                    result = forward_to_railway(client, item, api_base, admin_token)
                    job_id = result.get("job_id")

                    if result.get("status") == "already_processed":
                        print(f"  [idempotent] {video_id} already ingested in knowledge store (job {job_id})")
                        state["done"][video_id] = {"job_id": job_id, "file": path.name, "idempotent": True}
                        uploaded = True
                        ok_count += 1
                        break

                    print(f"  [submitted] {video_id} -> job {job_id}")

                    # Bounded Polling for Terminal State
                    terminal_state = "submitted"
                    if poll_completion and job_id:
                        print(f"  [polling]   Waiting for job {job_id} to finish...")
                        terminal_state, status_resp = poll_job_status(client, job_id, api_base, admin_token)
                        print(f"  [status]    {video_id} -> {terminal_state.upper()}")

                    save_reconciliation_record({
                        "video_id": video_id,
                        "job_id": job_id,
                        "idempotency_key": item.get("idempotency_key"),
                        "terminal_state": terminal_state,
                        "uploaded_at": time.time(),
                    })

                    if terminal_state in ["success", "submitted"]:
                        state["done"][video_id] = {"job_id": job_id, "file": path.name, "terminal_state": terminal_state}
                        state["failed"].pop(video_id, None)
                        ok_count += 1
                        uploaded = True
                        break
                    else:
                        state["failed"][video_id] = f"Job {job_id} terminal state: {terminal_state}"
                        break

                except httpx.HTTPStatusError as e:
                    if e.response.status_code in (401, 403):
                        print(f"  [auth error] Token invalid or expired (HTTP {e.response.status_code})")
                        token_expired = True
                        return ok_count, fail_count, skip_count, token_expired
                    elif e.response.status_code == 429:
                        wait = 2 ** (attempt + 1)
                        print(f"  [rate limit] 429 received, backing off {wait}s...")
                        time.sleep(wait)
                    else:
                        print(f"  [fail] HTTP error {e.response.status_code} for {video_id}: {e}")
                        state["failed"][video_id] = f"HTTP_{e.response.status_code}: {e}"
                        break
                except Exception as e:
                    if attempt < max_retries - 1:
                        time.sleep(1.0)
                    else:
                        print(f"  [fail] {video_id}: {e}")
                        state["failed"][video_id] = str(e)

            if not uploaded and not token_expired and video_id not in state["done"]:
                fail_count += 1

            save_state(state)

            if i < len(items_to_upload) - 1:
                time.sleep(delay)

    return ok_count, fail_count, skip_count, token_expired


def main() -> None:
    # Ponytail: self-check when invoked with --self-check
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        print("Running Ponytail self-check on uploader...")
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(
                "# Test Title\n\n"
                "**Video ID:** `test_123`\n"
                "**Speaker:** Sri Preethaji\n"
                "**Quality State:** trusted\n"
                "**Pipeline Version:** 2.0.0\n"
                "**Transcript Hash:** `abc123hash`\n\n"
                "## Transcript\n\n"
                "This is a sample test transcript."
            )
            tmp_name = f.name
        try:
            parsed = parse_transcript_md(Path(tmp_name))
            assert parsed is not None
            assert parsed["video_id"] == "test_123"
            assert parsed["speaker"] == "Sri Preethaji"
            assert parsed["quality_state"] == "trusted"
            assert parsed["idempotency_key"] is not None
            print("✅ Ponytail uploader self-check passed!")
        finally:
            Path(tmp_name).unlink(missing_ok=True)
        sys.exit(0)

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=None, help="Max files to upload (for testing)")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between uploads (default 0.5)")
    parser.add_argument("--api-base", default=API_BASE, help=f"Railway API base (default {API_BASE})")
    parser.add_argument("--no-poll", action="store_true", help="Submit asynchronously without polling for terminal completion")
    args = parser.parse_args()

    token = os.environ.get("MUKTHI_ADMIN_TOKEN", ADMIN_TOKEN).strip()
    if not token:
        print("ERROR: MUKTHI_ADMIN_TOKEN not set. Export it first:")
        print("  export MUKTHI_ADMIN_TOKEN='<your_token>'")
        sys.exit(1)

    if not TRANSCRIPTS_DIR.exists():
        print(f"ERROR: {TRANSCRIPTS_DIR} doesn't exist. Run Phase 1 first.")
        sys.exit(1)

    md_files = sorted(TRANSCRIPTS_DIR.glob("*.md"))
    if args.limit:
        md_files = md_files[: args.limit]

    print(f"\nUploading {len(md_files)} trusted transcript(s) -> {args.api_base}/api/ingest/raw-text\n")
    ok_c, fail_c, skip_c, expired = upload_batch_to_railway(
        md_files, api_base=args.api_base, admin_token=token, delay=args.delay, poll_completion=not args.no_poll
    )

    if expired:
        print("\n⚠️  Token expired or unauthorized. Please re-export MUKTHI_ADMIN_TOKEN and run again to resume.")
        sys.exit(2)

    print(f"\nDone. {ok_c} uploaded, {fail_c} failed, {skip_c} skipped this run.")
    print(f"State file: {STATE_FILE}")
    print(f"Reconciliation ledger: {RECONCILIATION_LEDGER_FILE}")


if __name__ == "__main__":
    main()
