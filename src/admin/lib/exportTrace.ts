// Export a query trace as JSON or CSV.
import type { QueryTrace } from "../types";

function download(filename: string, mime: string, content: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function exportTraceJSON(trace: QueryTrace): { filename: string; content: string } {
  const filename = `trace_${trace.query.id}_${Date.now()}.json`;
  const content = JSON.stringify(trace, null, 2);
  download(filename, "application/json", content);
  return { filename, content };
}

function csvEscape(v: unknown): string {
  if (v == null) return "";
  const s = typeof v === "string" ? v : JSON.stringify(v);
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function rowsToCsv(headers: string[], rows: Array<Record<string, unknown>>): string {
  const head = headers.join(",");
  const body = rows
    .map((r) => headers.map((h) => csvEscape(r[h])).join(","))
    .join("\n");
  return `${head}\n${body}`;
}

export function exportTraceCSV(trace: QueryTrace): { filename: string; content: string } {
  const filename = `trace_${trace.query.id}_${Date.now()}.csv`;
  const sections: string[] = [];

  // Section 1: query metadata
  sections.push("# QUERY");
  sections.push(
    rowsToCsv(
      [
        "id",
        "session_id",
        "anon_user_id",
        "query_text",
        "prompt_version_id",
        "model",
        "prompt_tokens",
        "completion_tokens",
        "cost_estimate",
        "latency_ms",
        "status",
        "created_at",
      ],
      [trace.query as unknown as Record<string, unknown>],
    ),
  );

  // Section 2: prompt
  sections.push("\n# PROMPT");
  sections.push(
    rowsToCsv(
      ["id", "name", "version", "active", "created_at"],
      [
        {
          id: trace.prompt.id,
          name: trace.prompt.name,
          version: trace.prompt.version,
          active: trace.prompt.active,
          created_at: trace.prompt.created_at,
        },
      ],
    ),
  );

  // Section 3: spans
  sections.push("\n# SPANS");
  sections.push(
    rowsToCsv(
      ["id", "name", "start_ms", "duration_ms", "attributes"],
      trace.spans.map((s) => ({
        id: s.id,
        name: s.name,
        start_ms: s.start_ms,
        duration_ms: s.duration_ms,
        attributes: s.attributes,
      })),
    ),
  );

  // Section 4: retrieval
  sections.push("\n# RETRIEVAL");
  if (trace.retrieval) {
    const r = trace.retrieval;
    sections.push(
      rowsToCsv(
        ["rank", "chunk_id", "source_doc", "score"],
        r.source_docs.map((src, i) => ({
          rank: i + 1,
          chunk_id: r.chunk_ids[i] ?? "",
          source_doc: src,
          score: r.scores[i] ?? "",
        })),
      ),
    );
  } else {
    sections.push("(no retrieval)");
  }

  // Section 5: response + judge
  sections.push("\n# RESPONSE_AND_JUDGE");
  if (trace.response) {
    const r = trace.response;
    sections.push(
      rowsToCsv(
        [
          "response_id",
          "faithfulness",
          "answer_relevancy",
          "context_precision",
          "context_recall",
          "hallucination_flag",
          "confidence",
          "judge_reasoning",
          "response_text",
        ],
        [
          {
            response_id: r.id,
            faithfulness: r.faithfulness,
            answer_relevancy: r.answer_relevancy,
            context_precision: r.context_precision,
            context_recall: r.context_recall,
            hallucination_flag: r.hallucination_flag,
            confidence: r.confidence,
            judge_reasoning: r.judge_reasoning,
            response_text: r.response_text,
          },
        ],
      ),
    );
  }

  // Section 6: triggers
  sections.push("\n# TRIGGERS");
  sections.push(
    rowsToCsv(
      ["id", "trigger_name", "metadata", "created_at"],
      trace.triggers.map((t) => ({
        id: t.id,
        trigger_name: t.trigger_name,
        metadata: t.metadata,
        created_at: t.created_at,
      })),
    ),
  );

  const content = sections.join("\n");
  download(filename, "text/csv", content);
  return { filename, content };
}
