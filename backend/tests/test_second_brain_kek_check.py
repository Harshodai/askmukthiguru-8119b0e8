"""Startup KEK check: count stored vault keys the server KEK cannot unwrap (the 'wrong KEK' outage)."""

import asyncio
import os
from unittest.mock import MagicMock

from services.second_brain.crypto import generate_dek, wrap_dek
from services.second_brain.second_brain_service import SecondBrainService


def _service(rows: list[dict], kek: bytes | None) -> SecondBrainService:
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=rows
    )
    service = SecondBrainService.__new__(SecondBrainService)
    service._db = db
    service._server_kek = kek
    return service


def test_all_keys_unwrap_with_the_current_kek():
    kek = os.urandom(32)
    rows = [
        {
            "user_id": f"u{i}",
            "wrapped_dek": wrap_dek(generate_dek(), kek),
            "wrap_mode": "server_wrapped",
        }
        for i in range(3)
    ]

    assert asyncio.run(_service(rows, kek).check_kek_against_stored_keys()) == (3, 0)


def test_keys_wrapped_by_another_kek_are_counted_as_failed():
    current, old = os.urandom(32), os.urandom(32)
    rows = [
        {
            "user_id": "ok",
            "wrapped_dek": wrap_dek(generate_dek(), current),
            "wrap_mode": "server_wrapped",
        },
        {
            "user_id": "stale",
            "wrapped_dek": wrap_dek(generate_dek(), old),
            "wrap_mode": "server_wrapped",
        },
    ]

    assert asyncio.run(_service(rows, current).check_kek_against_stored_keys()) == (2, 1)


def test_no_kek_or_no_db_checks_nothing():
    assert asyncio.run(_service([], None).check_kek_against_stored_keys()) == (0, 0)
