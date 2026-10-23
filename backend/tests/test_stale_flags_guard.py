"""scripts/guards/stale_flags.py: a dead boolean flag fails, a read flag does not."""

import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location(
        "stale_flags", ROOT / "scripts/guards/stale_flags.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_repo_has_no_new_unused_flag():
    result = subprocess.run(
        ["python3", str(ROOT / "scripts/guards/stale_flags.py")], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_unused_flag_is_detected_and_read_flag_is_not(tmp_path, monkeypatch):
    mod = _load()
    cfg = tmp_path / "backend/app/config.py"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        "class Settings:\n    dead_flag_enabled: bool = True\n    live_flag_enabled: bool = False\n"
    )
    (tmp_path / "backend/app/use.py").write_text("if settings.live_flag_enabled:\n    pass\n")
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "CONFIG", cfg)
    monkeypatch.setattr(mod, "ALLOW", tmp_path / "allow.txt")
    monkeypatch.setattr(
        mod, "tracked_files", lambda: ["backend/app/config.py", "backend/app/use.py"]
    )
    report = mod.analyse()
    assert report["dead_flag_enabled"]["kind"] == "UNUSED"
    assert "live_flag_enabled" not in report
    assert mod.main([]) == 1
