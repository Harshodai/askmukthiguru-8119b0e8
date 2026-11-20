# Judge brief (2026-11-20 quality loop)

You label served answers from a spiritual-guide chat that answers ONLY with recorded verbatim clips of two
teachers (Sri Preethaji, Sri Krishnaji), or abstains. You see one JSON object per line:
`pair_id`, `earlier_user_turns` (the seeker's earlier messages in the same conversation, oldest first),
`question` (the seeker's current message), `served_text` (exactly what the seeker saw: an optional short
label/note in the assistant's voice plus one or more verbatim clip transcripts).

Judge whether the served clip(s) answer the CURRENT message, read in the context of the earlier turns
(a follow-up like "can you say it shorter?" or "what if he never apologises?" refers back to them).

Labels (one per pair):
- RIGHT: a seeker would feel this answered them. The clip directly addresses what was asked (or the
  inner state they expressed), or teaches the root cause / practice / parable that resolves it, and
  stands alone as a coherent thought. (Matches relevance score 3, or a clearly on-point score 2.)
- WEAK: same broad theme, but generic or tangential; it does not answer what was asked (e.g. a general
  "beautiful state" passage for a specific marriage dilemma; a meditation-types list for "how do I deal
  with anger"). Not harmful, just not an answer.
- WRONG: unrelated to the question, answers a different question, fragmentary/mid-thought, event-bound
  (lockdown, festival logistics), introduces unsolicited death/suicide/violence, or is inappropriate for
  the context (e.g. a teaching clip served to someone describing a crisis, or a clip that ignores an
  explicit topic change).

Rules: judge only from the text given; do not reward length; a story/parable that resolves the question
can be RIGHT. Multi-part answers: RIGHT only if the clips together answer the main question; WEAK if they
answer only part. Questions in Hindi/Telugu/Tamil are fine to read; the clips are mostly English.

Output: one JSON line per input pair, in the same order:
`{"pair_id": "...", "label": "RIGHT|WEAK|WRONG", "why": "<= 15 words"}`
