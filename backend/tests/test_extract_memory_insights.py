"""Tests for rag.memory.extract_memory_insights (handoff §A3).

Contract: top-5 docs × 400-char snippets → one LLM call → up to k atomic
one-sentence claims as a JSON list of strings. [] on empty docs, no usable
text, no provider, LLM failure, unparsable output, or contaminated output.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag.memory import (
    _insight_snippets,
    _parse_insight_list,
    extract_memory_insights,
)


def _mock_openai_client(content: str):
    """OpenAI-compatible mock client returning `content` as the LLM reply."""
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = content
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
    return mock_client


def _doc(text: str) -> dict:
    return {"text": text, "source_url": "https://example.org/t1"}


class TestParseInsightList:
    def test_valid_list(self):
        assert _parse_insight_list(
            '["A still mind sees clearly.", "Breath anchors attention."]', 3
        ) == [
            "A still mind sees clearly.",
            "Breath anchors attention.",
        ]

    def test_caps_at_k(self):
        raw = json.dumps([f"Claim {i}." for i in range(6)])
        assert len(_parse_insight_list(raw, 3)) == 3

    def test_drops_non_strings_and_empties(self):
        raw = json.dumps([" Real claim. ", 42, None, "", {"a": 1}, "Second."])
        assert _parse_insight_list(raw, 5) == ["Real claim.", "Second."]

    def test_dedupes_case_insensitively(self):
        raw = json.dumps(["Same claim.", "same CLAIM. ", "Other."])
        assert _parse_insight_list(raw, 5) == ["Same claim.", "Other."]

    def test_rejects_garbage(self):
        assert _parse_insight_list("not json at all", 3) == []
        assert _parse_insight_list("", 3) == []
        assert _parse_insight_list('{"a": 1}', 3) == []
        assert _parse_insight_list("[1, 2", 3) == []

    def test_salvages_embedded_array(self):
        # Same salvage semantics as the canonical extractor's
        # _extract_json_array: prose-wrapped arrays still parse.
        assert _parse_insight_list('Here you go: ["Wrapped claim."]', 3) == ["Wrapped claim."]

    def test_strips_markdown_fence(self):
        raw = '```json\n["Fenced claim."]\n```'
        assert _parse_insight_list(raw, 3) == ["Fenced claim."]


class TestInsightSnippets:
    def test_dict_and_object_shapes(self):
        docs = [
            {"text": "dict text"},
            {"content": "dict content"},
            {"page_content": "dict page"},
            SimpleNamespace(page_content="object page"),
            SimpleNamespace(text="object text"),
        ]
        out = _insight_snippets(docs)
        for expected in ("dict text", "dict content", "dict page", "object page", "object text"):
            assert expected in out

    def test_truncates_to_400_chars(self):
        long_text = "A" * 1000
        out = _insight_snippets([_doc(long_text)])
        assert "A" * 400 in out
        assert "A" * 401 not in out

    def test_caps_at_five_docs(self):
        docs = [_doc(f"UNIQUE-DOC-{i} filler text here") for i in range(7)]
        out = _insight_snippets(docs)
        assert "UNIQUE-DOC-5" not in out
        assert "UNIQUE-DOC-6" not in out
        assert "UNIQUE-DOC-4" in out

    def test_empty_inputs(self):
        assert _insight_snippets([]) == ""
        assert _insight_snippets([{}, {"text": "   "}, None]) == ""


class TestExtractMemoryInsights:
    @pytest.mark.asyncio
    async def test_empty_docs_skips_llm(self):
        with patch("rag.memory._build_llm_client") as mock_build:
            assert await extract_memory_insights([]) == []
            mock_build.assert_not_called()

    @pytest.mark.asyncio
    async def test_unusable_text_skips_llm(self):
        with patch("rag.memory._build_llm_client") as mock_build:
            assert await extract_memory_insights([{}, {"text": "  "}]) == []
            mock_build.assert_not_called()

    @pytest.mark.asyncio
    @patch("rag.memory._build_llm_client")
    async def test_no_provider_returns_empty(self, mock_build):
        mock_build.return_value = None
        assert await extract_memory_insights([_doc("Deeksha is initiation.")]) == []

    @pytest.mark.asyncio
    @patch("rag.memory._build_llm_client")
    @patch("rag.memory.find_artifact", return_value=None)
    async def test_caps_claims_at_k(self, mock_artifact, mock_build):
        mock_build.return_value = (
            _mock_openai_client(json.dumps([f"Claim {i}." for i in range(5)])),
            "m",
        )
        out = await extract_memory_insights([_doc("Some teaching text.")], k=3)
        assert out == ["Claim 0.", "Claim 1.", "Claim 2."]

    @pytest.mark.asyncio
    @patch("rag.memory._build_llm_client")
    @patch("rag.memory.find_artifact", return_value=None)
    async def test_fewer_than_k_returned_as_is(self, mock_artifact, mock_build):
        mock_build.return_value = (_mock_openai_client(json.dumps(["Only one."])), "m")
        assert await extract_memory_insights([_doc("Some teaching text.")], k=3) == ["Only one."]

    @pytest.mark.asyncio
    @patch("rag.memory._build_llm_client")
    @patch("rag.memory.find_artifact", return_value=None)
    async def test_invalid_json_returns_empty(self, mock_artifact, mock_build):
        mock_build.return_value = (_mock_openai_client("I could not extract anything."), "m")
        assert await extract_memory_insights([_doc("Some teaching text.")]) == []

    @pytest.mark.asyncio
    @patch("rag.memory._build_llm_client")
    @patch("rag.memory.find_artifact", return_value="cot_leak_marker")
    async def test_contamination_rejected(self, mock_artifact, mock_build):
        mock_build.return_value = (_mock_openai_client(json.dumps(["Looks fine."])), "m")
        assert await extract_memory_insights([_doc("Some teaching text.")]) == []

    @pytest.mark.asyncio
    @patch("rag.memory._build_llm_client")
    async def test_llm_error_returns_empty(self, mock_build):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("down"))
        mock_build.return_value = (mock_client, "m")
        assert await extract_memory_insights([_doc("Some teaching text.")]) == []

    @pytest.mark.asyncio
    @patch("rag.memory._build_llm_client")
    @patch("rag.memory.find_artifact", return_value=None)
    async def test_snippet_truncation_in_sent_prompt(self, mock_artifact, mock_build):
        client = _mock_openai_client(json.dumps(["Claim."]))
        mock_build.return_value = (client, "m")
        await extract_memory_insights([_doc("Z" * 1000)])
        sent = client.chat.completions.create.call_args
        user_msg = sent.kwargs["messages"][1]["content"]
        assert "Z" * 400 in user_msg
        assert "Z" * 401 not in user_msg

    @pytest.mark.asyncio
    @patch("rag.memory.find_artifact", return_value=None)
    async def test_ollama_native_branch(self, mock_artifact):
        fake = SimpleNamespace(
            generate=AsyncMock(return_value=json.dumps(["Native claim.", "Second."]))
        )
        with patch("rag.memory._build_llm_client", return_value=(fake, "m", "ollama_native")):
            out = await extract_memory_insights([_doc("Teaching.")], k=2)
        assert out == ["Native claim.", "Second."]
        fake.generate.assert_awaited_once()
