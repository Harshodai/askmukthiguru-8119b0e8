"""NEW-RW-3 (RW-04): SIGTERM reaches the Celery child in worker and beat modes.

`start_railway.py` runs as PID 1. Linux ignores SIGTERM for a PID 1 process
that installed no handler, so before this change the Celery child never saw a
warm-shutdown signal and Railway's SIGKILL ended it (runbook G-4).

Each test starts a real harness process that imports `start_railway`, runs
`_supervise_celery_child` against a small fake child, and then receives a real
SIGTERM. Fake children only: no Celery, no broker, no LLM.

Edge cases covered (task NEW-RW-3):
- SIGTERM while a task is running: the child finishes the task, then exits 0.
- A second SIGTERM: it does not re-signal the child or cut the drain short.
- Beat holding its schedule file: it gets time to close it; a child that never
  exits is SIGKILLed once the grace period ends.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent

# The harness is the "PID 1" wrapper. It prints READY once the fake child is
# running, so the test never signals before the handler exists.
_HARNESS = textwrap.dedent(
    """
    import sys
    sys.path.insert(0, {backend!r})
    import start_railway

    child_script = sys.argv[1]
    grace = float(sys.argv[2])
    code = start_railway._supervise_celery_child(
        [sys.executable, "-u", child_script],
        label="test-child",
        grace_s=grace,
        on_started=lambda child: print("READY", flush=True),
    )
    print("EXIT", code, flush=True)
    sys.exit(code)
    """
).format(backend=str(BACKEND_DIR))

# Child that behaves like a Celery worker in warm shutdown: on SIGTERM it
# finishes the running "task" (0.6 s) and exits 0.
_WARM_CHILD = textwrap.dedent(
    """
    import signal, sys, time
    got = {"n": 0}
    def on_term(signum, frame):
        got["n"] += 1
        print("CHILD_TERM", got["n"], flush=True)
    signal.signal(signal.SIGTERM, on_term)
    print("CHILD_UP", flush=True)
    # A running task. The loop ends only after a SIGTERM and the task is done.
    deadline = None
    while True:
        time.sleep(0.05)
        if got["n"] and deadline is None:
            deadline = time.time() + 0.6   # finish the in-flight task
        if deadline is not None and time.time() >= deadline:
            print("CHILD_TASK_DONE", flush=True)
            sys.exit(0)
    """
)

# Child that never exits on SIGTERM (a wedged task or beat that cannot close).
_STUCK_CHILD = textwrap.dedent(
    """
    import signal, time
    signal.signal(signal.SIGTERM, lambda s, f: print("CHILD_TERM", flush=True))
    print("CHILD_UP", flush=True)
    while True:
        time.sleep(0.05)
    """
)


def _start(tmp_path: Path, child_src: str, grace: float) -> subprocess.Popen:
    harness = tmp_path / "harness.py"
    harness.write_text(_HARNESS)
    child = tmp_path / "child.py"
    child.write_text(child_src)
    proc = subprocess.Popen(
        [sys.executable, "-u", str(harness), str(child), str(grace)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(tmp_path),
    )
    # Wait for READY.
    deadline = time.time() + 20
    lines: list[str] = []
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        lines.append(line)
        if "READY" in line:
            proc._seen = lines  # type: ignore[attr-defined]
            return proc
    proc.kill()
    raise AssertionError("harness never printed READY:\n" + "".join(lines))


def _finish(proc: subprocess.Popen, timeout: float = 20) -> tuple[int, str]:
    out, _ = proc.communicate(timeout=timeout)
    return proc.returncode, "".join(proc._seen) + out  # type: ignore[attr-defined]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_sigterm_during_running_task_is_forwarded_and_child_finishes(tmp_path):
    proc = _start(tmp_path, _WARM_CHILD, grace=10)
    time.sleep(0.3)  # the child is inside its "task"
    proc.send_signal(signal.SIGTERM)
    code, out = _finish(proc)
    assert "CHILD_TERM 1" in out, out
    assert "CHILD_TASK_DONE" in out, out  # warm shutdown: the task completed
    assert code == 0, out


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_second_sigterm_is_not_forwarded_again(tmp_path):
    proc = _start(tmp_path, _WARM_CHILD, grace=10)
    time.sleep(0.3)
    proc.send_signal(signal.SIGTERM)
    time.sleep(0.1)
    proc.send_signal(signal.SIGTERM)  # second signal during the drain
    code, out = _finish(proc)
    assert out.count("CHILD_TERM") == 1, out  # child saw exactly one SIGTERM
    assert "CHILD_TASK_DONE" in out, out  # the second signal did not cut the drain
    assert code == 0, out


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_child_that_never_exits_is_killed_after_grace(tmp_path):
    proc = _start(tmp_path, _STUCK_CHILD, grace=1.0)
    time.sleep(0.3)
    started = time.time()
    proc.send_signal(signal.SIGTERM)
    code, out = _finish(proc)
    elapsed = time.time() - started
    assert "CHILD_TERM" in out, out
    assert 0.9 <= elapsed < 8, f"grace not honoured: {elapsed:.2f}s\n{out}"
    assert code != 0, out  # a forced kill must not look like a clean exit


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_child_exit_without_signal_returns_its_code(tmp_path):
    proc = _start(
        tmp_path,
        "import sys, time\nprint('CHILD_UP', flush=True)\ntime.sleep(0.3)\nsys.exit(7)\n",
        grace=5,
    )
    code, out = _finish(proc)
    assert code == 7, out


def test_shutdown_grace_parsing(monkeypatch):
    import start_railway as mod

    monkeypatch.delenv("CELERY_SHUTDOWN_GRACE_SECONDS", raising=False)
    assert mod.get_celery_shutdown_grace_s() == 25.0
    monkeypatch.setenv("CELERY_SHUTDOWN_GRACE_SECONDS", "50")
    assert mod.get_celery_shutdown_grace_s() == 50.0
    monkeypatch.setenv("CELERY_SHUTDOWN_GRACE_SECONDS", "  ")
    assert mod.get_celery_shutdown_grace_s() == 25.0
    for bad in ("0", "-3", "abc", "100000"):
        monkeypatch.setenv("CELERY_SHUTDOWN_GRACE_SECONDS", bad)
        with pytest.raises(SystemExit):
            mod.get_celery_shutdown_grace_s()


def test_beat_schedule_file_is_in_a_writable_directory():
    """The image runs as `appuser`, but `/app` is created by WORKDIR as root.
    Celery beat's default schedule file lands in the working directory, so
    beat must be told to write under /app/data (chowned to appuser)."""
    import start_railway as mod

    cmd = mod.build_celery_beat_command()
    assert "beat" in cmd
    schedule = cmd[cmd.index("--schedule") + 1] if "--schedule" in cmd else ""
    assert schedule.startswith("/app/data/"), cmd


def test_wrapper_has_signal_handler_code_for_celery_modes():
    """Guard against a revert to bare `subprocess.run`/`Popen().wait()`."""
    src = (BACKEND_DIR / "start_railway.py").read_text()
    assert "signal.signal(" in src
    assert "subprocess.run(" not in src
    assert os.path.exists(BACKEND_DIR / "start_railway.py")
