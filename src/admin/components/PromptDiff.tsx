import { useMemo } from "react";
import { cn } from "@/lib/utils";

interface Props {
  a: string;
  b: string;
}

type LineOp = { type: "same" | "add" | "del"; text: string };

// Simple LCS-based line diff (O(n*m) — fine for prompt-sized text).
function diffLines(left: string[], right: string[]): { left: LineOp[]; right: LineOp[] } {
  const m = left.length;
  const n = right.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      if (left[i] === right[j]) dp[i][j] = dp[i + 1][j + 1] + 1;
      else dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const leftOut: LineOp[] = [];
  const rightOut: LineOp[] = [];
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    if (left[i] === right[j]) {
      leftOut.push({ type: "same", text: left[i] });
      rightOut.push({ type: "same", text: right[j] });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      leftOut.push({ type: "del", text: left[i] });
      rightOut.push({ type: "same", text: "" });
      i++;
    } else {
      leftOut.push({ type: "same", text: "" });
      rightOut.push({ type: "add", text: right[j] });
      j++;
    }
  }
  while (i < m) {
    leftOut.push({ type: "del", text: left[i++] });
    rightOut.push({ type: "same", text: "" });
  }
  while (j < n) {
    leftOut.push({ type: "same", text: "" });
    rightOut.push({ type: "add", text: right[j++] });
  }
  return { left: leftOut, right: rightOut };
}

function Side({ ops, side }: { ops: LineOp[]; side: "a" | "b" }) {
  return (
    <pre className="text-xs bg-muted/40 rounded-md overflow-x-auto p-2">
      {ops.map((o, i) => (
        <div
          key={i}
          className={cn(
            "px-2 leading-5 whitespace-pre-wrap",
            o.type === "del" && side === "a" && "bg-destructive/15 text-destructive-foreground",
            o.type === "add" && side === "b" && "bg-emerald-500/15",
            o.type === "same" && o.text === "" && "h-5",
          )}
        >
          {o.text || "\u00A0"}
        </div>
      ))}
    </pre>
  );
}

export function PromptDiff({ a, b }: Props) {
  const { left, right } = useMemo(
    () => diffLines(a.split("\n"), b.split("\n")),
    [a, b],
  );
  return (
    <div className="grid grid-cols-2 gap-3">
      <Side ops={left} side="a" />
      <Side ops={right} side="b" />
    </div>
  );
}
