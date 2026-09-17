"""services/onnx_reranker.py:128 sized intra_op_num_threads from raw
os.cpu_count() -- reads the HOST/VM core count inside a container (10 on
the dev Docker Desktop VM), not the cgroup CPU quota (4.0). Same defect
class as L-DOCKER-9 (MKL/OpenBLAS/OMP), already fixed for the sibling
ONNX session in services/embedding_service.py:385-391. Fix: reuse
settings.omp_num_threads as the operator-tunable budget instead of
re-deriving one from cpu_count().
"""

from __future__ import annotations

import importlib


def _load_module():
    try:
        return importlib.import_module("services.onnx_reranker")
    except ImportError:
        return importlib.import_module("backend.services.onnx_reranker")


def test_reranker_session_reads_omp_num_threads_setting():
    m = _load_module()
    src = open(m.__file__).read()
    assert "settings.omp_num_threads" in src or "omp_num_threads" in src, (
        "OnnxReranker must size its ONNX thread pool from settings.omp_num_threads, "
        "not raw os.cpu_count()"
    )
    assert "intra_op_num_threads" in src and "inter_op_num_threads" in src


def _session_sizing_lines(path: str) -> list[str]:
    """The lines that actually assign an ONNX intra/inter-op thread count."""
    return [
        ln
        for ln in open(path).read().splitlines()
        if "op_num_threads" in ln and not ln.lstrip().startswith("#")
    ]


def test_no_onnx_session_sizes_threads_from_cpu_count():
    """Regression: both ONNX sessions must size from settings.omp_num_threads.

    An earlier fix left a `min(budget, (os.cpu_count() or 2) // 2)` ceiling on
    the assignment, which re-derives the HOST core count the fix existed to
    stop using -- and silently caps below the operator's configured budget on
    a host with fewer cores. Asserts against the real modules, not a copy of
    the formula: a test that re-implements the expression it is guarding
    passes even when the production code is wrong.
    """
    reranker = _load_module()
    try:
        embedding = importlib.import_module("services.embedding_service")
    except ImportError:
        embedding = importlib.import_module("backend.services.embedding_service")

    for mod in (reranker, embedding):
        lines = _session_sizing_lines(mod.__file__)
        assert lines, f"no intra/inter_op_num_threads assignment found in {mod.__file__}"
        for ln in lines:
            assert "cpu_count" not in ln, (
                f"{mod.__file__}: ONNX thread sizing must come from "
                f"settings.omp_num_threads, not cpu_count() -- got: {ln.strip()}"
            )


if __name__ == "__main__":
    test_reranker_session_reads_omp_num_threads_setting()
    test_no_onnx_session_sizes_threads_from_cpu_count()
    print("ok")
