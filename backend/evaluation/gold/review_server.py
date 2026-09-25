"""
Mukthi Guru — Gold Set Review Server & UI

Provides a local web interface for human annotators to review and label
candidate relevance clips alongside embedded YouTube video playback.

Blindness (B1 protocol): each server process is bound to exactly one judge
role via --judge. judge_a/judge_b each see and write only their own column;
the adjudicator sees both raw judgments (read-only) and writes only
`adjudicated`. This is enforced server-side in /api/rows (columns are
stripped before the response leaves the process) and /api/judge (a role may
only write its own column) — never trust the client to police this.

Usage:
  python -m evaluation.gold.review_server --csv ~/mukthiguru_attribution_data/gold_pilot/relevance_pilot.csv --port 8088 --judge a
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles  # noqa: F401 -- kept for API stability, not currently used
from pydantic import BaseModel
import uvicorn

logger = logging.getLogger(__name__)

app = FastAPI(title="Mukthi Guru — Gold Relevance Reviewer")

_CSV_PATH: Optional[Path] = None
_JUDGE_ROLE: Optional[str] = None  # "a" | "b" | "adjudicator", set by --judge
_TRANSCRIPT_DIRS: list[Path] = []  # dirs containing transcripts_B/<video_id>.json

# Guards every read-modify-write cycle against the CSV file so concurrent
# requests (or a GET racing a POST) never observe/produce a torn write.
_WRITE_LOCK = threading.Lock()

_ROLE_TO_FIELD = {"a": "judge_a", "b": "judge_b", "adjudicator": "adjudicated"}
_ROLE_LABEL = {"a": "Judge A", "b": "Judge B", "adjudicator": "Adjudicator"}
_JUDGE_COLUMNS = {"judge_a", "judge_b", "adjudicated"}
_ROLE_VISIBLE_JUDGE_COLUMNS = {
    "a": {"judge_a"},
    "b": {"judge_b"},
    "adjudicator": {"judge_a", "judge_b", "adjudicated"},
}
# clip_quality is a per-clip-audio quality label, not a judge verdict — but it
# still must stay blind to judge b (same B1 protocol as the relevance columns).
_ROLE_SEES_CLIP_QUALITY = {"a": True, "b": False, "adjudicator": True}

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

# YouTube video ids are always exactly 11 chars of this alphabet. Validating
# against this BEFORE touching the filesystem or building a player URL means
# a CSV row can never be used for path traversal or URL injection.
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

_CLIP_QUALITY_VALUES = ("clean", "mid_sentence", "fragment", "wrong_speaker", "audio_issue", "other", "")

ClipQuality = Literal["clean", "mid_sentence", "fragment", "wrong_speaker", "audio_issue", "other", ""]


class JudgmentUpdate(BaseModel):
    row_index: int
    judge: Literal["judge_a", "judge_b", "adjudicated"]
    value: Literal["yes", "no", ""]
    clip_quality: Optional[ClipQuality] = None
    equivalent_group: Optional[str] = None


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_csv_rows(path: Path, rows: list[dict[str, str]]) -> None:
    """Atomic write: build the new content in a temp file in the same
    directory, then os.replace() it over the target. A crash or exception
    between those two steps leaves the original file untouched — the reader
    never sees a partially-written CSV."""
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _visible_columns_for_role(role: Optional[str]) -> set[str]:
    visible_judge_cols = _ROLE_VISIBLE_JUDGE_COLUMNS.get(role, _JUDGE_COLUMNS)
    return visible_judge_cols


def _strip_hidden_columns(row: dict[str, str], role: Optional[str]) -> dict[str, str]:
    visible = _visible_columns_for_role(role)
    hidden = _JUDGE_COLUMNS - visible
    if not _ROLE_SEES_CLIP_QUALITY.get(role, True):
        hidden = hidden | {"clip_quality"}
    return {k: v for k, v in row.items() if k not in hidden}


def _find_transcript_path(video_id: str) -> Optional[Path]:
    """Locate transcripts_B/<video_id>.json under a configured dir. Returns
    None (no read attempted) unless video_id passes the strict id regex —
    that regex has no '/' or '.', so it is the path-traversal guard."""
    if not _VIDEO_ID_RE.match(video_id or ""):
        return None
    for base in _TRANSCRIPT_DIRS:
        candidate = base / "transcripts_B" / f"{video_id}.json"
        if candidate.exists():
            return candidate
    return None


def _load_transcript_words(video_id: str) -> list[dict]:
    path = _find_transcript_path(video_id)
    if path is None:
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _extract_context(words: list[dict], start: float, end: float, context_words: int = 40) -> dict:
    """Split a video's word list into (before clip, clip itself, after clip),
    each word slimmed to {w, spk} for the UI. A word overlaps the clip window
    if its span intersects [start, end)."""

    def _slim(w: dict) -> dict:
        return {"w": w.get("w", ""), "spk": w.get("spk", "?")}

    clip_indices = [
        i for i, w in enumerate(words)
        if w.get("start", 0.0) < end and w.get("end", 0.0) > start
    ]
    if not clip_indices:
        return {"before": [], "clip": [], "after": []}
    first, last = clip_indices[0], clip_indices[-1]
    before = words[max(0, first - context_words):first]
    after = words[last + 1:last + 1 + context_words]
    clip = words[first:last + 1]
    return {
        "before": [_slim(w) for w in before],
        "clip": [_slim(w) for w in clip],
        "after": [_slim(w) for w in after],
    }


HTML_CONTENT = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Mukthi Guru — Gold Annotation Review Tool</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; background: #0f172a; color: #f8fafc; }
    header { background: #1e293b; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; }
    h1 { margin: 0; font-size: 1.25rem; font-weight: 600; color: #38bdf8; }
    .stats { font-size: 0.9rem; color: #94a3b8; display: flex; gap: 20px; }
    .container { display: flex; height: calc(100vh - 65px); }
    .list-pane { width: 380px; border-right: 1px solid #334155; overflow-y: auto; background: #1e293b; }
    .item-card { padding: 14px 18px; border-bottom: 1px solid #334155; cursor: pointer; transition: background 0.15s; }
    .item-card:hover { background: #334155; }
    .item-card.active { background: #0284c7; color: white; }
    .item-card .q-title { font-weight: 600; font-size: 0.9rem; margin-bottom: 4px; }
    .item-card .sub { font-size: 0.75rem; color: #94a3b8; display: flex; justify-content: space-between; }
    .item-card.active .sub { color: #e0f2fe; }
    .badge { padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
    .badge-yes { background: #10b981; color: white; }
    .badge-no { background: #ef4444; color: white; }
    .badge-pending { background: #64748b; color: white; }
    .detail-pane { flex: 1; padding: 24px 32px; overflow-y: auto; display: flex; flex-direction: column; gap: 20px; }
    .section-title { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; margin-bottom: 6px; }
    .question-box { background: #1e293b; border: 1px solid #334155; padding: 16px; border-radius: 8px; font-size: 1.1rem; font-weight: 500; }
    .content-split { display: flex; gap: 24px; }
    .video-container { flex: 1; background: black; border-radius: 8px; overflow: hidden; min-height: 360px; display: flex; flex-direction: column; }
    iframe { width: 100%; flex: 1; min-height: 320px; border: 0; }
    .video-links { padding: 6px 10px; font-size: 0.8rem; color: #94a3b8; background: #0f172a; display: flex; gap: 12px; align-items: center; }
    .video-links a { color: #38bdf8; }
    .transcript-box { flex: 1; background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 18px; font-size: 0.95rem; line-height: 1.6; overflow-y: auto; }
    .clip-facts { font-size: 0.78rem; color: #94a3b8; margin: 6px 0 14px; }
    .clip-facts .warn { color: #f87171; font-weight: 600; }
    .context-legend { font-size: 0.72rem; color: #64748b; margin-bottom: 8px; }
    .ctx-before, .ctx-after { color: #64748b; }
    .ctx-word { margin-right: 2px; }
    .ctx-spk { font-size: 0.6rem; vertical-align: super; color: #38bdf8; }
    .judge-controls { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
    .btn-group { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
    .btn { padding: 10px 20px; border-radius: 6px; border: 0; font-weight: 600; cursor: pointer; font-size: 0.95rem; transition: opacity 0.15s; }
    .btn:hover { opacity: 0.9; }
    .btn-yes { background: #10b981; color: white; }
    .btn-no { background: #ef4444; color: white; }
    .btn-nav { background: #475569; color: white; margin-left: auto; }
    .btn-quality { background: #334155; color: #e2e8f0; font-weight: 500; padding: 6px 12px; font-size: 0.8rem; }
    .btn-quality.active { background: #7c3aed; color: white; }
    .adjudicator-readout { font-size: 0.85rem; color: #94a3b8; }
    .help-line { font-size: 0.75rem; color: #64748b; }
  </style>
</head>
<body>
  <header>
    <h1>AskMukthiGuru — Gold Relevance Labelling</h1>
    <div class="stats" id="stats-header">Loading...</div>
  </header>
  <div class="container">
    <div class="list-pane" id="list-pane"></div>
    <div class="detail-pane" id="detail-pane">
      <div>
        <div class="section-title">Question</div>
        <div class="question-box" id="q-text">Select an item from the list</div>
      </div>
      <div class="content-split">
        <div class="video-container" id="video-box">
          <iframe id="yt-player" src="" allow="autoplay"></iframe>
          <div class="video-links" id="video-links"></div>
        </div>
        <div class="transcript-box" id="transcript-box">
          <div class="section-title">Candidate Clip Verbatim Text</div>
          <div class="clip-facts" id="clip-facts"></div>
          <p id="clip-text">No clip selected</p>
          <div class="context-legend">Surrounding words in grey are context, not the candidate clip. Speaker tags (P/K/O/?) are <strong>machine-generated, unverified</strong>.</div>
          <div id="context-box"></div>
        </div>
      </div>
      <div class="judge-controls">
        <div class="section-title">Judge Decision</div>
        <p class="adjudicator-readout" id="adjudicator-readout"></p>
        <div class="btn-group">
          <span>__JUDGE_LABEL__ (Your Verdict):</span>
          <button class="btn btn-yes" onclick="submitJudge('yes')">YES (Answers Question)</button>
          <button class="btn btn-no" onclick="submitJudge('no')">NO (Irrelevant / Near Miss)</button>
          <button class="btn" onclick="replayClip()">&#9654; Replay clip</button>
          <button class="btn btn-nav" onclick="navigate(1)">Next &rarr;</button>
        </div>
        <div class="btn-group" id="quality-group"></div>
        <div class="help-line">Shortcuts: y/n = judge, j/k = next/prev row, 1-6 = clip quality (when visible)</div>
      </div>
    </div>
  </div>
  <script>
    const JUDGE_FIELD = "__JUDGE_FIELD__";
    const VIDEO_ID_RE = /^[A-Za-z0-9_-]{11}$/;
    const QUALITY_VALUES = ["clean", "mid_sentence", "fragment", "wrong_speaker", "audio_issue", "other"];
    const CAN_SEE_QUALITY = JUDGE_FIELD !== "judge_b";
    let rows = [];
    let currentIndex = 0;

    function escapeHtml(str) {
      const div = document.createElement('div');
      div.textContent = str ?? '';
      return div.innerHTML;
    }

    async function loadData() {
      const res = await fetch('/api/rows');
      rows = await res.json();
      renderList();
      updateStats();
      if (rows.length > 0) selectRow(0);
    }

    function updateStats() {
      const total = rows.length;
      const done = rows.filter(r => r[JUDGE_FIELD]).length;
      const yesCount = rows.filter(r => r[JUDGE_FIELD] === 'yes').length;
      document.getElementById('stats-header').innerText = `${done} of ${total} judged (${Math.round(done/total*100 || 0)}%) | Yes: ${yesCount}`;
    }

    function renderList() {
      const pane = document.getElementById('list-pane');
      pane.innerHTML = rows.map((r, i) => {
        let badge = '<span class="badge badge-pending">PENDING</span>';
        if (r[JUDGE_FIELD] === 'yes') badge = '<span class="badge badge-yes">YES</span>';
        if (r[JUDGE_FIELD] === 'no') badge = '<span class="badge badge-no">NO</span>';
        return `
          <div class="item-card ${i === currentIndex ? 'active' : ''}" onclick="selectRow(${i})">
            <div class="q-title">${escapeHtml(r.question_text || r.question_id)}</div>
            <div class="sub">
              <span>${escapeHtml(r.video_id)} (${Math.round(r.start)}s)</span>
              ${badge}
            </div>
          </div>
        `;
      }).join('');
    }

    function renderQualityButtons(row) {
      const group = document.getElementById('quality-group');
      if (!CAN_SEE_QUALITY) { group.innerHTML = ''; return; }
      group.innerHTML = '<span>Clip quality:</span>' + QUALITY_VALUES.map((v, i) => `
        <button class="btn btn-quality ${row.clip_quality === v ? 'active' : ''}" onclick="submitQuality('${v}')">${i + 1}. ${v}</button>
      `).join('');
    }

    function renderClipFacts(r) {
      const start = parseFloat(r.start) || 0;
      const end = parseFloat(r.end) || start;
      const duration = Math.max(0, end - start);
      const words = (r.text || '').trim().split(/\s+/).filter(Boolean);
      const midSentence = !/[.?!]['"”]?\s*$/.test((r.text || '').trim());
      document.getElementById('clip-facts').innerHTML =
        `Duration: ${duration.toFixed(1)}s | Words: ${words.length}` +
        (midSentence ? ` | <span class="warn">ends mid-sentence</span>` : '');
    }

    function renderVideoLinks(r, videoIdValid) {
      const start = Math.floor(parseFloat(r.start) || 0);
      const mm = String(Math.floor(start / 60)).padStart(2, '0');
      const ss = String(start % 60).padStart(2, '0');
      const box = document.getElementById('video-links');
      if (!videoIdValid) { box.innerHTML = '<span>No player — invalid video id</span>'; return; }
      const watchUrl = `https://www.youtube.com/watch?v=${encodeURIComponent(r.video_id)}&t=${start}s`;
      box.innerHTML = `<a href="${watchUrl}" target="_blank" rel="noopener">Open on YouTube at ${mm}:${ss}</a>`;
    }

    function renderContextWord(w) {
      return `<span class="ctx-word">${escapeHtml(w.w)}<sub class="ctx-spk">${escapeHtml(w.spk)}</sub></span>`;
    }

    async function loadContext(index) {
      const box = document.getElementById('context-box');
      box.innerHTML = 'Loading context…';
      try {
        const res = await fetch(`/api/context/${index}`);
        if (!res.ok) { box.innerHTML = ''; return; }
        const ctx = await res.json();
        box.innerHTML =
          `<span class="ctx-before">${ctx.before.map(renderContextWord).join(' ')}</span> ` +
          `<strong>${ctx.clip.map(renderContextWord).join(' ')}</strong> ` +
          `<span class="ctx-after">${ctx.after.map(renderContextWord).join(' ')}</span>`;
      } catch (e) {
        box.innerHTML = '';
      }
    }

    function selectRow(index) {
      currentIndex = index;
      renderList();
      const r = rows[index];
      document.getElementById('q-text').innerText = `${r.question_id}: ${r.question_text}`;
      document.getElementById('clip-text').innerText = r.text;
      renderClipFacts(r);
      renderQualityButtons(r);
      loadContext(index);

      const readout = document.getElementById('adjudicator-readout');
      if (JUDGE_FIELD === 'adjudicated') {
        readout.innerText = `Judge A: ${r.judge_a || '(pending)'} | Judge B: ${r.judge_b || '(pending)'}`;
      } else {
        readout.innerText = '';
      }

      const videoIdValid = VIDEO_ID_RE.test(r.video_id || '');
      renderVideoLinks(r, videoIdValid);
      const player = document.getElementById('yt-player');
      if (videoIdValid) {
        const start = Math.floor(parseFloat(r.start) || 0);
        const end = Math.ceil(parseFloat(r.end) || start + 30);
        player.src = `https://www.youtube-nocookie.com/embed/${r.video_id}?start=${start}&end=${end}&rel=0&autoplay=1`;
      } else {
        player.src = '';
      }
    }

    function replayClip() {
      const player = document.getElementById('yt-player');
      const src = player.src;
      if (src) { player.src = ''; player.src = src; }
    }

    async function submitJudge(value) {
      rows[currentIndex][JUDGE_FIELD] = value;
      updateStats();
      renderList();
      await fetch('/api/judge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ row_index: currentIndex, judge: JUDGE_FIELD, value: value })
      });
      if (currentIndex < rows.length - 1) selectRow(currentIndex + 1);
    }

    async function submitQuality(value) {
      if (!CAN_SEE_QUALITY) return;
      const row = rows[currentIndex];
      const nextValue = row.clip_quality === value ? '' : value;
      row.clip_quality = nextValue;
      renderQualityButtons(row);
      await fetch('/api/judge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ row_index: currentIndex, judge: JUDGE_FIELD, value: row[JUDGE_FIELD] || '', clip_quality: nextValue })
      });
    }

    function navigate(offset) {
      const next = currentIndex + offset;
      if (next >= 0 && next < rows.length) selectRow(next);
    }

    document.addEventListener('keydown', (e) => {
      if (rows.length === 0) return;
      if (e.key === 'y') submitJudge('yes');
      else if (e.key === 'n') submitJudge('no');
      else if (e.key === 'j') navigate(1);
      else if (e.key === 'k') navigate(-1);
      else if (CAN_SEE_QUALITY && /^[1-6]$/.test(e.key)) submitQuality(QUALITY_VALUES[parseInt(e.key, 10) - 1]);
    });

    window.onload = loadData;
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    field = _ROLE_TO_FIELD.get(_JUDGE_ROLE, "judge_a")
    label = _ROLE_LABEL.get(_JUDGE_ROLE, "Judge A")
    return HTML_CONTENT.replace("__JUDGE_FIELD__", field).replace("__JUDGE_LABEL__", label)


@app.get("/api/rows")
async def get_rows():
    if not _CSV_PATH or not _CSV_PATH.exists():
        raise HTTPException(status_code=404, detail="CSV file not found")
    with _WRITE_LOCK:
        rows = read_csv_rows(_CSV_PATH)
    return [_strip_hidden_columns(row, _JUDGE_ROLE) for row in rows]


@app.get("/api/context/{row_index}")
async def get_context(row_index: int):
    if not _CSV_PATH or not _CSV_PATH.exists():
        raise HTTPException(status_code=404, detail="CSV file not found")
    with _WRITE_LOCK:
        rows = read_csv_rows(_CSV_PATH)
    if row_index < 0 or row_index >= len(rows):
        raise HTTPException(status_code=404, detail="Row index out of range")

    row = rows[row_index]
    words = _load_transcript_words(row.get("video_id", ""))
    start = float(row.get("start") or 0.0)
    end = float(row.get("end") or start)
    return _extract_context(words, start, end)


@app.post("/api/judge")
async def submit_judgment(update: JudgmentUpdate):
    if not _CSV_PATH or not _CSV_PATH.exists():
        raise HTTPException(status_code=404, detail="CSV file not found")

    if _JUDGE_ROLE is not None:
        allowed_field = _ROLE_TO_FIELD[_JUDGE_ROLE]
        if update.judge != allowed_field:
            raise HTTPException(
                status_code=403,
                detail=f"Judge role '{_JUDGE_ROLE}' may only write '{allowed_field}', not '{update.judge}'",
            )
        if update.clip_quality is not None and not _ROLE_SEES_CLIP_QUALITY.get(_JUDGE_ROLE, True):
            raise HTTPException(
                status_code=403,
                detail=f"Judge role '{_JUDGE_ROLE}' may not write clip_quality",
            )

    with _WRITE_LOCK:
        rows = read_csv_rows(_CSV_PATH)
        if update.row_index < 0 or update.row_index >= len(rows):
            raise HTTPException(status_code=400, detail="Invalid row index")

        rows[update.row_index][update.judge] = update.value
        if update.clip_quality is not None:
            rows[update.row_index]["clip_quality"] = update.clip_quality
        if update.equivalent_group:
            rows[update.row_index]["equivalent_group"] = update.equivalent_group

        write_csv_rows(_CSV_PATH, rows)
    return {"status": "ok", "row_index": update.row_index}


def _validate_host(host: str, allow_remote: bool) -> None:
    """Refuse to bind anywhere but loopback unless the operator opts in —
    this server has no authentication."""
    if host not in _LOOPBACK_HOSTS and not allow_remote:
        raise ValueError(
            f"Refusing to bind to non-loopback host '{host}' without --allow-remote "
            "(this server has no authentication and would expose gold labels)."
        )


def main():
    parser = argparse.ArgumentParser(description="Mukthi Guru Gold Annotation Review Server")
    parser.add_argument("--csv", type=str, required=True, help="Path to relevance CSV")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host address")
    parser.add_argument("--port", type=int, default=8088, help="Port to listen on")
    parser.add_argument(
        "--judge", type=str, required=True, choices=["a", "b", "adjudicator"],
        help="Which judge this process serves — controls what it shows and can write (blindness)",
    )
    parser.add_argument(
        "--allow-remote", action="store_true",
        help="Allow binding to a non-loopback host (unauthenticated server — use with care)",
    )
    parser.add_argument(
        "--transcripts-dir", action="append", default=[],
        help="Dir containing transcripts_B/<video_id>.json (repeatable) — enables clip audio context",
    )
    args = parser.parse_args()

    try:
        _validate_host(args.host, args.allow_remote)
    except ValueError as e:
        logger.error(str(e))
        return

    global _CSV_PATH, _JUDGE_ROLE, _TRANSCRIPT_DIRS
    _CSV_PATH = Path(args.csv).expanduser().resolve()
    _JUDGE_ROLE = args.judge
    _TRANSCRIPT_DIRS = [Path(d).expanduser().resolve() for d in args.transcripts_dir]
    if not _CSV_PATH.exists():
        logger.error(f"CSV file not found at {_CSV_PATH}")
        return

    logger.info(f"Starting Gold Review Server on http://{args.host}:{args.port} for {_CSV_PATH} (judge={_JUDGE_ROLE})")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
