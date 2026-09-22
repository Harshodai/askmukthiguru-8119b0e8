# evals/grounding/ — PLAN.md Phase B2

Started 2026-09-22, alongside the multilingual crisis-detection fix. Same
honesty rules as `evals/README.md` — read this before trusting a pass here
as more than it is.

## What `verify_quote.py` actually checks

Two mechanical, offline-runnable checks, both against real on-disk data:

1. **Verbatim-quote check.** Given a quote string and a `video_id`, does the
   quote (exactly, or whitespace/punctuation-normalized) appear in
   `transcripts/<video_id>.md`? That file is raw YouTube transcript text
   fetched by the ingestion pipeline — the closest on-disk approximation to
   what Qdrant's indexed chunks actually derive from, before chunking and
   embedding.
2. **Attribution check.** Given a claimed teacher name and a `video_id`,
   does that teacher appear in the transcript file's own `**Speaker:**`
   header? Catches a citation that attributes a quote to the wrong teacher.

Plus `precision_recall_f1()` — a pure scoring function for a citation set
against a ground-truth relevant set, usable once real citation data exists.

## Why not `memory/okf/*.md`

OKF entries are LLM-synthesized summaries. Checked directly before building
this: only 2 of 715 non-staging entries even have a `**Quotes:**` block, and
that block itself is LLM-extracted, reviewed doctrine content — not a
guarantee of verbatim match against the original spoken words. Checking a
citation against another LLM's paraphrase would validate nothing. `memory/okf/`
is the right place to check whether an OKF-sourced answer matches the
*approved doctrine text*; it is not ground truth for "did the guru actually
say this."

## What this does NOT prove

**Nothing about the live product's actual citations.** This checker has
never been run against a single real, system-generated citation — that
needs a running backend producing real answers with real citations, which
does not exist in this environment (Railway is scaled to $0). The
`__main__` self-check proves the *checker* is correct (real transcript
excerpt = match, altered/fabricated phrasing = no match, missing source =
fails closed, not open) — it is a unit test of the tool, not an evaluation
of the product.

**Coverage gaps in the ground-truth corpus itself.** Only 763 of the
corpus's video sources have a `transcripts/<video_id>.md` file on disk (per
AGENTS.md's Aug 27 handoff, some sources' local transcripts were marked
`needs_refetch` and a REFETCH phase was never completed). A citation to a
video_id outside this set will correctly report `no_transcript` — that is
the checker refusing to guess, not a bug, but it means this can't yet
verify every possible citation the live system might produce.

**Relevance/completeness judgment.** "Is this the right source to have
cited for this claim?" and "should more sources have been cited?" are B2's
"claim-level faithfulness" and part of "citation precision/recall" —
`precision_recall_f1()` computes the metric once someone (a human or an
LLM judge) supplies the ground-truth relevant set; this module doesn't
generate that judgment itself.

## Before this is real Phase B2 coverage

1. Wire this against real citations once a live backend exists — pull a
   sample of actual chat responses, extract their citations, run
   `verify_verbatim_quote()`/`verify_attribution()` against each.
2. Extend `transcripts/` coverage (see the REFETCH phase note above) or
   accept `no_transcript` results as an honest "can't verify" rather than
   silently excluding those citations from the metric.
3. B3 (tone/impersonation checks) doesn't exist yet — a natural next
   mechanical piece, similar in spirit to this one: scan generated text for
   impersonation phrases ("as Sri Preethaji," blessing/absolution language)
   the same way this scans for verbatim/attribution correctness.
