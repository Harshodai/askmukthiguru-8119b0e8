"""
Unit tests for ingest/verbatim/asr_cleaner.py
"""

import pytest

from ingest.verbatim.asr_cleaner import (
    asr_cleaner_flags,
    asr_cleaner_notes,
    clean_clips,
    clean_verbatim_text,
)


class TestCleanVerbatimText:
    def test_rhetorical_sentence_repetition_preserved(self):
        """Sentence-boundary repetitions are preserved and not deleted."""
        s1 = "What is peace? Peace is an inner state."
        assert clean_verbatim_text(s1) == s1

        s2 = "Silence. Silence is not absence."
        assert clean_verbatim_text(s2) == s2

    def test_asr_cleaner_flags(self):
        """asr_cleaner_flags detects non-mutated patterns as quarantine reasons."""
        retreat = "In February when we meet, we will meditate."
        assert "retreat_date_announcement" in asr_cleaner_flags(retreat)

        severed = "This is the state from which you perform"
        assert "severed_trailing_clause" in asr_cleaner_flags(severed)

        ack = "Yes. Any time you want."
        assert "embedded_audience_ack" in asr_cleaner_flags(ack)

        clean = "Meditation brings deep stillness."
        assert asr_cleaner_flags(clean) == []

    def test_stutter_so_removal(self):
        """'So, So the thing' -> 'So the thing'"""
        result = clean_verbatim_text("So, So the thing is important.")
        assert result == "So the thing is important."

    def test_you_know_you_know_removal(self):
        """'you know, you know' de-dup"""
        result = clean_verbatim_text("You know, you know, when she is sad, you are actually there.")
        assert result == "You know, when she is sad, you are actually there."

    def test_it_kind_of_opener_removal(self):
        """'It kind of,' opener removed and first letter capitalized"""
        result = clean_verbatim_text("It kind of, any time you feel disturbed.")
        assert result == "Any time you feel disturbed."

    def test_no_no_reduction(self):
        """'no, no,' collapses to 'no,'"""
        result = clean_verbatim_text("He will say, no, no, I want to have my alcohol.")
        assert result == "He will say, no, I want to have my alcohol."

    def test_idempotency(self):
        """Running clean twice gives same result as running once."""
        text = "So, So the thing is. He will say, no, no, I want alcohol."
        once = clean_verbatim_text(text)
        twice = clean_verbatim_text(once)
        assert once == twice

    def test_empty_string_returns_empty(self):
        """Edge case: empty string returns empty string, no crash."""
        assert clean_verbatim_text("") == ""

    def test_clean_text_is_unchanged(self):
        """Clean text with no noise is not modified."""
        text = "Suffering arises when we resist what is. The moment you stop resisting, freedom appears."
        assert clean_verbatim_text(text) == text

    def test_first_letter_capitalized_after_it_kind_of_removal(self):
        """After removing 'It kind of,' the first letter of the remainder is capitalized."""
        result = clean_verbatim_text("It kind of, beauty is in the state within.")
        assert result[0].isupper()

    def test_double_spaces_cleaned(self):
        """No double spaces remain in output."""
        # Inject via a pattern that leaves double space
        result = clean_verbatim_text("So, So  the thing is right.")
        assert "  " not in result


class TestCleanClips:
    def test_clean_clips_modifies_verbatim_text(self):
        """clean_clips modifies verbatim_text in-place and returns the list."""
        clips = [{"verbatim_text": "So, So it is important."}]
        result = clean_clips(clips)
        assert result is clips  # same list returned
        assert result[0]["verbatim_text"] == "So it is important."

    def test_clean_clips_skips_clips_without_verbatim_text(self):
        """Clips missing 'verbatim_text' are not touched."""
        clips = [{"other_field": "value"}]
        result = clean_clips(clips)
        assert result[0] == {"other_field": "value"}

    def test_clean_clips_handles_empty_list(self):
        """Empty list returns empty list without error."""
        assert clean_clips([]) == []

    def test_clean_clips_multiple_clips(self):
        """All clips in the list are cleaned."""
        clips = [
            {"verbatim_text": "So, So the first clip."},
            {"verbatim_text": "It kind of, the second clip."},
        ]
        result = clean_clips(clips)
        assert result[0]["verbatim_text"] == "So the first clip."
        assert result[1]["verbatim_text"] == "The second clip."


class TestChantsAreNotCollapsed:
    """Invocations are repeated on purpose; the audio window plays the full chant."""

    def test_repeated_chants_are_kept(self):
        for text in (
            "Peace, peace, peace, peace to every being.",
            "Namaste, namaste to all of you.",
            "Shanti, shanti, shanti.",
        ):
            assert clean_verbatim_text(text) == text, text

    def test_ordinary_stutters_are_still_removed(self):
        assert clean_verbatim_text("She carried carried the weight.") == "She carried the weight."
        # an IMMEDIATE repeat only; a comma between the words is emphasis, see below
        assert clean_verbatim_text("relationships relationships are mirrors.") == (
            "relationships are mirrors."
        )

    def test_chant_protection_is_idempotent(self):
        text = "Peace, peace, peace, peace to every being."
        once = clean_verbatim_text(text)
        assert clean_verbatim_text(once) == once


class TestCommaRepeatsAreNotesNotEdits:
    """2026-10-28 review: a comma-separated echo may have been spoken; deleting it breaks
    the quote/audio match. The cleaner leaves it and reports it."""

    KEPT = [
        "I need you to be very, very patient with yourself.",
        "Life is a gift, a gift of a Beautiful State.",
        "Peace, peace, peace, peace, peace.",
        "It is, it is a quiet knowing.",
    ]

    def test_comma_separated_repeats_are_unchanged(self):
        for text in self.KEPT:
            assert clean_verbatim_text(text) == text, text

    def test_notes_name_them_without_editing(self):
        assert "comma_repeat" in asr_cleaner_notes(self.KEPT[0])
        assert "false_start_repeat" in asr_cleaner_notes(self.KEPT[1])
        assert asr_cleaner_notes("A clean sentence.") == []
        assert asr_cleaner_notes("") == []

    def test_notes_never_quarantine(self):
        # asr_cleaner_flags is the quarantine list; notes must not leak into it
        assert asr_cleaner_flags(self.KEPT[0]) == []
        assert asr_cleaner_flags(self.KEPT[2]) == []


@pytest.mark.parametrize(
    "text",
    [
        "So, so, so, what happens when you sit",
        "No, no, no, I do not want it.",
        "Yes, yes, yes. Okay, okay, okay, then we begin.",
        "You know, you know, you know, it is simple.",
        "I mean, I mean, I mean it.",
    ],
)
def test_cleaner_is_idempotent_on_stutter_runs(text):
    """The store re-cleans before hashing its point id, so clean(clean(x)) == clean(x)."""
    once = clean_verbatim_text(text)
    assert clean_verbatim_text(once) == once
