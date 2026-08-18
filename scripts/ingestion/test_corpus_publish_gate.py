#!/usr/bin/env python3
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus_publish_gate as gate


class CorpusPublishGateTests(unittest.TestCase):
    def make_fixture(self, state="trusted", tamper=False):
        root = Path(tempfile.mkdtemp())
        repo = root / "repo"
        corpus = repo / "scripts" / "ingestion" / "corpus"
        package = corpus / "video123"
        package.mkdir(parents=True)
        for filename, content in {
            "transcript.md": "A verified transcript.",
            "quality_report.json": json.dumps({
                "video_id": "video123",
                "quality_state": state,
                "quality_score": 0.9,
                "alignment_method": "forced_phoneme_alignment",
                "alignment_evidence_sha256": "e" * 64,
            }),
            "canonical_segments.json": json.dumps([{"start": 0.0, "end": 1.0, "text": "A verified transcript."}]),
            "correction_ledger.json": json.dumps([]),
        }.items():
            (package / filename).write_text(content, encoding="utf-8")
        artifacts = {}
        for filename in ("transcript.md", "quality_report.json", "canonical_segments.json", "correction_ledger.json"):
            digest = hashlib.sha256((package / filename).read_bytes()).hexdigest()
            artifacts[filename] = {"sha256": digest}
        if tamper:
            (package / "transcript.md").write_text("tampered", encoding="utf-8")
        (package / "artifact_manifest.json").write_text(json.dumps({"video_id": "video123", "artifacts": artifacts}), encoding="utf-8")
        audit = {
            "summary": {
                "issue_package_count": 0,
                "manifest_artifact_hash_mismatch_packages": 0,
                "manifest_raw_hash_mismatch_packages": 0,
            },
            "packages": [{"video_id": "video123", "package_ok": True, "quality_state": state}],
        }
        audit_path = root / "audit.json"
        audit_path.write_text(json.dumps(audit), encoding="utf-8")
        return repo, corpus, package, audit_path

    def test_trusted_package_publishes(self):
        repo, corpus, package, audit_path = self.make_fixture()
        release = gate.build_release(repo, corpus, audit_path, gate.DEFAULT_ALLOWED_STATES)
        self.assertTrue(release["publishable"])
        self.assertEqual(release["package_count"], 1)
        self.assertEqual(len(release["release_sha256"]), 64)

    def test_needs_review_is_blocked(self):
        repo, corpus, package, audit_path = self.make_fixture(state="needs_review")
        with self.assertRaises(SystemExit) as ctx:
            gate.build_release(repo, corpus, audit_path, gate.DEFAULT_ALLOWED_STATES)
        self.assertIn("package_state_not_publishable", str(ctx.exception))

    def test_manifest_tampering_is_blocked_independently_of_audit(self):
        repo, corpus, package, audit_path = self.make_fixture(tamper=True)
        with self.assertRaises(SystemExit) as ctx:
            gate.build_release(repo, corpus, audit_path, gate.DEFAULT_ALLOWED_STATES)
        self.assertIn("manifest_hash_mismatch:transcript.md", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
