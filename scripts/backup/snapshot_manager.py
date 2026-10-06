#!/usr/bin/env python3
"""
AskMukthiGuru — Dynamic Snapshot & Restore Manager
==================================================
Automates taking complete, production-grade backups and restoring data for:
  1. Qdrant (Vector Collection Snapshots via REST API)
  2. The graph (Memgraph `DUMP DATABASE` via mgconsole; legacy Neo4j via APOC)
  3. Supabase (Local Postgres schemas/data via Docker pg_dump)

Exit status is the contract the Makefile relies on: non-zero whenever a
required store could not be backed up or restored, so `make clean` and
`make docker-rebuild` refuse to delete volumes they could not save. Supabase is
optional (the local Supabase stack is often not running) and reports SKIPPED
rather than failing when its container is absent.

Usage:
    # Take a backup of all three databases
    python3 scripts/backup/snapshot_manager.py backup

    # Restore all databases from backup files
    python3 scripts/backup/snapshot_manager.py restore
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

# Host service endpoints
QDRANT_HOST_URL = os.environ.get("QDRANT_URL", "http://localhost:6333").rstrip("/")

# The graph container. Memgraph replaced Neo4j on 2026-09-19 and the `neo4j`
# compose service now sits behind the `legacy-neo4j` profile, so it is not
# running in a default `docker compose up`. Defaulting to the old container
# name made every graph backup a silent no-op against a container that does
# not exist. Both speak Bolt and ship cypher-shell, so the commands below are
# unchanged. Override with GRAPH_CONTAINER when running the legacy profile.
NEO4J_CONTAINER = os.environ.get("GRAPH_CONTAINER", "mukthiguru-memgraph")
NEO4J_PASS = os.environ["NEO4J_PASSWORD"]  # required

# Collections to snapshot. `make clean`/`make docker-rebuild` call this script
# as their protective backup before destroying volumes, so anything missing
# here is data the safety net does not actually save. The old single
# "spiritual_wisdom" default covered neither the live corpus collection nor
# the first-person teacher clips.
DEFAULT_COLLECTIONS = [
    os.environ.get("QDRANT_COLLECTION", "spiritual_wisdom_contextual"),
    os.environ.get("FIRST_PERSON_COLLECTION", "first_person_v7"),
]

# Backup directories on host
BACKUP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backups"))


def qdrant_backup_path(collection_name):
    """One snapshot file per collection, named after it."""
    return os.path.join(BACKUP_DIR, "qdrant", f"{collection_name}.snapshot")


NEO4J_BACKUP_PATH = os.path.join(BACKUP_DIR, "neo4j", "backup.cypher")
SUPABASE_BACKUP_PATH = os.path.join(BACKUP_DIR, "supabase", "data.sql")


def setup_directories():
    """Ensure all host backup directories exist."""
    os.makedirs(os.path.join(BACKUP_DIR, "qdrant"), exist_ok=True)
    os.makedirs(os.path.dirname(NEO4J_BACKUP_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(SUPABASE_BACKUP_PATH), exist_ok=True)
    print(f"[*] Backup directories established under: {BACKUP_DIR}")


def get_supabase_container():
    """Dynamically discover the running Supabase Postgres container name."""
    try:
        cmd = [
            "docker",
            "ps",
            "-a",
            "--filter",
            "ancestor=public.ecr.aws/supabase/postgres:17.6.1.106",
            "--format",
            "{{.Names}}",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        container_name = result.stdout.strip().split("\n")[0]
        if container_name:
            return container_name
    except Exception:
        pass

    # Fallback to name-based filter
    try:
        cmd = [
            "docker",
            "ps",
            "-a",
            "--filter",
            "name=supabase_db",
            "--format",
            "{{.Names}}",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        container_name = result.stdout.strip().split("\n")[0]
        if container_name:
            return container_name
    except Exception:
        pass

    return None


# ─── Qdrant Backup & Restore ──────────────────────────────────────────────────


def backup_qdrant(collection_name=None):
    """Create a collection snapshot and download it to the host."""
    collection_name = collection_name or DEFAULT_COLLECTIONS[0]
    snapshot_path = qdrant_backup_path(collection_name)
    print(f"\n[Qdrant] Starting backup of collection '{collection_name}'...")

    # 1. Trigger snapshot generation
    snapshot_url = f"{QDRANT_HOST_URL}/collections/{collection_name}/snapshots"
    req = urllib.request.Request(snapshot_url, method="POST")

    try:
        with urllib.request.urlopen(req) as res:
            resp_data = json.loads(res.read().decode())
            snapshot_name = resp_data["result"]["name"]
            print(f"  [+] Snapshot successfully created: {snapshot_name}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # A collection that does not exist holds nothing to lose.
            print(f"  [*] Collection '{collection_name}' does not exist. SKIPPED.")
            return None
        print(f"  [-] Qdrant refused the snapshot: HTTP {e.code} {e.reason}")
        return False
    except urllib.error.URLError as e:
        print(f"  [-] Connection to Qdrant failed. Is Qdrant running? {e}")
        return False
    except Exception as e:
        print(f"  [-] Failed to trigger Qdrant snapshot: {e}")
        return False

    # 2. Download the created snapshot
    download_url = f"{QDRANT_HOST_URL}/collections/{collection_name}/snapshots/{snapshot_name}"
    print(f"  [*] Downloading snapshot from Qdrant: {download_url}")

    try:
        urllib.request.urlretrieve(download_url, snapshot_path)
        print(
            f"  [✅] Qdrant backup saved: {snapshot_path} ({os.path.getsize(snapshot_path) / 1024 / 1024:.2f} MB)"
        )
        return True
    except Exception as e:
        print(f"  [-] Failed to download Qdrant snapshot: {e}")
        return False


def restore_qdrant(collection_name=None):
    """Upload and restore collection from snapshot."""
    collection_name = collection_name or DEFAULT_COLLECTIONS[0]
    snapshot_path = qdrant_backup_path(collection_name)
    print(f"\n[Qdrant] Restoring collection '{collection_name}' from snapshot...")

    if not os.path.exists(snapshot_path):
        print(f"  [*] No snapshot at {snapshot_path} (collection was absent at backup). SKIPPED.")
        return None

    # Standard multipart form data upload implementation using only standard library
    try:
        # Load snapshot file
        with open(snapshot_path, "rb") as f:
            snapshot_bytes = f.read()

        boundary = b"----WebKitFormBoundaryAskMukthiGuruBackup"
        parts = []
        parts.append(b"--" + boundary)
        parts.append(
            f'Content-Disposition: form-data; name="snapshot"; filename="{collection_name}.snapshot"'.encode()
        )
        parts.append(b"Content-Type: application/octet-stream")
        parts.append(b"")
        parts.append(snapshot_bytes)
        parts.append(b"--" + boundary + b"--")
        parts.append(b"")
        body = b"\r\n".join(parts)

        # Upload and recover snapshot
        upload_url = (
            f"{QDRANT_HOST_URL}/collections/{collection_name}/snapshots/upload?priority=snapshot"
        )
        req = urllib.request.Request(
            upload_url,
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary.decode()}",
                "Content-Length": str(len(body)),
            },
            method="POST",
        )

        print("  [*] Uploading snapshot to Qdrant collection...")
        with urllib.request.urlopen(req) as res:
            resp_data = json.loads(res.read().decode())
            if resp_data.get("status") == "ok":
                print(
                    f"  [✅] Qdrant collection '{collection_name}' successfully restored from snapshot!"
                )
                return True
            else:
                print(f"  [-] Qdrant restoration failed: {resp_data}")
                return False
    except Exception as e:
        print(f"  [-] Qdrant snapshot upload error: {e}")
        return False


# ─── Graph (Memgraph / legacy Neo4j) Backup & Restore ─────────────────────────
#
# Memgraph replaced Neo4j on 2026-09-19. It has no APOC and does not ship
# cypher-shell, so the old `CALL apoc.export.cypher.all` path failed on every
# default stack (verified 2026-10-05 against memgraph/memgraph-mage:latest:
# `cypher-shell` is not in the image). Memgraph's own `DUMP DATABASE;` through
# mgconsole produces a replayable cypherl file. The APOC path is kept for the
# `legacy-neo4j` profile.

GRAPH_USER = os.environ.get("NEO4J_USER", "neo4j")
_COUNT_QUERY = "MATCH (n) RETURN count(n) AS c;"


def _container_running(name):
    try:
        out = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip() == "true"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _graph_engine():
    """'memgraph' or 'neo4j', by which CLI the container ships; None if neither."""
    for engine, binary in (("memgraph", "mgconsole"), ("neo4j", "cypher-shell")):
        probe = subprocess.run(
            ["docker", "exec", NEO4J_CONTAINER, "sh", "-c", f"command -v {binary}"],
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0 and probe.stdout.strip():
            return engine
    return None


def _graph_run(engine, query, *extra):
    """Pipe one script into the CLI. mgconsole silently executes nothing (and
    exits 0) when the last statement has no trailing newline, which reads
    exactly like an empty graph, so the newline is not optional."""
    return subprocess.run(
        _graph_cli(engine, *extra),
        input=query.rstrip("\n") + "\n",
        capture_output=True,
        text=True,
        check=True,
    )


def _graph_cli(engine, *extra):
    if engine == "memgraph":
        return [
            "docker", "exec", "-i", NEO4J_CONTAINER, "mgconsole",
            "--username", GRAPH_USER, "--password", NEO4J_PASS, *extra,
        ]
    return [
        "docker", "exec", "-i", NEO4J_CONTAINER, "cypher-shell",
        "-u", GRAPH_USER, "-p", NEO4J_PASS, *extra,
    ]


def _graph_node_count(engine):
    """Live node count, or None when the query itself fails."""
    extra = ("--output-format=csv",) if engine == "memgraph" else ("--format", "plain")
    try:
        out = _graph_run(engine, _COUNT_QUERY, *extra)
    except subprocess.CalledProcessError as e:
        print(f"  [-] Graph count query failed: {(e.stderr or e.stdout).strip()}")
        return None
    for line in reversed(out.stdout.strip().splitlines()):
        token = line.strip().strip('"')
        if token.isdigit():
            return int(token)
    return None


def _recorded_node_count(text):
    first = text.splitlines()[0] if text else ""
    marker = "nodes="
    if first.startswith("//") and marker in first:
        value = first.split(marker, 1)[1].split()[0]
        if value.isdigit():
            return int(value)
    return None


def _neo4j_apoc_export():
    """Legacy Neo4j path: APOC plain-cypher stream through cypher-shell."""
    cypher_query = (
        "CALL apoc.export.cypher.all(null, {stream: true, format: 'plain'}) "
        "YIELD cypherStatements RETURN cypherStatements"
    )
    result = _graph_run("neo4j", cypher_query)
    # The single cypherStatements value spans many physical lines and
    # cypher-shell wraps it in one outer quote pair: strip that pair once.
    body_lines = result.stdout.strip().split("\n")[1:]
    if body_lines and body_lines[0].startswith('"'):
        body_lines[0] = body_lines[0][1:]
    if body_lines and body_lines[-1].endswith('"'):
        body_lines[-1] = body_lines[-1][:-1]
    return "".join(line.replace('\\"', '"').replace("\\n", "\n") + "\n" for line in body_lines)


def backup_neo4j():
    """Dump the graph to NEO4J_BACKUP_PATH. False means the graph is NOT saved.

    An empty dump only counts as success when the live graph really has zero
    nodes; a dump that comes back empty from a populated graph is a failure,
    never a silently "successful" empty file.
    """
    print(f"\n[Graph] Backing up '{NEO4J_CONTAINER}'...")
    if not _container_running(NEO4J_CONTAINER):
        print(
            f"  [-] Container '{NEO4J_CONTAINER}' is not running, so its data cannot be "
            "dumped. Start it (or set GRAPH_CONTAINER) and retry."
        )
        return False

    engine = _graph_engine()
    if engine is None:
        print(f"  [-] '{NEO4J_CONTAINER}' ships neither mgconsole nor cypher-shell.")
        return False

    nodes = _graph_node_count(engine)
    if nodes is None:
        print("  [-] Could not count graph nodes (check NEO4J_PASSWORD / NEO4J_USER).")
        return False

    try:
        if engine == "memgraph":
            dump = _graph_run(engine, "DUMP DATABASE;", "--output-format=cypherl").stdout
        else:
            dump = _neo4j_apoc_export()
    except subprocess.CalledProcessError as e:
        print(f"  [-] Graph dump failed: {(e.stderr or e.stdout).strip()}")
        return False

    if nodes > 0 and "CREATE" not in dump:
        print(f"  [-] Graph has {nodes} nodes but the dump is empty. Refusing to call this a backup.")
        return False

    header = f"// engine={engine} nodes={nodes} taken={time.strftime('%Y-%m-%dT%H:%M:%S')}\n"
    with open(NEO4J_BACKUP_PATH, "w", encoding="utf-8") as f:
        f.write(header + dump)
    print(
        f"  [✅] Graph backup saved: {NEO4J_BACKUP_PATH} "
        f"({nodes} nodes, {len(dump.splitlines())} statements, engine={engine})"
    )
    return True


def restore_neo4j():
    """Replay the dump into an EMPTY graph, then check the node count came back.

    Replaying into a populated graph would duplicate every node, so a graph that
    already holds data is left alone (reported, not overwritten).
    """
    print("\n[Graph] Restoring from backup...")
    if not os.path.exists(NEO4J_BACKUP_PATH):
        print(f"  [-] Graph backup not found at {NEO4J_BACKUP_PATH}.")
        return False
    with open(NEO4J_BACKUP_PATH, encoding="utf-8") as f:
        content = f.read()
    expected = _recorded_node_count(content)
    statements = "\n".join(
        line for line in content.splitlines() if line.strip() and not line.startswith("//")
    )
    if not statements:
        print("  [*] Backup records an empty graph; nothing to replay.")
        return True

    if not _container_running(NEO4J_CONTAINER):
        print(f"  [-] Container '{NEO4J_CONTAINER}' is not running.")
        return False
    engine = _graph_engine()
    if engine is None:
        print(f"  [-] '{NEO4J_CONTAINER}' ships neither mgconsole nor cypher-shell.")
        return False

    current = _graph_node_count(engine)
    if current is None:
        return False
    if current > 0:
        print(
            f"  [*] Graph already holds {current} nodes; not replaying over it "
            "(that would duplicate every node)."
        )
        return True

    try:
        _graph_run(engine, statements)
    except subprocess.CalledProcessError as e:
        print(f"  [-] Graph replay failed: {(e.stderr or e.stdout).strip()}")
        return False

    after = _graph_node_count(engine)
    if expected is not None and (after is None or after < expected):
        print(f"  [-] Replay finished but the graph has {after} nodes; backup recorded {expected}.")
        return False
    print(f"  [✅] Graph restored ({after} nodes).")
    return True


# ─── Supabase Backup & Restore ────────────────────────────────────────────────


def backup_supabase():
    """Perform pg_dump on the dynamic Supabase Postgres container."""
    print("\n[Supabase] Starting Postgres database backup...")

    container = get_supabase_container()
    if not container:
        print("  [*] No Supabase Postgres container found. SKIPPED (optional).")
        return None

    print(f"  [+] Identified Supabase container: {container}")

    # We use --data-only and --disable-triggers to securely extract seed data without breaking foreign key orders
    cmd = [
        "docker",
        "exec",
        container,
        "pg_dump",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "--data-only",
        "--schema=public",
        "--disable-triggers",
    ]

    try:
        print("  [*] Generating pg_dump seed SQL...")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        sql_data = result.stdout

        # Save to host backups path
        with open(SUPABASE_BACKUP_PATH, "w", encoding="utf-8") as f:
            f.write(sql_data)

        print(
            f"  [✅] Supabase backup saved: {SUPABASE_BACKUP_PATH} ({os.path.getsize(SUPABASE_BACKUP_PATH)/1024:.2f} KB)"
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [-] pg_dump execution failed: {e.stderr}")
        return False
    except Exception as e:
        print(f"  [-] Supabase backup error: {e}")
        return False


def restore_supabase():
    """Restore Supabase seed data inside the container."""
    print("\n[Supabase] Restoring seed data into database...")

    container = get_supabase_container()
    if not container:
        print("  [*] No Supabase Postgres container found. SKIPPED (optional).")
        return None

    if not os.path.exists(SUPABASE_BACKUP_PATH):
        print(f"  [*] No Supabase backup at {SUPABASE_BACKUP_PATH}. SKIPPED (optional).")
        return None

    with open(SUPABASE_BACKUP_PATH, encoding="utf-8") as f:
        sql_content = f.read().strip()

    if not sql_content:
        print("  [*] Backup SQL is empty. Skipping execution.")
        return True

    try:
        # Stream the SQL seed statements straight into psql in the container
        cmd = [
            "docker",
            "exec",
            "-i",
            container,
            "psql",
            "-U",
            "postgres",
            "-d",
            "postgres",
        ]

        print("  [*] Running psql data import script inside container...")
        result = subprocess.run(cmd, input=sql_content, capture_output=True, text=True, check=True)
        print("  [✅] Supabase data successfully restored!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [-] psql restoration failed: {e.stderr or e.stdout}")
        return False
    except Exception as e:
        print(f"  [-] Supabase restoration error: {e}")
        return False


# ─── Orchestrator Command Line Entry ──────────────────────────────────────────


def _summarise(label, results, start_time):
    """Print a summary and return the process exit code.

    True = done, None = optional store skipped, False = failed. Any False
    means exit 1: callers that delete volumes must stop.
    """
    print("\n" + "=" * 80)
    print(f"   {label} SUMMARY")
    print("=" * 80)
    words = {True: "[OK] DONE", None: "[--] SKIPPED (optional)", False: "[FAIL] FAILED"}
    for name, ok in results.items():
        print(f"  - {name:<40} {words[ok]}")
    print(f"  - Elapsed: {time.time() - start_time:.1f} seconds")
    print("=" * 80)
    failed = [name for name, ok in results.items() if ok is False]
    if failed:
        print(f"[FAIL] {label} incomplete: {', '.join(failed)}")
        return 1
    return 0



def main():
    parser = argparse.ArgumentParser(description="AskMukthiGuru — Backup & Restore Manager")
    parser.add_argument("action", choices=["backup", "restore"], help="Action to execute")
    parser.add_argument(
        "--collection",
        action="append",
        dest="collections",
        help="Qdrant collection to snapshot; repeatable. Defaults to the live "
        f"corpus and first-person clip collections ({', '.join(DEFAULT_COLLECTIONS)}).",
    )

    args = parser.parse_args()

    # Docker Desktop on macOS installs its CLI outside the default PATH.
    # Prepend it only when it exists, so this script also runs on Linux/CI.
    _mac_docker_bin = os.path.expanduser("~/.docker/bin")
    if os.path.isdir(_mac_docker_bin):
        os.environ["PATH"] = _mac_docker_bin + os.pathsep + os.environ.get("PATH", "")

    collections = args.collections or DEFAULT_COLLECTIONS

    setup_directories()

    start_time = time.time()

    if args.action == "backup":
        print("\n" + "=" * 80)
        print("   INITIATING MUKTHI GURU COMPREHENSIVE BACKUP PIPELINE")
        print("=" * 80)

        results = {f"Qdrant {c}": backup_qdrant(c) for c in collections}
        results["Graph"] = backup_neo4j()
        results["Supabase"] = backup_supabase()
        return _summarise("BACKUP", results, start_time)

    elif args.action == "restore":
        print("\n" + "=" * 80)
        print("   INITIATING MUKTHI GURU COMPREHENSIVE RESTORATION PIPELINE")
        print("=" * 80)

        results = {f"Qdrant {c}": restore_qdrant(c) for c in collections}
        results["Graph"] = restore_neo4j()
        results["Supabase"] = restore_supabase()
        return _summarise("RESTORE", results, start_time)
    return 2


if __name__ == "__main__":
    sys.exit(main())
