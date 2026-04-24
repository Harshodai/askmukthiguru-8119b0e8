import type { TraceSpan } from "@/admin/types";
import { cn } from "@/lib/utils";

interface Props {
  spans: TraceSpan[];
}

const COLORS: Record<TraceSpan["name"], string> = {
  guardrails_in: "bg-slate-400",
  embed: "bg-prana-blue/80",
  vector_search: "bg-secondary",
  rerank: "bg-violet-500",
  llm: "bg-primary",
  judge: "bg-amber-500",
  guardrails_out: "bg-slate-400",
};

export function SpanWaterfall({ spans }: Props) {
  if (!spans.length) {
    return <div className="text-sm text-muted-foreground">No spans recorded.</div>;
  }
  const total = Math.max(...spans.map((s) => s.start_ms + s.duration_ms));
  return (
    <div className="space-y-1.5">
      {spans.map((s) => {
        const leftPct = (s.start_ms / total) * 100;
        const widthPct = Math.max(0.5, (s.duration_ms / total) * 100);
        return (
          <div key={s.id} className="flex items-center gap-3 text-xs">
            <div className="w-32 shrink-0 text-muted-foreground font-mono">{s.name}</div>
            <div className="flex-1 relative h-5 bg-muted rounded-md overflow-hidden">
              <div
                className={cn("absolute top-0 h-full rounded-sm", COLORS[s.name])}
                style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                title={`${s.name}: ${s.duration_ms}ms`}
              />
            </div>
            <div className="w-16 text-right tabular-nums text-muted-foreground">
              {s.duration_ms}ms
            </div>
          </div>
        );
      })}
      <div className="text-[11px] text-muted-foreground pt-1">
        Total: <span className="tabular-nums">{total}ms</span>
      </div>
    </div>
  );
}
