"""Content-independent stylometry: measure whether text sounds like a person.

WHY THIS EXISTS
---------------
The product complaint is "answers read like AI, not like the Guru". Nothing in
the repo could measure that, so nothing could be tuned against it. The previous
instrument (``benchmarks/guru_voice_benchmark.py`` before 2026-09-15) scored a
hardcoded ``REFERENCE_VOICE`` string against a rubric derived from that same
string and reported 5.0/5.0 — it could not fail.

DESIGN, AND WHY NOT AN LLM JUDGE
--------------------------------
This is deterministic feature-distance stylometry (Burrows's-Delta shape: mean
absolute z-score over a fixed feature vector), NOT an LLM rubric.

* LLM judges are unreliable for exactly this task. They carry self-preference
  bias (they score their own register higher — https://arxiv.org/pdf/2410.21819),
  verbosity and position bias, and they prefer low-perplexity text, which is the
  very "AI register" we are trying to detect. Rubric-based judging is brittle to
  prompt wording (https://arxiv.org/pdf/2604.06996).
* The largest study of LLM style imitation deliberately avoided LLM-as-judge for
  this reason and used authorship attribution plus stylistic feature distance
  (LIWC / WritePrints Mahalanobis) instead —
  https://arxiv.org/pdf/2509.14543 ("Catch Me If You Can? Not Yet").
* Burrows's Delta is the established stylometric distance; it is content- and
  language-independent because it reads function words and form, not topic
  (https://academic.oup.com/dsh/article/32/suppl_2/ii4/3865676).

Features are FORM ONLY (pronoun rates, sentence-length distribution, hedges,
markdown density, known LLM tells). No topic words. A text scores well by
sounding like the teacher, never by mentioning the Beautiful State.

THE NEGATIVE CONTROL IS BUILT IN
--------------------------------
The corpus hands us a natural experiment: ``raptor_level=0`` leaf chunks are
human speech, ``raptor_level=1`` chunks are LLM-written RAPTOR summaries of that
*same* speech, on the *same* topics, in the *same* collection. Content is held
constant and only provenance varies. ``validate_profile()`` requires the metric
to separate them; if it cannot, the metric is broken and says so. This is what
makes the instrument non-self-scoring — the reference is 6,737 chunks of human
text the system did not generate, and the control is machine text about the
identical subject matter.

AI-tell features are sourced from measurement, not taste:
* Negative parallelism ("not just X, it's Y") appears ~3x more in LLM text than
  human text — https://en.wikipedia.org/wiki/Negative_parallelism
* Uniform 10-20 word sentences (low burstiness), hedge density, structural
  markers, and an "announcement colon" opener are documented LLM signatures —
  https://github.com/harshaneel/humanize/blob/main/humanize/SKILL.md
* Em-dash overproduction is measured at ~3.3x human frequency for GPT-4.1 —
  https://arxiv.org/pdf/2606.29540
"""

from __future__ import annotations

import math
import re
import statistics
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

PROFILE_DIR = Path(__file__).resolve().parent / "profiles"

# Ingestion-time headers wrapped around chunk bodies by the contextual chunker.
# They are machine-written scaffolding, never the speaker's words, and must be
# stripped before any stylometric reading of a corpus chunk.
_CTX_HEADER_RE = re.compile(
    r"\[(?:Source|Context|Potential Questions?)\s*:.*?\]\s*", re.IGNORECASE | re.DOTALL
)
_TRAILING_QUESTION_BLOCK_RE = re.compile(r"\[Potential Question.*", re.IGNORECASE | re.DOTALL)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_SECOND_PERSON_RE = re.compile(r"\b(?:you|your|yours|yourself|yourselves)\b", re.I)
_FIRST_PERSON_RE = re.compile(r"\b(?:i|me|my|mine|myself|we|us|our|ours)\b", re.I)
# "the person", "individuals", "one's" — the de-personalised register that
# third-party prose and LLM summaries use where a speaker would say "you".
_IMPERSONAL_RE = re.compile(
    r"\b(?:the person|a person|the individual|individuals?|one's|practitioners?|"
    r"seekers may|the seeker|people's)\b",
    re.I,
)
_NOMINALIZATION_RE = re.compile(r"\b\w{4,}(?:tion|ment|ness|ity|ance|ence)s?\b", re.I)
_HEDGE_RE = re.compile(
    r"\b(?:often|typically|generally|usually|may be|might be|can be|tends? to|"
    r"it is important to note|it is worth|in many cases|arguably|relatively)\b",
    re.I,
)
# Markdown / structural furniture. Guru speech contains none of it.
_MARKDOWN_RE = re.compile(r"(?:^\s*[-*+•✦▸]\s)|(?:\*\*)|(?:^#{1,6}\s)", re.M)
_NEGATIVE_PARALLELISM_RE = re.compile(
    r"\b(?:not just|not only|isn't just|is not just|it's not about|it is not about|"
    r"rather than merely|not merely)\b",
    re.I,
)
_AI_LEXICON_RE = re.compile(
    r"\b(?:delve|leverage|utilize|robust|comprehensive|streamline|foster|facilitate|"
    r"pivotal|nuanced|multifaceted|crucial|underscore|showcase|tapestry|testament|"
    r"interplay|intricate|ultimately|furthermore|moreover|additionally|holistic|"
    r"profound(?:ly)?|transformative|cultivate|embody|catalyst)\b",
    re.I,
)
_ANNOUNCEMENT_COLON_RE = re.compile(
    r"^[^\n:]{0,80}:\s*$|^(?:here(?:'s| is)|below)\b[^\n]{0,80}:", re.I | re.M
)
_EM_DASH_RE = re.compile(r"[—–]")
_QUESTION_RE = re.compile(r"\?")

# Order is the vector order. Keep stable: profiles on disk are keyed by name,
# but a rename silently changes what a stored profile means.
FEATURE_NAMES: tuple[str, ...] = (
    "second_person_rate",
    "first_person_rate",
    "impersonal_rate",
    "nominalization_rate",
    "hedge_rate",
    "markdown_rate",
    "negative_parallelism_rate",
    "ai_lexicon_rate",
    "announcement_colon_rate",
    "em_dash_rate",
    "question_rate",
    "median_sentence_len",
    "sentence_len_stdev",
    "mid_band_fraction",
)

# Features where a HIGHER value than the reference is a defect but a LOWER value
# is not. Scoring |z| symmetrically would penalise an answer for using fewer
# bullet markers than a speech transcript that has none, which is nonsense.
_ONE_SIDED_HIGH: frozenset[str] = frozenset(
    {
        "impersonal_rate",
        "nominalization_rate",
        "hedge_rate",
        "markdown_rate",
        "negative_parallelism_rate",
        "ai_lexicon_rate",
        "announcement_colon_rate",
        "em_dash_rate",
    }
)

MIN_WORDS_FOR_SCORE = 40


def strip_chunk_headers(text: str) -> str:
    """Remove ingestion-time ``[Source: ...]`` / ``[Context: ...]`` scaffolding."""
    if not text:
        return ""
    cleaned = _CTX_HEADER_RE.sub("", text)
    cleaned = _TRAILING_QUESTION_BLOCK_RE.sub("", cleaned)
    return cleaned.strip()


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def extract_features(text: str) -> dict[str, float]:
    """Return the form-only feature vector for ``text``.

    Rates are per 100 words except ``question_rate`` (per 100 sentences),
    the sentence-length statistics, and ``mid_band_fraction``.
    """
    words = text.split()
    n_words = max(len(words), 1)
    sents = _sentences(text)
    lengths = [len(s.split()) for s in sents] or [0]
    n_sents = max(len(sents), 1)
    per100 = lambda pattern: 100.0 * len(pattern.findall(text)) / n_words  # noqa: E731

    return {
        "second_person_rate": per100(_SECOND_PERSON_RE),
        "first_person_rate": per100(_FIRST_PERSON_RE),
        "impersonal_rate": per100(_IMPERSONAL_RE),
        "nominalization_rate": per100(_NOMINALIZATION_RE),
        "hedge_rate": per100(_HEDGE_RE),
        "markdown_rate": per100(_MARKDOWN_RE),
        "negative_parallelism_rate": per100(_NEGATIVE_PARALLELISM_RE),
        "ai_lexicon_rate": per100(_AI_LEXICON_RE),
        "announcement_colon_rate": per100(_ANNOUNCEMENT_COLON_RE),
        "em_dash_rate": per100(_EM_DASH_RE),
        "question_rate": 100.0 * len(_QUESTION_RE.findall(text)) / n_sents,
        "median_sentence_len": float(statistics.median(lengths)),
        "sentence_len_stdev": float(statistics.pstdev(lengths)) if len(lengths) > 1 else 0.0,
        "mid_band_fraction": sum(1 for length in lengths if 10 <= length <= 20) / n_sents,
    }


class ProfileProvenance(BaseModel):
    """How a profile was built. Without this a profile is an unfalsifiable claim."""

    model_config = {"extra": "allow"}

    source_collection: str = ""
    teacher_filter: str = ""
    verbatim_criteria: str = ""
    sample_count: int = 0
    built_at: str = ""
    validation: dict[str, float] = Field(default_factory=dict)


class VoiceProfile(BaseModel):
    """Measured style centroid for one teacher, built from verbatim speech only.

    Built by ``scripts/ops/build_voice_profiles.py`` and read at runtime. The
    profile is descriptive (what this teacher's speech measurably looks like),
    never prescriptive-by-hand — that is what makes it repeatable for teacher
    N+1 instead of a block someone wrote by taste.
    """

    model_config = {"frozen": True}

    teacher_id: str
    mean: dict[str, float]
    stdev: dict[str, float]
    provenance: ProfileProvenance = Field(default_factory=ProfileProvenance)

    @field_validator("mean", "stdev")
    @classmethod
    def _require_all_features(cls, v: dict[str, float]) -> dict[str, float]:
        missing = set(FEATURE_NAMES) - set(v)
        if missing:
            raise ValueError(f"profile is missing features: {sorted(missing)}")
        return v

    @property
    def is_certified(self) -> bool:
        """True when this profile's validation run separated human from machine text.

        An uncertified profile must not be used as a quality gate — it may be
        measuring noise. It is still usable for rendering a register block.
        """
        return self.provenance.validation.get("separates", 0.0) == 1.0

    def distance(self, text: str) -> float:
        """Guru Voice Distance: mean |z| over the feature vector. Lower is closer.

        One-sided features (see ``_ONE_SIDED_HIGH``) only contribute when the
        text EXCEEDS the reference — an answer is not penalised for having fewer
        bullet markers or em dashes than a speech transcript that has none.
        """
        feats = extract_features(text)
        zs = []
        for name in FEATURE_NAMES:
            sd = self.stdev.get(name, 0.0)
            if sd <= 1e-9:
                continue
            z = (feats[name] - self.mean.get(name, 0.0)) / sd
            if name in _ONE_SIDED_HIGH:
                z = max(z, 0.0)
            zs.append(abs(z))
        return sum(zs) / len(zs) if zs else 0.0

    def explain(self, text: str, top: int = 5) -> list[tuple[str, float, float, float]]:
        """Worst-offending features: (name, observed, reference_mean, signed z)."""
        feats = extract_features(text)
        rows = []
        for name in FEATURE_NAMES:
            sd = self.stdev.get(name, 0.0)
            if sd <= 1e-9:
                continue
            z = (feats[name] - self.mean.get(name, 0.0)) / sd
            if name in _ONE_SIDED_HIGH:
                z = max(z, 0.0)
            rows.append((name, feats[name], self.mean.get(name, 0.0), z))
        rows.sort(key=lambda r: -abs(r[3]))
        return rows[:top]


def build_profile(
    teacher_id: str, samples: Iterable[str], provenance: ProfileProvenance | None = None
) -> VoiceProfile:
    """Fit a profile from verbatim-speech samples.

    Raises on too little data rather than emitting a profile whose standard
    deviations are noise — a silently bad profile would make every later
    measurement meaningless.
    """
    vectors = [extract_features(s) for s in samples if len(s.split()) >= MIN_WORDS_FOR_SCORE]
    if len(vectors) < 30:
        raise ValueError(
            f"{teacher_id}: only {len(vectors)} usable samples "
            f"(>= {MIN_WORDS_FOR_SCORE} words); need >= 30 for a stable profile"
        )
    mean = {n: statistics.mean(v[n] for v in vectors) for n in FEATURE_NAMES}
    stdev = {n: statistics.pstdev([v[n] for v in vectors]) for n in FEATURE_NAMES}
    prov = (provenance or ProfileProvenance()).model_copy(update={"sample_count": len(vectors)})
    return VoiceProfile(teacher_id=teacher_id, mean=mean, stdev=stdev, provenance=prov)


def validate_profile(
    profile: VoiceProfile, human_holdout: list[str], machine_control: list[str]
) -> dict[str, float]:
    """Prove the metric discriminates, or the metric is worthless.

    ``human_holdout`` is verbatim speech the profile was NOT fitted on;
    ``machine_control`` is LLM-written prose about the SAME topics (RAPTOR
    summaries). Content is held constant, provenance varies. A profile that
    cannot separate them is reported as ``separates=0.0`` and must not be used
    as a quality gate.
    """
    human = [profile.distance(t) for t in human_holdout if len(t.split()) >= MIN_WORDS_FOR_SCORE]
    machine = [
        profile.distance(t) for t in machine_control if len(t.split()) >= MIN_WORDS_FOR_SCORE
    ]
    if not human or not machine:
        return {"separates": 0.0, "reason": "insufficient validation data"}
    # AUC via the Mann-Whitney relation: P(machine scores worse than human).
    wins = sum(1 for m in machine for h in human if m > h)
    ties = sum(1 for m in machine for h in human if math.isclose(m, h))
    auc = (wins + 0.5 * ties) / (len(machine) * len(human))
    return {
        "human_median": statistics.median(human),
        "machine_median": statistics.median(machine),
        "auc": auc,
        "separates": 1.0 if auc >= 0.75 else 0.0,
        "n_human": len(human),
        "n_machine": len(machine),
    }


def load_profile(teacher_id: str) -> VoiceProfile | None:
    """Load a built profile from disk. Returns None when absent (caller degrades)."""
    path = PROFILE_DIR / f"{teacher_id}.json"
    if not path.is_file():
        return None
    try:
        return VoiceProfile.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_profile(profile: VoiceProfile) -> Path:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    path = PROFILE_DIR / f"{profile.teacher_id}.json"
    path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    # Self-check: the metric must rank real speech above article prose, and must
    # not be fooled by topic. Both samples are about the same teaching.
    speech = (
        "You cannot hope that peace will happen to you on a perfect day sometime in "
        "the future while you allow your pain to linger in your heart every day for "
        "years. Peace has to become your reality now. The man who spoke to me had "
        "resigned to the fact that he will never please his father. I helped him see "
        "that resignation is not peace. It only disconnects you from people. What is "
        "happening inside you as you read this?"
    )
    article = (
        "The transition from I-consciousness to One Consciousness reveals that true "
        "spiritual awakening extends far beyond personal liberation, ultimately "
        "creating a profound ripple effect. This transformative shift in "
        "consciousness generally begins by healing the immediate family unit, which "
        "then uplifts the broader community. Furthermore, the cultivation of such "
        "states is not just a practice, it is a comprehensive way of being."
    )
    second_speech = (
        "You are not your thoughts. Watch them come and watch them go. I have seen "
        "this in thousands of people who sat with me. What do you notice when the "
        "noise settles? Sit with that question tonight and see what answers you."
    )
    prof = build_profile(
        "selfcheck",
        [speech] * 20 + [second_speech] * 20,
        provenance=ProfileProvenance(verbatim_criteria="self-check"),
    )
    d_speech, d_article = prof.distance(speech), prof.distance(article)
    assert d_speech < d_article, f"metric inverted: speech={d_speech} article={d_article}"
    v = validate_profile(prof, [speech], [article])
    assert v["auc"] == 1.0, v
    f = extract_features("Here is the answer:\n- **One**\n- **Two**\n- **Three**")
    assert f["markdown_rate"] > 0 and f["announcement_colon_rate"] > 0, f
    assert (
        extract_features("It is not just a practice, it is a way.")["negative_parallelism_rate"] > 0
    )
    print(
        f"speech distance {d_speech:.2f} < article distance {d_article:.2f}  (AUC {v['auc']:.2f})"
    )
    print("worst features in the article sample:")
    for name, obs, ref, z in prof.explain(article):
        print(f"  {name:28s} observed={obs:7.2f} reference={ref:7.2f} z={z:+.2f}")
    print("services/voice/style.py self-check OK")
