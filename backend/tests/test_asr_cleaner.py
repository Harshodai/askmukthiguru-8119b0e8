"""
Unit tests for ingest/verbatim/asr_cleaner.py
"""

from ingest.verbatim.asr_cleaner import clean_clips, clean_verbatim_text


class TestCleanVerbatimText:
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
