"""File-backed (mmap) prepacked ONNX Runtime model for the INT8 BGE-M3 encoder.

Why: a plain ``InferenceSession`` copies every initializer into private heap
(~840 MB for the 570 MB INT8 model: raw copy plus MLAS prepacked copy), so each
extra uvicorn worker duplicates it. ORT can instead write the optimized graph
with its initializers AND the prepacked weights in an external-data file, and
memory-map that file on load. Mapped pages live in the page cache and are
shared by every process that opens the same file (PSS is split between them).

Measured 2026-11-27 (ORT 1.30.0, linux/aarch64, bit-identical embeddings):
  independent session, N=1: 977 MB PSS; this artifact, N=1: 710 MB PSS
  (388 anon + 322 file, of which the tokenizer is ~276 MB anon);
  marginal cost of one more process: ~390 MB -> ~100 MB with fork-after-tokenizer.
Detail and sources: docs/operations/model-memory-sharing-research-2026-11-27.md.

The artifact is machine-specific (prepacked layout follows the MLAS kernels the
CPU selects; ORT itself warns an optimized model "should only be used in the
same environment the model was optimized in"). It is therefore built on the
serving host, never baked into an image, and keyed by ORT version, CPU feature
digest and model identity. A key change builds a fresh artifact; nothing is
reused across a mismatch. Builds are serialized with flock and published with an
atomic directory rename, so concurrent workers never see a half-written model.

Errors are raised, not swallowed: when the flag is on and the build fails, the
service must not silently fall back to a different memory profile. Every build
failure (child error, timeout, bad artifact) is a ``PrepackError`` so the caller
can tell it apart from a corrupt-model-cache error (see embedding_service).

Integrity: READY stores the byte size and sha256 of the graph and the data file,
written at build time. Every load checks the sizes and the graph hash (cheap);
the data hash (832 MB) is checked too when ``verify_data_hash`` is set. A
mismatch is logged as an error and the artifact is rebuilt, never served.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

_MODEL_NAME = "model.onnx"
_DATA_NAME = "model.onnx.data"
_READY_NAME = "READY"
# Initializers smaller than this stay inline in the .onnx; everything bigger
# (all the weight tensors) goes to the mmapped data file.
_EXTERNAL_MIN_BYTES = 1024
_TMP_PREFIX = "tmp."
_LOCK_NAME = ".build.lock"
_HASH_CHUNK = 1 << 20


class PrepackError(RuntimeError):
    """The prepacked-model build or its integrity check failed."""


def _cpu_digest() -> str:
    """Digest of the CPU feature flags MLAS dispatches on (Linux /proc/cpuinfo)."""
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            key = line.split(":", 1)[0].strip().lower()
            if key in ("flags", "features"):
                return hashlib.sha256(line.encode("utf-8")).hexdigest()[:16]
    # Non-Linux dev host: coarser, but still separates architectures.
    return hashlib.sha256(platform.platform().encode("utf-8")).hexdigest()[:16]


def artifact_key(model_file: Path, ort_version: str) -> str:
    """Stable id of (ORT build, CPU, source model). Any change means a rebuild."""
    st = model_file.stat()
    raw = "|".join(
        [
            ort_version,
            platform.machine(),
            _cpu_digest(),
            str(st.st_size),
            str(st.st_mtime_ns),
            "ENABLE_ALL",
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _build(model_file: Path, out_dir: Path) -> None:
    """Run one throwaway ORT load that serializes the optimized, prepacked model."""
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.intra_op_num_threads = 1
    so.inter_op_num_threads = 1
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    so.optimized_model_filepath = str(out_dir / _MODEL_NAME)
    so.add_session_config_entry(
        "session.optimized_model_external_initializers_file_name", _DATA_NAME
    )
    so.add_session_config_entry(
        "session.optimized_model_external_initializers_min_size_in_bytes", str(_EXTERNAL_MIN_BYTES)
    )
    so.add_session_config_entry("session.save_external_prepacked_constant_initializers", "1")
    session = ort.InferenceSession(
        str(model_file), sess_options=so, providers=["CPUExecutionProvider"]
    )
    del session  # release the ~1 GB private copy as soon as the files are written
    for name in (_MODEL_NAME, _DATA_NAME):
        if not (out_dir / name).is_file():
            raise RuntimeError(
                f"ONNX prepack build wrote no {name} in {out_dir}; "
                "refusing to serve from a partial artifact."
            )


def _build_in_subprocess(model_file: Path, out_dir: Path, timeout_s: float) -> None:
    """Build in a child so its ~1 GB transient heap never lingers in the serving process.

    Measured: building in-process left ~290 MB of anon heap behind (glibc does not
    return it), which would cancel part of the saving. The child is killed when it
    exceeds ``timeout_s`` (subprocess.run kills it on TimeoutExpired), so a stalled
    build cannot eat the startup budget silently: it raises ``PrepackError``.
    """
    cmd = [sys.executable, str(Path(__file__).resolve()), "--build", str(model_file), str(out_dir)]
    try:
        subprocess.run(cmd, check=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        raise PrepackError(f"ONNX prepack build exceeded {timeout_s:.0f}s and was killed") from exc
    except subprocess.CalledProcessError as exc:
        raise PrepackError(f"ONNX prepack build failed (exit {exc.returncode})") from exc


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_HASH_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_ready(directory: Path) -> None:
    """Record size + sha256 of both files. Hashing the data file reads all ~830 MB once."""
    record = {}
    for name in (_MODEL_NAME, _DATA_NAME):
        p = directory / name
        record[name] = {"bytes": p.stat().st_size, "sha256": _sha256_file(p)}
    (directory / _READY_NAME).write_text(json.dumps(record), encoding="utf-8")


def _integrity_problem(directory: Path, verify_data_hash: bool) -> str | None:
    """Return why the artifact must not be served, or None when it checks out."""
    try:
        record = json.loads((directory / _READY_NAME).read_text(encoding="utf-8"))
        for name in (_MODEL_NAME, _DATA_NAME):
            p = directory / name
            if p.stat().st_size != record[name]["bytes"]:
                return f"{name} size {p.stat().st_size} != recorded {record[name]['bytes']}"
        if _sha256_file(directory / _MODEL_NAME) != record[_MODEL_NAME]["sha256"]:
            return f"{_MODEL_NAME} sha256 mismatch"
        if (
            verify_data_hash
            and _sha256_file(directory / _DATA_NAME) != record[_DATA_NAME]["sha256"]
        ):
            return f"{_DATA_NAME} sha256 mismatch"
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return f"unreadable artifact or READY record: {exc!r}"
    return None


def _prune_cache(cache_root: Path, keep: Path) -> None:
    """Drop leftovers. Caller holds the build lock, so no builder is alive and every
    ``tmp.*`` dir is dead (SIGKILL/OOM skip ``finally``); older keys are superseded."""
    for entry in cache_root.iterdir():
        if entry.name == _LOCK_NAME or entry == keep or not entry.is_dir():
            continue
        logger.info("Removing stale ONNX prepack cache entry %s", entry.name)
        shutil.rmtree(entry)


def ensure_prepacked_model(
    model_file: Path,
    cache_root: Path,
    build_timeout_s: float,
    verify_data_hash: bool = True,
) -> Path:
    """Return the path of the mmap-able prepacked model, building it once if absent.

    Raises ``PrepackError`` on build failure, timeout, or an artifact that fails its
    integrity check right after being built. A cached artifact that fails the check is
    logged, removed and rebuilt; it is never served.
    """
    import onnxruntime as ort

    model_file = Path(model_file)
    if not model_file.is_file():
        raise FileNotFoundError(f"ONNX model not found for prepacking: {model_file}")
    cache_root.mkdir(parents=True, exist_ok=True)
    final_dir = cache_root / artifact_key(model_file, ort.__version__)
    ready = final_dir / _READY_NAME
    if ready.is_file() and _integrity_problem(final_dir, verify_data_hash) is None:
        return final_dir / _MODEL_NAME

    with open(cache_root / _LOCK_NAME, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # released when the file is closed
        if ready.is_file():  # another worker may have finished while we waited
            problem = _integrity_problem(final_dir, verify_data_hash)
            if problem is None:
                return final_dir / _MODEL_NAME
            logger.error(
                "ONNX prepack cache %s failed integrity (%s); rebuilding", final_dir.name, problem
            )
        tmp_dir = cache_root / f"{_TMP_PREFIX}{os.getpid()}.{uuid.uuid4().hex[:8]}"
        try:
            if final_dir.exists():
                shutil.rmtree(final_dir)
            _prune_cache(cache_root, keep=final_dir)
            tmp_dir.mkdir()
            logger.info("Building mmap-able ONNX prepacked model (one-off) for %s", model_file.name)
            _build_in_subprocess(model_file, tmp_dir, build_timeout_s)
            for name in (_MODEL_NAME, _DATA_NAME):
                if not (tmp_dir / name).is_file():
                    raise PrepackError(f"ONNX prepack build produced no {name}")
            _write_ready(tmp_dir)
            os.rename(tmp_dir, final_dir)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    return final_dir / _MODEL_NAME


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--build":
        _build(Path(sys.argv[2]), Path(sys.argv[3]))
        raise SystemExit(0)
    # Self-check (no model needed): the key is stable and separates ORT versions.
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "m.onnx"
        f.write_bytes(b"x" * 10)
        assert artifact_key(f, "1.30.0") == artifact_key(f, "1.30.0")
        assert artifact_key(f, "1.30.0") != artifact_key(f, "1.31.0")
    print("onnx_prepacked self-check ok")
