"""
onnx_embedding_probe.py — Phase 1: Checkpoint Capability Probe

Empirically determines whether a candidate ONNX INT8 checkpoint exports
dense-only or dense+sparse output heads. Downloads to an isolated scratch
directory so the production HF cache is never contaminated.

Usage:
    .venv/bin/python3 scripts/onnx_embedding_probe.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

CANDIDATE = "gpahal/bge-m3-onnx-int8"
SCRATCH = Path(tempfile.mkdtemp(prefix="onnx_probe_"))
ONNX_FILE = SCRATCH / "model_quantized.onnx"

# Immutable revisions (commit SHAs), resolved from the HF API on 2026-08-01.
# No repo heads — a later commit can silently change weights or tokenizer files.
CANDIDATE_REVISION = "2b34e84df040034d4b9eabb62383a87c18955822"
BGE_M3_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"


def _download_checkpoint() -> str:
    """Download the candidate ONNX checkpoint to a scratch directory."""
    from huggingface_hub import snapshot_download

    print(f"Downloading {CANDIDATE} (rev {CANDIDATE_REVISION}) to scratch: {SCRATCH}")
    local_path = snapshot_download(
        repo_id=CANDIDATE,
        revision=CANDIDATE_REVISION,
        local_dir=str(SCRATCH),
        local_dir_use_symlinks=False,
        resume_download=True,
        ignore_patterns=["*.md", "*.py", "requirements.txt"],
    )
    print(f"Downloaded to: {local_path}")
    return local_path


def _probe_with_onnxruntime(model_path: str) -> dict:
    """Load the ONNX model with plain onnxruntime and inspect output heads."""
    import onnxruntime as ort

    print("\n=== Probing with onnxruntime.InferenceSession ===")
    session = ort.InferenceSession(
        model_path,
        providers=["CPUExecutionProvider"],
    )

    # Input info
    print(f"\nInputs ({len(session.get_inputs())}):")
    for inp in session.get_inputs():
        print(f"  {inp.name}: shape={inp.shape}, type={inp.type}")

    # Output info — this is the critical section
    outputs = session.get_outputs()
    print(f"\nOutputs ({len(outputs)}):")
    output_info = {}
    for out in outputs:
        print(f"  {out.name}: shape={out.shape}, type={out.type}")
        output_info[out.name] = {"shape": out.shape, "type": out.type}

    # Run a forward pass to see actual output shapes/data
    tokenizer = _get_tokenizer()
    texts = ["What is the Four Sacred Secrets?", "How do I practice Soul Sync?"]
    inputs = tokenizer(texts, padding=True, truncation=True, return_tensors="np")
    ort_inputs = {
        k: v.astype(np.int64)
        for k, v in inputs.items()
    }

    print(f"\nForward pass with {len(texts)} texts:")
    raw_outputs = session.run(None, ort_inputs)
    for i, (out, arr) in enumerate(zip(outputs, raw_outputs)):
        print(f"  output[{i}] {out.name}: shape={arr.shape}, dtype={arr.dtype}")
        print(f"    range: [{arr.min():.6f}, {arr.max():.6f}]")

    return {
        "output_info": output_info,
        "num_outputs": len(outputs),
        "output_names": [o.name for o in outputs],
        "raw_outputs": raw_outputs,
    }


def _probe_with_optimum(model_path: str) -> dict:
    """Load the model through Optimum (ORTModelForCustomTasks) — production path."""
    print("\n=== Probing with ORTModelForCustomTasks ===")
    try:
        from optimum.onnxruntime import ORTModelForCustomTasks
    except ImportError:
        print("  optimum[onnxruntime] not installed — skipping")
        return {"available": False}

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-m3", revision=BGE_M3_REVISION)
    model = ORTModelForCustomTasks.from_pretrained(
        str(SCRATCH),
        file_name="model_quantized.onnx",
    )

    texts = ["What is the Four Sacred Secrets?", "How do I practice Soul Sync?"]
    inputs = tokenizer(texts, padding=True, truncation=True, return_tensors="pt")

    print(f"  Input shapes: {[(k, v.shape) for k, v in inputs.items()]}")
    outputs = model(**inputs)
    print(f"  Output type: {type(outputs).__name__}")

    if isinstance(outputs, tuple):
        print(f"  Tuple with {len(outputs)} elements:")
        for i, out in enumerate(outputs):
            if hasattr(out, "shape"):
                print(f"    [{i}]: shape={out.shape}, dtype={out.dtype}")
            elif isinstance(out, list):
                print(f"    [{i}]: list with {len(out)} elements")
                if len(out) > 0:
                    print(f"      first element type: {type(out[0]).__name__}")
                    if hasattr(out[0], "shape"):
                        print(f"      first element shape: {out[0].shape}")
    elif hasattr(outputs, "keys"):
        print(f"  Dict keys: {list(outputs.keys())}")
        for k, v in outputs.items():
            if hasattr(v, "shape"):
                print(f"    {k}: shape={v.shape}, dtype={v.dtype}")
            elif isinstance(v, list):
                print(f"    {k}: list[{len(v)}]")

    return {"available": True}


def _get_tokenizer():
    """Get the bge-m3 tokenizer (used for both probe methods), pinned revision."""
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained("BAAI/bge-m3", revision=BGE_M3_REVISION)


def _produce_verdict(ort_info: dict, optimum_info: dict) -> str:
    """Determine and print verdict."""
    print("\n" + "=" * 60)
    print("VERDICT")
    print("=" * 60)

    output_names = ort_info["output_names"]
    num_outputs = ort_info["num_outputs"]
    raw = ort_info["raw_outputs"]

    # Dense embedding output
    has_dense_output = any("dense" in n.lower() for n in output_names) or (
        num_outputs >= 1 and len(raw[0].shape) == 2
    )

    # Sparse output (lexical weights or token weights)
    has_sparse_output = any(
        "sparse" in n.lower() or "lexical" in n.lower() or "token_weight" in n.lower()
        for n in output_names
    ) or (num_outputs >= 2 and len(raw[1].shape) == 2 and raw[1].shape[-1] == 1)

    has_colbert = any("colbert" in n.lower() for n in output_names) or num_outputs >= 3

    print(f"  Output heads: {num_outputs}")
    for name, shape in zip(output_names, [o.shape for o in raw]):
        print(f"    {name}: {shape}")

    print()
    if has_sparse_output:
        print("  >> VERDICT: DENSE_AND_SPARSE (and ColBERT)" if has_colbert
              else "  >> VERDICT: DENSE_AND_SPARSE")
    else:
        print("  >> VERDICT: DENSE_ONLY")
    print()

    print("  Implications:")
    if has_sparse_output:
        print("    ✓ Live retrieval path (dense + sparse hybrid search) is feasible")
        print("    ✓ RAPTOR clustering (dense-only) is feasible")
    else:
        print("    ✗ Live retrieval path requires sparse head — NOT available")
        print("    ✓ RAPTOR clustering (dense-only) is feasible")
    if has_colbert:
        print("    ✓ ColBERT late interaction is available (optional)")
    print()

    return "DENSE_AND_SPARSE" if has_sparse_output else "DENSE_ONLY"


def _cleanup():
    """Remove the scratch directory."""
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
        print(f"Cleaned up scratch: {SCRATCH}")


def main():
    print(f"ONNX Embedding Probe — Candidate: {CANDIDATE}")
    print(f"Scratch directory: {SCRATCH}")
    print()

    try:
        local_path = _download_checkpoint()
        model_file = os.path.join(local_path, "model_quantized.onnx")

        if not os.path.exists(model_file):
            print(f"ERROR: model_quantized.onnx not found at {model_file}")
            # List what we got
            for f in Path(local_path).iterdir():
                print(f"  {f.name} ({f.stat().st_size / 1e6:.1f} MB)" if f.is_file()
                      else f"  {f.name}/")
            sys.exit(1)

        ort_info = _probe_with_onnxruntime(model_file)
        optimum_info = _probe_with_optimum(local_path)
        verdict = _produce_verdict(ort_info, optimum_info)

        print(f"\nFinal verdict: {verdict}")
        return verdict
    except Exception as e:
        print(f"\nERROR during probe: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        _cleanup()


if __name__ == "__main__":
    main()
