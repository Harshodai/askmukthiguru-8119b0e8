"""Local labelling tool for the listening audit and the gold-set overlap batch (X-1).

Runs ONLY on this machine: binds 127.0.0.1, per-reviewer login, tasks and
progress stay under gitignored .work/label_tasks/ — clip/transcript text
never enters git. Exports per-annotator CSVs in the exact SHEET_COLS order
that evals/gold_set_v1/score_gold.py reads.

Usage (host-side, backend venv for Flask):
    cd backend
    LABEL_USERS="sushmita:pw1,sanketh:pw2" \
    .venv/bin/python ../scripts/ops/local_label.py \
        --tasks ../evals/gold_set_v1/annotator_A.csv --outdir ../.work/label_tasks/A

Then open http://127.0.0.1:8471/ and /export to download the filled sheet.
Reviewers behind the same LAN: ssh -L 8471:127.0.0.1:8471 <mac> (no public URL).
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import hmac
import html
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from flask import Flask, Response, redirect, request  # noqa: E402  (Flask is in the backend venv)

SHEET_COLS = ["pair_id", "question_id", "question_type", "question", "clip_text",
              "speaker_label", "video_url_with_timestamp", "duration_s",
              "relevance_0_3", "complete_yes_no", "speaker_is_teacher_yes_no_unsure",
              "risk_yes_no", "notes"]
DIMS = {
    "relevance_0_3": ["0", "1", "2", "3"],
    "complete_yes_no": ["yes", "no"],
    "speaker_is_teacher_yes_no_unsure": ["yes", "no", "unsure"],
    "risk_yes_no": ["yes", "no"],
}

app = Flask(__name__)
TASKS: list[dict] = []
OUTDIR = Path(".work/label_tasks/default")


def _users() -> dict[str, str]:
    users = {}
    for pair in (os.getenv("LABEL_USERS") or "").split(","):
        if ":" in pair:
            name, pw = pair.split(":", 1)
            if name.strip() and pw:
                users[name.strip()] = pw
    return users


def _authed() -> str | None:
    users = _users()
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return None
    try:
        decoded = base64.b64decode(auth[6:]).decode("utf-8")
        name, _, pw = decoded.partition(":")
    except Exception:
        return None
    if name in users and hmac.compare_digest(users[name], pw):
        return name
    return None


def _need_auth() -> Response:
    return Response("Login required.\n", 401, {"WWW-Authenticate": 'Basic realm="labels"'})


def _progress_path() -> Path:
    return OUTDIR / "progress.json"


def _load_progress() -> dict:
    try:
        return json.loads(_progress_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_progress(progress: dict) -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    tmp = OUTDIR / f".progress.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(progress, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, _progress_path())


def _next_row(user: str) -> dict | None:
    progress = _load_progress()
    for row in TASKS:
        done = progress.get(row["pair_id"], {})
        if user not in (done.get("annotators") or []):
            return row
    return None


def _render(row: dict, user: str, msg: str = "") -> str:
    progress = _load_progress()
    total = len(TASKS)
    mine = sum(1 for r in TASKS if user in ((_load_progress().get(r["pair_id"], {}).get("annotators")) or []))
    del progress
    q = row.get("question") or ""
    audit = not q.strip()
    radios = ""
    for dim, allowed in DIMS.items():
        opts = " ".join(
            f'<label><input type="radio" name="{dim}" value="{v}" required> {v}</label>'
            for v in allowed
        )
        radios += f"<p><b>{dim}</b><br>{opts}</p>"
    return f"""<!doctype html><html><body>
<h2>{html.escape(user)} — {mine}/{total} labelled</h2>
<p style="color:green">{html.escape(msg)}</p>
{'<p><i>Audit mode: no question — judge the clip alone.</i></p>' if audit else f'<h3>Question</h3><p>{html.escape(q)}</p>'}
<h3>Clip ({html.escape(row.get("speaker_label") or "?")}, {html.escape(row.get("duration_s") or "?")}s)</h3>
<p><a href="{html.escape(row.get("video_url_with_timestamp") or "#")}" target="_blank">watch at timestamp</a>
{f' · point {html.escape(row.get("point_id") or row["pair_id"])}' if audit else ''}</p>
<blockquote>{html.escape(row.get("clip_text") or "")}</blockquote>
<form method="post" action="/label">
<input type="hidden" name="pair_id" value="{html.escape(row["pair_id"])}">
{radios}
<p><b>notes</b> (required for unsure; write SKIPPED to skip)<br>
<textarea name="notes" rows="2" cols="70"></textarea></p>
<p><button type="submit">Save &amp; next</button></p>
</form>
<p><a href="/export">export my filled CSV</a></p>
</body></html>"""


@app.get("/")
def index():
    user = _authed()
    if user is None:
        return _need_auth()
    pid = request.args.get("pair_id")
    row = next((r for r in TASKS if r["pair_id"] == pid), None) if pid else _next_row(user)
    if row is None:
        return f"<p>Done — {html.escape(user)} labelled every row. <a href='/export'>export</a></p>"
    return _render(row, user, request.args.get("msg", ""))


@app.post("/label")
def label():
    user = _authed()
    if user is None:
        return _need_auth()
    pid = request.form.get("pair_id", "")
    row = next((r for r in TASKS if r["pair_id"] == pid), None)
    if row is None:
        return redirect("/?msg=" + "unknown+row")
    notes = (request.form.get("notes") or "").strip()
    skipped = "SKIPPED" in notes.upper()
    vals = {}
    for dim, allowed in DIMS.items():
        v = (request.form.get(dim) or "").strip().lower()
        if not skipped and v not in allowed:
            return redirect(f"/?pair_id={pid}&msg=" + f"bad+{dim}")
        vals[dim] = "" if skipped else v
    if not skipped and any(k == "speaker_is_teacher_yes_no_unsure" and v == "unsure" for k, v in vals.items()) and not notes:
        return redirect(f"/?pair_id={pid}&msg=" + "notes+required+for+unsure")
    progress = _load_progress()
    entry = progress.get(pid, {})
    entry.update(vals)
    entry["notes"] = notes
    entry["annotators"] = sorted(set(entry.get("annotators") or []) | {user})
    progress[pid] = entry
    _save_progress(progress)
    return redirect("/")


@app.get("/export")
def export():
    user = _authed()
    if user is None:
        return _need_auth()
    progress = _load_progress()
    lines = [",".join(SHEET_COLS)]
    buf = __import__("io").StringIO()
    writer = csv.DictWriter(buf, fieldnames=SHEET_COLS, extrasaction="ignore")
    writer.writeheader()
    for row in TASKS:
        out = {c: row.get(c, "") for c in SHEET_COLS}
        entry = progress.get(row["pair_id"], {})
        if user in (entry.get("annotators") or []):
            for dim in list(DIMS) + ["notes"]:
                out[dim] = entry.get(dim, "")
        writer.writerow(out)
    digest = hashlib.sha256(buf.getvalue().encode("utf-8")).hexdigest()[:12]
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={user}_filled_{digest}.csv"},
    )


def _is_gitignored(path: Path) -> bool:
    """True when labels written here cannot enter git: outside the repo, or ignored."""
    import subprocess

    repo_root = Path(__file__).resolve().parents[1]
    try:
        path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return True  # outside the repo: nothing here can be committed
    try:
        proc = subprocess.run(
            ["git", "check-ignore", "-q", str(path)],
            cwd=repo_root,
            capture_output=True,
            timeout=10,
        )
        return proc.returncode == 0
    except (OSError, ValueError):
        # No git available: fall back to the narrow .work convention.
        return ".work" in path.resolve().parts


def main() -> None:
    global TASKS, OUTDIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True, help="annotator sheet CSV (SHEET_COLS shape)")
    ap.add_argument("--outdir", required=True, help="gitignored progress/export dir")
    ap.add_argument("--port", type=int, default=int(os.getenv("LABEL_PORT", "8471")))
    args = ap.parse_args()
    if not _users():
        raise SystemExit("Set LABEL_USERS='name:pw,...' (reviewer passwords, local only).")
    with open(args.tasks, newline="", encoding="utf-8-sig") as fh:
        TASKS = list(csv.DictReader(fh))
    if not TASKS or TASKS[0].get("pair_id") is None:
        raise SystemExit("tasks CSV has no pair_id column — expected the annotator sheet shape.")
    OUTDIR = Path(args.outdir)
    # Local-only guarantee: outputs must land where git ignores them.
    # Basis is `git check-ignore` (the actual contract), not a path substring
    # (review round 2: substring checks accept tracked paths containing "work").
    if not _is_gitignored(OUTDIR):
        raise SystemExit(f"Refusing: outdir {OUTDIR} is not git-ignored.")
    print(f"labelling: {len(TASKS)} rows, outdir={OUTDIR} — bind 127.0.0.1:{args.port}")
    app.run(host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
