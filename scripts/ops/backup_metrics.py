"""Write `backup_last_success_timestamp_seconds` for one backup target.

NEW-OPS-4 (OPS-007). Call `record_backup_success` only AFTER the artefact is
verified (size above zero, checksum, test restore). A backup that fails
verification must not refresh the timestamp: `BackupStale` in
`infrastructure/prometheus/alerting-rules.yml` reads it.

Two sinks, both optional:

- Textfile: `BACKUP_METRICS_DIR/backup_last_success__<store>__<target>.prom`,
  written atomically, for a node_exporter textfile collector on the backup host.
- Pushgateway: `PUSHGATEWAY_URL` (HTTP PUT of the same text).

With neither set the function warns and returns False. The alert then reads an
absent series and fires, which is the honest result: nothing is reporting.

Standard library only, so cron hosts need no virtualenv.
"""

from __future__ import annotations

import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

METRIC = "backup_last_success_timestamp_seconds"
_SAFE = re.compile(r"^[A-Za-z0-9_.:-]+$")


def render(store: str, target: str, timestamp: float) -> str:
    for label, value in (("store", store), ("target", target)):
        if not _SAFE.match(value):
            raise ValueError(f"unsafe {label} label for a metric: {value!r}")
    return (
        f"# HELP {METRIC} Unix time of the last backup that passed verification\n"
        f"# TYPE {METRIC} gauge\n"
        f'{METRIC}{{store="{store}",target="{target}"}} {int(timestamp)}\n'
    )


def _write_textfile(directory: Path, store: str, target: str, text: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    final = directory / f"backup_last_success__{store}__{target}.prom"
    tmp = final.with_name(final.name + f".tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, final)  # atomic: the collector never reads a half-written file
    return final


def _push(url: str, store: str, target: str, text: str) -> None:
    path = "/metrics/job/backup/store/{}/target/{}".format(
        urllib.parse.quote(store, safe=""), urllib.parse.quote(target, safe="")
    )
    req = urllib.request.Request(
        url.rstrip("/") + path,
        data=text.encode("utf-8"),
        method="PUT",
        headers={"Content-Type": "text/plain; version=0.0.4"},
    )
    with urllib.request.urlopen(req, timeout=15):  # nosec B310 -- operator backup tool, URL from env
        pass


def record_backup_success(
    store: str,
    target: str,
    *,
    now: float | None = None,
    textfile_dir: str | None = None,
    pushgateway_url: str | None = None,
) -> bool:
    """Return True when at least one sink took the timestamp."""
    text = render(store, target, time.time() if now is None else now)
    directory = textfile_dir if textfile_dir is not None else os.environ.get("BACKUP_METRICS_DIR")
    gateway = pushgateway_url if pushgateway_url is not None else os.environ.get("PUSHGATEWAY_URL")
    wrote = False
    if directory:
        try:
            path = _write_textfile(Path(directory), store, target, text)
            print(f"  [+] Backup timestamp written: {path}")
            wrote = True
        except OSError as exc:
            print(f"  [!] Could not write the textfile metric: {exc}")
    if gateway:
        try:
            _push(gateway, store, target, text)
            print("  [+] Backup timestamp pushed to the Pushgateway")
            wrote = True
        except (urllib.error.URLError, OSError) as exc:
            print(f"  [!] Could not push to the Pushgateway: {exc}")
    if not wrote:
        print(
            f"  [!] {METRIC} not reported: set BACKUP_METRICS_DIR or PUSHGATEWAY_URL. "
            "BackupStale will read an absent series."
        )
    return wrote
