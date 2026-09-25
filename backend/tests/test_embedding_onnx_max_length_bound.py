"""Regression test for the 2026-09-24 segfault investigation.

`_onnx_tokenizer` is constructed with `model_max_length=8192`
(`_load_onnx_encoder`), and every ONNX encode call used to pass
`truncation=True` with no explicit `max_length=`, so a batch truncated (or
didn't) against that 8192-token ceiling. Attention memory is O(seq_len^2);
retrieval chunks are 400-1500 chars (~100-375 tokens), so nothing in the
product needs anywhere near 8192 -- an unbounded text reaching this path
could balloon the ONNX arena allocation, matching the "Failed to allocate
memory" DequantizeLinear/Transpose log lines observed alongside the
LettuceDetect segfault.

Each of the three ONNX tokenizer call sites (`encode`, `_encode_batch_onnx`,
`_encode_with_colbert_onnx`) must now pass `max_length=_ONNX_EMBED_MAX_LENGTH`
explicitly.
"""

from __future__ import annotations

import numpy as np
import pytest

from services.embedding_service import EmbeddingService, _ONNX_EMBED_MAX_LENGTH


class _FakeOnnxTokenizer:
    """Captures the kwargs it was called with; returns minimal valid arrays."""

    cls_token_id = 0
    eos_token_id = 1
    pad_token_id = 2
    unk_token_id = 3

    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, texts, **kwargs):
        self.calls.append(kwargs)
        n = len(texts) if isinstance(texts, list) else 1
        return {
            "input_ids": np.array([[10, 11]] * n),
            "attention_mask": np.array([[1, 1]] * n),
        }


class _FakeOnnxSession:
    def run(self, output_names, feed):
        n = feed["input_ids"].shape[0]
        seq_len = feed["input_ids"].shape[1]
        dense = np.zeros((n, 4), dtype="float32")
        sparse = np.zeros((n, seq_len, 1), dtype="float32")
        colbert = np.zeros((n, seq_len, 4), dtype="float32")
        return [dense, sparse, colbert]


@pytest.fixture
def service_with_fake_onnx():
    from unittest.mock import MagicMock

    service = EmbeddingService()
    service._onnx_tokenizer = _FakeOnnxTokenizer()
    service._onnx_session = _FakeOnnxSession()
    # `_ensure_encoder()`'s short-circuit checks `self._encoder`, not
    # `self._onnx_session` (see backend/CLAUDE.md's "_load_onnx_encoder
    # marker" note) -- without this, `encode()` tries to load the real model.
    service._encoder = MagicMock()
    return service


def test_encode_batch_onnx_bounds_max_length(service_with_fake_onnx):
    service = service_with_fake_onnx
    service._encode_batch_onnx(["some passage text"], start_time=0.0)
    assert service._onnx_tokenizer.calls[-1]["max_length"] == _ONNX_EMBED_MAX_LENGTH
    assert service._onnx_tokenizer.calls[-1]["truncation"] is True


def test_encode_query_onnx_bounds_max_length(service_with_fake_onnx):
    service = service_with_fake_onnx
    service.encode(["a query"])
    assert service._onnx_tokenizer.calls[-1]["max_length"] == _ONNX_EMBED_MAX_LENGTH


def test_encode_with_colbert_onnx_bounds_max_length(service_with_fake_onnx):
    service = service_with_fake_onnx
    service._encode_with_colbert_onnx(["a passage"], start_time=0.0)
    assert service._onnx_tokenizer.calls[-1]["max_length"] == _ONNX_EMBED_MAX_LENGTH


if __name__ == "__main__":
    from unittest.mock import MagicMock

    svc = EmbeddingService()
    svc._onnx_tokenizer = _FakeOnnxTokenizer()
    svc._onnx_session = _FakeOnnxSession()
    svc._encoder = MagicMock()
    svc._encode_batch_onnx(["x"], start_time=0.0)
    assert svc._onnx_tokenizer.calls[-1]["max_length"] == _ONNX_EMBED_MAX_LENGTH
    print("OK")
