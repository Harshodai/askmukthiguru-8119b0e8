"""GURU-012 remainder (H27): a wisdom tip credits a teacher only with a locator.

A locator is a span/point id, or a YouTube video id plus a start time. A tip
without one is served with no teacher credit (teacher == ""), whether it was
curated by an admin, harvested from the corpus, or read from the tips cache.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.api import teachings as t

TEACHER = "Sri Preethaji & Sri Krishnaji"


@pytest.mark.parametrize(
    ("tip", "ok"),
    [
        ({"span_id": "span-1"}, True),
        ({"point_id": "8a6e0804-2bd0-5a5c-9d9b-0b5f6f1e8f11"}, True),
        ({"video_id": "dQw4w9WgXcQ", "start_ms": 12000}, True),
        ({"video_id": "dQw4w9WgXcQ", "start_ms": 0}, True),
        ({"video_id": "dQw4w9WgXcQ"}, False),
        ({"video_id": "not a video id", "start_ms": 5}, False),
        ({"video_id": "dQw4w9WgXcQ", "start_ms": -1}, False),
        ({"video_id": "dQw4w9WgXcQ", "start_ms": True}, False),
        ({"source": "Master Discourse"}, False),
        ({}, False),
    ],
)
def test_has_locator(tip, ok):
    assert t._has_locator(tip) is ok


def test_payload_strips_credit_without_locator():
    payload = t._build_payload(
        [
            {"text": "a", "teacher": TEACHER},
            {"text": "b", "teacher": TEACHER, "video_id": "dQw4w9WgXcQ", "start_ms": 1000},
        ]
    )
    teachers = [tip["teacher"] for tip in payload["tips"]]
    assert teachers == ["", TEACHER]


def test_harvested_tip_without_locator_has_no_credit():
    row = {"content": "Suffering is a call to awaken. It is not a punishment.", "metadata": {}}
    qdrant = SimpleNamespace(scroll_content=lambda topic, limit=25: [row])
    pool = t._harvest_tip_pool(qdrant)
    assert pool and all(tip["teacher"] == "" for tip in pool)


def test_harvested_tip_with_locator_keeps_credit():
    row = {
        "content": "Suffering is a call to awaken. It is not a punishment.",
        "metadata": {"video_id": "dQw4w9WgXcQ", "start_ms": 4200, "teacher": "Sri Krishnaji"},
    }
    qdrant = SimpleNamespace(scroll_content=lambda topic, limit=25: [row])
    pool = t._harvest_tip_pool(qdrant)
    assert pool[0]["teacher"] == "Sri Krishnaji"
    assert pool[0]["video_id"] == "dQw4w9WgXcQ" and pool[0]["start_ms"] == 4200


def test_cached_payload_is_re_checked(monkeypatch):
    cached = {"tips": [{"id": "x", "text": "a", "teacher": TEACHER}], "generated_at": "t"}

    class _Redis:
        def get(self, _key):
            return json.dumps(cached)

    monkeypatch.setattr(t, "_get_redis", lambda: _Redis())
    out = asyncio.run(t.get_wisdom_tips(container=None))
    assert out["tips"][0]["teacher"] == ""


def test_admin_tip_without_locator_is_stored_without_credit(monkeypatch):
    saved = {}
    monkeypatch.setattr(t, "_get_curated_library", lambda: [])
    monkeypatch.setattr(t, "_save_curated_library", lambda lib: saved.setdefault("lib", lib))
    monkeypatch.setattr(t, "_get_redis", lambda: None)

    async def _gen(_c):
        return {}

    monkeypatch.setattr(t, "_generate_tips", _gen)
    admin = {"is_superuser": True}
    entry = asyncio.run(
        t.add_curated_teaching(
            {"text": "Be still.", "teacher": TEACHER}, user=admin, container=None
        )
    )
    assert entry["teacher"] == ""
    entry = asyncio.run(
        t.add_curated_teaching(
            {"text": "Be still.", "teacher": TEACHER, "video_id": "dQw4w9WgXcQ", "start_ms": 3000},
            user=admin,
            container=None,
        )
    )
    assert entry["teacher"] == TEACHER
    assert entry["video_id"] == "dQw4w9WgXcQ" and entry["start_ms"] == 3000
