"""Torch-free tokenizer for the ONNX serving path.

`transformers.AutoTokenizer` costs far more resident memory than the raw
`tokenizers.Tokenizer` for the BGE-M3 vocabulary: about 860 MB for the
tokenizer alone (1171 MB vs 311 MB). With both ONNX services loaded the
shipped path saves ~320-350 MB RSS while torch is still imported (torch alone
is ~522 MB; `EmbeddingService._thread_setup` still imports it). Measured
2026-11-27 inside the backend image. See docs/operations/fast-tokenizer-2026-11-27.md
for the note on host-built index points. The two ONNX services
(`embedding_service.py`, `onnx_reranker.py`) only ever call the tokenizer as
`tok(texts[, pairs], padding=True, truncation=True, max_length=N,
return_tensors="np")` and read four special-token ids, so this adapter
implements exactly that surface on top of `tokenizers` and nothing else.

Anything outside that surface raises. Load-time problems raise
`FastTokenizerLoadError`; the two services that have a torch fallback
(`EmbeddingService._ensure_reranker`, `RerankerService._load_fallback`) re-raise
it rather than switching models. Residual case: a corrupt tokenizer.json makes
`tokenizers.Tokenizer.from_file` raise a bare `Exception`, which those generic
handlers still treat like any other ONNX load failure (warning + fallback).
`ONNX_TOKENIZER_BACKEND=transformers` (see `app.config`) keeps the old
AutoTokenizer path as a rollback; it is imported lazily and only then.

NOTE: the live v13 index was built host-side with transformers 4.57.6, which
tokenizes 215 of 11,070 real transcript lines differently from 5.x (trailing
whitespace adds an extra token id 6). Queries were already tokenized the 5.x
way in the container, so that mismatch pre-exists. Future host builds now match
query time but will not reproduce existing points byte-for-byte: record this
before any partial re-embed. `tokenizers` is only a transitive dependency
(pinned via transformers in the lock); pin it explicitly if transformers is
ever dropped from the image.

Thread safety: `Tokenizer.enable_truncation/enable_padding` mutate the shared
Rust object, so each call holds a lock across configure + encode. Tokenising a
batch is microseconds-to-milliseconds, so serialising it is harmless.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

_TextBatch = str | Sequence[str]


class FastTokenizerLoadError(RuntimeError):
    """The tokenizer files cannot be loaded or are not an XLM-R tokenizer we reproduce.

    Callers that otherwise fall back (e.g. ONNX reranker -> torch CrossEncoder)
    must re-raise this one: with the fast backend selected, a broken tokenizer is
    a configuration/artifact error, not a reason to switch models silently.
    """


class FastTokenizer:
    """Subset of the HF fast-tokenizer call API, backed by `tokenizers`."""

    def __init__(self, model_dir: str | Path) -> None:
        from tokenizers import Tokenizer

        model_dir = Path(model_dir)
        tok_json = model_dir / "tokenizer.json"
        if not tok_json.is_file():
            raise FastTokenizerLoadError(
                f"tokenizer.json not found in {model_dir}. The 'tokenizers' ONNX tokenizer "
                "backend needs it; set ONNX_TOKENIZER_BACKEND=transformers to use the "
                "AutoTokenizer fallback instead."
            )
        self._tok = Tokenizer.from_file(str(tok_json))
        self._lock = threading.Lock()

        cfg_path = model_dir / "tokenizer_config.json"
        cfg: dict[str, Any] = json.loads(cfg_path.read_text()) if cfg_path.is_file() else {}
        if cfg.get("tokenizer_class") != "XLMRobertaTokenizer":
            raise FastTokenizerLoadError(
                f"FastTokenizer only reproduces XLMRobertaTokenizer, got {cfg.get('tokenizer_class')!r}"
            )
        self._match_transformers_v5_xlmr()
        self.cls_token_id = self._special_id(cfg, "cls_token")
        self.eos_token_id = self._special_id(cfg, "eos_token")
        self.pad_token_id = self._special_id(cfg, "pad_token")
        self.unk_token_id = self._special_id(cfg, "unk_token")
        self._pad_token = self._tok.id_to_token(self.pad_token_id)

    def _match_transformers_v5_xlmr(self) -> None:
        """Rebuild the normalizer/pre-tokenizer exactly as transformers 5.x does.

        transformers>=5 ignores tokenizer.json's own pipeline for XLM-R and
        reconstructs it (`XLMRobertaTokenizer.__init__`): normalizer = the
        Precompiled charsmap only, pre-tokenizer = WhitespaceSplit + Metaspace.
        The upstream BGE-M3 tokenizer.json instead carries Precompiled+Replace(" {2,}")
        and bare Metaspace, which differs on whitespace-only text and on text
        containing special-token strings. Serving ran on the 5.x behaviour
        (requirements.txt pins transformers==5.19.0), so that is what we keep.
        The reranker's tokenizer.json already has this shape; this is then a no-op.
        """
        from tokenizers import normalizers, pre_tokenizers

        norm = self._tok.normalizer
        if isinstance(norm, normalizers.Sequence):
            charsmaps = [
                n
                for n in (norm[i] for i in range(len(norm)))
                if isinstance(n, normalizers.Precompiled)
            ]
            if len(charsmaps) != 1:
                raise FastTokenizerLoadError(
                    f"expected exactly one Precompiled normalizer, got {len(charsmaps)}"
                )
            self._tok.normalizer = charsmaps[0]
        elif not isinstance(norm, normalizers.Precompiled):
            raise FastTokenizerLoadError(f"unexpected XLM-R normalizer {norm!r}")

        pre = self._tok.pre_tokenizer
        if isinstance(pre, pre_tokenizers.Metaspace):
            self._tok.pre_tokenizer = pre_tokenizers.Sequence(
                [pre_tokenizers.WhitespaceSplit(), pre]
            )
        elif not (
            isinstance(pre, pre_tokenizers.Sequence)
            and isinstance(pre[0], pre_tokenizers.WhitespaceSplit)
        ):
            raise FastTokenizerLoadError(f"unexpected XLM-R pre-tokenizer {pre!r}")

    def _special_id(self, cfg: dict[str, Any], key: str) -> int:
        token = cfg.get(key)
        if isinstance(token, dict):  # AddedToken-style entry
            token = token.get("content")
        if not isinstance(token, str):
            raise FastTokenizerLoadError(
                f"tokenizer_config.json has no usable {key!r} (got {token!r})"
            )
        token_id = self._tok.token_to_id(token)
        if token_id is None:
            raise FastTokenizerLoadError(f"{key} {token!r} is not in the tokenizer vocabulary")
        return int(token_id)

    def __call__(
        self,
        text: _TextBatch,
        text_pair: _TextBatch | None = None,
        *,
        padding: Any = True,
        truncation: Any = True,
        max_length: int | None = None,
        return_tensors: str | None = "np",
    ) -> dict[str, np.ndarray]:
        # Only the call shape the serving path uses; refuse the rest loudly.
        if padding is not True or truncation is not True or return_tensors != "np":
            raise ValueError(
                "FastTokenizer supports only padding=True, truncation=True, return_tensors='np'"
            )
        if not isinstance(max_length, int) or max_length < 1:
            raise ValueError(f"FastTokenizer needs a positive int max_length, got {max_length!r}")

        texts = [text] if isinstance(text, str) else list(text)
        if not texts:
            raise ValueError("FastTokenizer received an empty batch")
        if text_pair is None:
            inputs: list[Any] = texts
        else:
            pairs = [text_pair] if isinstance(text_pair, str) else list(text_pair)
            if len(pairs) != len(texts):
                raise ValueError(f"text/text_pair length mismatch: {len(texts)} vs {len(pairs)}")
            inputs = list(zip(texts, pairs))

        with self._lock:
            self._tok.enable_truncation(max_length=max_length)
            self._tok.enable_padding(pad_id=self.pad_token_id, pad_token=self._pad_token)
            encodings = self._tok.encode_batch(inputs, add_special_tokens=True)

        return {
            "input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
        }


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m services.fast_tokenizer <model_dir>")
    tok = FastTokenizer(sys.argv[1])
    out = tok(["hello", "a longer sentence here"], padding=True, truncation=True, max_length=16)
    assert out["input_ids"].shape == out["attention_mask"].shape
    assert out["input_ids"][0, 0] == tok.cls_token_id
    print({k: v.shape for k, v in out.items()})
