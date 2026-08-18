# Post-Fix End-to-End Transcript Corpus Recheck

**Repository:** `Harshodai/askmukthiguru-8119b0e8`
**Corpus:** `scripts/ingestion/corpus/`
**Verification date:** 18 August 2026
**Method:** Read-only deterministic validation across 12 parallel workers

## Result

The latest recheck confirms that the user’s corpus repairs are effective. All **745 video directories now pass the structural and integrity validator**. There are **zero issue packages**, **zero manifest artifact-hash mismatches**, **zero raw-source hash mismatches**, **zero timestamp-like transcript warnings**, and **zero correction-ledger issue packages**. The remaining 166 warnings are limited to the soft paragraph-length target and do not represent package corruption.

The formerly incomplete directories are now represented with explicit repository-supported states: **45 `unavailable`** and **43 `dead_lettered`**, each with a complete package shape sufficient for downstream exclusion and auditability. The remaining materialized speech packages are `needs_review` or `sound_only`; no package is silently promoted to `trusted` without a review record.

| Verification measure | Latest result |
|---|---:|
| Video directories scanned | **745** |
| Packages passing structural/integrity checks | **745 / 745** |
| Issue packages | **0** |
| Warning packages | **166** |
| `needs_review` | **652** |
| `sound_only` | **5** |
| `unavailable` | **45** |
| `dead_lettered` | **43** |
| Correction-ledger candidates inventoried | **1,064** |
| Packages with correction-ledger issues | **0** |
| Artifact SHA-256 mismatches | **0** |
| Raw-source SHA-256 mismatches | **0** |
| Timestamp-like transcript warnings | **0** |
| Paragraph-target warnings | **166** |

## Correction Inventory

The latest correction inventory reports **246 packages with ledgers** and **1,064 correction candidates**. Its issue count is empty. This confirms that the previously failing correction-ledger packages now satisfy the implemented schema checks, including half-open character offsets, matched/replacement text consistency, original and corrected segment hashes, and reversal metadata.

The correction inventory is intentionally a candidate/review inventory rather than an automatic declaration that every terminology change is semantically correct. The corpus now preserves the evidence required for a human reviewer to confirm ambiguous phonetic or transliteration decisions without losing the original segment.

## Quality-State Interpretation

The quality-state distribution is now explicit and operationally useful. The 45 unavailable and 43 dead-lettered packages are no longer malformed empty directories; they are classified outcomes that downstream ingestion can exclude deterministically. The 652 `needs_review` packages remain conservatively gated because they are not promoted to trusted status without review evidence. The five `sound_only` packages are valid repository states and should be handled according to the project’s sound-only policy.

The score distribution includes 566 packages at 0.70, 53 at 0.45, 38 at 0.50, and 88 at 0.00 for unavailable/dead-lettered outcomes. These scores are deterministic pipeline outputs, not calibrated WER. External research remains relevant: WER can understate meaning-changing errors and proper-noun failures, while contemporary ASR corpora use independent alignment and multidimensional quality filtering [1] [2] [3].

## Remaining Warnings

The only remaining validator warning is that **166 packages have most paragraphs outside the nominal 300–500-character target**. This is a retrieval-format warning, not an integrity defect. The corpus-wide paragraph median remains **396 characters**, indicating that the central distribution is aligned with the design goal; outliers can arise from final residual paragraphs, short recordings, or sentence-boundary preservation.

No further repair is required to close the structural audit. If desired, paragraph warnings can be reduced later through a soft packing heuristic, but they should not be converted into hard package failures without testing retrieval quality and short-video behavior.

## Integrity Conclusion

The latest recheck recomputed every SHA-256 digest listed by each artifact manifest and every listed raw-source digest. All comparisons passed. This establishes that the current files match their recorded manifests. As described by NIST, message digests are used to detect whether messages have changed since the digests were generated [1]. The manifest remains an integrity check, not an external signature of producer identity; stronger provenance would require signed commits or an external signing/attestation layer.

## Verification Commands

```bash
python3 scripts/ingestion/corpus_end_to_end_audit.py \
  scripts/ingestion/corpus \
  --out scripts/ingestion/corpus_end_to_end_audit_latest \
  --workers 12

python3 scripts/ingestion/review_corrections_inventory.py \
  --corpus scripts/ingestion/corpus \
  --out scripts/ingestion/reviews/latest_correction_inventory
```

The targeted Python compilation check passed for the audit and correction-review scripts, `corpus_engine.py`, the parallel extractor, doctrine-term services, transcript polisher, and Whisper quality service. The repository-wide `test_transcript_quality_gates.py` collection remains blocked in the connected Python 3.9 environment by an unrelated pre-existing annotation incompatibility in `backend/services/ocr_service.py` (`str | None` without postponed annotations); this was not changed as part of the transcript commit.

## References

[1]: https://csrc.nist.gov/pubs/fips/180-4/upd1/final NIST, “FIPS 180-4, Secure Hash Standard (SHS).”
[2]: https://machinelearning.apple.com/research/humanizing-wer Apple Machine Learning Research, “Humanizing Word Error Rate for ASR Transcript Readability and Accessibility.”
[3]: https://aclanthology.org/2025.acl-long.135/ Yang et al., “GigaSpeech 2: An Evolving, Large-Scale and Multi-domain ASR Corpus with Automated Crawling, Transcription and Refinement.”
