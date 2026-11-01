import pytest

try:
    from app.streaming.admission_router import StreamAdmissionRouter
except ModuleNotFoundError:
    from backend.app.streaming.admission_router import StreamAdmissionRouter


@pytest.mark.asyncio
async def test_admission_router_fast_path():
    router = StreamAdmissionRouter(max_concurrency=10, saturation_threshold=0.90)
    result = await router.admit_request("session-1")
    assert result["status"] == 200
    assert result["action"] == "stream"
    assert router.get_current_concurrency() == 1
    await router.release_session("session-1")
    assert router.get_current_concurrency() == 0


@pytest.mark.asyncio
async def test_admission_router_slow_path_saturation():
    router = StreamAdmissionRouter(max_concurrency=2, saturation_threshold=0.50)
    # Fill concurrency to trigger saturation (1 active >= 2 * 0.50)
    await router.admit_request("session-1")

    result = await router.admit_request("session-2")
    assert result["status"] == 202
    assert result["action"] == "defer"


@pytest.mark.asyncio
async def test_sequence_numbering_and_ring_buffer():
    router = StreamAdmissionRouter()
    session_id = "test-seq-session"

    seq0 = await router.record_event(session_id, "token", {"text": "Om"})
    seq1 = await router.record_event(session_id, "token", {"text": " Shanti"})

    assert seq0 == 0
    assert seq1 == 1

    missed = await router.get_events_since(session_id, last_event_id=-1)
    assert len(missed) == 2
    assert missed[0]["seq"] == 0
    assert missed[1]["seq"] == 1

    missed_from_0 = await router.get_events_since(session_id, last_event_id=0)
    assert len(missed_from_0) == 1
    assert missed_from_0[0]["seq"] == 1


@pytest.mark.asyncio
async def test_low_latency_sse_generator():
    try:
        from app.streaming.sse_generator import LowLatencySSEGenerator
    except ModuleNotFoundError:
        from backend.app.streaming.sse_generator import LowLatencySSEGenerator

    generator = LowLatencySSEGenerator(lookahead_chars=10)

    # Test think tag stripping
    clean = generator.strip_think_tags("Intro <think>private CoT reasoning</think> Extro")
    assert clean == "Intro  Extro"

    # Test event formatting
    event = generator.format_event("token", {"text": "Om"}, event_id=42)
    assert "event: token" in event
    assert "id: 42" in event
    assert 'data: {"text": "Om"}' in event

    # Test stream transform with lookahead
    async def sample_stream():
        yield "Hello "
        yield "<think>thinking</think>"
        yield "World! This is a long sentence."

    events = []
    async for ev in generator.transform_stream(sample_stream()):
        events.append(ev)

    assert len(events) >= 1
    assert "thinking" not in "".join(events)
