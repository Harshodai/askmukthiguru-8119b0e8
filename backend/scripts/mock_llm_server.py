"""OpenAI-compatible mock LLM server for P1-OPS-7 load tests.

Serves POST /v1/chat/completions returning a canned ~800-token response so a
load test exercises the full chat pipeline (Qdrant → rerank → LLM → guardrails)
without LLM cost or rate limits. Pure stdlib — no framework required.

Usage:
    python scripts/mock_llm_server.py --port 9002
    # point the backend at it:
    LLM_PROVIDER=nim NIM_BASE_URL=http://127.0.0.1:9002/v1 NIM_API_KEY=mock \
        uvicorn app.main:app --port 8000

Optional --slow 0.05 adds artificial per-token delay to emulate real LLM latency.
"""

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


_CANNED_RESPONSE = (
    "The essence of inner stillness is not found by silencing thought, but by "
    "witnessing it without identification. In the teaching of the Gurus, stillness "
    "is the natural state that remains when the mind's commentary falls away. "
    "Begin with three slow breaths, noticing where the body meets the chair. "
    "Allow sounds to arise and pass without chasing them. When a thought appears, "
    "neither push it away nor follow it — simply return to the sensation of "
    "breathing. This is not effort; it is letting the surface settle. Over days, "
    "the turbulence of distraction lessens, and a deeper rest becomes accessible. "
    "What arises is not emptiness, but vividness. The practice is simple: notice, "
    "return, rest. Each return is not failure; it is the practice itself. "
    "In this way, stillness grows from repetition, not from force."
)

_EXTRA_WORDS = (
    "Peace flows like a river beneath the noise. Awareness itself is the guru. "
    "When the watcher remains steady, emotions become weather. The breath is the "
    "bridge between the body and the vast. Gratitude dissolves the narrow self. "
    "Love is not a concept; it is the felt texture of presence. Let each journey "
    "unfold without hurry. The grace of the teaching is its simplicity. "
)


def _canned_body() -> str:
    target_tokens = 800
    words = (_CANNED_RESPONSE + " " + _EXTRA_WORDS).split()
    seed_len = len(words)
    repeats = max(1, target_tokens // seed_len)
    text = (" ".join(words) + " ") * repeats
    return text[: target_tokens * 6]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence request logging
        pass

    def do_POST(self):  # noqa: N802 (http.server API)
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        if length:
            self.rfile.read(length)
        time.sleep(self.server.slow_per_token * 200)  # emulate ~200-token latency
        payload = {
            "id": "chatcmpl-mock-0001",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "mock-800-token",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": _canned_body()},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 32, "completion_tokens": 800, "total_tokens": 832},
        }
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 (http.server API)
        body = b'{"status":"ok","model":"mock-800-token"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock OpenAI-compatible LLM for load tests")
    parser.add_argument("--port", type=int, default=9002)
    parser.add_argument("--slow", type=float, default=0.0, help="seconds added per ~200 tokens")
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.slow_per_token = args.slow
    print(f"Mock LLM listening on http://127.0.0.1:{args.port}/v1/chat/completions", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nMock LLM stopped", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())