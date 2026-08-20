from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.second_brain.crypto import generate_dek, unwrap_dek, wrap_dek
from scripts.ops.rotate_brain_kek import _parse_args, _rewrap_blob


def _key(seed: int) -> bytes:
    return bytes([seed]) * 32


def test_rewrap_preserves_dek_without_payload_plaintext() -> None:
    old_kek = _key(1)
    new_kek = _key(2)
    dek = generate_dek()
    old_blob = wrap_dek(dek, old_kek)
    replacement = _rewrap_blob(old_blob, old_kek, new_kek)
    assert replacement != old_blob
    assert unwrap_dek(replacement, new_kek) == dek


def test_apply_requires_explicit_confirmation() -> None:
    args = _parse_args(["--apply"])
    assert args.apply is True
    assert args.confirm_rewrap is False


def test_key_fixture_is_valid_base64url_shape() -> None:
    encoded = base64.urlsafe_b64encode(_key(9)).decode("ascii")
    assert len(base64.urlsafe_b64decode(encoded)) == 32
