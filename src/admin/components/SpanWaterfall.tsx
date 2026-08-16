import type { TraceSpan } from "@/admin/types";
import { cn } from "@/lib/utils";

interface Props {
  spans?: TraceSpan[] | null;
}

const COLORS: Record<string, string> = {
  guardrails_in: "bg-slate-400",
  embed: "bg-prana-blue/80",
  vector_search: "bg-secondary",
  rerank: "bg-violet-500",
  llm: "bg-primary",
  judge: "bg-amber-500",
  guardrails_out: "bg-slate-400",
};

export function SpanWaterfall({ spans }: Props) {
  const safeSpans = Array.isArray(spans) ? spans.filter(Boolean) : [];
  if (!safeSpans.length) {
    return <div className="text-sm text-muted-foreground">No spans recorded.</div>;
  }
  const maxTime = Math.max(
    0,
    ...safeSpans.map((s) => (Number(s?.start_ms) || 0) + (Number(s?.duration_ms) || 0)),
  );
  const total = maxTime > 0 ? maxTime : 1;

  return (
    <div className="space-y-1.5">
      {safeSpans.map((s, idx) => {
        const startMs = Number(s?.start_ms) || 0;
        const durationMs = Number(s?.duration_ms) || 0;
        const leftPct = Math.min(100, Math.max(0, (startMs / total) * 100));
        const widthPct = Math.min(100 - leftPct, Math.max(0.5, (durationMs / total) * 100));
        const spanName = s?.name ?? "span";
        return (
          <div key={s?.id ?? `span-${idx}`} className="flex items-center gap-3 text-xs">
            <div className="w-32 shrink-0 text-muted-foreground font-mono truncate" title={spanName}>
              {spanName}
            </div>
            <div className="flex-1 relative h-5 bg-muted rounded-md overflow-hidden">
              <div
                className={cn("absolute top-0 h-full rounded-sm", COLORS[spanName] ?? "bg-slate-400")}
                style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                title={`${spanName}: ${durationMs}ms`}
              />
            </div>
            <div className="w-16 text-right tabular-nums text-muted-foreground">
              {durationMs}ms
            </div>
          </div>
        );
      })}
      <div className="text-[11px] text-muted-foreground pt-1">
        Total: <span className="tabular-nums">{maxTime}ms</span>
      </div>
    </div>
  );
}
