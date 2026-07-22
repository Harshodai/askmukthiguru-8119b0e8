#!/usr/bin/env python3
"""backup_lightrag_checkpoint.py — Dump LightRAG SQLite checkpoint DB to JSON.

Protects long-running LightRAG ingestion state by creating timestamped backups
of the document_status table.

Usage:
  cd backend
  .venv/bin/python scripts/ops/backup_lightrag_checkpoint.py [--db-path ./lightrag_data/doc_status.db]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

DEFAULT_DB_PATH = os.getenv("LIGHTRAG_DB", "./lightrag_data/doc_status.db")
BACKUP_DIR = "./data/lightrag_backups"


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup LightRAG SQLite checkpoint")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH, help="Path to doc_status.db")
    parser.add_argument("--out-dir", default=BACKUP_DIR, help="Backup output directory")
    args = parser.parse_args()

    if not os.path.exists(args.db_path):
        print(f"WARN: LightRAG DB file not found at {args.db_path}. Skipping backup.")
        return

    os.makedirs(args.out_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(args.out_dir, f"lightrag_checkpoint_{ts}.json")

    try:
        with sqlite3.connect(args.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='document_status';")
            if not cursor.fetchone():
                print("WARN: Table 'document_status' not found in database.")
                return

            cursor.execute("SELECT * FROM document_status")
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            data = [dict(zip(cols, row)) for row in rows]

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        print(f"✓ LightRAG checkpoint backed up ({len(data)} documents) → {out_file}")
    except Exception as e:
        print(f"ERROR: Failed to backup LightRAG checkpoint: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
