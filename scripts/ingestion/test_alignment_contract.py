#!/usr/bin/env python3
import unittest
from alignment_contract import validate_alignment_evidence


class AlignmentContractTests(unittest.TestCase):
    def test_valid_forced_alignment(self):
        quality = {"alignment_method": "forced_phoneme_alignment", "alignment_evidence_sha256": "a" * 64, "speech_interval_coverage_ratio": 0.95}
        segments = {"segments": [{"start": 0.0, "end": 1.0}, {"start": 1.0, "end": 2.0}]}
        self.assertEqual(validate_alignment_evidence(quality, segments, True), [])

    def test_overlap_is_rejected(self):
        quality = {"speech_interval_coverage_ratio": 0.95}
        segments = [{"start": 0.0, "end": 1.0}, {"start": 0.9, "end": 2.0}]
        self.assertIn("segment_overlap:1", validate_alignment_evidence(quality, segments, False))

    def test_trusted_requires_evidence(self):
        errors = validate_alignment_evidence({}, {"segments": []}, True)
        self.assertIn("trusted_alignment_method_missing_or_unknown", errors)
        self.assertIn("trusted_alignment_evidence_digest_missing_or_invalid", errors)


if __name__ == "__main__":
    unittest.main()
