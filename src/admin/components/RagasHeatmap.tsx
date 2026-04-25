import { useMemo } from "react";
import { format } from "date-fns";
import { useRagasHeatmap } from "@/admin/hooks/useAdminData";
import { cn } from "@/lib/utils";

const METRICS = [
  { key: "faithfulness", label: "Faithfulness" },
  { key: "answer_relevancy", label: "Answer relevancy" },
  { key: "context_precision", label: "Context precision" },
  { key: "context_recall", label: "Context recall" },
] as const;

function colorFor(v: number) {
  if (v === 0) return "bg-muted";
  if (v >= 0.85) return "bg-emerald-500/80";
  if (v >= 0.75) return "bg-emerald-500/55";
  if (v >= 0.65) return "bg-amber-500/65";
  if (v >= 0.5) return "bg-orange-500/70";
  return "bg-destructive/80";
}

export function RagasHeatmap({ buckets = 8 }: { buckets?: number }) {
  const { data } = useRagasHeatmap(buckets);

  const grid = useMemo(() => {
    if (!data) return [];
    const byMetric = new Map<string, typeof data>();
    data.forEach((c) => {
      const arr = byMetric.get(c.metric) ?? [];
      arr.push(c);
      byMetric.set(c.metric, arr);
    });
    return METRICS.map((m) => ({
      label: m.label,
      cells: (byMetric.get(m.key) ?? []).sort(
        (a, b) => +new Date(a.bucket) - +new Date(b.bucket),
      ),
    }));
  }, [data]);

  const xLabels = grid[0]?.cells.map((c) => format(new Date(c.bucket), "MMM d")) ?? [];

  return (
    <div className="space-y-2">
      <div
        className="grid gap-1 text-[10px]"
        style={{ gridTemplateColumns: `120px repeat(${buckets}, 1fr)` }}
      >
        <div />
        {xLabels.map((l, i) => (
          <div key={i} className="text-center text-muted-foreground">
            {l}
          </div>
        ))}
        {grid.map((row) => (
          <>
            <div key={`l-${row.label}`} className="text-xs text-muted-foreground self-center">
              {row.label}
            </div>
            {row.cells.map((c) => (
              <div
                key={`${row.label}-${c.bucket}`}
                className={cn(
                  "h-8 rounded text-[10px] flex items-center justify-center font-medium text-foreground/80",
                  colorFor(c.value),
                )}
                title={`${row.label} · ${format(new Date(c.bucket), "MMM d HH:mm")}: ${(
                  c.value * 100
                ).toFixed(1)}%`}
              >
                {c.value > 0 ? (c.value * 100).toFixed(0) : ""}
              </div>
            ))}
          </>
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
