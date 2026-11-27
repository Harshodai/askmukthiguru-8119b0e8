"""Tests for the default-OFF mmap-prepacked ONNX encoder path (2026-11-27)."""

import subprocess
from pathlib import Path

import pytest

from app.config import Settings
from services import onnx_prepacked as op

TIMEOUT = 30.0


def test_flag_defaults_off() -> None:
    fields = Settings.model_fields
    assert fields["onnx_mmap_prepacked_enabled"].default is False
    assert fields["onnx_prepacked_cache_dir"].default == ""
    assert fields["onnx_prepacked_build_timeout_s"].default == 120.0
    assert fields["onnx_prepacked_verify_data_hash"].default is True


def _model(tmp_path: Path) -> Path:
    f = tmp_path / "model_quantized.onnx"
    if not f.exists():  # rewriting would change mtime, hence the cache key
        f.write_bytes(b"x" * 64)
    return f


def test_key_changes_with_ort_version_and_model(tmp_path: Path) -> None:
    f = _model(tmp_path)
    assert op.artifact_key(f, "1.30.0") == op.artifact_key(f, "1.30.0")
    assert op.artifact_key(f, "1.30.0") != op.artifact_key(f, "1.31.0")
    k = op.artifact_key(f, "1.30.0")
    f.write_bytes(b"y" * 65)
    assert op.artifact_key(f, "1.30.0") != k


def _fake_build(calls: list[Path]):
    def build(model_file: Path, out_dir: Path, timeout_s: float) -> None:
        calls.append(out_dir)
        (out_dir / op._MODEL_NAME).write_bytes(b"graph")
        (out_dir / op._DATA_NAME).write_bytes(b"weights")

    return build


def _ensure(tmp_path: Path, cache: Path, **kw) -> Path:
    return op.ensure_prepacked_model(_model(tmp_path), cache, TIMEOUT, **kw)


def test_builds_once_then_reuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Path] = []
    monkeypatch.setattr(op, "_build_in_subprocess", _fake_build(calls))
    cache = tmp_path / "cache"
    first = _ensure(tmp_path, cache)
    second = _ensure(tmp_path, cache)
    assert first == second and first.is_file()
    assert (first.parent / op._READY_NAME).is_file()
    assert len(calls) == 1
    assert not [p for p in cache.iterdir() if p.name.startswith(op._TMP_PREFIX)]


def test_failed_build_raises_and_publishes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(model_file: Path, out_dir: Path, timeout_s: float) -> None:
        raise op.PrepackError("build failed")

    monkeypatch.setattr(op, "_build_in_subprocess", boom)
    cache = tmp_path / "cache"
    with pytest.raises(op.PrepackError, match="build failed"):
        _ensure(tmp_path, cache)
    assert [p.name for p in cache.iterdir()] == [op._LOCK_NAME]


def test_missing_model_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        op.ensure_prepacked_model(tmp_path / "nope.onnx", tmp_path / "cache", TIMEOUT)


def test_subprocess_failure_and_timeout_become_prepack_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict = {}

    def fake_run(cmd, check, timeout):
        seen["cmd"], seen["check"], seen["timeout"] = cmd, check, timeout
        raise seen["exc"]

    monkeypatch.setattr(op.subprocess, "run", fake_run)
    seen["exc"] = subprocess.CalledProcessError(3, "x")
    with pytest.raises(op.PrepackError, match="exit 3"):
        op._build_in_subprocess(tmp_path / "m.onnx", tmp_path / "out", 7.5)
    assert seen["check"] is True and seen["timeout"] == 7.5 and "--build" in seen["cmd"]
    seen["exc"] = subprocess.TimeoutExpired("x", 7.5)
    with pytest.raises(op.PrepackError, match="exceeded"):
        op._build_in_subprocess(tmp_path / "m.onnx", tmp_path / "out", 7.5)


def test_stale_tmp_dirs_and_other_keys_are_pruned_before_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    for name in ("tmp.999.deadbeef", "oldkey0123456789abcd"):
        (cache / name).mkdir(parents=True)
        (cache / name / "model.onnx.data").write_bytes(b"leak")
    monkeypatch.setattr(op, "_build_in_subprocess", _fake_build([]))
    final = _ensure(tmp_path, cache).parent
    assert sorted(p.name for p in cache.iterdir()) == sorted([op._LOCK_NAME, final.name])


def test_ready_records_sizes_and_hashes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib
    import json

    monkeypatch.setattr(op, "_build_in_subprocess", _fake_build([]))
    d = _ensure(tmp_path, tmp_path / "cache").parent
    rec = json.loads((d / op._READY_NAME).read_text())
    assert rec[op._DATA_NAME] == {"bytes": 7, "sha256": hashlib.sha256(b"weights").hexdigest()}
    assert rec[op._MODEL_NAME]["bytes"] == 5


@pytest.mark.parametrize(
    "victim,payload,verify",
    [
        (op._DATA_NAME, b"short", True),  # size change, caught even without data hash
        (op._DATA_NAME, b"WEIGHTS", True),  # same size, bit flip: needs the data hash
        (op._MODEL_NAME, b"GRAPH", False),  # graph hash is always checked
    ],
)
def test_tampered_cache_is_rebuilt_never_served(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, victim: str, payload: bytes, verify: bool
) -> None:
    calls: list[Path] = []
    monkeypatch.setattr(op, "_build_in_subprocess", _fake_build(calls))
    cache = tmp_path / "cache"
    d = _ensure(tmp_path, cache, verify_data_hash=verify).parent
    (d / victim).write_bytes(payload)
    again = _ensure(tmp_path, cache, verify_data_hash=verify)
    assert len(calls) == 2  # rebuilt
    assert (again.parent / op._DATA_NAME).read_bytes() == b"weights"
    assert again.read_bytes() == b"graph"


def test_same_size_data_flip_is_not_caught_when_data_hash_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Documents the trade-off of onnx_prepacked_verify_data_hash=False."""
    calls: list[Path] = []
    monkeypatch.setattr(op, "_build_in_subprocess", _fake_build(calls))
    cache = tmp_path / "cache"
    d = _ensure(tmp_path, cache, verify_data_hash=False).parent
    (d / op._DATA_NAME).write_bytes(b"WEIGHTS")
    _ensure(tmp_path, cache, verify_data_hash=False)
    assert len(calls) == 1


def test_prepack_failure_never_triggers_hf_cache_wipe(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed prepack build must not reach _clear_hf_cache_for (it deletes the
    pinned BGE-M3 tokenizer snapshot the ONNX path depends on)."""
    from app.config import settings
    from services.embedding_service import EmbeddingService

    service = EmbeddingService()
    cleared: list[str] = []

    def fake_load_encoder(self, model_name, device):
        raise op.PrepackError("build timed out")

    monkeypatch.setattr(EmbeddingService, "_load_encoder", fake_load_encoder)
    monkeypatch.setattr(
        EmbeddingService, "_clear_hf_cache_for", lambda self, model_id: cleared.append(model_id)
    )
    monkeypatch.setattr(EmbeddingService, "_thread_setup", lambda self: None)
    monkeypatch.setattr(EmbeddingService, "_get_device", lambda self: "cpu")
    monkeypatch.setattr(settings, "embedding_model", "BAAI/bge-m3")
    monkeypatch.setattr(service, "_encoder", None)
    with pytest.raises(op.PrepackError):
        service._ensure_encoder()
    assert cleared == []
