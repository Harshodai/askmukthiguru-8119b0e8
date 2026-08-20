#!/usr/bin/env python3
"""Safely re-wrap Second Brain Mode-A DEKs under a replacement BRAIN_KEK.

Default mode is dry-run. Applying requires both ``--apply`` and the explicit
``--confirm-rewrap`` flag. The old and new KEKs are read from environment
variables and are never printed. User payload plaintext is never decrypted.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from supabase import Client, create_client

try:
    from backend.services.second_brain.crypto import (
        VaultIntegrityError,
        derive_server_kek,
        unwrap_dek,
        wrap_dek,
    )
except ModuleNotFoundError:
    from services.second_brain.crypto import (  # type: ignore[no-redef]
        VaultIntegrityError,
        derive_server_kek,
        unwrap_dek,
        wrap_dek,
    )

LOGGER = logging.getLogger("rotate_brain_kek")
PAGE_SIZE = 100


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-env", default="BRAIN_KEK")
    parser.add_argument("--new-env", default="BRAIN_KEK_NEXT")
    parser.add_argument("--page-size", type=int, default=PAGE_SIZE)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-rewrap", action="store_true")
    parser.add_argument("--allow-empty", action="store_true")
    return parser.parse_args(argv)


def _kek_from_env(name: str) -> bytes:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"{name} is missing")
    return derive_server_kek(value)


def _client_from_env() -> Client:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_KEY", "") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY/SUPABASE_SERVICE_ROLE_KEY are required")
    return create_client(url, key)


def _fetch_mode_a_rows(client: Client, page_size: int) -> List[Dict[str, Any]]:
    if page_size < 1 or page_size > 1000:
        raise ValueError("--page-size must be between 1 and 1000")
    rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        response = (
            client.table("user_brain_keys")
            .select("user_id,wrap_mode,wrapped_dek")
            .eq("wrap_mode", "server_wrapped")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = list(response.data or [])
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def _rewrap_blob(wrapped_dek: str, old_kek: bytes, new_kek: bytes) -> str:
    dek = unwrap_dek(wrapped_dek, old_kek)
    replacement = wrap_dek(dek, new_kek)
    if unwrap_dek(replacement, new_kek) != dek:
        raise VaultIntegrityError("replacement wrapped DEK failed verification")
    return replacement


def _build_plan(rows: Iterable[Dict[str, Any]], old_kek: bytes, new_kek: bytes) -> List[Tuple[str, str, str]]:
    plan: List[Tuple[str, str, str]] = []
    for row in rows:
        user_id = str(row.get("user_id") or "")
        wrapped_dek = str(row.get("wrapped_dek") or "")
        if not user_id or not wrapped_dek:
            raise RuntimeError("Mode-A row is missing user_id or wrapped_dek")
        plan.append((user_id, wrapped_dek, _rewrap_blob(wrapped_dek, old_kek, new_kek)))
    return plan


def _apply_plan(client: Client, plan: Iterable[Tuple[str, str, str]]) -> int:
    updated = 0
    for user_id, old_blob, replacement in plan:
        response = (
            client.table("user_brain_keys")
            .update({"wrapped_dek": replacement, "rotated_at": datetime.now(timezone.utc).isoformat()})
            .eq("user_id", user_id)
            .eq("wrap_mode", "server_wrapped")
            .eq("wrapped_dek", old_blob)
            .execute()
        )
        changed = list(response.data or [])
        if len(changed) != 1:
            raise RuntimeError(f"compare-and-swap failed; changed={len(changed)}")
        updated += 1
    return updated


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.apply and not args.confirm_rewrap:
        LOGGER.error("--apply requires --confirm-rewrap")
        return 2
    if args.apply and args.allow_empty:
        LOGGER.error("--allow-empty cannot be combined with --apply")
        return 2
    try:
        old_kek = _kek_from_env(args.old_env)
        new_kek = _kek_from_env(args.new_env)
        if old_kek == new_kek:
            raise RuntimeError("old and replacement KEKs must differ")
        client = _client_from_env()
        rows = _fetch_mode_a_rows(client, args.page_size)
        if not rows and not args.allow_empty:
            raise RuntimeError("no Mode-A rows found; refusing empty rotation")
        plan = _build_plan(rows, old_kek, new_kek)
        LOGGER.info("validated %d Mode-A wrapped DEK replacements; plaintext was not read", len(plan))
        if not args.apply:
            LOGGER.info("dry-run complete; no database rows changed")
            return 0
        updated = _apply_plan(client, plan)
        if updated != len(plan):
            raise RuntimeError(f"updated {updated} of {len(plan)} planned rows")
        LOGGER.info("rotation applied to %d Mode-A vault rows", updated)
        return 0
    except Exception as exc:
        LOGGER.error("BRAIN_KEK rotation aborted: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
