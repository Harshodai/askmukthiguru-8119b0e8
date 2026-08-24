import ast
import io
import tokenize
from pathlib import Path


def test_benchmark_cache_reset_has_no_shell_or_global_redis_flush():
    source_path = Path(__file__).parents[1] / "benchmarks" / "ruthless_benchmark.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "run"):
            continue
        if not (isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess"):
            continue
        assert not any(
            keyword.arg == "shell"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in node.keywords
        ), "benchmark subprocesses must never use shell=True"

    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    source_without_comments = tokenize.untokenize(
        token for token in tokens if token.type != tokenize.COMMENT
    )
    assert "flushall" not in source_without_comments.lower()
