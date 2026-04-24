# Backend integration (askmukthiguru chat code)

Once the chat backend is brought into this project, wire telemetry with these
five calls. Everything else (judge, RAGAS scoring, alert evaluation) runs
asynchronously without further plumbing.

## The 5-line wiring

```ts
// In your chat handler:
const queryId = await telemetry.recordQuery({
  sessionId, queryText, model, promptVersionId, anonUserId,
});

const ctx = await withSpan(queryId, "vector_search",
  () => vectorStore.search(queryText));
await telemetry.recordRetrieval({
  queryId,
  chunkIds: ctx.ids,
  scores: ctx.scores,
  sourceDocs: ctx.sources,
});

const answer = await withSpan(queryId, "llm",
  () => llm.complete(prompt));

const responseId = await telemetry.recordResponse({
  queryId,
  responseText: answer.text,
  citations: answer.citations,
});

if (sereneTriggered) {
  await telemetry.recordTrigger({ queryId, name: "serene_mind" });
}

// Judge runs automatically in the background.
```

End-user UI calls `telemetry.recordFeedback({ responseId, rating })` on 👍/👎.

## Span naming convention

Use these names so the waterfall renders consistently:
`guardrails_in | embed | vector_search | rerank | llm | judge | guardrails_out`

## Judge — single AI call returning all 4 RAGAS scores + safety

Run inside an edge function so `LOVABLE_API_KEY` stays server-side.

```ts
const evalTool = {
  type: "function",
  function: {
    name: "evaluate",
    parameters: {
      type: "object",
      required: [
        "faithfulness","answer_relevancy","context_precision","context_recall",
        "hallucination","reason","safety",
      ],
      properties: {
        faithfulness:      { type: "number" },
        answer_relevancy:  { type: "number" },
        context_precision: { type: "number" },
        context_recall:    { type: "number" },
        hallucination:     { type: "boolean" },
        reason:            { type: "string" },
        safety: {
          type: "object",
          properties: {
            prompt_injection: { type: "boolean" },
            pii_detected:     { type: "boolean" },
            toxicity:         { type: "boolean" },
          },
        },
      },
    },
  },
};

await fetch("https://ai.gateway.lovable.dev/v1/chat/completions", {
  method: "POST",
  headers: {
    Authorization: `Bearer ${Deno.env.get("LOVABLE_API_KEY")}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    model: "google/gemini-2.5-flash",
    messages: [
      { role: "system", content: JUDGE_PROMPT },
      { role: "user",   content: JSON.stringify({ query, context, answer }) },
    ],
    tools: [evalTool],
    tool_choice: { type: "function", function: { name: "evaluate" } },
  }),
});
```

## Cost calculation

```
cost = (prompt_tokens / 1000) * model_pricing.input_per_1k
     + (completion_tokens / 1000) * model_pricing.output_per_1k
```

Cache `model_pricing` in memory for the request lifetime.

## PII redaction

Run a regex pass before persisting `query_text` and `response_text`:
- emails, phone numbers, Indian PAN/Aadhaar patterns
- replace matches with `[redacted:email]` etc.

The `Settings` page surfaces a toggle for this.

## Service-role writes only

All `telemetry.*` writes happen in edge functions using `SUPABASE_SERVICE_ROLE_KEY`.
**Never** expose telemetry write APIs to the browser — the schema is read-only
for the admin role and write-only for the service role.
