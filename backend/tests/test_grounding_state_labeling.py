"""A shipped answer must not be labelled an abstention.

`grounding_state` feeds hallucination analytics. The terminal success branch of
`format_final_answer` never set it, so an "abstained" written earlier in the
graph survived onto answers that shipped with full prose and citations —
observed live 2026-09-12 on a tier3_complex response.
"""

import inspect

from rag.nodes import generation


def test_success_branch_sets_grounding_state():
    src = inspect.getsource(generation.format_final_answer)
    # The terminal result dict is the one carrying follow_up_suggestions.
    assert '"follow_up_suggestions": follow_up_suggestions,' in src
    head, _, tail = src.partition('"follow_up_suggestions": follow_up_suggestions,')
    assert '"grounding_state": "grounded"' in tail[:800], (
        "the shipped-answer branch must state its own grounding_state rather "
        "than inheriting a stale one"
    )


def test_abstention_branches_still_label_abstained():
    src = inspect.getsource(generation)
    assert src.count('"grounding_state": "abstained"') >= 4
