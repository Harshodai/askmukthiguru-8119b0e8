from __future__ import annotations

import base64

import pytest
from backend.services.second_brain.crypto import derive_server_kek


def test_derive_server_kek_accepts_padded_and_unpadded_base64url() -> None:
    raw = bytes(range(32))
    padded = base64.urlsafe_b64encode(raw).decode("ascii")
    unpadded = padded.rstrip("=")

    assert derive_server_kek(padded) == raw
    assert derive_server_kek(unpadded) == raw


def test_derive_server_kek_rejects_wrong_length() -> None:
    short = base64.urlsafe_b64encode(b"too-short").decode("ascii")

    with pytest.raises(ValueError, match="exactly 32 bytes"):
        derive_server_kek(short)
