"""Data-derived doctrine lexicon and ASR variant correction.

Replaces the hand-maintained variant lists in ``doctrine_terms.py``. Those lists
could only fix mis-transcriptions somebody had already seen and typed in, which
is why the live corpus carries "Ojas" in 15 chunks and "Ujash" in 4 **from the
same video** — ``Ojas Shakti`` is a named Ekam meditation practice and no entry
for it existed. A list cannot enumerate what ASR will invent next: the same word
arrives as ``Ujash``, ``Ujasi``, ``Ojasi``, ``Ojus``. Similarity has to be
computed, not looked up.

Two ideas carry the design.

**The authority corpus is the dictionary.** Vocabulary is derived from sources
that are already correct — the professionally-edited books, the official Ekam and
Oneness Movement pages, terms many independent corpus sources already agree on,
and a general English frequency list. Nothing is typed by hand.

**Precision comes from refusing to act.** A naive phonetic pass over general
vocabulary destroys spiritual text: measured over 89,061 live chunks, phonetic
collision families include ``peace``x111,163 against ``piece``x1,616 and
``four``x260,481 against ``fear``x3,203. Rewriting *peace* to *piece* in doctrine
is far worse than leaving ``Ujash`` alone. So a token is corrected only when
**every** gate passes, and the default at each gate is to do nothing:

1. the token is absent from the authority vocabulary (if it is present it is
   correct by definition — this is what makes ``peace`` and ``piece`` both safe,
   since both appear in the books);
2. the token is rare in the corpus and concentrated in few sources (a spelling
   used widely across many independent sources is real usage, not an ASR slip);
3. exactly one authority term matches phonetically — an ambiguous match is
   abandoned rather than guessed;
4. string similarity to that term clears a high threshold.

Every correction records which gate chain admitted it, so a wrong rule is
traceable rather than mysterious. See ``explain()``.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_BACKEND = Path(__file__).resolve().parents[1]
LEXICON_PATH: Path = _BACKEND / "data" / "doctrine_lexicon.json"

# A token must look like a word before it is even considered.
_TOKEN_RE = re.compile(r"\b[A-Za-z][a-zA-Z'’-]{2,}\b")

# --- Correction gates -------------------------------------------------------
# Deliberately conservative. Every threshold trades recall for precision, and on
# doctrine text a false correction is unrecoverable (it is quoted to a seeker as
# the guru's own words) while a missed one merely leaves the status quo.

# Above this corpus frequency a spelling is real usage, not an ASR error, even if
# the authority sources happen not to contain it.
_MAX_CORPUS_FREQ_TO_CORRECT: int = 40
# ...and if many independent sources use the spelling, it is not one bad ASR run.
_MAX_SOURCES_TO_CORRECT: int = 3
# Similarity to the candidate, applied ONLY to tokens the vocabulary gate has
# already rejected. Measured on real pairs, similarity alone cannot separate the
# two classes at any threshold:
#
#     should correct   ujash/ojas 0.783   diksha/deeksha 0.864
#     must not touch   piece/peace 0.880  soil/soul 0.867
#
# `piece/peace` outscores `ujash/ojas`, so a threshold high enough to protect
# ordinary English would reject most real ASR errors, and one low enough to catch
# them would rewrite `peace`. The protection therefore does NOT live here — it
# lives in the vocabulary gate, which never lets `peace`, `piece`, `soul` or
# `soil` become candidates at all because every one of them is in the authority
# corpus. Freed of that duty, this threshold can sit low enough to catch a
# leading-vowel swap, which is the single most common Indic ASR error.
_MIN_SIMILARITY: float = 0.78
# Absolute edit distance ceiling, so a short token cannot pass on ratio alone.
_MAX_EDIT_DISTANCE: int = 2
# A candidate must be long enough that a phonetic key means something.
_MIN_TOKEN_LEN: int = 4
# How far a book/site term must outweigh a consensus candidate before the
# candidate is treated as that term's mis-transcription rather than a spelling in
# its own right. 10x is deliberately far below the measured ekam/akam ratio (26x)
# and far above ordinary variation, so it separates the two cases cleanly.
_AUTHORITY_DOMINANCE: int = 10
# Occurrences a non-English target must have across curated sources before it can
# attract a correction. Filters OCR fragments out of the target set.
_MIN_TARGET_SUPPORT: int = 3


def _phonetic_key(word: str) -> str:
    """Phonetic code for *word*, normalised for Indic transliteration.

    Metaphone alone treats the leading vowel of ``Ojas`` and ``Ujash`` as
    distinct. Transliterated Sanskrit has no stable vowel spelling — o/u, i/e and
    a/u alternate freely between transcribers — so vowels are folded to a single
    class before encoding, which is the whole reason ``Ujasi`` and ``Ojas`` can
    meet without either being written down anywhere.
    """
    import jellyfish

    value = re.sub(r"[^a-z]", "", word.lower())
    if not value:
        return ""
    # Aspirated consonants are the other unstable axis: Sanskrit distinguishes
    # k/kh, t/th, d/dh, but English transcribers drop or add the h at will
    # (mukti/mukthi, diksha/deeksha, ujash/ojas). Fold the digraphs before
    # encoding — metaphone alone codes a trailing "sh" differently from "s" and
    # so puts ujash and ojas in different buckets, where they can never meet.
    for digraph, plain in (
        ("ph", "f"),
        ("th", "t"),
        ("kh", "k"),
        ("gh", "g"),
        ("dh", "d"),
        ("bh", "b"),
        ("ch", "c"),
        ("sh", "s"),
    ):
        value = value.replace(digraph, plain)
    value = re.sub(r"(.)\1+", r"\1", value)  # doubled letters
    folded = re.sub(r"[aeiou]+", "a", value)  # all vowels equivalent
    return jellyfish.metaphone(folded) or folded.upper()


@dataclass
class LexiconStats:
    """Where the vocabulary came from — reported, never guessed at."""

    counts: dict[str, int] = field(default_factory=dict)
    built_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"built_at": self.built_at, "sources": self.counts}


@dataclass
class Correction:
    """One applied or rejected correction, with the reason."""

    token: str
    replacement: Optional[str]
    reason: str
    similarity: float = 0.0

    @property
    def applied(self) -> bool:
        return self.replacement is not None


class DoctrineLexicon:
    """Authority vocabulary plus the phonetic index built over it."""

    def __init__(
        self,
        vocabulary: dict[str, int],
        stats: Optional[LexiconStats] = None,
        corpus_freq: Optional[dict[str, int]] = None,
        corpus_sources: Optional[dict[str, int]] = None,
        proper_nouns: Optional[dict[str, int]] = None,
        targets: Optional[dict[str, int]] = None,
        general_english: Optional[Iterable[str]] = None,
        curated: Optional[Iterable[str]] = None,
        clean_curated: Optional[Iterable[str]] = None,
    ) -> None:
        # Curated sources that are not OCR output (the official websites).
        self.clean_curated = set(clean_curated or ())
        # Vocabulary from the books and official sites — text this project
        # vouches for, as opposed to spellings the corpus merely repeats.
        self.curated = set(curated or ())
        # Ordinary English. Protects prose, and is excluded from the phonetic
        # correction path so a fragment cannot be "fixed" into a common word.
        self.general_english = set(general_english or ())
        self.vocabulary = {w.lower(): c for w, c in vocabulary.items()}
        # Words seen capitalised mid-sentence in the authority sources.
        self.proper_nouns = {w.lower(): c for w, c in (proper_nouns or {}).items()}
        self.stats = stats or LexiconStats()
        self.corpus_freq = corpus_freq or {}
        self.corpus_sources = corpus_sources or {}
        # PROTECT with everything, CORRECT TOWARD only trusted doctrine sources.
        # The asymmetry is the whole design. A 200k English list is what keeps
        # `soar`, `steel` and `knots` safe, but its long tail is foreign words and
        # noise, and using it as a correction TARGET produced `yascha -> yasaka`,
        # `sthita -> stith` and `no-op -> knoop`. Targets come from the books, the
        # official sites and strong corpus consensus — text this project vouches
        # for. Everything else can only ever protect, never attract.
        self.targets = {w.lower(): c for w, c in (targets or vocabulary).items()}
        # A target must be a real WORD. Corpus consensus admits any spelling that
        # enough sources share, and a systematic truncation qualifies: "ealth"
        # reached the target set that way and produced `alth -> ealth`, repairing
        # one fragment into another. Wordhood evidence is membership in general
        # English or in the curated book/site vocabulary — never consensus alone.
        # The curated sources are not fragment-free either: the book PDF was
        # OCR'd, so `ealth` and `ense` sit in its text and attracted `alth` and
        # `eness`. A doctrine term absent from English must therefore EARN its
        # place by recurring — `ojas` and `humsa` appear repeatedly, a one-off
        # OCR slip does not.
        # Clean-text sources (scraped HTML) have no OCR damage, so every word in
        # them is a valid target — this is what keeps `ojas`, which appears only a
        # couple of times on ekam.org, correctable. OCR'd sources (the book PDFs)
        # do contain fragments like `ealth` and `ense`, so a word seen ONLY there
        # must recur before it can attract anything.
        real = (
            self.general_english
            | self.clean_curated
            | {w for w in self.curated if self.targets.get(w, 0) >= _MIN_TARGET_SUPPORT}
        )
        self._index: dict[str, list[str]] = defaultdict(list)
        for word in self.targets:
            if len(word) >= _MIN_TOKEN_LEN and (not real or word in real):
                self._index[_phonetic_key(word)].append(word)

    # -- persistence ---------------------------------------------------------

    def save(self, path: Path = LEXICON_PATH) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    **self.stats.as_dict(),
                    "vocabulary": self.vocabulary,
                    "proper_nouns": self.proper_nouns,
                    "targets": self.targets,
                    "general_english": sorted(self.general_english),
                    "curated": sorted(self.curated),
                    "clean_curated": sorted(self.clean_curated),
                    "corpus_freq": self.corpus_freq,
                    "corpus_sources": self.corpus_sources,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(cls, path: Path = LEXICON_PATH) -> DoctrineLexicon:
        data = json.loads(path.read_text(encoding="utf-8"))
        stats = LexiconStats(counts=data.get("sources", {}), built_at=data.get("built_at", ""))
        return cls(
            data.get("vocabulary", {}),
            stats,
            data.get("corpus_freq", {}),
            data.get("corpus_sources", {}),
            data.get("proper_nouns", {}),
            data.get("targets", {}),
            data.get("general_english", []),
            data.get("curated", []),
            data.get("clean_curated", []),
        )

    # -- correction ----------------------------------------------------------

    def explain(self, token: str) -> Correction:
        """Decide what to do with *token*, and say why. Pure — no side effects."""
        from rapidfuzz.distance import JaroWinkler, Levenshtein

        raw = token
        word = token.lower().strip("'’-")

        if len(word) < _MIN_TOKEN_LEN:
            return Correction(raw, None, "too short to judge")
        # A possessive or a hyphenated compound is a writing choice, not a
        # transcription error. Treating them as candidates rewrote `chakra's` to
        # `chakras` and `pre-conditioned` to `preconditioned` — changing grammar
        # and house style while claiming to fix ASR.
        if any(ch in raw for ch in "'’-"):
            return Correction(raw, None, "possessive or hyphenated compound")
        if word in self.vocabulary:
            return Correction(raw, None, "present in authority vocabulary")

        freq = self.corpus_freq.get(word, 0)
        if freq > _MAX_CORPUS_FREQ_TO_CORRECT:
            return Correction(raw, None, f"common in corpus ({freq} uses)")
        sources = self.corpus_sources.get(word, 0)
        if sources > _MAX_SOURCES_TO_CORRECT:
            return Correction(raw, None, f"used across {sources} independent sources")

        candidates = self._index.get(_phonetic_key(word), [])
        if not candidates:
            return Correction(raw, None, "no phonetic match in authority vocabulary")

        # A capitalised token mid-text is almost always a proper noun — a person,
        # a place, a tradition — and those are precisely the words no general
        # vocabulary contains, so they reach this point looking exactly like ASR
        # errors. Correcting them is how a 4,000-chunk sample produced
        # `preeta -> pretty`, `Rome -> room`, `Maori -> more` and
        # `Christians -> christina's`. Only accept a proper-noun correction when
        # the target is itself capitalised in the authority sources, i.e. one
        # proper noun mapping to another.
        if raw[:1].isupper() and not raw.isupper():
            candidates = [c for c in candidates if self.proper_nouns.get(c)]
            if not candidates:
                return Correction(raw, None, "capitalised token with no proper-noun candidate")

        # A truncated fragment is the dominant residual error class: OCR and ASR
        # cut words off (`coura`, `succe`, `blems`, `professiona`), and edit
        # distance then picks a SHORTER neighbour — `coura -> core`,
        # `succe -> such` — when the truth is always a longer completion.
        # Completion is far stronger evidence than similarity, so it is tried
        # first and, when a unique one exists, wins outright.
        completions = sorted((c for c in candidates if c.startswith(word) and c != word), key=len)
        if completions:
            shortest = completions[0]
            tied = [c for c in completions if len(c) == len(shortest)]
            if len(tied) == 1:
                return Correction(raw, _match_case(raw, shortest), "prefix completion", 1.0)
            return Correction(raw, None, f"ambiguous completion: {tied[:3]}")

        # The phonetic path may only aim at DOCTRINE-specific vocabulary — terms
        # absent from general English. A rare fragment that sounds like an
        # ordinary word (`blems`/`balms`, `filld`/`field`, `caree`/`carry`) is a
        # truncation the prefix rule already declined, not a mis-heard doctrine
        # term, and guessing there produced most of the residual damage. `ojas`
        # is in no English wordlist, which is exactly why it is a legitimate
        # target and `balms` is not.
        doctrine_only = [c for c in candidates if c not in self.general_english]
        if not doctrine_only:
            return Correction(
                raw, None, "phonetic matches are ordinary English, not doctrine terms"
            )

        scored = sorted(
            (
                (JaroWinkler.similarity(word, c), c)
                for c in doctrine_only
                if Levenshtein.distance(word, c) <= _MAX_EDIT_DISTANCE
            ),
            reverse=True,
        )
        if not scored:
            return Correction(raw, None, "phonetic match but edit distance too large")

        best_score, best = scored[0]
        if best_score < _MIN_SIMILARITY:
            return Correction(raw, None, f"best match {best!r} too weak", best_score)
        # Ambiguity is abandoned, not guessed: if two DIFFERENT authority terms
        # both match this closely there is no evidence for choosing between them.
        if len(scored) > 1 and abs(scored[1][0] - best_score) < 1e-9:
            return Correction(
                raw, None, f"ambiguous between {best!r} and {scored[1][1]!r}", best_score
            )

        return Correction(raw, _match_case(raw, best), "phonetic + similarity", best_score)

    def correct(self, text: str) -> tuple[str, list[Correction]]:
        """Return *text* with confident corrections applied, plus the audit trail."""
        applied: list[Correction] = []

        def _sub(match: re.Match) -> str:
            decision = self.explain(match.group(0))
            if decision.applied:
                applied.append(decision)
                return decision.replacement or match.group(0)
            return match.group(0)

        return _TOKEN_RE.sub(_sub, text or ""), applied


_SHARED: Optional[DoctrineLexicon] = None
_LOAD_FAILED = False


def get_lexicon() -> Optional[DoctrineLexicon]:
    """The process-wide lexicon, or None if it has not been built on this host.

    Loading parses a ~7MB JSON, so it happens once and the result is held for the
    life of the process. A missing file is NOT an error: the file is derived
    (``python -m scripts.ops.build_doctrine_lexicon``) and is absent on a fresh
    checkout or a slim image. Callers fall back to the hand-maintained
    ``doctrine_terms`` map, which is strictly smaller but never wrong — so the
    absence costs recall, never precision.
    """
    global _SHARED, _LOAD_FAILED
    if _SHARED is not None or _LOAD_FAILED:
        return _SHARED
    try:
        # Pass the path explicitly: `load`'s default argument binds LEXICON_PATH at
        # import time, so a later reassignment of the module global (tests, an ops
        # script pointing at a rebuilt file) would be silently ignored.
        _SHARED = DoctrineLexicon.load(LEXICON_PATH)
        logger.info(
            "doctrine lexicon loaded: %d vocabulary, %d correction targets",
            len(_SHARED.vocabulary),
            len(_SHARED.targets),
        )
    except FileNotFoundError:
        _LOAD_FAILED = True
        logger.warning(
            "no doctrine lexicon at %s — falling back to the doctrine_terms map. "
            "Build it with: python -m scripts.ops.build_doctrine_lexicon",
            LEXICON_PATH,
        )
    except Exception as exc:  # corrupt JSON, missing rapidfuzz/jellyfish
        _LOAD_FAILED = True
        logger.error("doctrine lexicon at %s is unusable (%s)", LEXICON_PATH, exc)
    return _SHARED


def reload_lexicon() -> None:
    """Drop the cached lexicon so the next call re-reads the file (after a rebuild)."""
    global _SHARED, _LOAD_FAILED
    _SHARED = None
    _LOAD_FAILED = False


def _match_case(original: str, replacement: str) -> str:
    """Carry the original token's casing onto the replacement."""
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


# --- building ---------------------------------------------------------------


def _words(text: str) -> Iterable[str]:
    for match in _TOKEN_RE.finditer(text or ""):
        yield match.group(0).lower().strip("'’-")


def build_lexicon(
    authority_texts: dict[str, Iterable[str]],
    corpus_texts: Optional[Iterable[tuple[str, str]]] = None,
    min_consensus_sources: int = 20,
    protect_only: frozenset[str] = frozenset({"english"}),
    ocr_sources: frozenset[str] = frozenset({"books"}),
) -> DoctrineLexicon:
    """Derive the lexicon from authority texts, plus corpus consensus.

    ``authority_texts`` maps a source label ("book", "ekam.org") to its texts.
    ``corpus_texts`` yields ``(source_url, text)`` for the whole corpus; a
    spelling that ``min_consensus_sources`` independent sources agree on is
    treated as correct even when no authority source contains it, which is how
    ordinary English survives without anyone curating a stop list.
    """
    vocabulary: dict[str, int] = defaultdict(int)
    proper_nouns: dict[str, int] = defaultdict(int)
    # Sources whose words may be corrected TOWARD. `protect_only` labels (the
    # general English list) still populate `vocabulary`, so they shield prose,
    # but never attract a correction.
    targets: dict[str, int] = defaultdict(int)
    general_english: set[str] = set()
    curated: set[str] = set()
    clean_curated: set[str] = set()
    stats = LexiconStats(built_at=datetime.now(UTC).isoformat())

    for label, texts in authority_texts.items():
        before = len(vocabulary)
        for text in texts:
            for match in _TOKEN_RE.finditer(text or ""):
                token = match.group(0)
                word = token.lower().strip("'\u2019-")
                vocabulary[word] += 1
                # Capitalised NOT at a sentence start is real proper-noun
                # evidence; sentence-initial capitals say nothing.
                prefix = (text[max(0, match.start() - 2) : match.start()]).strip()
                if token[:1].isupper() and prefix and prefix[-1] not in ".!?\n":
                    proper_nouns[word] += 1
                if label in protect_only:
                    general_english.add(word)
                else:
                    targets[word] += 1
                    curated.add(word)
                    if label not in ocr_sources:
                        clean_curated.add(word)
        stats.counts[label] = len(vocabulary) - before

    corpus_freq: dict[str, int] = defaultdict(int)
    per_word_sources: dict[str, set] = defaultdict(set)
    if corpus_texts:
        for source_url, text in corpus_texts:
            for word in _words(text):
                corpus_freq[word] += 1
                per_word_sources[word].add(source_url)

    corpus_sources = {w: len(s) for w, s in per_word_sources.items()}

    # Consensus alone would let a SYSTEMATIC ASR error promote itself to
    # authority. Measured: "akam" is absent from the books yet appears in 26
    # sources / 401 uses, because Whisper mishears "Ekam" the same way every
    # time — and once admitted it becomes uncorrectable, since gate 1 treats
    # vocabulary membership as proof of correctness. Repetition is not evidence
    # when the error has a single common cause.
    #
    # So a consensus candidate is refused when a *higher-authority* term (from
    # the books or the official sites, never from consensus itself) shares its
    # phonetic key and dominates it by `_AUTHORITY_DOMINANCE`. "ekam" carries
    # 10,572 uses against "akam"'s 401 — a 26x margin — so "akam" stays out and
    # stays correctable. Where support is comparable, both are kept: genuine
    # spelling variation exists, and the books say "mukti" while the movement's
    # own branding says "Mukthi".
    authority_keys: dict[str, int] = {}
    for word, count in vocabulary.items():
        if len(word) >= _MIN_TOKEN_LEN:
            key = _phonetic_key(word)
            authority_keys[key] = max(authority_keys.get(key, 0), corpus_freq.get(word, count))

    consensus: dict[str, int] = {}
    shadowed: list[str] = []
    for word, sources in corpus_sources.items():
        if sources < min_consensus_sources or word in vocabulary:
            continue
        dominant = authority_keys.get(_phonetic_key(word), 0)
        if dominant >= max(1, corpus_freq[word]) * _AUTHORITY_DOMINANCE:
            shadowed.append(word)
            continue
        consensus[word] = corpus_freq[word]

    for word, count in consensus.items():
        vocabulary[word] += count
        targets[word] += count
    stats.counts["corpus_consensus"] = len(consensus)
    stats.counts["consensus_refused_shadowed"] = len(shadowed)
    if shadowed:
        logger.info(
            "consensus refused %d spellings shadowed by a dominant authority term: %s",
            len(shadowed),
            ", ".join(sorted(shadowed)[:12]),
        )

    stats.counts["proper_nouns"] = len(proper_nouns)
    stats.counts["correction_targets"] = len(targets)
    return DoctrineLexicon(
        dict(vocabulary),
        stats,
        dict(corpus_freq),
        corpus_sources,
        dict(proper_nouns),
        dict(targets),
        general_english,
        curated,
        clean_curated,
    )


if __name__ == "__main__":  # pragma: no cover - self-check
    logging.basicConfig(level=logging.INFO)
    # The gates matter more than the matches, so the self-check asserts both.
    lex = build_lexicon(
        {
            "synthetic": [
                "Ojas is the essence of immunity. Tejas and Prana complete it. "
                "Peace is not a piece of anything. Deeksha awakens Ekam."
            ]
        }
    )
    fixed, corrections = lex.correct("Ujash and Ujasi and Ojasi shield you. Peace is not a piece.")
    print(fixed)
    for c in corrections:
        print(f"  {c.token} -> {c.replacement} ({c.reason}, {c.similarity:.3f})")
    assert "Ojas" in fixed, fixed
    assert "piece" in fixed and "Peace" in fixed, "general English must be untouched"
    assert lex.explain("piece").replacement is None
    print("self-check OK")
