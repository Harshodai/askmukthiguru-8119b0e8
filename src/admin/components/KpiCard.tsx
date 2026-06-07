import { Card, CardContent } from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { ArrowDown, ArrowUp } from "lucide-react";

interface Props {
  label: string;
  value: string;
  hint?: string;
  tooltip?: string;
  delta?: number; // percent change vs prior period
  tone?: "default" | "good" | "warn" | "bad";
}

export function KpiCard({ label, value, hint, tooltip, delta, tone = "default" }: Props) {
  const toneClass =
    tone === "good"
      ? "text-emerald-600 dark:text-emerald-400"
      : tone === "warn"
        ? "text-amber-600 dark:text-amber-400"
        : tone === "bad"
          ? "text-destructive"
          : "text-foreground";

  const card = (
    <Card>
      <CardContent className="p-4">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          {label}
        </div>
        <div className={cn("mt-1.5 text-2xl font-semibold tabular-nums", toneClass)}>
          {value}
        </div>
        <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
          {delta != null && (
            <span
              className={cn(
                "inline-flex items-center gap-0.5",
                delta >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-destructive",
              )}
            >
              {delta >= 0 ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}
              {Math.abs(delta).toFixed(1)}%
            </span>
          )}
          {hint && <span>{hint}</span>}
        </div>
      </CardContent>
    </Card>
  );

  if (!tooltip) return card;

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div>{card}</div>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-xs">
          {tooltip}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
