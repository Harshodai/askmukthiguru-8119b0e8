import json
from collections.abc import AsyncGenerator


async def stream_sarvam_response(
    messages: list, model: str = "sarvam-105b", temperature: float = 0.3, api_key: str = None
) -> AsyncGenerator[str, None]:
    """Stream LLM response using SSE format for real-time display."""
    import httpx

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            "https://api.sarvam.ai/chat/completions",
            headers={"api-subscription-key": api_key, "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "stream": True,  # Enable streaming
            },
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        if "choices" in chunk and len(chunk["choices"]) > 0:
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content")
                            reasoning_content = delta.get("reasoning_content")
                            if content:
                                yield content
                            elif reasoning_content:
                                yield reasoning_content
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue
