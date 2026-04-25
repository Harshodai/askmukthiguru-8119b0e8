import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  current: number;
  prior: number | null;
  /** When true, lower is better (e.g. latency, hallucination). */
  inverse?: boolean;
  format?: (v: number) => string;
}

export function MetricDelta({ current, prior, inverse, format }: Props) {
  if (prior == null) return <span className="text-xs text-muted-foreground">—</span>;
  const diff = current - prior;
  if (Math.abs(diff) < 1e-6) {
    return (
      <span className="text-xs inline-flex items-center gap-0.5 text-muted-foreground">
        <Minus className="h-3 w-3" /> 0
      </span>
    );
  }
  const isImprovement = inverse ? diff < 0 : diff > 0;
  const Icon = diff > 0 ? ArrowUp : ArrowDown;
  return (
    <span
      className={cn(
        "text-xs inline-flex items-center gap-0.5",
        isImprovement ? "text-emerald-600 dark:text-emerald-400" : "text-destructive",
      )}
    >
      <Icon className="h-3 w-3" />
      {format ? format(Math.abs(diff)) : Math.abs(diff).toFixed(3)}
    </span>
  );
}
