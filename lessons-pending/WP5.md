# WP5 lesson entries (to merge into lessons.md)

### L-WP5-GUARANTEE-1 (2026-10-07): an outcome promise in generated text needs a deterministic floor, and quotes must stay out of it
Root cause: the only guard against "your problems will melt like ice" / "addictions spontaneously fall away" / "the hurt resolves naturally" in a generated answer was one prompt sentence ("You do not promise outcomes") plus a narrow verification regex (`i guarantee|this will cure`). Nothing caught a promise the model wrote anyway, and the live s1 answer shipped "the hurt resolves naturally".
Rule: every generated-answer return of `format_final_answer` passes `_label_synthesis`, which runs `services.voice.register.neutralize_guarantees` on the product's own prose ("will melt" -> "can melt", "spontaneously fall away" -> "can fall away", "I guarantee you can conquer any challenge" -> "You can meet challenges with more steadiness", time-to-result -> "with practice (how long it takes varies)"). Text inside quotation marks and blockquote lines is never edited: a verbatim teacher quote keeps its wording byte for byte, and the deterministic "What this teaching does not establish" note is appended instead. Negated forms ("there is no guarantee", "cannot cure") are left alone.
Test: backend/tests/test_manus_scenarios_e2e.py (`test_guarantee_phrasing_becomes_possibility`, `test_guarantee_rewriter_leaves_quotes_negations_and_plain_teaching_alone`, `test_teacher_quote_text_is_never_altered`).

### L-WP5-SCOPE-1 (2026-10-07): the scope note is keyed on what the seeker raised, not on words the answer happens to use
Root cause: a first cut triggered "not a treatment for anxiety" and "does not ask you to get in touch with anyone" on a root-cause-of-suffering answer, because the answer described the suffering state as "anxious" and mentioned "relationships". A test regex also matched "illness" inside "stillness".
Rule: clinical words and outcome words count anywhere (quotes included: a quoted promise is where the note matters); everyday distress words and relationship words count only in the question; contact advice in the answer counts. Always use word boundaries for health vocabulary.
Test: `test_scope_note_topics`.

### L-WP5-CITE-1 (2026-10-07): `_cite_sentences` flattened every paragraph and numbered list
Root cause: it split sentences on `(?<=[.!?])\s+` (newlines included) and rejoined with " ". A guided practice shipped as "...mind. 1. Sit ... 2. Breathe ...", and paragraph-level safety ordering (inner observation before contact advice) collapsed into one run-on block. Lines ending in a citation marker survived only by accident (the marker breaks the punctuation-whitespace pattern).
Rule: keep each sentence's original separator; only non-newline whitespace collapses to one space.
Test: `test_cite_sentences_keeps_paragraphs_and_numbered_steps`, and the S3 good-answer case (steps must stay one per line).

### L-WP5-ATTR-1 (2026-10-07): teacher-name support is judged per sentence, against the list the [n] markers index
Root cause: `_neutralize_unsupported_teacher_attribution` checked support answer-wide against `state["citations"]`. Live s1 kept "Sri Krishnaji describes this shift ... [3]" although [3] was an 'Ekam / O&O Academy' clip, because another sentence cited a Sri Krishnaji clip; live s2 kept "Sri Krishnaji teaches" on an unmarked paragraph drawn from a speaker-Unknown summary. Separately, the sentence-start check indexed the full answer with a paragraph-relative offset, so a rewrite could start a sentence with lower-case "the teachings".
Rule: `_label_synthesis` receives the FINAL citations (after `_sanitize_citations` / `remap_citation_markers`). When the answer uses markers, a sentence naming a teacher must cite, with its own marker, a source whose speaker is that teacher, or the paragraph must quote verbatim a document of that speaker; otherwise the name becomes "the teachings". An answer with no markers keeps the answer-wide check. Leading markers belong to the previous sentence.
Test: `test_s1_unsupported_attribution_is_rewritten_per_sentence`, the S1/S2 bad-answer cases; existing `test_attribution_floor_f2.py::test_terminal_node_keeps_attribution_when_sources_are_present` still passes.

### L-WP5-QUOTE-1 (2026-10-07): the fast-tier and redacted returns never demoted invented quotes
Root cause: `_unquote_unverifiable_spans` ran only on the main return of `format_final_answer`. The fast-tier and `grounded_redacted` returns shipped quoted spans found in no document as if they were a teacher's words, and (with the guarantee rewrite protecting quotes) an invented quoted promise would also have escaped neutralisation.
Rule: `_label_synthesis` demotes unverifiable quotes for every generated return before neutralising promises.
Test: `test_invented_quote_on_the_fast_and_redacted_returns_is_demoted_then_neutralised`.
