"""
Mukthi Guru — Text Cleaner (Fable 5.2 Deterministic Parser Refactoring)

Replaces 14-pass FILLER_WORDS regex loops, catastrophic backtracking
`_REPEATED_TOKEN_RE`, and `__DOT__`/`__COMMA__` string sentinel mutations with:
  - `_strip_markup_and_annotations_dfa()`: Single-pass O(N) character state machine
  - `_collapse_repeated_ngrams_token_stream()`: Linear O(N) token n-gram deduplicator
  - `_filter_timestamps_and_fillers_token_stream()`: Single-pass token filter
  - `split_sentences_deterministic()`: Stateful boundary-aware sentence splitter
"""

import logging
import re
import unicodedata

try:
    from rag.nodes.utils import DOCTRINE_SYNONYMS
except Exception:
    DOCTRINE_SYNONYMS = {}

logger = logging.getLogger(__name__)

FILLER_WORDS = {
    "um",
    "uh",
    "erm",
    "like",
    "you know",
    "i mean",
    "basically",
    "actually",
    "literally",
    "right",
    "so basically",
    "kind of",
    "sort of",
}

_TIMESTAMP_TOKEN_RE = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?$")
_NON_SPEECH_WORDS = frozenset({"music", "bgm", "instrumental", "singing"})
_NON_SPEECH_BIGRAMS = frozenset({("background", "music"), ("song", "playing")})

_ABBREVIATIONS = frozenset(
    {
        "mr.",
        "mrs.",
        "ms.",
        "dr.",
        "prof.",
        "sr.",
        "jr.",
        "e.g.",
        "i.e.",
        "vs.",
        "etc.",
        "viz.",
        "inc.",
        "ltd.",
        "a.m.",
        "p.m.",
        "no.",
        "fig.",
        "approx.",
        "ca.",
        "co.",
        "sri.",
        "shri.",
    }
)


def _strip_markup_and_annotations_dfa(text: str) -> str:
    """Linear O(N) character state machine for bracket, HTML, music, and speaker tags."""
    out: list[str] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if ch == "[":
            close = text.find("]", i + 1, min(n, i + 120))
            if close != -1 and "\n" not in text[i + 1 : close]:
                out.append(" ")
                i = close + 1
                continue
        if ch == "<":
            close = text.find(">", i + 1, min(n, i + 120))
            if close != -1 and "\n" not in text[i + 1 : close]:
                out.append(" ")
                i = close + 1
                continue
        if ch == "♪":
            close = text.find("♪", i + 1, min(n, i + 200))
            if close != -1:
                out.append(" ")
                i = close + 1
                continue
            out.append(" ")
            i += 1
            continue
        if ch == ">" and i + 1 < n and text[i + 1] == ">":
            j = i + 2
            while j < n and text[j] in (" ", "\t"):
                j += 1
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            if j < n and text[j] == ":":
                out.append(" ")
                i = j + 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _collapse_repeated_ngrams_token_stream(tokens: list[str]) -> list[str]:
    """Linear O(N) token-stream deduplicator for 1-to-4 word spans repeated 3+ times."""
    if len(tokens) < 3:
        return tokens
    result = list(tokens)
    for k in (1, 2, 3, 4):
        out: list[str] = []
        i = 0
        n = len(result)
        while i < n:
            if i + 3 * k <= n:
                base = [t.lower() for t in result[i : i + k]]
                reps = 1
                j = i + k
                while j + k <= n and [t.lower() for t in result[j : j + k]] == base:
                    reps += 1
                    j += k
                if reps >= 3:
                    out.extend(result[i : i + k])
                    i = j
                    continue
            out.append(result[i])
            i += 1
        result = out
    return result


def _filter_timestamps_and_fillers_token_stream(tokens: list[str]) -> list[str]:
    """Single-pass O(N) removal of timestamps, non-speech caption words, and fillers."""
    out: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        bare = tok.strip(".,!?;:\"'()").lower()
        punct_suffix = tok[len(tok.rstrip(".,!?;:")) :]

        if _TIMESTAMP_TOKEN_RE.match(bare):
            i += 1
            continue

        if i + 1 < n:
            nxt_tok = tokens[i + 1]
            nxt_bare = nxt_tok.strip(".,!?;:\"'()").lower()
            nxt_punct = nxt_tok[len(nxt_tok.rstrip(".,!?;:")) :]
            pair_str = f"{bare} {nxt_bare}"
            if pair_str in FILLER_WORDS or (bare, nxt_bare) in _NON_SPEECH_BIGRAMS:
                if nxt_punct:
                    out.append(nxt_punct)
                i += 2
                continue

        if bare in FILLER_WORDS or bare in _NON_SPEECH_WORDS:
            if punct_suffix:
                out.append(punct_suffix)
            i += 1
            continue

        out.append(tok)
        i += 1
    return out


def clean_transcript(text: str) -> str:
    """Clean raw transcript text through a linear O(N) deterministic pipeline."""
    if not text:
        return ""

    text = (
        text.replace("\x00", "")
        .replace("<|begin_of_text|>", "")
        .replace("<|eot_id|>", "")
        .replace("<|end_of_text|>", "")
    )
    text = unicodedata.normalize("NFC", text)
    original_len = len(text)

    text = _strip_markup_and_annotations_dfa(text)
    raw_tokens = text.split()
    deduped_tokens = _collapse_repeated_ngrams_token_stream(raw_tokens)
    filtered_tokens = _filter_timestamps_and_fillers_token_stream(deduped_tokens)
    text = " ".join(filtered_tokens)

    text = re.sub(r"\.{3,}", "...", text)
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    text = re.sub(r"([.!?])\s*([A-Z])", r"\1 \2", text)
    text = " ".join(text.split())

    text = normalize_spiritual_terms(text)

    cleaned_len = len(text)
    reduction = ((original_len - cleaned_len) / original_len * 100) if original_len > 0 else 0
    logger.debug(
        f"Cleaned text: {original_len} -> {cleaned_len} chars ({reduction:.1f}% reduction)"
    )
    return text


def split_sentences_deterministic(text: str) -> list[str]:
    """Stateful sentence boundary scanner preserving abbreviations, decimals, and Indic dandas."""
    if not text:
        return []
    tokens = text.split()
    if not tokens:
        return []

    sentences: list[str] = []
    current: list[str] = []

    for tok in tokens:
        current.append(tok)
        stripped = tok.rstrip("\"'”’)]")
        if not stripped:
            continue
        last_char = stripped[-1]
        if last_char in (".", "!", "?", "\u0964", "\u0965"):
            low_tok = stripped.lower()
            if low_tok in _ABBREVIATIONS or (
                low_tok.endswith("al.") and len(current) >= 2 and current[-2].lower() == "et"
            ):
                continue
            if len(stripped) == 2 and stripped[0].isupper() and last_char == ".":
                continue
            sentences.append(" ".join(current))
            current = []

    if current:
        sentences.append(" ".join(current))
    return sentences


def clean_for_embedding(text: str) -> str:
    """Additional cleaning specifically for embedding quality."""
    text = clean_transcript(text)
    sentences = split_sentences_deterministic(text)
    meaningful = [s.strip() for s in sentences if len(s.strip()) > 20]
    return " ".join(meaningful)


def normalize_spiritual_terms(text: str) -> str:
    if not text:
        return ""
    try:
        from services.doctrine_terms import apply_corrections

        return apply_corrections(text)
    except Exception as e:
        logger.debug("Failed to apply doctrine_terms corrections: %s", e)
        return text
