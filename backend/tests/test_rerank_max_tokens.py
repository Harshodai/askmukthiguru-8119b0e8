"""NEW-LOAD-6: the LLM rerank call sets a small explicit max_tokens.

The rerank returns clip indices ("2,1,3") or "NONE". Without max_tokens a
call could run to the provider default (2048, capped at the 800-token fast
ceiling on OpenRouter; 8192 on Sarvam or NIM; LOAD_AND_COST_MODEL.md §2).
Eight indices with commas need about 16 tokens.
"""

from __future__ import annotations

from services.first_person_pipeline import _RERANK_MAX_TOKENS, _llm_rerank_clips


class _LLM:
    def __init__(self):
        self.kwargs = None

    def generate(self, **kwargs):
        self.kwargs = kwargs
        return "2,1"


def test_rerank_sends_small_max_tokens():
    llm = _LLM()
    _llm_rerank_clips("q", [{"verbatim_text": "a"}, {"verbatim_text": "b"}], llm)
    assert llm.kwargs["max_tokens"] == _RERANK_MAX_TOKENS
    assert 16 <= _RERANK_MAX_TOKENS <= 32
