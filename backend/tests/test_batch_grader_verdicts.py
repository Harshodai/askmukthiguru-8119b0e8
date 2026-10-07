"""The batch grader must report the grader's verdict, not overrule it.

Before 2026-09-26 both providers forced document 0 to relevant whenever nothing
came back relevant -- including when the grader explicitly said "no" to every
document -- so CRAG's rewrite/abstain branch could never fire on an honest "no".
"""

import pytest

from services.openrouter_service import OpenRouterService
from services.sarvam_service import SarvamCloudService

DOCS = ["The quietness of the night.", "A recipe for dal."]


def _service(cls, monkeypatch, grader_output):
    svc = cls.__new__(cls)  # grading logic only; no client or network needed

    async def fake_fast(*args, **kwargs):
        return grader_output

    monkeypatch.setattr(svc, "_generate_fast", fake_fast, raising=False)
    return svc


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", [OpenRouterService, SarvamCloudService])
async def test_explicit_no_to_every_document_is_respected(cls, monkeypatch):
    svc = _service(cls, monkeypatch, "1: no - off topic\n2: no - off topic")
    results = await svc.batch_grade_relevance("How do I quiet my mind?", DOCS)
    assert [r["relevant"] for r in results] == [False, False]


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", [OpenRouterService, SarvamCloudService])
async def test_unparseable_grader_output_keeps_top_document_as_before(cls, monkeypatch):
    svc = _service(cls, monkeypatch, "I cannot grade these documents.")
    results = await svc.batch_grade_relevance("How do I quiet my mind?", DOCS)
    assert [r["relevant"] for r in results] == [True, False]
    assert "unparseable" in results[0]["reason"].lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", [OpenRouterService, SarvamCloudService])
async def test_mixed_verdicts_pass_through(cls, monkeypatch):
    svc = _service(cls, monkeypatch, "1: yes - on topic\n2: no")
    results = await svc.batch_grade_relevance("How do I quiet my mind?", DOCS)
    assert [r["relevant"] for r in results] == [True, False]
