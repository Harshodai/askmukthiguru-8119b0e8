"""NEW-OPS-4 (OPS-007): `scripts/ops/backup_qdrant.py` and its cron file.

What the audit found and what these tests prove, against a fake Qdrant HTTP
server (no real Qdrant, no network beyond 127.0.0.1):

- The script never sent an API key, so it failed against a keyed Qdrant.
- The cron file pinned `first_person_v7`, so after a v10 promotion the nightly
  job kept backing up a collection that is no longer served.
- No job wrote `backup_last_success_timestamp_seconds`, so `BackupStale` read an
  absent series. The timestamp must be written only AFTER the artefact verifies.

Not proven here: a real Qdrant snapshot restore, the cron install on a host, a
Prometheus scrape of the textfile. Those need the owner's host (UNPROVEN).
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
OPS_DIR = REPO_ROOT / "scripts" / "ops"
CRON = REPO_ROOT / "infrastructure" / "cron" / "mukthiguru-backup"


def _snapshot_bytes() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        data = b"{}"
        info = tarfile.TarInfo("config.json")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class FakeQdrant:
    """Records every request. `points` is what a restore reports back."""

    def __init__(self, *, points: int = 7, restored_points: int | None = None, corrupt=False):
        self.points = points
        self.restored_points = points if restored_points is None else restored_points
        self.corrupt = corrupt
        self.requests: list[tuple[str, str, str | None]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep test output quiet
                pass

            def _reply(self, payload: dict | bytes, status: int = 200):
                body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _handle(self):
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
                owner.requests.append((self.command, self.path, self.headers.get("api-key")))
                parts = self.path.split("?")[0].strip("/").split("/")
                if self.command == "POST" and parts[-1] == "snapshots":
                    return self._reply({"result": {"name": "snap-1.snapshot"}})
                if self.command == "GET" and len(parts) == 4 and parts[2] == "snapshots":
                    return self._reply(b"not a tar" if owner.corrupt else _snapshot_bytes())
                if self.command == "POST" and parts[-1] == "upload":
                    return self._reply({"result": True})
                if self.command in ("PUT", "DELETE"):
                    return self._reply({"result": True})
                if self.command == "GET" and parts[0] == "collections" and len(parts) == 2:
                    count = (
                        owner.restored_points if parts[1].startswith("_verify_") else owner.points
                    )
                    return self._reply(
                        {
                            "result": {
                                "status": "green",
                                "points_count": count,
                                "config": {
                                    "params": {"vectors": {"size": 4, "distance": "Cosine"}}
                                },
                            }
                        }
                    )
                return self._reply({"error": "unexpected"}, 404)

            do_GET = do_POST = do_PUT = do_DELETE = _handle

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def _load_script(monkeypatch, tmp_path, qdrant_url: str, **env):
    monkeypatch.setenv("QDRANT_URL", qdrant_url)
    monkeypatch.setenv("BACKUP_BASE_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("BACKUP_METRICS_DIR", str(tmp_path / "metrics"))
    for name in ("QDRANT_API_KEY", "QDRANT_WRITE_API_KEY", "PUSHGATEWAY_URL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.syspath_prepend(str(OPS_DIR))
    spec = importlib.util.spec_from_file_location(
        "backup_qdrant_under_test", OPS_DIR / "backup_qdrant.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def fake():
    server = FakeQdrant()
    yield server
    server.close()


def _prom_files(tmp_path: Path) -> list[Path]:
    d = tmp_path / "metrics"
    return sorted(d.glob("*.prom")) if d.exists() else []


def test_backup_sends_the_api_key_on_every_request(monkeypatch, tmp_path, fake):
    mod = _load_script(monkeypatch, tmp_path, fake.url, QDRANT_API_KEY="read-write-key")
    assert mod.backup("first_person_v10", retention=3) is True
    assert fake.requests, "no request reached the fake Qdrant"
    without_key = [(m, p) for m, p, key in fake.requests if key != "read-write-key"]
    assert not without_key, f"requests sent without the API key: {without_key}"


def test_write_key_wins_over_the_shared_key(monkeypatch, tmp_path, fake):
    """Creating a snapshot needs the write key; the backend never holds it."""
    mod = _load_script(
        monkeypatch, tmp_path, fake.url, QDRANT_API_KEY="shared", QDRANT_WRITE_API_KEY="write"
    )
    assert mod.backup("first_person_v10", retention=3) is True
    assert {key for _, _, key in fake.requests} == {"write"}


def test_no_key_set_sends_no_key_header(monkeypatch, tmp_path, fake):
    mod = _load_script(monkeypatch, tmp_path, fake.url)
    assert mod.backup("first_person_v10", retention=3) is True
    assert {key for _, _, key in fake.requests} == {None}


def test_verified_backup_writes_the_success_timestamp(monkeypatch, tmp_path, fake):
    mod = _load_script(monkeypatch, tmp_path, fake.url)
    assert mod.backup("first_person_v10", retention=3) is True
    files = _prom_files(tmp_path)
    assert len(files) == 1, files
    text = files[0].read_text(encoding="utf-8")
    assert "# TYPE backup_last_success_timestamp_seconds gauge" in text
    match = re.search(
        r'backup_last_success_timestamp_seconds\{store="qdrant",target="first_person_v10"\} (\d+)',
        text,
    )
    assert match, text
    assert int(match.group(1)) > 1_700_000_000


def test_corrupt_artefact_writes_no_timestamp_and_is_not_kept_as_a_good_backup(
    monkeypatch, tmp_path
):
    bad = FakeQdrant(corrupt=True)
    try:
        mod = _load_script(monkeypatch, tmp_path, bad.url)
        assert mod.backup("first_person_v10", retention=3) is False
    finally:
        bad.close()
    assert _prom_files(tmp_path) == []
    kept = list((tmp_path / "backups").glob("first_person_v10_*.snapshot"))
    assert kept == [], f"a failed artefact must not count toward retention: {kept}"


def test_point_count_mismatch_writes_no_timestamp(monkeypatch, tmp_path):
    drifted = FakeQdrant(points=7, restored_points=3)
    try:
        mod = _load_script(monkeypatch, tmp_path, drifted.url)
        assert mod.backup("first_person_v10", retention=3) is False
    finally:
        drifted.close()
    assert _prom_files(tmp_path) == []


def test_unreachable_qdrant_writes_no_timestamp(monkeypatch, tmp_path):
    mod = _load_script(monkeypatch, tmp_path, "http://127.0.0.1:9")
    assert mod.backup("first_person_v10", retention=3) is False
    assert _prom_files(tmp_path) == []


def test_serving_collections_come_from_settings_not_a_pinned_name():
    import importlib.util as iu

    spec = iu.spec_from_file_location("bq_resolve", OPS_DIR / "backup_qdrant.py")
    mod = iu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cfg = SimpleNamespace(
        first_person_collection="first_person_v10",
        first_person_context_collection="first_person_v10",
    )
    assert mod.resolve_serving_collections(cfg) == ["first_person_v10"]
    cfg = SimpleNamespace(
        first_person_collection="first_person_v8",
        first_person_context_collection="first_person_v10",
    )
    assert mod.resolve_serving_collections(cfg) == ["first_person_v8", "first_person_v10"]
    empty = SimpleNamespace(first_person_collection="", first_person_context_collection=" ")
    with pytest.raises(SystemExit):
        mod.resolve_serving_collections(empty)


def test_cron_does_not_pin_a_versioned_first_person_collection():
    code = [
        ln
        for ln in CRON.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    pinned = [ln for ln in code if re.search(r"first_person_v\d+", ln)]
    assert not pinned, f"cron pins a collection name: {pinned}"
    assert any("backup_qdrant.py --serving" in ln for ln in code), "no serving-collection job"


def test_cron_env_documents_the_api_key_and_metrics_dir():
    text = CRON.read_text(encoding="utf-8")
    for name in ("QDRANT_WRITE_API_KEY", "BACKUP_METRICS_DIR"):
        assert name in text, f"{name} is not documented in the cron install notes"


# --- scripts/ops/backup_metrics.py ------------------------------------------


def _metrics_module(monkeypatch):
    monkeypatch.syspath_prepend(str(OPS_DIR))
    spec = importlib.util.spec_from_file_location("bm_under_test", OPS_DIR / "backup_metrics.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_metric_name_matches_the_alert_rule(monkeypatch):
    mod = _metrics_module(monkeypatch)
    rules = (REPO_ROOT / "infrastructure/prometheus/alerting-rules.yml").read_text(encoding="utf-8")
    assert mod.METRIC in rules


def test_textfile_is_written_atomically_and_replaced(monkeypatch, tmp_path):
    mod = _metrics_module(monkeypatch)
    assert mod.record_backup_success("qdrant", "c1", now=1_800_000_000, textfile_dir=str(tmp_path))
    assert mod.record_backup_success("qdrant", "c1", now=1_800_000_100, textfile_dir=str(tmp_path))
    files = list(tmp_path.iterdir())
    assert [f.name for f in files] == ["backup_last_success__qdrant__c1.prom"], files
    assert "1800000100" in files[0].read_text(encoding="utf-8")


def test_no_sink_returns_false_and_says_so(monkeypatch, capsys):
    mod = _metrics_module(monkeypatch)
    monkeypatch.delenv("BACKUP_METRICS_DIR", raising=False)
    monkeypatch.delenv("PUSHGATEWAY_URL", raising=False)
    assert mod.record_backup_success("qdrant", "c1") is False
    assert "BackupStale" in capsys.readouterr().out


def test_unsafe_label_value_is_refused(monkeypatch, tmp_path):
    mod = _metrics_module(monkeypatch)
    with pytest.raises(ValueError):
        mod.record_backup_success("qdrant", 'x"} 1\n#', textfile_dir=str(tmp_path))


def test_pushgateway_receives_a_put_with_the_sample(monkeypatch):
    mod = _metrics_module(monkeypatch)
    seen: list[tuple[str, str, str]] = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_PUT(self):
            body = self.rfile.read(int(self.headers["Content-Length"])).decode()
            seen.append((self.command, self.path, body))
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        assert mod.record_backup_success("graph", "neo4j", now=1_800_000_000, pushgateway_url=url)
    finally:
        srv.shutdown()
        srv.server_close()
    assert seen and seen[0][0] == "PUT"
    assert seen[0][1] == "/metrics/job/backup/store/graph/target/neo4j"
    assert 'store="graph",target="neo4j"} 1800000000' in seen[0][2]


def test_neo4j_dump_job_reports_only_after_verification():
    src = (OPS_DIR / "backup_neo4j.py").read_text(encoding="utf-8")
    verify = src.index("ok = verify_dump(host_dest)")
    report = src.index('record_backup_success("graph", "neo4j")')
    assert report > verify
