"""Static contract for the memory-extract edge function's prompt handling.

The extraction prompt was rewritten to put policy in the system role and the
conversation text in a separate JSON data payload (so transcript text cannot
act as instructions). Only the cloud branch was updated; the local Ollama
branch kept referencing the deleted ``extractionPrompt`` constant, which threw
``ReferenceError`` at request time, was swallowed by the surrounding ``try``,
and made local extraction silently return ``{inserted: 0}`` forever.
"""

from pathlib import Path

SOURCE = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "functions"
    / "memory-extract"
    / "index.ts"
)


def test_both_llm_branches_use_the_system_prompt_and_data_payload():
    source = SOURCE.read_text(encoding="utf-8")

    assert "extractionPrompt" not in source, (
        "the removed prompt constant is still referenced somewhere in the "
        "function; the local Ollama branch throws ReferenceError on every call"
    )
    assert source.count("extractionSystem") >= 3, (
        "expected the declaration plus one use per LLM branch (gateway, ollama)"
    )

    # Both branches must keep the untrusted transcript in a separate data
    # message, never concatenated into the instruction text.
    payload = 'JSON.stringify({ user_message: userMsg, assistant_message: assistantMsg })'
    assert source.count(payload) == 2
    assert source.count('{ role: "system", content: extractionSystem }') == 2
