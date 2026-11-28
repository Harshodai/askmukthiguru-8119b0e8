"""FastTokenizer (raw `tokenizers`) must match transformers.AutoTokenizer exactly.

The ONNX serving path swapped AutoTokenizer (~320-350 MB more RSS while torch is still imported; about 860 MB for the tokenizer alone) for
`services/fast_tokenizer.FastTokenizer`. These tests run both on the real
BGE-M3 and reranker tokenizer files and assert identical `input_ids` and
`attention_mask` for every call shape the services use. They skip with a clear
reason when the model files are not on this machine (host CI); inside the
backend container they run for real.
"""

from __future__ import annotations

import os
import random
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np
import pytest

from app.config import settings
from services.fast_tokenizer import FastTokenizer, FastTokenizerLoadError

# REQUIRE_TRANSFORMERS_5=1 (scripts/ops/verify_fast_tokenizer_in_image.sh) turns
# every skip into a failure and demands transformers 5.x, so "0 skipped" is
# enforceable proof that equivalence holds against the version serving runs.
_STRICT = os.environ.get("REQUIRE_TRANSFORMERS_5") == "1"


def _skip(reason: str) -> None:
    if _STRICT:
        pytest.fail(f"REQUIRE_TRANSFORMERS_5=1 forbids skipping: {reason}")
    pytest.skip(reason)


def _import_transformers():
    try:
        import transformers
    except ImportError:
        _skip("transformers is not installed")
    return transformers


@pytest.fixture(scope="session", autouse=True)
def _require_transformers_5():
    if _STRICT:
        major = int(_import_transformers().__version__.split(".")[0])
        if major != 5:
            pytest.fail(f"REQUIRE_TRANSFORMERS_5=1 but transformers major is {major}, not 5")


_EMBED_MAX = 1024  # services.embedding_service._ONNX_EMBED_MAX_LENGTH
_RERANK_MAX = 512  # services.onnx_reranker.predict max_length

_TEXTS = [
    "What is the meaning of inner peace?",
    "",
    "ok",
    "Hello  world \t with\nnewlines and   spaces.",
    "ध्यान से मन शांत होता है और जीवन में स्पष्टता आती है।",  # Hindi
    "ధ్యానం మనసును ప్రశాంతంగా ఉంచుతుంది.",  # Telugu
    "தியானம் மனதை அமைதிப்படுத்துகிறது.",  # Tamil
    "ಧ್ಯಾನವು ಮನಸ್ಸನ್ನು ಶಾಂತಗೊಳಿಸುತ್ತದೆ.",  # Kannada
    "ध्यानामुळे मन शांत होते आणि जीवनात स्पष्टता येते.",  # Marathi
    "ധ്യാനം മനസ്സിനെ ശാന്തമാക്കുന്നു.",  # Malayalam
    "Peace 🙏🧘‍♀️ and joy ✨ 😀 together",
    "mixed English and हिन्दी and తెలుగు in one line",
    "word " * 3000,  # far past both max lengths
    "लंबा पाठ " * 1500,
]

# Whitespace-only text and special-token strings inside text tokenise differently
# in transformers 4.x (which follows tokenizer.json) and 5.x (which rebuilds the
# XLM-R pipeline). Serving pins 5.x (requirements.txt), and so does FastTokenizer.
_V5_ONLY_TEXTS = [
    " ",
    "\n\n",
    "\t",
    "\u00a0",
    "</s> <s> <pad> special tokens inside the text <unk>",
]


def _transformers_major() -> int:
    transformers = _import_transformers()
    return int(transformers.__version__.split(".")[0])


def _needs_v5() -> None:
    if _transformers_major() < 5:
        _skip("whitespace/special-token edge cases follow transformers 5.x behaviour")


def _all_texts() -> list[str]:
    return _TEXTS + (_V5_ONLY_TEXTS if _transformers_major() >= 5 else [])


_PAIRS = [
    ("what is suffering", "Suffering arises from the mind's resistance to what is."),
    ("", ""),
    ("ध्यान क्या है", "ध्यान मन को शांत करने की एक विधि है।"),
    ("q " * 700, "short doc"),  # long query, short doc
    ("short query", "d " * 700),  # short query, long doc
    ("q " * 400, "d " * 400),  # both long: longest_first truncation
    ("Peace 🙏", "😀 joy"),
]


def _find_dir(model_dir_name: str) -> Path | None:
    roots = []
    if os.environ.get("HF_HOME"):
        roots.append(Path(os.environ["HF_HOME"]) / "hub")
    roots.append(Path.home() / ".cache" / "huggingface" / "hub")
    for root in roots:
        base = root / model_dir_name
        if base.is_dir():
            hits = sorted(base.rglob("tokenizer.json"))
            if hits:
                return hits[0].parent
    return None


@pytest.fixture(scope="module")
def embed_dir() -> Path:
    path = _find_dir("models--gpahal--bge-m3-onnx-int8")
    if path is None:
        _skip("BGE-M3 ONNX tokenizer files not present on this machine")
    return path


@pytest.fixture(scope="module")
def rerank_dir() -> Path:
    path = _find_dir("models--temsa--mmarco-mMiniLMv2-L12-H384-v1-onnx-cpu-qint8")
    if path is None:
        _skip("temsa reranker tokenizer files not present on this machine")
    return path


@pytest.fixture(scope="module")
def embed_pair(embed_dir):
    transformers = _import_transformers()
    old = transformers.AutoTokenizer.from_pretrained(
        str(embed_dir), local_files_only=True, model_max_length=8192
    )
    return FastTokenizer(embed_dir), old


@pytest.fixture(scope="module")
def rerank_pair(rerank_dir):
    transformers = _import_transformers()
    old = transformers.AutoTokenizer.from_pretrained(
        str(rerank_dir), use_fast=True, trust_remote_code=False
    )
    return FastTokenizer(rerank_dir), old


def _assert_same(new_out, old_out) -> None:
    # The services only ever read these keys; token_type_ids must not appear on
    # either side for these XLM-R models (the reranker guards with `in inputs`).
    assert "token_type_ids" not in old_out
    assert set(new_out) == {"input_ids", "attention_mask"}
    for key in ("input_ids", "attention_mask"):
        assert new_out[key].shape == old_out[key].shape, key
        assert new_out[key].dtype == old_out[key].dtype, key
        assert np.array_equal(new_out[key], old_out[key]), key


def _both(pair, *args, max_length):
    new, old = pair
    kw = dict(padding=True, truncation=True, max_length=max_length, return_tensors="np")
    return new(*args, **kw), old(*args, **kw)


@pytest.mark.parametrize("max_length", [_EMBED_MAX, 16])
def test_embedder_batch_mixed_lengths(embed_pair, max_length):
    _assert_same(*_both(embed_pair, _all_texts(), max_length=max_length))


@pytest.mark.parametrize("text", _TEXTS)
def test_embedder_single_text_each(embed_pair, text):
    _assert_same(*_both(embed_pair, [text], max_length=_EMBED_MAX))


@pytest.mark.parametrize("text", _V5_ONLY_TEXTS)
def test_embedder_v5_edge_text_each(embed_pair, text):
    _needs_v5()
    _assert_same(*_both(embed_pair, [text], max_length=_EMBED_MAX))


def test_embedder_fuzz_matches_transformers(embed_pair):
    _needs_v5()
    rng = random.Random(1234)
    alphabet = (
        list("abcxyz ABC 0123 .,!?'-\t\n\u00a0")
        + list("ध्यानमनशांतिதியானம்ధ్యానంಧ್ಯಾನ🙏✨")
        + [
            "<s>",
            "</s>",
            "<pad>",
            "<unk>",
            "<mask>",
            "  ",
            "▁",
        ]
    )
    texts = ["".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40))) for _ in range(400)]
    for i in range(0, len(texts), 40):
        _assert_same(*_both(embed_pair, texts[i : i + 40], max_length=24))


def test_embedder_bare_string_matches_list(embed_pair):
    _assert_same(*_both(embed_pair, "Hello there", max_length=_EMBED_MAX))


def test_embedder_truncates_long_input_and_pads_right(embed_pair):
    new_out, old_out = _both(embed_pair, ["word " * 3000, "hi"], max_length=_EMBED_MAX)
    _assert_same(new_out, old_out)
    assert new_out["input_ids"].shape == (2, _EMBED_MAX)
    pad = embed_pair[0].pad_token_id
    assert new_out["input_ids"][1, -1] == pad and new_out["attention_mask"][1, -1] == 0
    assert new_out["input_ids"][1, 0] == embed_pair[0].cls_token_id


def test_embedder_special_token_ids(embed_pair):
    new, old = embed_pair
    for attr in ("cls_token_id", "eos_token_id", "pad_token_id", "unk_token_id"):
        assert getattr(new, attr) == getattr(old, attr), attr


@pytest.mark.parametrize("max_length", [_RERANK_MAX, 32])
def test_reranker_sentence_pairs(rerank_pair, max_length):
    queries, docs = zip(*_PAIRS)
    _assert_same(*_both(rerank_pair, list(queries), list(docs), max_length=max_length))


@pytest.mark.parametrize("pair", _PAIRS)
def test_reranker_single_pair_each(rerank_pair, pair):
    _assert_same(*_both(rerank_pair, [pair[0]], [pair[1]], max_length=_RERANK_MAX))


def test_reranker_text_batch(rerank_pair):
    _assert_same(*_both(rerank_pair, _all_texts(), max_length=_RERANK_MAX))


def test_concurrent_calls_match_serial(embed_pair):
    new, old = embed_pair
    expected = old(_all_texts(), padding=True, truncation=True, max_length=64, return_tensors="np")
    texts = _all_texts()
    failures: list[str] = []

    def work(i: int) -> None:
        for _ in range(20):
            # Alternate max_length so a missing lock would leak truncation state.
            ml = 64 if i % 2 == 0 else 8
            out = new(texts, padding=True, truncation=True, max_length=ml, return_tensors="np")
            if ml == 64 and not np.array_equal(out["input_ids"], expected["input_ids"]):
                failures.append(f"thread {i} diverged")

    threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not failures


# --- machine-independent checks (no model files needed) ----------------------


def test_default_backend_is_transformers_until_5x_equivalence_is_verified():
    """The swap is opt-in: it must not become the default before the in-image check
    (scripts/ops/verify_fast_tokenizer_in_image.sh) shows 0 skipped on transformers 5.x."""
    assert settings.onnx_tokenizer_backend == "transformers"


def test_missing_tokenizer_json_raises_clear_error(tmp_path):
    with pytest.raises(FastTokenizerLoadError, match="tokenizer.json not found"):
        FastTokenizer(tmp_path)


def test_unsupported_call_shapes_raise(tmp_path):
    tok = FastTokenizer.__new__(FastTokenizer)  # no model needed: validation runs first
    with pytest.raises(ValueError, match="padding=True"):
        tok(["a"], padding="max_length", max_length=8)
    with pytest.raises(ValueError, match="max_length"):
        tok(["a"], padding=True, truncation=True)


def test_fast_tokenizer_import_does_not_pull_transformers():
    code = "import sys; import services.fast_tokenizer; assert 'transformers' not in sys.modules"
    backend_dir = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, "-c", code], cwd=backend_dir, check=True)


# --- no silent torch fallback when the fast tokenizer cannot load -------------


class _BrokenFastTokenizerReranker:
    def __init__(self, *args, **kwargs):
        raise FastTokenizerLoadError("tokenizer.json not found (test)")


def test_embedding_service_reranker_raises_on_tokenizer_load_error(monkeypatch):
    import services.onnx_reranker as onnx_reranker
    from services.embedding_service import EmbeddingService

    monkeypatch.setattr(settings, "reranker_backend", "onnx_int8")
    monkeypatch.setattr(onnx_reranker, "OnnxReranker", _BrokenFastTokenizerReranker)
    svc = EmbeddingService()
    monkeypatch.setattr(svc, "_thread_setup", lambda: None)
    monkeypatch.setattr(svc, "_get_device", lambda: "cpu")
    with pytest.raises(FastTokenizerLoadError):
        svc._ensure_reranker()


def test_reranker_service_fallback_raises_on_tokenizer_load_error(monkeypatch):
    import services.onnx_reranker as onnx_reranker
    from services.reranker_service import RerankerService

    monkeypatch.setattr(settings, "reranker_backend", "onnx_int8")
    monkeypatch.setattr(onnx_reranker, "OnnxReranker", _BrokenFastTokenizerReranker)
    with pytest.raises(FastTokenizerLoadError):
        RerankerService()._load_fallback()
