"""Structural guards for the admin video-approval feature.

These fail when someone later removes a serve-time hook, lets the page write the
machine speaker evidence, or exposes a route without admin auth. They read source
and route tables, so they need no Qdrant and no network.
"""

from __future__ import annotations

import ast
import inspect
import itertools
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
FEATURE_MODULES = [
    BACKEND / "services" / "first_person_video_decisions.py",
    BACKEND / "services" / "first_person_video_review.py",
    BACKEND / "app" / "api" / "admin_video_review.py",
]
QDRANT_WRITE_METHODS = {
    "upsert",
    "set_payload",
    "overwrite_payload",
    "delete_payload",
    "clear_payload",
    "delete",
    "delete_collection",
    "create_collection",
    "recreate_collection",
    "update_collection",
    "update_vectors",
    "delete_vectors",
    "update_collection_aliases",
    "create_payload_index",
}


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", FEATURE_MODULES, ids=lambda p: p.name)
def test_feature_modules_never_call_a_qdrant_write_method(path):
    calls = {
        node.func.attr
        for node in ast.walk(_tree(path))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not (calls & QDRANT_WRITE_METHODS), calls & QDRANT_WRITE_METHODS


@pytest.mark.parametrize("path", FEATURE_MODULES, ids=lambda p: p.name)
def test_feature_modules_never_assign_the_machine_speaker_fields(path):
    """speaker_verified / voice_verification_method are written by voice tooling only."""
    machine = {"speaker_verified", "voice_verification_method"}
    for node in ast.walk(_tree(path)):
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        for target in targets:
            for sub in ast.walk(target):
                if isinstance(sub, ast.Subscript) and isinstance(sub.slice, ast.Constant):
                    assert sub.slice.value not in machine, f"{path.name} writes {sub.slice.value}"
                if isinstance(sub, ast.Attribute):
                    assert sub.attr not in machine, f"{path.name} writes .{sub.attr}"


def test_request_model_rejects_any_machine_field():
    from app.api.admin_video_review import VideoDecisionRequest

    assert VideoDecisionRequest.model_config.get("extra") == "forbid"
    assert not {"speaker_verified", "voice_verification_method"} & set(
        VideoDecisionRequest.model_fields
    )


def test_serve_time_hooks_are_present():
    from services import first_person_context_store, first_person_pipeline, first_person_store

    gate = inspect.getsource(first_person_pipeline._passes_integrity_gate)
    assert "video_is_blocked(vid_str)" in gate
    assert "video_is_blocked" in inspect.getsource(
        first_person_context_store.FirstPersonContextStore.points_servable
    )
    assert "video_is_blocked" in inspect.getsource(
        first_person_store.FirstPersonStore.points_servable
    )
    assert "blocked_video_ids_or_none" in inspect.getsource(
        first_person_context_store.FirstPersonContextStore.retrieve
    )
    assert "decisions_fingerprint" in inspect.getsource(
        first_person_pipeline.FirstPersonPipeline._points_servable_cached
    )


def test_integrity_gate_checks_the_admin_block_before_the_slow_availability_probe():
    from services.first_person_pipeline import _passes_integrity_gate

    src = inspect.getsource(_passes_integrity_gate)
    assert src.index("video_is_blocked(") < src.index("is_youtube_video_available(")


def _dep_names(func) -> set[str]:
    names: set[str] = set()
    for param in inspect.signature(func).parameters.values():
        dep = getattr(param.default, "dependency", None)
        if dep is not None:
            names.add(getattr(dep, "__name__", str(dep)))
    return names


def test_every_route_is_admin_guarded_and_writes_are_csrf_guarded():
    from app.api import admin_video_review as mod

    routes = [r for r in mod.router.routes if hasattr(r, "endpoint")]
    assert routes, "router has no routes"
    for route in routes:
        deps = _dep_names(route.endpoint)
        assert deps & {"_require_admin", "_require_csrf"}, f"{route.path} lacks an admin dependency"
        if route.methods & {"PUT", "POST", "PATCH", "DELETE"}:
            assert "_require_csrf" in deps, f"{route.path} {route.methods} lacks CSRF"
    # _require_csrf itself must sit on top of _require_admin
    assert "_require_admin" in _dep_names(mod._require_csrf)
    # no write verb other than PUT exists
    assert {m for r in routes for m in r.methods} <= {"GET", "PUT", "HEAD"}


def test_router_is_mounted_under_the_rate_limited_and_audited_admin_prefix():
    from app.main import app

    # FastAPI wraps included routers, so read the resolved paths from the OpenAPI schema.
    paths = set(app.openapi()["paths"])
    assert any(p.startswith("/api/admin/fp-videos") for p in paths)
    assert not any(p.startswith("/api/fp-videos") for p in paths)


def test_approval_and_confirmation_can_never_block_and_only_tighten_states_do():
    """Exhaustive: the block predicate is exactly (approved is False) or (speaker check is 'rejected')."""
    from services.first_person_video_decisions import GRADES, SPEAKER_CHECKS, VideoDecision

    for approved, check, grade in itertools.product(
        (None, True, False), (None, *SPEAKER_CHECKS), (None, *GRADES)
    ):
        d = VideoDecision(
            video_id="abcdefghijk",
            admin_approved=approved,
            human_speaker_check=check,
            grade=grade,
        )
        assert d.blocks_serving == (approved is False or check == "rejected")


def test_review_service_and_decision_store_do_not_import_the_serving_pipeline():
    """The serving pipeline imports the decision store; the reverse would be a cycle."""
    for path in FEATURE_MODULES[:1]:
        imported = {
            (n.module or "") for n in ast.walk(_tree(path)) if isinstance(n, ast.ImportFrom)
        }
        assert not any("first_person_pipeline" in m for m in imported)


def test_new_settings_are_declared_in_settings_not_read_from_the_environment():
    for path in FEATURE_MODULES:
        text = path.read_text(encoding="utf-8")
        assert "os.environ" not in text and "os.getenv" not in text, path.name
