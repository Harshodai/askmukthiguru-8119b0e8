"""L-DOCKER-18: routes must Depends(get_container_async), never the sync get_container."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_route_uses_sync_get_container_dependency() -> None:
    offenders = []
    for folder in ("routers", "app/api"):
        for path in (ROOT / folder).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "Depends"
                    and node.args
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id == "get_container"
                ):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, f"sync Depends(get_container) (use get_container_async): {offenders}"
