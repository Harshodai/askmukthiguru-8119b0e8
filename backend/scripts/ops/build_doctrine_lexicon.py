"""Build the doctrine lexicon from authoritative sources. No hand-typed terms.

    python -m scripts.ops.build_doctrine_lexicon            # build + save + calibrate
    python -m scripts.ops.build_doctrine_lexicon --no-web   # skip the scrape (offline)

Authority sources, in descending trust:

* **Books** — professionally edited and measured at 0% contamination, so their
  spelling is correct by construction. This is also what makes ordinary English
  safe: `peace` and `piece` both appear, so neither can ever be a correction
  candidate.
* **Official sites** (ekam.org, theonenessmovement.org) — supply practice names
  the books omit. `Ojas`, `Tejas` and `Prana` are absent from
  The_Four_Sacred_Secrets.pdf yet name a real Ekam meditation, which is exactly
  the gap that let "Ujash" survive in the corpus.
* **Corpus consensus** — a spelling used by many independent sources is real
  usage. This covers general English without anyone curating a stop list, and it
  degrades gracefully: if the scrape fails, consensus still protects the corpus.

The corpus itself is NOT an authority for rare words — that would make every ASR
error self-justifying. Only the consensus threshold admits corpus spellings.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import urllib.request
from collections.abc import Iterator
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.doctrine_lexicon import DoctrineLexicon, build_lexicon  # noqa: E402

logger = logging.getLogger("build_doctrine_lexicon")

# Official sources named by the project owner. Kept here rather than in config
# because they identify the doctrine's publishers, not a tunable.
AUTHORITY_URLS: tuple[str, ...] = (
    "https://www.ekam.org/meditation-practices",
    "https://www.ekamindia.org/meditation-practices",
    "https://www.theonenessmovement.org/",
)

# Trusted content types inside the corpus — edited prose, not ASR output.
_BOOK_TYPES = {"book", "pdf"}

# Known variant -> canonical pairs used ONLY to score the built lexicon. They are
# never fed into it; a calibration set that trained the thing it measures would
# report its own inputs back as success.
_CALIBRATION_SHOULD_FIX = (
    ("ujash", "ojas"),
    ("ujasi", "ojas"),
    ("ojasi", "ojas"),
    ("diksha", "deeksha"),
    ("mukti", "mukthi"),
    ("akam", "ekam"),
)
_CALIBRATION_MUST_NOT_TOUCH = (
    "peace",
    "piece",
    "soul",
    "soil",
    "must",
    "most",
    "four",
    "fear",
    "care",
    "core",
    "shield",
    "should",
    "time",
    "theme",
    "teaching",
    "them",
)


def _scroll(collection: str, qdrant_url: str) -> Iterator[dict]:
    offset = None
    while True:
        body: dict = {"limit": 1000, "with_payload": True, "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        request = urllib.request.Request(
            f"{qdrant_url}/collections/{collection}/points/scroll",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        result = json.load(urllib.request.urlopen(request))["result"]  # nosec B310
        for point in result["points"]:
            yield point.get("payload") or {}
        offset = result.get("next_page_offset")
        if offset is None:
            return


async def _scrape(urls: tuple[str, ...]) -> dict[str, str]:
    """Fetch the official pages. A failure is reported, never silently skipped."""
    # `is_safe_public_url` is the project's SSRF guard (rejects private, loopback
    # and link-local resolutions). Reused rather than re-implemented — a second
    # copy of a security check is a second thing to get wrong.
    from ingest.audio_transcriber import is_safe_public_url
    from ingest.web_scraper import scrape_and_clean_web_article

    pages: dict[str, str] = {}
    for url in urls:
        try:
            text = await scrape_and_clean_web_article(url, is_safe_public_url)
            if text and text.strip():
                pages[url] = text
                logger.info("scraped %s (%d chars)", url, len(text))
            else:
                logger.warning("scraped %s but it returned no text", url)
        except Exception as exc:
            logger.warning("could not scrape %s: %s", url, exc)
    return pages


def calibrate(lexicon: DoctrineLexicon) -> dict:
    """Score the lexicon on held-out pairs. Precision is the number that matters."""
    fixed_right = fixed_wrong = missed = 0
    details: list[str] = []

    for variant, canonical in _CALIBRATION_SHOULD_FIX:
        decision = lexicon.explain(variant)
        if decision.replacement is None:
            missed += 1
            details.append(f"  MISS  {variant} -> ? ({decision.reason})")
        elif decision.replacement.lower() == canonical:
            fixed_right += 1
            details.append(
                f"  OK    {variant} -> {decision.replacement} ({decision.similarity:.3f})"
            )
        else:
            fixed_wrong += 1
            details.append(f"  WRONG {variant} -> {decision.replacement} (wanted {canonical})")

    false_positives = 0
    for word in _CALIBRATION_MUST_NOT_TOUCH:
        decision = lexicon.explain(word)
        if decision.replacement is not None:
            false_positives += 1
            details.append(f"  DAMAGE {word} -> {decision.replacement} ({decision.reason})")

    attempted = fixed_right + fixed_wrong + false_positives
    precision = fixed_right / attempted if attempted else 1.0
    recall = fixed_right / len(_CALIBRATION_SHOULD_FIX)
    return {
        "precision": precision,
        "recall": recall,
        "corrected_right": fixed_right,
        "corrected_wrong": fixed_wrong,
        "false_positives": false_positives,
        "missed": missed,
        "details": details,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    parser.add_argument("--collection", default="spiritual_wisdom")
    parser.add_argument("--no-web", action="store_true", help="skip the official-site scrape")
    parser.add_argument(
        "--min-consensus",
        type=int,
        default=20,
        help="independent sources that must agree before a corpus spelling counts",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    book_texts: list[str] = []
    corpus: list[tuple[str, str]] = []
    per_source_types: dict[str, str] = {}
    for payload in _scroll(args.collection, args.qdrant_url):
        text = payload.get("text") or ""
        if not text:
            continue
        source = payload.get("source_url") or "?"
        corpus.append((source, text))
        content_type = str(payload.get("content_type") or "").lower()
        per_source_types.setdefault(source, content_type)
        if content_type in _BOOK_TYPES:
            book_texts.append(text)

    logger.info(
        "corpus: %d chunks, %d sources, %d book chunks",
        len(corpus),
        len(per_source_types),
        len(book_texts),
    )

    # A general English wordlist is what actually protects ordinary prose. The
    # books plus the official sites yield ~5,700 words; English needs 50k-100k,
    # and every legitimate word OUTSIDE the vocabulary becomes a correction
    # candidate. Measured without it, a 4,000-chunk sample produced 187 distinct
    # rules including soar->sore, steel->steal, knots->notes and bodhi->body —
    # roughly 30% precision. Coverage here IS the safety property.
    english_words: list[str] = []
    try:
        from wordfreq import top_n_list

        english_words = top_n_list("en", 200_000)
        logger.info("english wordlist: %d words", len(english_words))
    except Exception as exc:
        logger.error(
            "wordfreq unavailable (%s) — REFUSING to build, since without an "
            "English wordlist the lexicon rewrites ordinary prose",
            exc,
        )
        return 1

    authority: dict[str, list[str]] = {
        "books": book_texts,
        "english": [" ".join(english_words)],
    }
    if not args.no_web:
        pages = await _scrape(AUTHORITY_URLS)
        for url, text in pages.items():
            authority[url] = [text]
        if not pages:
            logger.warning(
                "no official page could be scraped — the lexicon will lack practice "
                "names such as Ojas/Tejas/Prana that the books do not contain"
            )

    lexicon = build_lexicon(authority, corpus, min_consensus_sources=args.min_consensus)
    path = lexicon.save()

    print("\nlexicon sources:")
    for label, count in lexicon.stats.counts.items():
        print(f"  {label:60s} +{count} new words")
    print(f"  {'TOTAL vocabulary':60s} {len(lexicon.vocabulary)}")
    print(f"saved -> {path}")

    report = calibrate(lexicon)
    print("\ncalibration (held-out pairs, never fed into the lexicon):")
    for line in report["details"]:
        print(line)
    print(f"\n  precision {report['precision']:.3f}   recall {report['recall']:.3f}")
    print(
        f"  corrected right {report['corrected_right']}, wrong {report['corrected_wrong']}, "
        f"false positives {report['false_positives']}, missed {report['missed']}"
    )
    if report["false_positives"]:
        print("\n  !! FALSE POSITIVES present — real English was rewritten. Do not ship.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
