import { useMemo, Fragment } from "react";
import { format } from "date-fns";
import { useRagasHeatmap } from "@/admin/hooks/useAdminData";
import { cn } from "@/lib/utils";

const METRICS = [
  { key: "faithfulness", label: "Faithfulness" },
  { key: "answer_relevancy", label: "Answer relevancy" },
  { key: "context_precision", label: "Context precision" },
  { key: "context_recall", label: "Context recall" },
] as const;

function colorFor(v?: number | null) {
  if (v == null || typeof v !== "number" || Number.isNaN(v) || v <= 0) return "bg-muted";
  if (v >= 0.85) return "bg-emerald-500/80";
  if (v >= 0.75) return "bg-emerald-500/55";
  if (v >= 0.65) return "bg-amber-500/65";
  if (v >= 0.5) return "bg-orange-500/70";
  return "bg-destructive/80";
}

function safeFormatDate(dStr?: string | null, fmt = "MMM d"): string {
  if (!dStr) return "—";
  const d = new Date(dStr);
  if (Number.isNaN(d.getTime())) return "—";
  try {
    return format(d, fmt);
  } catch {
    return "—";
  }
}

export function RagasHeatmap({ buckets = 8 }: { buckets?: number }) {
  const { data, isLoading, isError, error } = useRagasHeatmap(buckets);

  const grid = useMemo(() => {
    if (!data || !Array.isArray(data)) return [];
    const byMetric = new Map<string, typeof data>();
    data.forEach((c) => {
      if (!c || !c.metric) return;
      const arr = byMetric.get(c.metric) ?? [];
      arr.push(c);
      byMetric.set(c.metric, arr);
    });
    return METRICS.map((m) => ({
      label: m.label,
      key: m.key,
      cells: (byMetric.get(m.key) ?? []).sort((a, b) => {
        const tA = a?.bucket ? new Date(a.bucket).getTime() : 0;
        const tB = b?.bucket ? new Date(b.bucket).getTime() : 0;
        return (Number.isNaN(tA) ? 0 : tA) - (Number.isNaN(tB) ? 0 : tB);
      }),
    }));
  }, [data]);

  const xLabels = useMemo(() => {
    const firstCells = grid[0]?.cells ?? [];
    return firstCells.map((c) => safeFormatDate(c?.bucket, "MMM d"));
  }, [grid]);

  if (isLoading) {
    return <div className="text-xs text-muted-foreground py-6 text-center">Loading heatmap data…</div>;
  }

  if (isError) {
    return (
      <div className="text-xs text-destructive py-4 text-center">
        Failed to load heatmap: {(error as Error)?.message || "Unknown error"}
      </div>
    );
  }

  if (!grid.length || grid.every((r) => !r.cells.length)) {
    return <div className="text-xs text-muted-foreground py-6 text-center">No judge heatmap data recorded yet.</div>;
  }

  return (
    <div className="space-y-2">
      <div
        className="grid gap-1 text-[10px]"
        style={{ gridTemplateColumns: `120px repeat(${Math.max(1, xLabels.length || buckets)}, 1fr)` }}
      >
        <div />
        {xLabels.map((l, i) => (
          <div key={`xlabel-${i}`} className="text-center text-muted-foreground">
            {l}
          </div>
        ))}
        {grid.map((row) => (
          <Fragment key={`row-${row.key}`}>
            <div className="text-xs text-muted-foreground self-center">
              {row.label}
            </div>
            {(row.cells ?? []).map((c, cIdx) => {
              const val = typeof c?.value === "number" && !Number.isNaN(c.value) ? c.value : 0;
              const dateLabel = safeFormatDate(c?.bucket, "MMM d HH:mm");
              return (
                <div
                  key={`${row.key}-${c?.bucket ?? cIdx}`}
                  className={cn(
                    "h-8 rounded text-[10px] flex items-center justify-center font-medium text-foreground/80",
                    colorFor(val),
                  )}
                  title={`${row.label} · ${dateLabel}: ${(val * 100).toFixed(1)}%`}
                >
                  {val > 0 ? (val * 100).toFixed(0) : ""}
                </div>
              );
            })}
          </Fragment>
        ))}
      </div>
      <div className="flex items-center gap-3 text-[10px] text-muted-foreground pt-1">
        <span>Lower</span>
        <div className="flex gap-0.5">
          {["bg-destructive/80", "bg-orange-500/70", "bg-amber-500/65", "bg-emerald-500/55", "bg-emerald-500/80"].map(
            (c, i) => (
              <div key={i} className={cn("h-3 w-6 rounded-sm", c)} />
            ),
          )}
        </div>
        <span>Higher</span>
      </div>
    </div>
  );
}
