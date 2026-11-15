#!/usr/bin/env python3
"""AskMukthiGuru — OpenRouter API Key UI & Setup Server.

Provides a clean, secure local UI to input, validate, and replace
OPENROUTER_API_KEY in backend/.env without exposing keys to agent context.

Usage:
    python3 scripts/ops/update_openrouter_key_ui.py [--port 8765] [--open]
    python3 scripts/ops/update_openrouter_key_ui.py --native-dialog
    python3 scripts/ops/update_openrouter_key_ui.py --cli
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

# Locate repo root and backend directory
_HERE = Path(__file__).resolve()
if (_HERE.parents[2] / "backend").is_dir():
    REPO_ROOT = _HERE.parents[2]
elif (_HERE.parents[1] / "backend").is_dir():
    REPO_ROOT = _HERE.parents[1]
else:
    REPO_ROOT = Path.cwd()

BACKEND_DIR = REPO_ROOT / "backend"
BACKEND_ENV = BACKEND_DIR / ".env"
ROOT_ENV = REPO_ROOT / ".env"


def mask_key(key: str) -> str:
    """Mask key preserving prefix and suffix for identification."""
    k = key.strip()
    if not k:
        return "(empty)"
    if len(k) <= 12:
        return k[:3] + "..." + k[-2:]
    return k[:8] + "..." + k[-4:]


def read_current_key() -> str:
    """Read current OPENROUTER_API_KEY from backend/.env."""
    if not BACKEND_ENV.is_file():
        return ""
    for line in BACKEND_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("OPENROUTER_API_KEY=") and not line.startswith("#"):
            return line.split("=", 1)[1].strip()
    return ""


def test_openrouter_key(api_key: str) -> tuple[bool, str, dict[str, Any]]:
    """Test API key directly against OpenRouter /api/v1/auth/key."""
    key = api_key.strip()
    if not key:
        return False, "Key cannot be empty.", {}

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/auth/key",
        headers={
            "Authorization": f"Bearer {key}",
            "HTTP-Referer": "https://askmukthiguru.local",
            "X-Title": "AskMukthiGuru Key Setup",
            "User-Agent": "AskMukthiGuru-KeySetup/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return True, "Key is active and authenticated with OpenRouter.", data.get("data", {})
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
            err_data = json.loads(body)
            msg = err_data.get("error", {}).get("message", body)
        except Exception:
            msg = body or str(e)
        return False, f"OpenRouter returned HTTP {e.code}: {msg}", {}
    except Exception as e:
        return False, f"Connection error: {e}", {}


def update_env_file(target_file: Path, new_key: str) -> bool:
    """Safely replace OPENROUTER_API_KEY in a .env file with backup."""
    if not target_file.is_file():
        return False

    raw = target_file.read_text(encoding="utf-8")
    lines = raw.splitlines()

    # Create timestamped backup
    ts = int(time.time())
    backup_path = target_file.with_name(f"{target_file.name}.bak.{ts}")
    backup_path.write_text(raw, encoding="utf-8")

    updated = False
    new_lines = []
    for line in lines:
        if line.strip().startswith("OPENROUTER_API_KEY=") and not line.strip().startswith("#"):
            new_lines.append(f"OPENROUTER_API_KEY={new_key}")
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(f"OPENROUTER_API_KEY={new_key}")

    target_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return True


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AskMukthiGuru — OpenRouter Key Setup</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body { background-color: #0b0f19; color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  </style>
</head>
<body class="min-h-screen flex items-center justify-center p-4">
  <div class="max-w-xl w-full bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6 sm:p-8 space-y-6">
    <div class="space-y-2 border-b border-slate-800 pb-4">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 font-bold text-xl">
          अ
        </div>
        <div>
          <h1 class="text-xl font-bold tracking-tight text-slate-100">OpenRouter API Key Setup</h1>
          <p class="text-xs text-slate-400">AskMukthiGuru Attribution & Evaluation Pipeline</p>
        </div>
      </div>
    </div>

    <!-- Current Key Status -->
    <div id="current-status-box" class="p-4 rounded-xl bg-slate-800/50 border border-slate-700/50 space-y-2">
      <div class="flex items-center justify-between text-xs font-medium">
        <span class="text-slate-400">Current Key in backend/.env:</span>
        <span id="current-key-display" class="font-mono text-slate-200">Loading...</span>
      </div>
      <div id="status-badge" class="text-xs flex items-center gap-2 text-slate-400">
        <span class="inline-block w-2 h-2 rounded-full bg-slate-500"></span> Checking status...
      </div>
    </div>

    <!-- Key Input Form -->
    <div class="space-y-4">
      <div>
        <label for="api-key" class="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
          New OpenRouter API Key
        </label>
        <div class="relative">
          <input
            id="api-key"
            type="password"
            placeholder="sk-or-v1-..."
            autocomplete="off"
            spellcheck="false"
            class="w-full px-4 py-3 bg-slate-950 border border-slate-700 rounded-xl text-sm font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition pr-24"
          />
          <div class="absolute right-2 top-2 flex items-center gap-1">
            <button
              id="btn-toggle-show"
              type="button"
              class="px-2.5 py-1.5 text-xs text-slate-400 hover:text-slate-200 bg-slate-800/80 rounded-lg hover:bg-slate-700 transition"
            >
              Show
            </button>
            <button
              id="btn-paste"
              type="button"
              class="px-2.5 py-1.5 text-xs text-amber-400 hover:text-amber-300 bg-amber-500/10 rounded-lg hover:bg-amber-500/20 transition"
            >
              Paste
            </button>
          </div>
        </div>
        <p class="text-[11px] text-slate-400 mt-1.5">
          Format: starts with <code class="text-amber-400">sk-or-v1-</code>. Key is validated live before writing to <code class="text-slate-300">backend/.env</code>.
        </p>
      </div>

      <!-- Result Alert Banner -->
      <div id="result-alert" class="hidden p-4 rounded-xl text-xs space-y-1"></div>

      <!-- Action Buttons -->
      <div class="flex items-center gap-3 pt-2">
        <button
          id="btn-save"
          type="button"
          class="flex-1 py-3 px-4 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-sm rounded-xl transition shadow-lg shadow-amber-500/10 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <span id="save-spinner" class="hidden animate-spin rounded-full h-4 w-4 border-2 border-slate-950 border-t-transparent"></span>
          <span id="save-btn-text">Validate & Save to backend/.env</span>
        </button>
      </div>
    </div>

    <!-- Post-Save Actions (Revealed upon success) -->
    <div id="post-save-actions" class="hidden border-t border-slate-800 pt-4 space-y-3">
      <h3 class="text-xs font-semibold text-slate-300 uppercase tracking-wider">Next Step: Restart Stack</h3>
      <p class="text-xs text-slate-400">Recreate the Docker backend container with the updated credentials and flush caches:</p>
      <button
        id="btn-recreate"
        type="button"
        class="w-full py-2.5 px-4 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs rounded-xl transition flex items-center justify-center gap-2"
      >
        <span id="recreate-spinner" class="hidden animate-spin rounded-full h-3 w-3 border-2 border-white border-t-transparent"></span>
        <span id="recreate-btn-text">Recreate Backend Container & Flush Caches</span>
      </button>
      <pre id="recreate-output" class="hidden p-3 bg-slate-950 rounded-lg text-[11px] font-mono text-slate-300 max-h-40 overflow-y-auto whitespace-pre-wrap"></pre>
    </div>
  </div>

  <script>
    const apiKeyInput = document.getElementById('api-key');
    const btnToggleShow = document.getElementById('btn-toggle-show');
    const btnPaste = document.getElementById('btn-paste');
    const btnSave = document.getElementById('btn-save');
    const saveSpinner = document.getElementById('save-spinner');
    const saveBtnText = document.getElementById('save-btn-text');
    const resultAlert = document.getElementById('result-alert');
    const currentKeyDisplay = document.getElementById('current-key-display');
    const statusBadge = document.getElementById('status-badge');
    const postSaveActions = document.getElementById('post-save-actions');
    const btnRecreate = document.getElementById('btn-recreate');
    const recreateSpinner = document.getElementById('recreate-spinner');
    const recreateBtnText = document.getElementById('recreate-btn-text');
    const recreateOutput = document.getElementById('recreate-output');

    // Toggle password visibility
    btnToggleShow.addEventListener('click', () => {
      const isPassword = apiKeyInput.type === 'password';
      apiKeyInput.type = isPassword ? 'text' : 'password';
      btnToggleShow.textContent = isPassword ? 'Hide' : 'Show';
    });

    // Paste button
    btnPaste.addEventListener('click', async () => {
      try {
        const text = await navigator.clipboard.readText();
        apiKeyInput.value = text.trim();
        apiKeyInput.focus();
      } catch (err) {
        alert('Could not access clipboard. Please paste manually into the input box.');
      }
    });

    // Fetch initial status
    async function loadStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        currentKeyDisplay.textContent = data.masked_key;
        if (data.is_active) {
          statusBadge.innerHTML = '<span class="inline-block w-2 h-2 rounded-full bg-emerald-400"></span> <span class="text-emerald-400 font-semibold">Active & Authenticated</span> (' + (data.label || 'Default') + ')';
        } else {
          statusBadge.innerHTML = '<span class="inline-block w-2 h-2 rounded-full bg-rose-500"></span> <span class="text-rose-400 font-semibold">Inactive / Unauthorized (401)</span>';
        }
      } catch (err) {
        currentKeyDisplay.textContent = 'Error reading status';
        statusBadge.innerHTML = '<span class="inline-block w-2 h-2 rounded-full bg-amber-400"></span> Error connecting to server';
      }
    }
    loadStatus();

    // Save button click
    btnSave.addEventListener('click', async () => {
      const key = apiKeyInput.value.trim();
      if (!key) {
        showAlert('error', 'Please enter your OpenRouter API key.');
        return;
      }

      btnSave.disabled = true;
      saveSpinner.classList.remove('hidden');
      saveBtnText.textContent = 'Validating against OpenRouter API...';
      resultAlert.classList.add('hidden');

      try {
        const res = await fetch('/api/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ api_key: key })
        });
        const data = await res.json();

        if (data.success) {
          showAlert('success', '✅ ' + data.message + ' (Label: ' + (data.details.label || 'Standard') + ')');
          currentKeyDisplay.textContent = data.masked_key;
          statusBadge.innerHTML = '<span class="inline-block w-2 h-2 rounded-full bg-emerald-400"></span> <span class="text-emerald-400 font-semibold">Active & Saved</span>';
          apiKeyInput.value = '';
          postSaveActions.classList.remove('hidden');
        } else {
          showAlert('error', '❌ ' + data.error);
        }
      } catch (err) {
        showAlert('error', 'Network error communicating with local server: ' + err.message);
      } finally {
        btnSave.disabled = false;
        saveSpinner.classList.add('hidden');
        saveBtnText.textContent = 'Validate & Save to backend/.env';
      }
    });

    // Recreate container button
    btnRecreate.addEventListener('click', async () => {
      btnRecreate.disabled = true;
      recreateSpinner.classList.remove('hidden');
      recreateBtnText.textContent = 'Recreating container & flushing caches...';
      recreateOutput.classList.remove('hidden');
      recreateOutput.textContent = 'Executing docker compose recreation...\\n';

      try {
        const res = await fetch('/api/recreate-backend', { method: 'POST' });
        const data = await res.json();
        recreateOutput.textContent += (data.output || data.message || 'Done');
        if (data.success) {
          recreateOutput.textContent += '\\n✅ Backend stack successfully recreated and ready!';
        } else {
          recreateOutput.textContent += '\\n❌ Error: ' + (data.error || 'Recreation failed');
        }
      } catch (err) {
        recreateOutput.textContent += '\\n❌ Error: ' + err.message;
      } finally {
        btnRecreate.disabled = false;
        recreateSpinner.classList.add('hidden');
        recreateBtnText.textContent = 'Recreate Backend Container & Flush Caches';
      }
    });

    function showAlert(type, text) {
      resultAlert.classList.remove('hidden', 'bg-rose-950/50', 'border-rose-800', 'text-rose-200', 'bg-emerald-950/50', 'border-emerald-800', 'text-emerald-200');
      if (type === 'success') {
        resultAlert.classList.add('bg-emerald-950/50', 'border', 'border-emerald-800', 'text-emerald-200');
      } else {
        resultAlert.classList.add('bg-rose-950/50', 'border', 'border-rose-800', 'text-rose-200');
      }
      resultAlert.innerHTML = text;
    }
  </script>
</body>
</html>
"""


class KeySetupHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        """Suppress standard access logs for clean console output."""
        return

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            body = HTML_PAGE.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/status":
            current_k = read_current_key()
            is_active = False
            details: dict[str, Any] = {}
            if current_k:
                is_active, _, details = test_openrouter_key(current_k)

            payload = {
                "masked_key": mask_key(current_k),
                "is_active": is_active,
                "label": details.get("label", ""),
                "limit": details.get("limit", None),
                "usage": details.get("usage", None),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path == "/api/save":
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(raw_body)
            except Exception:
                self.send_error(HTTPStatus.BAD_REQUEST, "Invalid JSON")
                return

            new_key = data.get("api_key", "").strip()
            if not new_key:
                resp = {"success": False, "error": "API key cannot be empty"}
            else:
                ok, message, details = test_openrouter_key(new_key)
                if not ok:
                    resp = {"success": False, "error": message}
                else:
                    # Save to backend/.env
                    up_backend = update_env_file(BACKEND_ENV, new_key)
                    # Also update root .env if present
                    if ROOT_ENV.is_file():
                        update_env_file(ROOT_ENV, new_key)

                    resp = {
                        "success": True,
                        "message": "Key verified and saved successfully to backend/.env",
                        "masked_key": mask_key(new_key),
                        "details": details,
                    }

            body = json.dumps(resp).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/api/recreate-backend":
            cmd = (
                "cd backend && "
                "bash ../scripts/docker-safe.sh docker compose -f docker-compose.yml -f docker-compose.graded.yml up -d --force-recreate --no-deps backend && "
                "make flush-cache && make verify-cache-empty"
            )
            res = subprocess.run(
                ["bash", "-c", cmd],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
            )
            resp = {
                "success": res.returncode == 0,
                "output": res.stdout + ("\n" + res.stderr if res.stderr else ""),
                "returncode": res.returncode,
            }
            body = json.dumps(resp).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)


def run_native_dialog() -> int:
    """Prompt user via macOS native AppleScript dialog."""
    ascript = """
    tell application "System Events"
        activate
        set userResponse to (display dialog "Enter your active OpenRouter API Key (sk-or-v1-...):" default answer "" with hidden answer with title "AskMukthiGuru — OpenRouter Key Setup" buttons {"Cancel", "Validate & Save"} default button "Validate & Save")
        return text returned of userResponse
    end tell
    """
    res = subprocess.run(["osascript", "-e", ascript], capture_output=True, text=True)
    if res.returncode != 0:
        print("Cancelled by user.")
        return 1

    key = res.stdout.strip()
    if not key:
        print("Empty key entered. Cancelled.")
        return 1

    print("Validating key with OpenRouter API...")
    ok, msg, details = test_openrouter_key(key)
    if not ok:
        print(f"❌ Error: {msg}")
        return 1

    update_env_file(BACKEND_ENV, key)
    if ROOT_ENV.is_file():
        update_env_file(ROOT_ENV, key)

    print(f"✅ Key verified and saved successfully to backend/.env! (Label: {details.get('label', 'Default')})")
    return 0


def run_cli() -> int:
    """Prompt user via terminal getpass."""
    import getpass

    key = getpass.getpass("Enter OPENROUTER_API_KEY (typing hidden): ").strip()
    if not key:
        print("Empty key entered. Cancelled.")
        return 1

    print("Validating key with OpenRouter API...")
    ok, msg, details = test_openrouter_key(key)
    if not ok:
        print(f"❌ Error: {msg}")
        return 1

    update_env_file(BACKEND_ENV, key)
    if ROOT_ENV.is_file():
        update_env_file(ROOT_ENV, key)

    print(f"✅ Key verified and saved successfully to backend/.env! (Label: {details.get('label', 'Default')})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AskMukthiGuru OpenRouter Key Setup Server")
    parser.add_argument("--port", type=int, default=8765, help="Port to serve on (default: 8765)")
    parser.add_argument("--native-dialog", action="store_true", help="Prompt via macOS GUI dialog")
    parser.add_argument("--cli", action="store_true", help="Prompt via terminal getpass")
    parser.add_argument("--open", action="store_true", help="Automatically open browser tab")
    args = parser.parse_args()

    if args.native_dialog:
        return run_native_dialog()
    if args.cli:
        return run_cli()

    server = HTTPServer(("127.0.0.1", args.port), KeySetupHandler)
    url = f"http://localhost:{args.port}"
    print(f"🚀 AskMukthiGuru Key Setup UI running at {url}")
    print("Press Ctrl+C to stop.")

    if args.open:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
