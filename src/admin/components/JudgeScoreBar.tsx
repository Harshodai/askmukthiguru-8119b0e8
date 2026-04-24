interface Props {
  label: string;
  value: number; // 0..1
}

export function JudgeScoreBar({ label, value }: Props) {
  const pct = Math.round(value * 100);
  const tone =
    pct >= 80
      ? "bg-emerald-500"
      : pct >= 65
        ? "bg-primary"
        : pct >= 50
          ? "bg-amber-500"
          : "bg-destructive";
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-muted-foreground">{label}</span>
        <span className="tabular-nums font-medium">{pct}%</span>
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div className={`h-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
