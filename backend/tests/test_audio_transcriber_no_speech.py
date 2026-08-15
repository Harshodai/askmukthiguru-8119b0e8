"""No-speech vs genuine-failure distinction in audio_transcriber._transcribe_chunks.

transcribe_with_whisper returns "" (confirmed no speech -- music/silence) as a
sentinel distinct from None (genuine transcription failure). _transcribe_chunks
must surface a different, greppable RuntimeError message for the all-no-speech
case so DLQ error classification can bucket it as expected/permanent rather
than an alarming generic failure.
"""

from pathlib import Path

import pytest

from ingest.audio_transcriber import _transcribe_chunks


@pytest.mark.asyncio
async def test_all_chunks_no_speech_raises_distinct_message(monkeypatch):
    monkeypatch.setattr(
        "ingest.audio_transcriber.transcribe_with_whisper",
        lambda video_id, path: "",
    )
    chunks = [Path("chunk_0.wav"), Path("chunk_1.wav")]

    with pytest.raises(RuntimeError, match="No speech detected"):
        await _transcribe_chunks(chunks)


@pytest.mark.asyncio
async def test_genuine_failure_keeps_generic_message(monkeypatch):
    monkeypatch.setattr(
        "ingest.audio_transcriber.transcribe_with_whisper",
        lambda video_id, path: None,
    )
    chunks = [Path("chunk_0.wav")]

    with pytest.raises(RuntimeError, match="produced no output"):
        await _transcribe_chunks(chunks)


@pytest.mark.asyncio
async def test_mixed_no_speech_and_success_keeps_successful_text(monkeypatch):
    # 9/10 chunks have real speech (90% coverage, clears the existing 85% floor);
    # 1 is a confirmed music-only intro chunk that must be silently dropped, not
    # treated as a failure that trips the coverage gate.
    calls = {f"audio_chunk_{i}": f"segment {i} text" for i in range(1, 10)}
    calls["audio_chunk_0"] = ""
    monkeypatch.setattr(
        "ingest.audio_transcriber.transcribe_with_whisper",
        lambda video_id, path: calls[video_id],
    )
    chunks = [Path(f"chunk_{i}.wav") for i in range(10)]

    result = await _transcribe_chunks(chunks)
    assert "segment 1 text" in result
    assert result.count("segment") == 9


if __name__ == "__main__":
    import asyncio

    async def _self_check():
        import ingest.audio_transcriber as mod

        orig = mod.transcribe_with_whisper
        mod.transcribe_with_whisper = lambda video_id, path: ""
        try:
            await _transcribe_chunks([Path("a.wav")])
            raise AssertionError("expected RuntimeError")
        except RuntimeError as e:
            assert "No speech detected" in str(e), e
        finally:
            mod.transcribe_with_whisper = orig

        print("test_audio_transcriber_no_speech self-check OK")

    asyncio.run(_self_check())
