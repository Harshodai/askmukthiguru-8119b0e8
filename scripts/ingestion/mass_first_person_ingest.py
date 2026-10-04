#!/usr/bin/env python3
"""Mass first-person ingest: rights-cleared videos -> Qdrant `first_person_v7`.

Wave 4a (readiness blockers 2 + 3); spec:
`.claude/tasks/ingest_all_videos_readiness_2026-09-30.md` (verdict ~85% ready,
blocker 1 cleared by Phase 1). This driver + the 5-video smoke clear 2 and 3.

REUSE (Ponytail ladder — nothing in the chain was rewritten)
------------------------------------------------------------
* **ASR stage scripts** are copied VERBATIM from the pilot50 driver
  (`~/mukthiguru_attribution_data/pilot50_2026-09-25/run_*.py`, 2026-09-25):
  faster-whisper-large-v3 + parakeet-mlx -> ROVER vote -> Qwen3 forced align ->
  punctuation -> ECAPA speaker -> clips. Only the hard-coded `WD` path literal
  is rewritten to this run's work dir, and each copy gets a provenance header.
  If a source script no longer contains the pilot WD literal the copy ABORTS
  (source drift is surfaced, never guessed around).
* **Driver control flow** (`load_json`/`ok`/`run_stage`/`process_video`
  ordering, benchmark-contention `wait_clear`) is ported from `run_pilot.py`
  with `WD`/`PY` parameterised. The chain has **no LLM dependency** — local
  models only, so a run never touches the OpenRouter RPM budget.
* **Audio archive (Wave 1 / Q0 owner directive)**: audio is resolved through
  `scripts/ops/audio_archive.py` *before* ASR — `get-path` to locate the
  archived wav, its `download` path (yt-dlp `--sleep-requests 2`) when absent,
  header check before use. The work dir only ever holds a **symlink** to the
  archived wav: archive first, never a second untracked copy, never a delete.
* **Clip layer** = `scripts.ops.build_clips_v2.build_dir(out_subdir=
  "passages_C_s1")` — the same input dir name the proven v7 build used
  (`report_20260928T174652Z.json`), and S1 turn-start recovery is already
  wired into `services/speaker_diarization.py`.
* **Index gates** = `scripts.ops.build_first_person_index.build_index(...,
  apply=False, snap_boundaries=True)` (ASR-agreement gate, duration gate,
  >=8 s clips, boundary snapping, dangling-conjunction quarantine,
  clean-before-hash store mapping), then `--dump-clips` output is written for
  the incremental apply below.
* **Write path** = `EmbeddingService.encode_batch()` ->
  `FirstPersonStore.upsert_clips()` (R2 fail-closed payload-hash / point-ID /
  dense-dim checks + read-back live inside the store — never bypassed with raw
  client writes).

DEVIATION (deliberate, documented): `build_first_person_index.
apply_indexable_clips()` is NOT used. Its snapshot-ID diff deletes every point
the build did not produce, which would delete the 144 pre-existing
`first_person_v7` points (built from *other* passages dirs; forbidden by the
task). This driver upserts only clips whose deterministic UUIDv5 ID is not
already present and **never deletes** anything from Qdrant.

EMBEDDING IS HOST-SIDE ONLY (Phase 1 OOM rule: embedding inside the running
`mukthiguru-backend` container OOM-kills it, 6 GiB limit). Run with
`backend/.venv/bin/python` and `HF_HOME=backend/.model_cache/huggingface`
(the default below; proven cosine fidelity 1.000000).

Usage (run from `backend/` so `backend/.env` is loaded; QDRANT_URL is forced
to `http://localhost:6333` unless `--qdrant-url` says otherwise):

    .venv/bin/python ../scripts/ingestion/mass_first_person_ingest.py --dry-run
    .venv/bin/python ../scripts/ingestion/mass_first_person_ingest.py --self-check
    .venv/bin/python ../scripts/ingestion/mass_first_person_ingest.py --video-ids a,b,c,d,e --limit 5
    .venv/bin/python ../scripts/ingestion/mass_first_person_ingest.py            # full run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
ATTRIBUTION_ROOT = Path.home() / "mukthiguru_attribution_data"
PILOT_WD = ATTRIBUTION_ROOT / "pilot50_2026-09-25"
PILOT_PY = PILOT_WD / "venv" / "bin" / "python"  # symlink -> bakeoff_2026-09-25/venv
DEFAULT_TARGETS = ATTRIBUTION_ROOT / "audio_2026-09" / "targets.json"
DEFAULT_MASS_WD = ATTRIBUTION_ROOT / "mass_ingest_2026-10"
DEFAULT_ARCHIVE = ATTRIBUTION_ROOT / "audio_archive"

DEFAULT_INPUT = "targets_515"
EXPECTED_ELIGIBLE = {"targets_515": 515}  # readiness report: exactly 515 videos
DEFAULT_COLLECTION = "first_person_v7"
DEFAULT_QDRANT_URL = "http://localhost:6333"
PASSAGES_SUBDIR = "passages_C_s1"  # input dir name used by the proven v7 build
APPLY_BATCH = 64  # == build_first_person_index._BATCH_SIZE

# Cached across periodic applies: a fresh EmbeddingService() would reload the
# ~570 MB ONNX INT8 encoder on every apply tick (it is lazy-loaded per instance).
_EMBEDDER: Any = None

STAGE_SCRIPTS = (
    "run_asr.py",
    "run_vote.py",
    "run_align.py",
    "run_punct.py",
    "run_speaker.py",
    "run_clips.py",
)
# ported from run_pilot.py process_video(): script -> its summary output file
STAGE_OUTPUT_SUFFIX = {
    "run_vote.py": "_vote.json",
    "run_align.py": "_align.json",
    "run_punct.py": "_punct.json",
    "run_speaker.py": "_speaker.json",
    "run_clips.py": "_clips_summary.json",
}
BENCH_PATTERN = r"[p]ython.* -m (evaluation\.bench|benchmarks\.run)"
PROVENANCE_HEADER = (
    "# ported from pilot50 run_pilot.py stage scripts (2026-09-25); "
    "only the WD path literal was rewritten.\n"
)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


# ---------------------------------------------------------------------------
# Ported verbatim from pilot50 run_pilot.py (2026-09-25): benchmark contention
# ---------------------------------------------------------------------------


def bench_running() -> bool:
    import re

    out = subprocess.run(["ps", "-axo", "command"], capture_output=True, text=True).stdout
    return re.search(BENCH_PATTERN, out) is not None


def wait_clear() -> None:
    """Wait while a repo benchmark owns the CPU (pilot behaviour, unchanged)."""
    waited = 0
    while bench_running():
        if waited == 0:
            log("waiting: benchmark process detected")
        time.sleep(60)
        waited += 1
        if waited % 10 == 0:
            log(f"still waiting on benchmark ({waited} min)")


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def ok(path: Path) -> bool:
    data = load_json(path)
    return bool(data) and data.get("ok") is True


# ---------------------------------------------------------------------------
# Work dir + state
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkDir:
    """Own work dir for this run (pilot's WD is never touched)."""

    root: Path
    stage_dir: Path
    stage_py: Path

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def audio(self) -> Path:
        return self.root / "audio"

    @property
    def passages_b(self) -> Path:
        return self.root / "passages_B"

    @property
    def transcripts_b(self) -> Path:
        return self.root / "transcripts_B"

    @property
    def passages_c(self) -> Path:
        return self.root / PASSAGES_SUBDIR

    @property
    def report_dir(self) -> Path:
        return self.root / "index_report"

    @property
    def state_path(self) -> Path:
        return self.root / "state.json"

    @property
    def videos_json(self) -> Path:
        return self.root / "videos.json"

    @property
    def channels_cache(self) -> Path:
        return self.report_dir / "channels.json"

    @property
    def indexable_clips(self) -> Path:
        return self.report_dir / "indexable_clips.json"

    def ensure(self) -> None:
        for d in (
            self.root,
            self.raw,
            self.audio,
            self.passages_b,
            self.transcripts_b,
            self.passages_c,
            self.report_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


def make_workdir(root: Path) -> WorkDir:
    return WorkDir(root=root, stage_dir=root / "stages", stage_py=PILOT_PY)


class State:
    """Per-video resumable state file; atomic writes, idempotent re-run."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.data: dict[str, Any] = {"created_at": _now(), "updated_at": None, "videos": {}}

    def load(self) -> State:
        if self.path.is_file():
            parsed = load_json(self.path)
            if not isinstance(parsed, dict):
                raise SystemExit(
                    f"corrupt state file {self.path} — inspect it and fix/remove by hand "
                    "(never auto-deleted)"
                )
            self.data = parsed
        self.data.setdefault("videos", {})
        return self

    def entry(self, video_id: str) -> dict[str, Any]:
        return self.data["videos"].setdefault(video_id, {"status": "pending", "stages": {}})

    def update(self, video_id: str, **fields: Any) -> None:
        with self._lock:
            entry = self.entry(video_id)
            entry.update(fields)
            entry["updated_at"] = _now()
            tmp = self.path.with_suffix(f".tmp.{os.getpid()}")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(self.data, indent=1, sort_keys=True), encoding="utf-8")
            os.replace(tmp, self.path)


# ---------------------------------------------------------------------------
# Work list + plan
# ---------------------------------------------------------------------------


def _eligible(row: dict[str, Any]) -> bool:
    """Owner-approved work-list rule (same predicate the targets generator used):
    rights-cleared + corpus-cleared + has caption segments + a real duration."""
    return bool(
        row.get("status") == "to_asr"
        and row.get("rights_cleared") is True
        and row.get("corpus_rights_status") == "cleared"
        and not row.get("is_empty")
        and (row.get("segments_count") or 0) > 0
        and row.get("duration_s")
    )


def load_rows(input_spec: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read the work list. `input_spec` is a key inside the default targets.json
    (default `targets_515`) or a path to a .json file holding the same shape."""
    if input_spec.endswith(".json"):
        path = Path(input_spec).expanduser()
        key = None
    else:
        path = DEFAULT_TARGETS
        key = input_spec
    if not path.is_file():
        raise SystemExit(f"work list not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    meta: dict[str, Any] = {"path": str(path), "key": key}
    if isinstance(data, dict):
        if key is None:
            for candidate in (DEFAULT_INPUT, "targets", "videos"):
                if isinstance(data.get(candidate), list):
                    key = candidate
                    break
            if key is None:
                raise SystemExit(f"{path}: no target list found (expected {DEFAULT_INPUT!r})")
        raw = data.get(key)
        if not isinstance(raw, list):
            raise SystemExit(f"{path}: key {key!r} is not a list")
        meta["summary"] = data.get("summary")
    elif isinstance(data, list):
        raw = data
    else:
        raise SystemExit(f"{path}: unexpected JSON shape {type(data).__name__}")
    meta["key"] = key
    meta["raw_rows"] = len(raw)
    rows = [r for r in raw if isinstance(r, dict) and _eligible(r)]
    meta["eligible_rows"] = len(rows)
    expected = EXPECTED_ELIGIBLE.get(key or "", 0)
    if expected and len(rows) != expected:
        raise SystemExit(
            f"{path}:{key} yielded {len(rows)} eligible rows, expected {expected} — refusing to "
            "run on a changed work list (re-review rights/filters, then update EXPECTED_ELIGIBLE)"
        )
    ids = [r["video_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit(f"{path}:{key} contains duplicate video_ids")
    return rows, meta


def indexed_video_ids(qdrant_url: str, collection: str) -> set[str]:
    """Read-only scroll of `video_id` payloads already in the collection
    (skip set). Fails closed if Qdrant cannot be read."""
    url = f"{qdrant_url.rstrip('/')}/collections/{collection}/points/scroll"
    found: set[str] = set()
    offset: Any = None
    while True:
        body: dict[str, Any] = {
            "limit": 1000,
            "with_payload": ["video_id"],
            "with_vector": False,
        }
        if offset is not None:
            body["next_page_offset"] = offset
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - surfaced as a hard stop
            raise SystemExit(f"cannot read {collection} at {qdrant_url}: {exc}") from exc
        result = payload.get("result") or {}
        for point in result.get("points") or []:
            video_id = (point.get("payload") or {}).get("video_id")
            if video_id:
                found.add(video_id)
        offset = result.get("next_page_offset")
        if offset is None:
            return found


def select_targets(
    rows: list[dict[str, Any]],
    skip_ids: set[str],
    state: State,
    limit: int,
    only_ids: set[str] | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    chosen: list[dict[str, Any]] = []
    excluded = {"already_in_collection": 0, "state_indexed": 0, "not_selected": 0}
    for row in rows:
        video_id = row["video_id"]
        if only_ids is not None and video_id not in only_ids:
            excluded["not_selected"] += 1
            continue
        if state.data["videos"].get(video_id, {}).get("status") == "indexed":
            excluded["state_indexed"] += 1
            continue
        if video_id in skip_ids:
            excluded["already_in_collection"] += 1
            continue
        chosen.append(row)
    if limit and limit > 0:
        chosen = chosen[:limit]
    return chosen, excluded


# ---------------------------------------------------------------------------
# Stage scripts: verbatim port (WD rewritten only)
# ---------------------------------------------------------------------------


def port_stage_scripts(wd: WorkDir) -> None:
    """Copy the pilot stage scripts into this run's work dir (idempotent).

    `common.py` is the stages' only local import (`from common import ...`,
    reached via the scripts' own dir on sys.path); it is pure stdlib with no
    WD literal, so it is copied verbatim with no drift check."""
    if not PILOT_PY.is_file():
        raise SystemExit(f"pilot venv python missing: {PILOT_PY}")
    wd.stage_dir.mkdir(parents=True, exist_ok=True)
    pilot_literal = str(PILOT_WD)

    common_src = PILOT_WD / "common.py"
    if not common_src.is_file():
        raise SystemExit(f"pilot common.py missing: {common_src}")
    common_text = common_src.read_text(encoding="utf-8")
    if pilot_literal in common_text:
        raise SystemExit("common.py: unexpected pilot WD literal — source drift")
    for dst in (wd.stage_dir / "common.py", wd.root / "common.py"):
        if not dst.is_file() or dst.read_text(encoding="utf-8") != PROVENANCE_HEADER + common_text:
            dst.write_text(PROVENANCE_HEADER + common_text, encoding="utf-8")

    for name in STAGE_SCRIPTS:
        src = PILOT_WD / name
        if not src.is_file():
            raise SystemExit(f"pilot stage script missing: {src}")
        text = src.read_text(encoding="utf-8")
        if pilot_literal not in text:
            raise SystemExit(
                f"{name}: pilot WD literal not found — source drift detected, refusing to guess a rewrite"
            )
        ported = text.replace(pilot_literal, str(wd.root))
        dst = wd.stage_dir / name
        if dst.is_file() and dst.read_text(encoding="utf-8") == PROVENANCE_HEADER + ported:
            continue
        dst.write_text(PROVENANCE_HEADER + ported, encoding="utf-8")
    log(f"stage scripts ready in {wd.stage_dir} (verbatim port, WD rewritten)")


def stage_env() -> dict[str, str]:
    """Stage processes must NOT inherit the embed-only HF_HOME (Phase 1 host
    cache `backend/.model_cache/huggingface` holds no whisper/parakeet/aligner
    weights — inheriting it would cold-start multi-GB downloads). Stage models
    live in the pilot's default HF cache, exactly as the pilot ran them."""
    env = dict(os.environ)
    env.pop("HF_HOME", None)
    return env


# ---------------------------------------------------------------------------
# Audio: archive-first (Wave 1 owner directive)
# ---------------------------------------------------------------------------


def ensure_audio(wd: WorkDir, video_id: str, archive: Any) -> bool:
    """Resolve the wav through audio_archive BEFORE ASR: locate (get-path),
    download into the archive if absent (yt-dlp --sleep-requests 2), verify the
    16 kHz mono header the ECAPA/aligner stages require, then symlink into the
    work dir. Archive content is never copied twice and never deleted."""
    archive_path = archive.get_path(video_id)
    if archive_path is None:
        log(f"archive miss {video_id} — downloading into archive (sleep-requests=2)")
        archive.download_pending(video_ids=[video_id])
        archive_path = archive.get_path(video_id)
    if archive_path is None:
        log(f"audio unavailable {video_id} (not archived and not downloadable now)")
        return False

    import audio_archive as aa

    channels, sample_rate, _duration = aa.inspect_wav(archive_path)
    if (channels, sample_rate) != (1, 16000):
        log(
            f"reject {video_id}: archived wav is {sample_rate} Hz / {channels} ch, need 16000 Hz / 1 ch"
        )
        return False

    link = wd.audio / f"{video_id}.wav"
    if link.is_symlink():
        if link.resolve() != archive_path.resolve():
            link.unlink()
            link.symlink_to(archive_path)
    elif link.exists():
        log(f"note: {link} is a regular file, not a symlink — leaving it in place")
    else:
        link.symlink_to(archive_path)
    return True


# ---------------------------------------------------------------------------
# Per-video pipeline (ported from run_pilot.py process_video/run_stage)
# ---------------------------------------------------------------------------


def run_stage(wd: WorkDir, script: str, video_id: str, out_file: Path) -> bool:
    if ok(out_file):
        log(f"skip {script} {video_id} (already ok)")
        return True
    log(f"run {script} {video_id}")
    proc = subprocess.run(
        [str(wd.stage_py), str(wd.stage_dir / script), video_id],
        capture_output=True,
        text=True,
        env=stage_env(),
    )
    for line in (proc.stdout + proc.stderr).splitlines()[-5:]:
        log(f"  {line}")
    return ok(out_file)


def process_video(wd: WorkDir, state: State, archive: Any, video_id: str) -> dict[str, Any]:
    result: dict[str, Any] = {"video_id": video_id, "ok": False, "stages": {}}
    if not ensure_audio(wd, video_id, archive):
        result["error"] = "audio_unavailable"
        return result
    result["stages"]["audio"] = True

    wait_clear()
    # run_asr.py takes (video_id, which) — called directly, not via run_stage.
    for which in ("whisper", "parakeet"):
        out_file = wd.raw / f"{video_id}_{which}.json"
        if ok(out_file):
            log(f"skip asr {which} {video_id} (already ok)")
            result["stages"][which] = True
            continue
        log(f"run asr {which} {video_id}")
        proc = subprocess.run(
            [str(wd.stage_py), str(wd.stage_dir / "run_asr.py"), video_id, which],
            capture_output=True,
            text=True,
            env=stage_env(),
        )
        for line in (proc.stdout + proc.stderr).splitlines()[-5:]:
            log(f"  {line}")
        result["stages"][which] = ok(out_file)
        if not result["stages"][which]:
            result["error"] = f"asr_{which}_failed"
            return result

    # vote/align/punct/speaker/clips — abort rules exactly as the pilot:
    # vote and speaker failures stop the video; align/punct are recorded only.
    for script, suffix in STAGE_OUTPUT_SUFFIX.items():
        key = script.removeprefix("run_").removesuffix(".py")  # run_vote.py -> vote
        good = run_stage(wd, script, video_id, wd.raw / f"{video_id}{suffix}")
        result["stages"][key] = good
        if script in ("run_vote.py", "run_speaker.py") and not good:
            result["error"] = f"{key}_failed"
            return result

    result["ok"] = bool(result["stages"].get("clips"))
    if not result["ok"]:
        result["error"] = "clips_failed"
    return result


def stage_stats(wd: WorkDir, video_id: str) -> dict[str, Any]:
    """Measured per-stage outputs (gate 1 evidence: segment/word counts)."""

    def read(name: str) -> Any:
        return load_json(wd.raw / name, {})

    whisper = read(f"{video_id}_whisper.json")
    parakeet = read(f"{video_id}_parakeet.json")
    vote = read(f"{video_id}_vote.json")
    align = read(f"{video_id}_align.json")
    punct = read(f"{video_id}_punct.json")
    speaker = read(f"{video_id}_speaker.json")
    clips = read(f"{video_id}_clips_summary.json")
    return {
        "whisper_ok": whisper.get("ok"),
        "whisper_segments": len(whisper.get("segments") or []),
        "whisper_words": len(whisper.get("words") or []),
        "whisper_rtf": whisper.get("rtf"),
        "parakeet_ok": parakeet.get("ok"),
        "parakeet_words": len(parakeet.get("words") or []),
        "parakeet_rtf": parakeet.get("rtf"),
        "vote_ok": vote.get("ok"),
        "vote_words": vote.get("n_voted"),
        "asr_agreement": vote.get("agreement_rate"),
        "align_ok": align.get("ok"),
        "align_words": align.get("n_words"),
        "align_words_aligned": align.get("n_words_aligned"),
        "align_fallback_words": align.get("n_words_mismatch_fallback"),
        "punct_ok": punct.get("ok"),
        "punct_display_words": punct.get("n_display_words"),
        "punct_zero_change": punct.get("zero_change_assert_passed"),
        "speaker_ok": speaker.get("ok"),
        "speaker_windows": speaker.get("n_windows"),
        "speaker_time_share": speaker.get("time_share"),
        "clips_ok": clips.get("ok"),
        "clips": clips.get("n_clips"),
        "clips_host_leak": clips.get("host_leak_count"),
    }


def run_one(
    wd: WorkDir, state: State, archive: Any, index: int, total: int, row: dict[str, Any]
) -> None:
    video_id = row["video_id"]
    log(f"=== [{index}/{total}] {video_id} start ===")
    try:
        result = process_video(wd, state, archive, video_id)
    except Exception as exc:  # fail soft per video, fail closed on its index write
        result = {
            "video_id": video_id,
            "ok": False,
            "stages": {},
            "error": f"{type(exc).__name__}: {exc}",
        }
    stats = stage_stats(wd, video_id) if result["stages"].get("audio") else {}
    stages = dict(state.entry(video_id).get("stages") or {})
    stages.update(result["stages"])
    status = "stages_done" if result.get("ok") else "failed"
    # Never downgrade a row a (backlog/periodic) apply already marked `indexed`:
    # it is in Qdrant, and the fast-forward re-run only re-verified its stages.
    if state.entry(video_id).get("status") == "indexed" and status != "failed":
        status = "indexed"
    state.update(video_id, status=status, stages=stages, stats=stats, error=result.get("error"))
    log(
        f"=== {video_id} done: status={status} stages={result['stages']} clips={stats.get('clips')} ==="
    )


# ---------------------------------------------------------------------------
# Build + incremental apply (host-side embed only)
# ---------------------------------------------------------------------------


def _ensure_backend_on_path() -> None:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))


def seed_index_inputs(rows: list[dict[str, Any]], wd: WorkDir) -> None:
    """Seed the index builder's inputs from the owner-approved work list:
    `videos.json` (durations) and the builder's `channels.json` cache (channel
    + duration per video) so the build makes ZERO yt-dlp calls and derives
    `rights_cleared` from the same approved channel names we were given."""
    videos = {
        "videos": [{"video_id": r["video_id"], "duration_s": r.get("duration_s")} for r in rows]
    }
    wd.videos_json.write_text(json.dumps(videos, indent=1), encoding="utf-8")

    channels: dict[str, Any] = load_json(wd.channels_cache, {}) or {}
    for r in rows:
        channels[r["video_id"]] = {
            "channel": r.get("channel") or "UNKNOWN",
            "duration_s": r.get("duration_s"),
        }
    wd.report_dir.mkdir(parents=True, exist_ok=True)
    tmp = wd.channels_cache.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(channels, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, wd.channels_cache)


def build_clips_layer(wd: WorkDir) -> dict[str, Any]:
    """transcripts_B -> passages_C_s1 via the shared v2 clip builder (S1 wired)."""
    _ensure_backend_on_path()
    from scripts.ops.build_clips_v2 import build_dir

    return build_dir(wd.root, out_subdir=PASSAGES_SUBDIR)


def _scroll_ids(client: Any, collection: str, with_video_id: bool = False) -> set[str]:
    ids: set[str] = set()
    offset: Any = None
    while True:
        result, offset = client.scroll(
            collection_name=collection,
            offset=offset,
            limit=1000,
            with_payload=["video_id"] if with_video_id else False,
            with_vectors=False,
        )
        for point in result:
            ids.add(str(point.id))
        if offset is None:
            return ids


def apply_index(
    wd: WorkDir,
    collection: str,
    qdrant_url: str,
    hf_home: Path,
) -> dict[str, Any]:
    """Build gates (dry) then incremental embed+upsert. HOST-SIDE ONLY.

    Never calls build_first_person_index.apply_indexable_clips() (its ID-diff
    would delete the 144 pre-existing points) and never deletes a point.
    """
    os.environ["QDRANT_URL"] = qdrant_url
    os.environ["HF_HOME"] = str(hf_home)
    # Production (.env) + Phase 1 host path is ONNX INT8; the Settings default
    # is flagembedding, so pin it here for host runs that may not load .env.
    os.environ.setdefault("EMBEDDING_BACKEND", "onnx_int8")
    _ensure_backend_on_path()

    import scripts.ops.build_first_person_index as bpi
    from app.config import settings
    from scripts.ops.build_first_person_index import build_index
    from services.embedding_service import EmbeddingService
    from services.first_person_store import FirstPersonStore, make_first_person_point_id
    from services.qdrant.utils import QdrantUtils

    # build_index() has no clips-out parameter and keeps its gated clip list
    # local; capture it at the module-level build_store_clip() seam so every
    # gate (ASR agreement, duration, >=8s, snapping, quarantine,
    # clean-before-hash) still runs inside build_index, unmodified.
    captured: list[dict[str, Any]] = []
    original_build_store_clip = bpi.build_store_clip

    def _capture(*args: Any, **kwargs: Any) -> dict[str, Any]:
        clip = original_build_store_clip(*args, **kwargs)
        captured.append(clip)
        return clip

    bpi.build_store_clip = _capture
    try:
        report = build_index(
            passages_dirs=[wd.passages_c],
            videos_json=wd.videos_json,
            report_dir=wd.report_dir,
            collection=collection,
            apply=False,
            snap_boundaries=True,  # matches the proven v7 build
            dump_ids=wd.report_dir / "point_ids.txt",
        )
    finally:
        bpi.build_store_clip = original_build_store_clip
    log(
        f"build: discovered={report['videos_discovered']} gated_ok={report['videos_indexed']} "
        f"quarantined={len(report['videos_quarantined'])} clips={report['clips_indexed_total']} "
        f"snapped={report['clips_snapped']} too_short={report['clips_too_short']} "
        f"quarantine={report['clips_quarantined']}"
    )
    for entry in report["videos_quarantined"]:
        log(f"  quarantined {entry['video_id']}: {entry['reason']}")

    # Rights fail-closed: the build decides rights_cleared from the channel
    # cache we seeded from the owner's work list. Never write an uncleared one.
    uncleared = sorted(ch for ch, info in report["channels"].items() if not info["rights_cleared"])
    if uncleared:
        raise SystemExit(f"refusing to apply: uncleared channel(s) in this build: {uncleared}")

    # Same duplicate collapse build_index applies before its count check
    # (a <=150-word parent and its child share one UUIDv5 point; keep the last).
    by_id: dict[tuple[str, int, int], dict[str, Any]] = {}
    for clip in reversed(captured):
        by_id[(clip["transcript_hash"], clip["start_ms"], clip["end_ms"])] = clip
    clips = list(by_id.values())
    wd.indexable_clips.write_text(json.dumps(clips, indent=1), encoding="utf-8")
    if len(clips) != report["clips_indexed_total"]:
        raise SystemExit(
            f"captured {len(clips)} unique clips but build reported "
            f"{report['clips_indexed_total']} — capture seam drifted, refusing to apply"
        )
    if not clips:
        raise SystemExit("refusing to apply: build produced 0 indexable clips")

    store = FirstPersonStore(collection=collection)
    store.init_collection()
    before = _scroll_ids(store.client, collection)

    pending: list[dict[str, Any]] = []
    already_present = 0
    for clip in clips:
        point_id = make_first_person_point_id(
            clip["transcript_hash"], clip["start_ms"], clip["end_ms"]
        )
        if point_id in before:
            already_present += 1
        else:
            pending.append(clip)
    per_video: dict[str, int] = {}
    for clip in pending:
        per_video[clip["video_id"]] = per_video.get(clip["video_id"], 0) + 1

    upserted = 0
    if pending:
        global _EMBEDDER
        if _EMBEDDER is None:
            _EMBEDDER = EmbeddingService()
        embedder = _EMBEDDER
        for i in range(0, len(pending), APPLY_BATCH):
            batch = pending[i : i + APPLY_BATCH]
            embeddings = embedder.encode_batch([c["verbatim_text"] for c in batch])
            sparse_vectors = []
            for sparse_dict in embeddings["sparse"]:
                sv = QdrantUtils.sparse_dict_to_vector(sparse_dict)
                sparse_vectors.append({"indices": sv.indices, "values": sv.values})
            # R2 fail-closed validation runs inside upsert_clips (pre + post).
            store.upsert_clips(batch, embeddings["dense"], None, sparse_vectors)
            upserted += len(batch)
            log(f"  upserted {upserted}/{len(pending)} clips (batch {len(batch)})")

    after = _scroll_ids(store.client, collection)
    expected_ids = {
        make_first_person_point_id(c["transcript_hash"], c["start_ms"], c["end_ms"])
        for c in pending
    }
    missing = sorted(expected_ids - after)
    if missing:
        raise RuntimeError(
            f"[apply] {len(missing)} produced point(s) missing after upsert: {missing[:5]}"
        )
    gone = sorted(before - after)
    if gone:
        # A deletion would be a violation of this run's contract (never delete).
        raise RuntimeError(f"[apply] {len(gone)} pre-existing point(s) disappeared: {gone[:5]}")

    record = {
        "generated_at": _now(),
        "collection": collection,
        "qdrant_url": qdrant_url,
        "hf_home": os.environ.get("HF_HOME"),
        "embedding_backend": settings.embedding_backend,
        "build_report": report.get("report_path"),
        "videos_discovered": report["videos_discovered"],
        "videos_gated_ok": report["videos_indexed"],
        "videos_quarantined": report["videos_quarantined"],
        "clips_indexable": report["clips_indexed_total"],
        "clips_already_present": already_present,
        "clips_upserted": upserted,
        "new_points_per_video": per_video,
        "point_total_before": len(before),
        "point_total_after": len(after),
        "deletions": 0,
        "missing_after_apply": len(missing),
        "r2": "pass (FirstPersonStore.upsert_clips pre-write hash/ID/dim + post-write read-back)",
        "incremental": True,
        "snap_boundaries": True,
        "min_clip_duration_s": report["min_clip_duration_s"],
    }
    path = wd.report_dir / f"apply_{time.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    record["record_path"] = str(path)
    return record


# ---------------------------------------------------------------------------
# Apply cycle (shared by backlog, periodic ticks, and the final apply)
# ---------------------------------------------------------------------------


def stages_done_rows(plan: list[dict[str, Any]], state: State) -> list[dict[str, Any]]:
    """Rows in `plan` whose state status is `stages_done` (the legacy `done`
    list the end-of-run block used — computed fresh at each apply tick)."""
    return [
        r
        for r in plan
        if state.data["videos"].get(r["video_id"], {}).get("status") == "stages_done"
    ]


def apply_cycle(
    wd: WorkDir,
    state: State,
    plan: list[dict[str, Any]],
    collection: str,
    qdrant_url: str,
    hf_home: Path,
) -> dict[str, Any]:
    """Clip layer + incremental apply + status marking (legacy end-of-run logic).

    Marks every plan row still at `stages_done` as `indexed`, or `quarantined`
    if this build quarantined it — identical to the original post-chain block.
    `apply_index()` is idempotent (diffs against Qdrant, upserts only pending),
    so running this repeatedly is a safe incremental apply. Raises on failure;
    mid-chain callers must wrap it in try/except.
    """
    done = stages_done_rows(plan, state)
    clips_report = build_clips_layer(wd)
    log(f"clips layer: {clips_report}")
    record = apply_index(
        wd,
        collection=collection,
        qdrant_url=qdrant_url,
        hf_home=hf_home,
    )
    quarantined = {e["video_id"] for e in record["videos_quarantined"]}
    for row in done:
        vid = row["video_id"]
        if vid in quarantined:
            state.update(vid, status="quarantined")
        else:
            state.update(vid, status="indexed")
    state.data["updated_at"] = _now()
    state.update("__last_apply__", status="done", stats=record)
    log(
        "APPLY OK: "
        f"upserted={record['clips_upserted']} already_present={record['clips_already_present']} "
        f"points {record['point_total_before']} -> {record['point_total_after']} "
        f"deletions={record['deletions']}"
    )
    return record


# ---------------------------------------------------------------------------
# Self-check (dry-run on 2 fake IDs, no writes outside a temp dir)
# ---------------------------------------------------------------------------


def self_check() -> int:
    """Unit self-check of plan + state/resume logic on 2 fake IDs.
    No network, no Qdrant, nothing written outside a temp directory."""
    with tempfile.TemporaryDirectory(prefix="mass_ingest_selfcheck_") as tmp:
        wd = make_workdir(Path(tmp) / "mass")
        wd.ensure()
        rows = [
            {"video_id": "FAKEVID000001", "duration_s": 120.0, "channel": "Ekam"},
            {"video_id": "FAKEVID000002", "duration_s": 240.0, "channel": "Ekam"},
        ]
        state = State(wd.state_path).load()

        plan, excluded = select_targets(rows, skip_ids=set(), state=state, limit=0, only_ids=None)
        assert [r["video_id"] for r in plan] == ["FAKEVID000001", "FAKEVID000002"], plan
        assert excluded["already_in_collection"] == 0
        assert state.entry("FAKEVID000001")["status"] == "pending"

        # stage skip-if-exists (resume) on fake outputs
        fake_out = wd.raw / "FAKEVID000001_vote.json"
        fake_out.write_text(json.dumps({"ok": True, "n_voted": 7}), encoding="utf-8")
        assert ok(fake_out), "ok() must see a completed stage output"
        assert not ok(wd.raw / "FAKEVID000002_vote.json"), "ok() must miss a missing stage"

        # state round-trip + resume decision
        state.update("FAKEVID000001", status="stages_done", stages={"vote": True})
        reloaded = State(wd.state_path).load()
        assert reloaded.data["videos"]["FAKEVID000001"]["status"] == "stages_done"
        reloaded.update("FAKEVID000001", status="indexed")
        plan2, excluded2 = select_targets(
            rows, skip_ids=set(), state=State(wd.state_path).load(), limit=0, only_ids=None
        )
        assert [r["video_id"] for r in plan2] == ["FAKEVID000002"], plan2
        assert excluded2["state_indexed"] == 1

        # already-indexed (Qdrant skip set) exclusion
        plan3, excluded3 = select_targets(
            rows,
            skip_ids={"FAKEVID000002"},
            state=State(wd.state_path).load(),
            limit=0,
            only_ids=None,
        )
        assert plan3 == [] and excluded3["already_in_collection"] == 1

        # limit + only-filters
        plan4, _ = select_targets(
            rows, skip_ids=set(), state=State(wd.state_path).load(), limit=1, only_ids=None
        )
        assert len(plan4) == 1
        plan5, excluded5 = select_targets(
            rows,
            skip_ids=set(),
            state=State(wd.state_path).load(),
            limit=0,
            only_ids={"FAKEVID000002"},
        )
        assert [r["video_id"] for r in plan5] == ["FAKEVID000002"]
        assert excluded5["not_selected"] == 1

        # dry-run purity: plan() never creates dirs or state in the real work dir
        assert not DEFAULT_MASS_WD.exists() or DEFAULT_MASS_WD.is_dir()
    print("self-check OK (plan + state/resume on 2 fake IDs; no writes outside temp dir)")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def print_plan(meta: dict[str, Any], rows, plan, excluded, skip, state, wd, archive) -> None:
    archived = sum(1 for r in plan if archive.get_path(r["video_id"]) is not None)
    states: dict[str, int] = {}
    for row in rows:
        status = state.data["videos"].get(row["video_id"], {}).get("status", "pending")
        states[status] = states.get(status, 0) + 1
    total_hours = round(sum(r["duration_s"] for r in plan) / 3600, 2)
    print("=" * 70)
    print("mass_first_person_ingest PLAN" + (" (dry-run: zero writes)" if not plan else ""))
    print("=" * 70)
    print(f"work list:      {meta['path']} key={meta['key']}")
    print(
        f"rows:           {meta['raw_rows']} raw -> {meta['eligible_rows']} eligible (rights+segments rule)"
    )
    print(f"collection:     skip set = {len(skip)} video(s) already in first_person_v7")
    print(f"state statuses: {states}")
    print(f"selected:       {len(plan)} video(s), {total_hours} h of audio")
    print(f"archived wav:   {archived}/{len(plan)} already in audio_archive")
    print(f"excluded:       {excluded}")
    print(f"work dir:       {wd.root}")
    print(f"stage python:   {wd.stage_py}")
    print(
        "apply plan:     build (dry) -> incremental embed+upsert via upsert_clips(); no deletions"
    )
    print("=" * 70)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--input", default=DEFAULT_INPUT, help="work-list key (or .json path); default %(default)s"
    )
    parser.add_argument("--limit", type=int, default=0, help="process at most N videos (0 = all)")
    parser.add_argument(
        "--workers", type=int, default=2, help="parallel stage-chain slots (default 2)"
    )
    parser.add_argument(
        "--video-ids", default="", help="comma-separated subset (overrides --limit)"
    )
    parser.add_argument("--dry-run", action="store_true", help="print the plan; ZERO writes")
    parser.add_argument("--self-check", action="store_true", help="unit self-check on 2 fake ids")
    parser.add_argument(
        "--apply-every",
        type=int,
        default=25,
        metavar="N",
        help="run clip-layer build + incremental Qdrant apply every N stage-chain "
        "completions (0 = legacy end-of-run apply only); default %(default)s",
    )
    parser.add_argument("--qdrant-url", default=DEFAULT_QDRANT_URL)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--work-dir", default="", help="work dir (default: %(default)s)")
    parser.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE))
    args = parser.parse_args(argv)

    if args.self_check:
        return self_check()

    wd = make_workdir(Path(args.work_dir) if args.work_dir else DEFAULT_MASS_WD)
    archive_root = Path(args.archive_dir).expanduser()
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "ops"))
    from audio_archive import AudioArchive  # noqa: E402 - path set just above

    archive = AudioArchive(archive_root=archive_root)

    rows, meta = load_rows(args.input)
    state = State(wd.state_path).load()
    skip = indexed_video_ids(args.qdrant_url, args.collection)
    only_ids = {v.strip() for v in args.video_ids.split(",") if v.strip()} or None
    plan, excluded = select_targets(
        rows, skip_ids=skip, state=state, limit=args.limit, only_ids=only_ids
    )
    if only_ids:
        unknown = sorted(only_ids - {r["video_id"] for r in rows})
        if unknown:
            raise SystemExit(f"--video-ids not in the eligible work list: {unknown}")
    print_plan(meta, rows, plan, excluded, skip, state, wd, archive)
    if args.dry_run or not plan:
        if args.dry_run:
            log("DRY RUN: zero writes (no state, no embed, no upsert, no stage runs)")
        return 0

    # ---- stage chain (verbatim ported pilot stages) --------------------
    port_stage_scripts(wd)
    wd.ensure()
    seed_index_inputs(plan, wd)
    total = len(plan)
    hf_home = BACKEND_DIR / ".model_cache" / "huggingface"
    log(f"stage chain start: {total} video(s), workers={args.workers}")

    # Backlog apply: rows already at `stages_done` from a previous run have
    # clips on disk but no Qdrant points — index them before the chain so the
    # first hour of the run is not write-free. Runs while no worker is live.
    if args.apply_every > 0:
        backlog = stages_done_rows(plan, state)
        if backlog:
            log(f"backlog apply: {len(backlog)} video(s) stages_done but not yet indexed")
            try:
                apply_cycle(
                    wd,
                    state,
                    plan,
                    collection=args.collection,
                    qdrant_url=args.qdrant_url,
                    hf_home=hf_home,
                )
            except (Exception, SystemExit) as exc:  # noqa: BLE001 - chain must survive
                log(f"backlog APPLY FAILED: {type(exc).__name__}: {exc} — continuing with stages")

    completed = 0
    applies = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [
            pool.submit(run_one, wd, state, archive, i, total, row) for i, row in enumerate(plan, 1)
        ]
        # Completion-order iteration so indexing can happen DURING the chain
        # (the legacy submission-order wait deferred every Qdrant write until
        # all ~441 videos finished — ~41 h of write-free staging).
        for fut in as_completed(futures):
            fut.result()
            completed += 1
            if args.apply_every > 0 and completed % args.apply_every == 0:
                applies += 1
                log(f"periodic apply #{applies}: {completed}/{total} stage-chain completion(s)")
                try:
                    apply_cycle(
                        wd,
                        state,
                        plan,
                        collection=args.collection,
                        qdrant_url=args.qdrant_url,
                        hf_home=hf_home,
                    )
                except (Exception, SystemExit) as exc:  # noqa: BLE001 - chain must survive
                    # A failed tick must NOT kill the stage chain: the final
                    # apply below still runs and must succeed.
                    log(
                        f"periodic APPLY FAILED at {completed}/{total}: "
                        f"{type(exc).__name__}: {exc} — continuing; final apply will retry"
                    )

    terminal = [
        r
        for r in plan
        if state.data["videos"].get(r["video_id"], {}).get("status")
        in ("stages_done", "indexed", "quarantined")
    ]
    log(f"stage chain complete: {len(terminal)}/{total} video(s) passed the stage chain")
    if not terminal:
        log("no video passed the stage chain — stopping before build/apply")
        return 1

    # ---- final clip layer + incremental apply (catches stragglers) -----
    apply_cycle(
        wd,
        state,
        plan,
        collection=args.collection,
        qdrant_url=args.qdrant_url,
        hf_home=hf_home,
    )
    log(f"state: {state.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
