#!/usr/bin/env python3
"""
AskMukthiGuru — Dynamic Snapshot & Restore Manager
==================================================
Automates taking complete, production-grade backups and restoring data for:
  1. Qdrant (Vector Collection Snapshots via REST API)
  2. Neo4j (Graph Database APOC cypher streams via Docker cypher-shell)
  3. Supabase (Local Postgres schemas/data via Docker pg_dump)

Prevents any data loss during local rebuilding, cache clearing, or database resets.

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
        print(f"  [-] Qdrant snapshot not found at {snapshot_path}. Skipping Qdrant restore.")
        return False

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


# ─── Neo4j Backup & Restore ────────────────────────────────────────────────────


def backup_neo4j():
    """Stream out a plain cypher backup from Neo4j APOC export."""
    print("\n[Neo4j] Starting graph backup via APOC Cypher stream...")

    cypher_query = "CALL apoc.export.cypher.all(null, {stream: true, format: 'plain'}) YIELD cypherStatements RETURN cypherStatements"

    cmd = [
        "docker",
        "exec",
        NEO4J_CONTAINER,
        "cypher-shell",
        "-u",
        "neo4j",
        "-p",
        NEO4J_PASS,
        cypher_query,
    ]

    try:
        print("  [*] Executing stream export in Neo4j container...")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        # Parse output: skip header row and extract the cypher statements
        lines = result.stdout.strip().split("\n")
        if len(lines) < 2:
            print("  [-] Neo4j APOC export returned empty graph state.")
            # Write a simple fallback cypher file
            with open(NEO4J_BACKUP_PATH, "w", encoding="utf-8") as f:
                f.write("// Neo4j Empty Graph State Backup\n")
            return True

        # The query returns cypherStatements column, a single string value
        # that cypher-shell wraps in one leading/trailing quote pair — but
        # since the value itself contains embedded newlines (one per
        # statement), it spans many *physical* output lines. Stripping
        # quotes per-line (checking each line starts AND ends with '"')
        # never matches for a multi-line value, leaving a stray leading '"'
        # in the restored file that broke cypher-shell's parser on restore
        # ("Invalid input '\"CREATE ...'"). The outer quote pair belongs to
        # the whole value, so strip it once, from the first and last lines.
        body_lines = lines[1:]
        if body_lines and body_lines[0].startswith('"'):
            body_lines[0] = body_lines[0][1:]
        if body_lines and body_lines[-1].endswith('"'):
            body_lines[-1] = body_lines[-1][:-1]
        cypher_text = ""
        for line in body_lines:
            cypher_text += line.replace('\\"', '"').replace("\\n", "\n") + "\n"

        with open(NEO4J_BACKUP_PATH, "w", encoding="utf-8") as f:
            f.write(cypher_text)

        print(
            f"  [✅] Neo4j graph backup saved: {NEO4J_BACKUP_PATH} ({len(cypher_text.splitlines())} cypher lines)"
        )
        return True

    except subprocess.CalledProcessError as e:
        print(f"  [-] Neo4j backup execution failed: {e.stderr}")
        return False
    except Exception as e:
        print(f"  [-] Neo4j backup error: {e}")
        return False


def restore_neo4j():
    """Restore Neo4j database using the exported backup cypher file."""
    print("\n[Neo4j] Restoring graph database from Cypher backup...")

    if not os.path.exists(NEO4J_BACKUP_PATH):
        print(f"  [-] Neo4j backup file not found at {NEO4J_BACKUP_PATH}. Skipping restore.")
        return False

    # Read the Cypher backup content
    with open(NEO4J_BACKUP_PATH, encoding="utf-8") as f:
        cypher_content = f.read().strip()

    if not cypher_content or cypher_content.startswith("//"):
        print("  [*] Backup cypher is empty. Skipping execution.")
        return True

    try:
        # We pass the cypher file content directly into cypher-shell via stdin
        cmd = [
            "docker",
            "exec",
            "-i",
            NEO4J_CONTAINER,
            "cypher-shell",
            "-u",
            "neo4j",
            "-p",
            NEO4J_PASS,
        ]

        print("  [*] Running Cypher restoration scripts inside container...")
        result = subprocess.run(
            cmd, input=cypher_content, capture_output=True, text=True, check=True
        )
        print("  [✅] Neo4j graph database successfully restored!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [-] Neo4j cypher execution failed: {e.stderr or e.stdout}")
        return False
    except Exception as e:
        print(f"  [-] Neo4j restoration error: {e}")
        return False


# ─── Supabase Backup & Restore ────────────────────────────────────────────────


def backup_supabase():
    """Perform pg_dump on the dynamic Supabase Postgres container."""
    print("\n[Supabase] Starting Postgres database backup...")

    container = get_supabase_container()
    if not container:
        print("  [-] Running Supabase Postgres container not found. Skipping backup.")
        return False

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
        print("  [-] Running Supabase Postgres container not found. Skipping restore.")
        return False

    if not os.path.exists(SUPABASE_BACKUP_PATH):
        print(f"  [-] Supabase data SQL not found at {SUPABASE_BACKUP_PATH}. Skipping restore.")
        return False

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

        q_ok = all([backup_qdrant(c) for c in collections])
        n_ok = backup_neo4j()
        s_ok = backup_supabase()

        print("\n" + "=" * 80)
        print("   BACKUP PIPELINE EXECUTION SUMMARY")
        print("=" * 80)
        print(f"  - Qdrant collection:  {'[✅] SUCCESS' if q_ok else '[❌] FAILED'}")
        print(f"  - Neo4j graph state:  {'[✅] SUCCESS' if n_ok else '[❌] FAILED'}")
        print(f"  - Supabase postgres:  {'[✅] SUCCESS' if s_ok else '[❌] FAILED'}")
        print(f"  - Elapsed duration:   {time.time() - start_time:.1f} seconds")
        print("=" * 80)

    elif args.action == "restore":
        print("\n" + "=" * 80)
        print("   INITIATING MUKTHI GURU COMPREHENSIVE RESTORATION PIPELINE")
        print("=" * 80)

        q_ok = all([restore_qdrant(c) for c in collections])
        n_ok = restore_neo4j()
        s_ok = restore_supabase()

        print("\n" + "=" * 80)
        print("   RESTORATION PIPELINE EXECUTION SUMMARY")
        print("=" * 80)
        print(f"  - Qdrant collection:  {'[✅] RESTORED' if q_ok else '[[-] SKIPPED / FAILED'}")
        print(f"  - Neo4j graph state:  {'[✅] RESTORED' if n_ok else '[[-] SKIPPED / FAILED'}")
        print(f"  - Supabase postgres:  {'[✅] RESTORED' if s_ok else '[[-] SKIPPED / FAILED'}")
        print(f"  - Elapsed duration:   {time.time() - start_time:.1f} seconds")
        print("=" * 80)


if __name__ == "__main__":
    main()
