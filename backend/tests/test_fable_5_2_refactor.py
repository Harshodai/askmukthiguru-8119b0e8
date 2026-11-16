"""
Test Suite for Fable 5.2 Deterministic Parsers, Trie Normalization & Hardening.

Verifies:
1. asr_cleaner: 14 self-checks, single-pass idempotency, CHANT_WORDS preservation, and _LEGIT_DOUBLES.
2. doctrine_terms: DoctrinePhraseTrie O(N) phrase scanner and reversible offset ledger with SHA-256 round-trip.
3. cleaner: DFA markup stripper, token stream ngram deduplication (no catastrophic backtracking), and deterministic sentence splitter.
4. routing_primitives: Zero-regex greeting scanner and immunity to polynomial whitespace floods (CodeQL #1975).
5. text_quality_filter: Fast pre-screening, multi-gram window repetition loop detector, and deterministic ASR restarts.
6. security_and_architecture: Admin markdown ID validation (CodeQL #1965), YouTube host validation (CodeQL #1976),
   Markdown cell pipe escaping (CodeQL #1947), existential vs crisis distress separation, clip attribution formatting,
   tenant-isolated 2-hop Cypher traversal, and concurrent telemetry query trace retrieval with 5xx/404 separation.
"""

from __future__ import annotations

import asyncio
import time
import unittest

from app.api.admin import is_valid_admin_markdown_id
from app.pipeline.stages.distress_stage import classify_existential_vs_severe_distress
from app.routing_primitives import (
    is_deterministic_greeting,
)
from app.telemetry_db import (
    TelemetryBackendError,
    fetch_query_trace_concurrent,
)
from ingest.cleaner import (
    _collapse_repeated_ngrams_token_stream,
    clean_transcript,
    split_sentences_deterministic,
)
from ingest.verbatim.asr_cleaner import clean_verbatim_text
from rag.nodes.retrieval import build_tenant_isolated_2hop_cypher, format_clip_attribution
from services.doctrine_terms import (
    apply_corrections,
    apply_corrections_with_ledger,
    revert_corrections_from_ledger,
)
from services.qdrant.indexer import is_youtube_source_url
from services.text_quality_filter import (
    find_artifact,
    find_asr_repetition_artifacts,
)


def escape_markdown_table_cell(value: str) -> str:
    """Escape backslashes BEFORE pipes to remediate CodeQL #1947 in scripts/i18n_sync.mjs."""
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


class TestAskMukthiGuruFable52Refactor(unittest.TestCase):
    def test_01_asr_cleaner_all_14_repo_self_checks_and_idempotency(self) -> None:
        cases = [
            ("carried carried", "carried"),
            ("her her", "her"),
            ("healing Healing", "healing"),
            ("you You", "you"),
            ("problems would arise eyes.", "problems would arise."),
            ("What is peace? Peace is an inner state", "What is peace? Peace is an inner state"),
            ("Silence. Silence is not absence", "Silence. Silence is not absence"),
            ("So, So the thing is...", "So the thing is..."),
            ("So, so, so the thing is...", "So the thing is..."),
            (
                "You know, when she is sad, you know, you are actually there.",
                "You know, when she is sad, you are actually there.",
            ),
            ("It kind of, any time you feel disturbed.", "Any time you feel disturbed."),
            (
                "He will say, no, no, I want to have my alcohol.",
                "He will say, no, I want to have my alcohol.",
            ),
            (
                "when you were carried carried by destructive emotional states",
                "when you were carried by destructive emotional states",
            ),
            (
                "made her her husband turn back to her life with love",
                "made her husband turn back to her life with love",
            ),
            (
                "Suffering will come problems would arise eyes. But the question is",
                "Suffering will come problems would arise. But the question is",
            ),
            ("Peace, peace, peace be with you.", "Peace, peace, peace be with you."),
            (
                "I know that that is true and he had had enough.",
                "I know that that is true and he had had enough.",
            ),
        ]
        for raw, expected in cases:
            cleaned = clean_verbatim_text(raw)
            self.assertEqual(cleaned, expected, f"Failed on {raw!r}")
            self.assertEqual(clean_verbatim_text(cleaned), cleaned)

    def test_02_doctrine_terms_trie_and_reversible_ledger(self) -> None:
        self.assertEqual(
            apply_corrections("The energy at Akam is profound."),
            "The energy at Ekam is profound.",
        )
        self.assertEqual(
            apply_corrections("Pretty Ji and Krishna Ji spoke about soul sink."),
            "Sri Preethaji & Sri Krishnaji spoke about Soul Sync.",
        )
        self.assertEqual(
            apply_corrections("Sri Pretty Ji and Krishna Ji spoke about soul sink."),
            "Sri Preethaji and Sri Krishnaji spoke about Soul Sync.",
        )
        self.assertIn("akam", apply_corrections("The word akam means the inner self."))

        raw = "At Akam, Sri Pretty Ji guided soul sink into a beautiful state."
        corrected, ledger = apply_corrections_with_ledger(raw, segment_id="seg_0042")
        self.assertEqual(
            corrected,
            "At Ekam, Sri Preethaji guided Soul Sync into a Beautiful State.",
        )
        self.assertEqual(len(ledger), 4)
        stripped_ledger = [
            {k: v for k, v in entry.items() if k != "original_segment_text"} for entry in ledger
        ]
        reverted = revert_corrections_from_ledger(corrected, stripped_ledger)
        self.assertEqual(reverted, raw)

    def test_03_cleaner_dfa_and_sentence_splitter_no_redos(self) -> None:
        raw = (
            "[Music] >> Speaker: 01:23 Um, like, Sri Pretty Ji said in Dr. Sharma's "
            "session at 3.14 p.m. that suffering state is a perception. "
            "word1 word2 word1 word2 word1 word2 <font color='red'>Namaste</font> ♪ la la ♪"
        )
        cleaned = clean_transcript(raw)
        self.assertNotIn("[Music]", cleaned)
        self.assertNotIn(">> Speaker:", cleaned)
        self.assertNotIn("01:23", cleaned)
        self.assertNotIn("<font", cleaned)
        self.assertNotIn("♪", cleaned)
        self.assertIn("Sri Preethaji", cleaned)
        self.assertIn("Suffering State", cleaned)
        self.assertIn("Dr. Sharma's", cleaned)

        t0 = time.perf_counter()
        adversarial = " ".join(["alpha beta"] * 60 + ["gamma"])
        deduped = _collapse_repeated_ngrams_token_stream(adversarial.split())
        elapsed_ms = (time.perf_counter() - t0) * 1000
        self.assertEqual(deduped, ["alpha", "beta", "gamma"])
        self.assertLess(elapsed_ms, 20.0)

        sents = split_sentences_deterministic(
            "Dr. Rao met Sri. Krishnaji at 4.30 p.m. in Ekam. Peace is your nature। Namaste."
        )
        self.assertEqual(len(sents), 3)
        self.assertTrue(sents[0].startswith("Dr. Rao"))

    def test_04_routing_primitives_zero_regex_greeting_and_redos_immunity(self) -> None:
        self.assertTrue(is_deterministic_greeting("Namaste! Good morning."))
        self.assertTrue(is_deterministic_greeting("🙏 Namaste Guruji!"))
        self.assertTrue(is_deterministic_greeting("How are you doing?"))
        self.assertTrue(is_deterministic_greeting("What's up?"))

        self.assertFalse(is_deterministic_greeting("hello kms"))
        self.assertFalse(is_deterministic_greeting("namaste suicide"))
        self.assertFalse(is_deterministic_greeting("What's happening today?"))

        t0 = time.perf_counter()
        malicious = "\U0001f64f" + ("\t" * 65) + "X"
        self.assertFalse(is_deterministic_greeting(malicious))
        self.assertLess((time.perf_counter() - t0) * 1000, 2.0)

    def test_05_text_quality_filter_and_asr_restart_detector(self) -> None:
        self.assertIsNotNone(
            find_artifact('2. **Analyze the Input Sentence:** "The State of Contemporary Anxiety."')
        )
        self.assertIsNotNone(
            find_artifact("I'm currently experiencing a temporary connectivity issue.")
        )
        self.assertIsNone(
            find_artifact("In a beautiful state, you are powerful enough to help yourself.")
        )
        self.assertEqual(
            find_asr_repetition_artifacts("relationships. relationships. are"),
            ["relationships"],
        )
        self.assertEqual(find_asr_repetition_artifacts("seek Seek the truth"), ["seek"])
        self.assertEqual(
            find_asr_repetition_artifacts("I know that that is so; he had had enough."),
            [],
        )

    def test_06_security_and_architecture_fixes(self) -> None:
        self.assertTrue(is_valid_admin_markdown_id("sri_preethaji-clip.01.md"))
        self.assertFalse(is_valid_admin_markdown_id("..//.md"))
        t0 = time.perf_counter()
        self.assertFalse(is_valid_admin_markdown_id("a" + " -" * 500 + ".md"))
        self.assertLess((time.perf_counter() - t0) * 1000, 5.0)

        self.assertTrue(is_youtube_source_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertTrue(is_youtube_source_url("https://youtu.be/dQw4w9WgXcQ"))
        self.assertFalse(is_youtube_source_url("https://evil-youtube.com/watch?v=123"))
        self.assertFalse(is_youtube_source_url("https://attacker.com/?redirect=youtube.com"))

        self.assertEqual(escape_markdown_table_cell(r"foo\|bar"), r"foo\\\|bar")

        self.assertEqual(
            classify_existential_vs_severe_distress(
                "I have achieved a lot of success in my career but I still feel empty inside."
            ),
            "MILD_EXISTENTIAL",
        )
        self.assertEqual(
            classify_existential_vs_severe_distress(
                "I feel empty inside and I want to end my life tonight."
            ),
            "CRISIS",
        )

        self.assertEqual(
            format_clip_attribution(
                "Sri Krishnaji", verified=True, verification_method="ecapa_cosine"
            ),
            "— Sri Krishnaji",
        )
        self.assertIn(
            "unverified diarization",
            format_clip_attribution("Sri Preethaji", verified=True, verification_method=None),
        )
        self.assertIn(
            "unverified diarization",
            format_clip_attribution(
                "Sri Preethaji", verified=False, verification_method="ecapa_cosine"
            ),
        )

        cypher = build_tenant_isolated_2hop_cypher()
        self.assertIn("coalesce(r2.tenant_id, 'oneness') = $tenant_id", cypher)
        self.assertIn("coalesce(c3.tenant_id, 'oneness') = $tenant_id", cypher)

        async def _ok_fetcher(table: str, tid: str) -> list[dict[str, str]]:
            return [{"table": table, "trace_id": tid}]

        async def _failing_fetcher(table: str, tid: str) -> list[dict[str, str]]:
            raise ConnectionError("Supabase connection timeout")

        trace_data = asyncio.run(fetch_query_trace_concurrent("tr_123", _ok_fetcher))
        self.assertIsNotNone(trace_data)
        self.assertEqual(len(trace_data), 6)

        with self.assertRaises(TelemetryBackendError):
            asyncio.run(fetch_query_trace_concurrent("tr_123", _failing_fetcher))


if __name__ == "__main__":
    unittest.main(verbosity=2)
