# `/api/chat/stream` Streaming Protocol Contract

> **Status**: STABLE as of 2026-02 (RAG Phase 2 — 20 emission sites instrumented).
> **Versioning**: This document IS the contract. Bump the doc version when you break compat.
> **Doc version**: `1.0`

---

## 0. TL;DR — the only 3 frame types

```
event: status
data: <human-readable progress message>

event: token
data: <one chunk of the answer text>

event: done
data: {"trace_id":"...","intent":"FACTUAL","citations":[...],"query_tier":"fast","latency_ms":4500}
```

Frames are separated by a blank line (`\r\n\r\n` per SSE spec). The connection
closes after `done`. Any other frame your client sees is undocumented.

---

## 1. Endpoint

`POST /api/chat/stream`

### Request (identical to `/api/chat`)
```http
POST /api/chat/stream
Authorization: Bearer <supabase-jwt-or-local-hs256-jwt>
Content-Type: application/json
Accept: text/event-stream
```

Body — same Pydantic schema as `/api/chat` (`ChatRequest` in
`backend/app/schemas.py`):

```json
{
  "messages": [
    {"role": "user",      "content": "What is the Beautiful State?"},
    {"role": "assistant", "content": "The Beautiful State is..."}
  ],
  "user_message": "Tell me more about that",
  "session_id": "wa-+91...-2026-02-15",
  "meditation_step": 0,
  "language": "en",
  "last_serene_mind_at": null
}
```

### Response

`Content-Type: text/event-stream` with `Cache-Control: no-cache` and
`Connection: keep-alive`. Frame stream as below.

---

## 2. Frame schema

### 2.1 `event: status`

Human-readable progress message. **Never machine-parsed.** UI clients render
verbatim. The exact text is subject to A/B testing — do NOT switch on the
content. If you need to switch UI states, switch on **frame order**, not
content (see §3).

```
event: status
data: Understanding your question...
```

Status `data` is plain UTF-8 text, may contain emoji, may span multiple
lines (newlines inside `data` are encoded as `\ndata: ` continuation per
SSE spec; the helper at `backend/rag/nodes/utils.py:emit_status` only
emits single-line messages).

### 2.2 `event: token`

One chunk of the answer text. Concatenate all `token` data in arrival
order to reconstruct the final answer.

```
event: token
data:  the Beautiful State is

event: token
data:  the state of inner peace
```

`data` is plain UTF-8 text. **Leading/trailing whitespace is significant** —
the backend emits with intentional spacing. Do NOT trim.

Chunk size is implementation-dependent. Treat each frame as opaque bytes;
do not assume word boundaries.

### 2.3 `event: done`

Single terminal frame containing the full response metadata as JSON.
Connection closes after this frame.

```
event: done
data: {"trace_id":"abc-123","intent":"FACTUAL","citations":["https://...","https://..."],"query_tier":"fast","latency_ms":4500,"meditation_step":0,"hallucination_flag":false,"confidence_score":8.5,"faithfulness_score":0.92,"relevancy_score":0.88,"model_used":"deepseek-r1:7b","verification":{"passed":true,"is_faithful":true,"confidence":8.5}}
```

**Schema** (subset of `ChatResponse`):

| Field | Type | Always present? | Notes |
|---|---|---|---|
| `trace_id` | string | yes | UUID. Log this on the client; quote when reporting issues. |
| `intent` | string | yes | One of `FACTUAL`, `RELATIONAL`, `FOLLOW_UP`, `MEDITATION`, `CASUAL`, `ADVERSARIAL`, `DISTRESS`, `SAFETY_VIOLATION`. |
| `citations` | string[] | yes (may be `[]`) | Source URLs. |
| `query_tier` | string | yes | `"fast"`, `"standard"`, `"deep"`. |
| `latency_ms` | number | yes | End-to-end wall time. |
| `meditation_step` | number | yes | 0 if no active session. Echo this in the next request. |
| `hallucination_flag` | bool | yes | True if `verify_answer` failed. UI may surface a "low confidence" badge. |
| `confidence_score` | number | yes | 0-10 scale. |
| `faithfulness_score` | number | yes | 0-1. |
| `relevancy_score` | number | yes | 0-1. |
| `model_used` | string | yes | e.g. `deepseek-r1:7b`. |
| `verification` | object | yes | `{passed, is_faithful, confidence, details}`. |
| `blocked` | bool | optional | True if safety-violated. If true, `response` content was replaced server-side. |
| `block_reason` | string\|null | optional | Set when `blocked=true`. |
| `proactive_serene_mind` | object\|null | optional | If non-null, suggest a meditation. |
| `node_timings` | object | optional | Map of node name → milliseconds. Debugging only. |

---

## 3. Ordering guarantees

The backend GUARANTEES this frame ordering:

```
1. First frame is ALWAYS event: status with data "Understanding your question..."
2. Zero or more event: status frames (progress messages)
3. One or more event: token frames (the answer streams here)
4. Exactly one event: done frame
5. Stream closes
```

**Implications for clients:**
- If you see `event: token` before any `event: status`, that's a backend bug —
  file an issue.
- If the stream closes without `event: done`, treat as a connection error
  (see §5).
- A `status` frame may arrive AFTER `token` frames in some tiers (e.g.,
  `verify_answer` emits status post-generation). Clients should KEEP rendering
  any late `status` frames as ephemeral progress indicators, not assume the
  response is incomplete.

### Status frame sequence by tier (informational, NOT a contract)

```
fast tier (~3-8s):
  status: "Understanding your question..."
  status: "Saying hello..." OR "Holding space..." (handle_* nodes)
  token, token, ...
  done

standard tier (~10-20s):
  status: "Understanding your question..."
  status: "Connecting this to your previous question..."  (resolve_followup, if history)
  status: "Breaking the question into deeper parts..."   (decompose_query)
  status: "Walking the teaching graph..."                (navigate_knowledge_tree)
  status: "Imagining the shape of the answer..."         (generate_hyde)
  status: "Searching knowledge base..."                  (retrieve_documents)
  status: "Ranking the most relevant teachings..."       (rerank_documents)
  status: "Filtering for relevance..."                   (grade_documents)
  status: "Checking if I have enough to answer well..."  (check_context_sufficiency)
  status: "Gathering surrounding context..."             (enrich_context)
  status: "Composing the response..."                    (context_engineer)
  token, token, token, ...                                (generate_answer streams)
  status: "Reviewing the response for clarity..."        (reflect_on_answer)
  status: "Verifying alignment with the teachings..."    (verify_answer)
  status: "Checking consistency with our conversation..." (check_contradiction)
  status: "Annotating sources..."                        (explain_retrieval)
  status: "Finalizing your response..."                  (format_final_answer)
  done

deep tier:
  Same as standard but with longer per-stage latency and possibly
  "Rephrasing the question for better retrieval..." (rewrite_query) if
  CRAG fires.
```

Status messages are TUNED for end users. Do not show technical strings
("decompose_query started") — render the human-readable text as-is.

---

## 4. Authentication

Same as `/api/chat`. Three valid token classes:
1. **Supabase JWT** (HS256 or asymmetric) — preferred for browser clients
2. **Service-role token** — superuser; treat like a DB password
3. **Local HS256 JWT** signed with `backend/.env:JWT_SECRET` — used by the
   WhatsApp bot (see `WHATSAPP_BOT_INTEGRATION.md` Option B)

A 401 closes the connection BEFORE any frames are emitted. Clients must
handle this distinctly from mid-stream errors (§5).

---

## 5. Error handling

### 5.1 Pre-stream errors (status code on the HTTP response)

| Status | Meaning | Client action |
|---|---|---|
| `401` | Bad/expired JWT | Refresh token, retry once |
| `403` | Forbidden (banned user / blocked endpoint) | Surface to user; do not retry |
| `422` | Malformed request body (Pydantic) | Fix payload; bug in client |
| `429` | Rate limited | Exponential backoff |
| `5xx` | Backend exception before stream started | Treat as transient; retry with backoff |

### 5.2 Mid-stream failures

If the connection drops AFTER frames started flowing but BEFORE `event: done`:
- The token chunks you received SO FAR are valid partial output
- DO NOT retry the same request — the backend may have partially committed
  state (cached embeddings, etc.); a retry could produce a slightly different
  answer
- Surface "Response interrupted" to the user; allow them to manually retry
  with a button click

### 5.3 Server-side errors expressed as a status frame

If the backend can't recover but doesn't want to drop the connection, you
may see:

```
event: status
data: I am catching my breath. Please try again in a moment.

event: done
data: {"trace_id":"...","intent":"CASUAL","citations":[],"query_tier":"fast","blocked":false}
```

This is a graceful failure mode. Treat as a complete (but apologetic) response.

---

## 6. Client reference (TypeScript)

```ts
type ChatStreamFrame =
  | { event: "status"; data: string }
  | { event: "token";  data: string }
  | { event: "done";   data: ChatDoneMeta };

interface ChatDoneMeta {
  trace_id: string;
  intent: "FACTUAL" | "RELATIONAL" | "FOLLOW_UP" | "MEDITATION"
        | "CASUAL"  | "ADVERSARIAL" | "DISTRESS" | "SAFETY_VIOLATION";
  citations: string[];
  query_tier: "fast" | "standard" | "deep";
  latency_ms: number;
  meditation_step: number;
  hallucination_flag: boolean;
  confidence_score: number;
  faithfulness_score: number;
  relevancy_score: number;
  model_used: string;
  verification: { passed: boolean; is_faithful: boolean; confidence: number; details?: string };
  blocked?: boolean;
  block_reason?: string | null;
}

async function chatStream(req: ChatRequest, jwt: string,
                         onStatus: (msg: string) => void,
                         onToken:  (chunk: string) => void,
                         onDone:   (meta: ChatDoneMeta) => void): Promise<void> {
  const resp = await fetch(`${API_URL}/api/chat/stream`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${jwt}`,
      "Content-Type":  "application/json",
      "Accept":        "text/event-stream",
    },
    body: JSON.stringify(req),
  });

  if (!resp.ok || !resp.body) {
    throw new Error(`stream init failed: ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    // SSE frames are separated by blank lines
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const lines = frame.split("\n");
      let ev = "message";
      const dataLines: string[] = [];
      for (const line of lines) {
        if (line.startsWith("event:")) ev = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
      }
      const data = dataLines.join("\n");
      if (ev === "status") onStatus(data);
      else if (ev === "token") onToken(data);
      else if (ev === "done") {
        try { onDone(JSON.parse(data)); } catch { /* malformed done — log */ }
      }
    }
  }
}
```

Drop-in usage:

```ts
await chatStream(
  { messages: [], user_message: "What is the Beautiful State?",
    meditation_step: 0, language: "en" },
  jwt,
  (msg)  => setStatus(msg),
  (tok)  => setAnswer(prev => prev + tok),
  (meta) => { setMeta(meta); setLoading(false); },
);
```

---

## 7. Python client reference

```python
import json, requests

def chat_stream(api_url: str, jwt: str, payload: dict):
    """Yields (event_name, data) tuples until `done`."""
    with requests.post(
        f"{api_url}/api/chat/stream",
        headers={
            "Authorization": f"Bearer {jwt}",
            "Content-Type":  "application/json",
            "Accept":        "text/event-stream",
        },
        json=payload,
        stream=True,
        timeout=120,
    ) as resp:
        resp.raise_for_status()
        buf = ""
        for chunk in resp.iter_content(chunk_size=1024, decode_unicode=True):
            buf += chunk
            while "\n\n" in buf:
                frame, buf = buf.split("\n\n", 1)
                ev, data_lines = "message", []
                for line in frame.split("\n"):
                    if line.startswith("event:"):
                        ev = line[6:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].lstrip(" "))
                data = "\n".join(data_lines)
                if ev == "done":
                    yield ev, json.loads(data)
                    return
                yield ev, data
```

Usage:

```python
for event, data in chat_stream(api_url, jwt, payload):
    if event == "status":
        print(f"[…] {data}")
    elif event == "token":
        print(data, end="", flush=True)
    elif event == "done":
        print(f"\n\n[trace_id={data['trace_id']} tier={data['query_tier']}]")
```

---

## 8. Compatibility & versioning

This contract is **stable for v1**. The backend will not:
- Remove `status`, `token`, `done` event types
- Remove any required field from the `done` payload
- Change ordering rules in §3

The backend MAY:
- Add new optional fields to the `done` payload
- Add new `event: status` messages (clients render them transparently — they
  must not match on content)
- Reorder `status` frames within a tier (since order isn't a content contract)

If you need to break compat (e.g., binary frames, new event types), bump the
doc version to `2.0` and gate via an `Accept-Stream-Version: 2` request header.

---

## 9. What this protocol does NOT support (intentionally)

- **Mid-stream cancellation by the client.** Closing the HTTP connection works
  but the backend keeps generating until the graph terminates (state is
  written to DB). If you need cancellation, add a `request_id` → cancellation
  token map in the backend; future work.
- **Multi-user fan-out / WebSocket multiplexing.** One HTTP connection = one
  conversation. Multiple parallel conversations require multiple connections.
- **Streaming images, audio, or other binary content.** Text only. If the
  backend ever generates images (e.g., meditation diagrams), define a new
  event type and bump the doc version.
- **Backwards-deliverable retries.** If the connection breaks at frame 17,
  the backend cannot resume from frame 18. Restart from scratch.

---

## 10. Where this contract is implemented in the backend

| Concern | File | Function |
|---|---|---|
| HTTP route | `backend/app/main.py` | `/api/chat/stream` handler |
| SSE serialization | `backend/app/stream_orchestrator.py` | `stream_chat` async generator |
| Status emission helper | `backend/rag/nodes/utils.py` | `emit_status(config, msg)` |
| Token streaming | `backend/rag/nodes/generation.py` | `generate_answer` node, line ~244+ |
| Done payload assembly | `backend/app/stream_orchestrator.py` | final yield with `event: done` |

If you modify the contract, update this doc in the same PR. Treat
`STREAM_PROTOCOL.md` as a versioned interface document, not a README.
