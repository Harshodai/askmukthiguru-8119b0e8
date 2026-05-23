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
QDRANT_HOST_URL = "http://localhost:6333"
NEO4J_CONTAINER = "mukthiguru-neo4j"
NEO4J_PASS = "mukthiguru_neo4j_pass"

# Backup directories on host
BACKUP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backups"))
QDRANT_BACKUP_PATH = os.path.join(BACKUP_DIR, "qdrant", "spiritual_wisdom.snapshot")
NEO4J_BACKUP_PATH = os.path.join(BACKUP_DIR, "neo4j", "backup.cypher")
SUPABASE_BACKUP_PATH = os.path.join(BACKUP_DIR, "supabase", "data.sql")


def setup_directories():
    """Ensure all host backup directories exist."""
    os.makedirs(os.path.dirname(QDRANT_BACKUP_PATH), exist_ok=True)
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


def backup_qdrant(collection_name="spiritual_wisdom"):
    """Create a collection snapshot and download it to the host."""
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
        urllib.request.urlretrieve(download_url, QDRANT_BACKUP_PATH)
        print(
            f"  [✅] Qdrant backup saved: {QDRANT_BACKUP_PATH} ({os.path.getsize(QDRANT_BACKUP_PATH) / 1024 / 1024:.2f} MB)"
        )
        return True
    except Exception as e:
        print(f"  [-] Failed to download Qdrant snapshot: {e}")
        return False


def restore_qdrant(collection_name="spiritual_wisdom"):
    """Upload and restore collection from snapshot."""
    print(f"\n[Qdrant] Restoring collection '{collection_name}' from snapshot...")

    if not os.path.exists(QDRANT_BACKUP_PATH):
        print(f"  [-] Qdrant snapshot not found at {QDRANT_BACKUP_PATH}. Skipping Qdrant restore.")
        return False

    # Standard multipart form data upload implementation using only standard library
    try:
        # Load snapshot file
        with open(QDRANT_BACKUP_PATH, "rb") as f:
            snapshot_bytes = f.read()

        boundary = b"----WebKitFormBoundaryAskMukthiGuruBackup"
        parts = []
        parts.append(b"--" + boundary)
        parts.append(
            b'Content-Disposition: form-data; name="snapshot"; filename="spiritual_wisdom.snapshot"'
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

        # The query returns cypherStatements column. Let's merge statements.
        # We strip quotes that cypher-shell wraps around columns if any.
        cypher_text = ""
        for line in lines[1:]:
            if line.startswith('"') and line.endswith('"'):
                line = line[1:-1]
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
    parser.add_argument("--collection", default="spiritual_wisdom", help="Target Qdrant collection")

    args = parser.parse_args()

    # Enforce Docker path on macOS
    os.environ["PATH"] = "/Users/harshodaikolluru/.docker/bin:" + os.environ.get("PATH", "")

    setup_directories()

    start_time = time.time()

    if args.action == "backup":
        print("\n" + "=" * 80)
        print("   INITIATING MUKTHI GURU COMPREHENSIVE BACKUP PIPELINE")
        print("=" * 80)

        q_ok = backup_qdrant(args.collection)
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

        q_ok = restore_qdrant(args.collection)
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
