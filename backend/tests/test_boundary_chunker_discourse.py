"""Regression coverage for backend/CLAUDE.md's chunking defect: the corpus's
raptor_level=0 chunks are median 15 words / 74.8% single-sentence — cadence
destroyed at chunk time. Root-cause finding (see task report): that corpus
was built before ingest/boundary_chunker.py existed, and NO re-ingest is in
scope, so the only thing to prove here is that TODAY'S chunker does not
reproduce the defect on real discourse text.

REAL_TRANSCRIPT below is genuine Sri Preethaji discourse pulled directly from
the live `spiritual_wisdom_contextual` collection (one legacy chunk per line,
[Source:]/[Context:]/[Potential Questions:] metadata stripped) — i.e. this is
exactly the kind of one-sentence-per-chunk fragmentation described above,
used here as the *input* to prove the current chunker recombines it into
multi-sentence discourse spans instead of preserving the fragmentation.
"""

from __future__ import annotations

import re

from ingest.boundary_chunker import chunk_with_contextual_headers

REAL_TRANSCRIPT = """Look at the world, they're all stressed.

Yes, everyone is stressed, and they're responding from stress.

They're relating from stress, and they're creating abundance or trying to create wealth from stress.

Japanese "ikigai" means life purpose.

Yes, and it's very related to your "dharma" in India.

What Sri Sri Krishnaji and I have done is bringing together of these two extremes and showing: only when you live in a beautiful inner state, are able to experience life free of stress and anxiety and fear, that is when you will be able to be your best.

So if you want to create a great destiny, so it is not prefixed, everything is not prefixed.

If you want to create a great destiny, it is possible.

The purpose of every life, everybody's life, is to experience freedom, to experience liberation, and to live an enlightened state and to live an enlightened life.

Hello, my name is Kahanda, and I'm so excited to host this special guest from India, Shri Sri Preethaji.

Thank you so much for joining us.

Wonderful being over here.

So we are filming this in Tokyo, and we are so excited to have you back.

It's so beautiful to be back in Tokyo.

So obviously, I hope you - you seem to love Japan because you seem to be coming back so many times.

Absolutely love being here and the way people learn.

People are really looking at the way you're teaching and learning.

People are really looking for having spirituality into their lives.

Open and receptive people are looking for.

Japanese people love Indian culture, Indian philosophy, and the depth of India.

Indian curries are a favorite of Japanese kids.

India is part of our life.

Kids loved Indian curries.

I'd like to ask you some questions on your teachings.

I understand this audience will be very general, so people may not understand about spirituality or religion.

I teach people to live in a Beautiful State.

To have a very beautiful inner experience of life.

To be very calm, peaceful, joyful.

To be very connected, feeling gratitude.

Life is to be very calm, peaceful, joyful.

To live one's life free of stress.

To live in a beautiful inner state.

To experience life from that beautiful inner state.

To create wealth from that beautiful inner state.

To relate with one's children or partner from that beautiful inner state.

To live free of suffering.
"""


def _strip_header(chunk: str) -> str:
    return re.sub(r"^\[[^\]]*\]\n?", "", chunk)


def _sentence_count(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()])


def test_real_discourse_is_recombined_into_multi_sentence_chunks():
    """The input is legacy one-sentence-per-line fragmentation (see module
    docstring). Today's chunker must not reproduce that: chunks should be
    multi-sentence discourse spans, not single utterances."""
    chunks = chunk_with_contextual_headers(
        REAL_TRANSCRIPT,
        title="Calm Is Your Superpower",
        speaker="Sri Preethaji",
        topic="Nature of Suffering",
        target_size=1200,
        overlap_sentences=1,
    )
    assert chunks, "chunker produced no output for real transcript text"

    bodies = [_strip_header(c) for c in chunks]
    sentence_counts = [_sentence_count(b) for b in bodies]
    word_counts = [len(b.split()) for b in bodies]

    single_sentence_ratio = sum(1 for n in sentence_counts if n <= 1) / len(sentence_counts)
    median_words = sorted(word_counts)[len(word_counts) // 2]

    # The corpus defect this guards against: median 15 words, 74.8%
    # single-sentence. Today's chunker must land far on the other side.
    assert median_words >= 60, f"chunks too short: median {median_words} words (defect was 15)"
    assert single_sentence_ratio <= 0.2, (
        f"{single_sentence_ratio:.0%} of chunks are single-sentence (defect was 74.8%)"
    )


def test_chunk_headers_carry_source_speaker_topic():
    chunks = chunk_with_contextual_headers(
        REAL_TRANSCRIPT,
        title="Calm Is Your Superpower",
        speaker="Sri Preethaji",
        topic="Nature of Suffering",
    )
    assert chunks[0].startswith(
        "[Source: Calm Is Your Superpower | Speaker: Sri Preethaji | Topic: Nature of Suffering]"
    )


if __name__ == "__main__":
    test_real_discourse_is_recombined_into_multi_sentence_chunks()
    test_chunk_headers_carry_source_speaker_topic()
    print("OK: boundary chunker preserves discourse on real transcript text")
