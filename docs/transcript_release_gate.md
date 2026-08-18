# Transcript Corpus Release Gate

The transcript corpus uses a **write–audit–publish** rule. The working corpus may contain `needs_review`, `unavailable`, `dead_lettered`, and `sound_only` packages, but the published snapshot may contain only `trusted` or `trusted_after_review` packages.

Run the gate from the repository root:

```bash
python3 scripts/ingestion/corpus_publish_gate.py \
  --repo . \
  --corpus scripts/ingestion/corpus \
  --audit scripts/ingestion/corpus_end_to_end_audit_latest.json \
  --output scripts/ingestion/corpus_release_latest.json
```

The command is **fail-closed**. It refuses publication when the audit reports issues, when a package is not in an allowed trust state, when a canonical file is missing, when an artifact digest differs from `artifact_manifest.json`, when a raw-source digest differs, or when a trusted package lacks alignment method and alignment-evidence digest.

The gate also checks canonical segment timing. Segments must have numeric `start` and `end` values, `end > start`, and no overlap with the preceding segment. Coverage ratios, when present, must be between 0 and 1. Trusted alignment methods are restricted to `forced_phoneme_alignment`, `word_level_alignment`, `human_audio_review`, and `source_caption_alignment`.

The release file is written atomically with a temporary file and `os.replace`. Its digest binds the release snapshot to the audit digest, repository Git SHA, package artifact digests, and the gate version. This is still a local attestation, not a replacement for a signed in-toto or Cosign release signature; signing can be added at deployment time.

## Required workflow

First acquire raw material and retain the source and extractor metadata. Then write candidate artifacts into a versioned working snapshot. Run the deterministic audit and the contract tests. Route low-confidence or doctrine-sensitive items to human review. Only then invoke the release gate and publish the resulting immutable snapshot to downstream Qdrant or LightRAG consumers.

A checksum match alone never upgrades a package to trusted. A package can be byte-perfect and remain `needs_review` until its content and alignment evidence are approved.
