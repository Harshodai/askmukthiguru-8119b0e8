import { useMemo } from "react";
import { cn } from "@/lib/utils";

interface Props {
  a?: string | null;
  b?: string | null;
}

type LineOp = { type: "same" | "add" | "del"; text: string };

// Simple LCS-based line diff (O(n*m) with memory guard for large inputs).
function diffLines(left: string[] = [], right: string[] = []): { left: LineOp[]; right: LineOp[] } {
  const safeLeft = Array.isArray(left) ? left : [];
  const safeRight = Array.isArray(right) ? right : [];
  const m = safeLeft.length;
  const n = safeRight.length;

  // Protect against pathological inputs that would freeze browser memory
  if (m * n > 500_000) {
    return {
      left: safeLeft.map((t) => ({ type: "same", text: t })),
      right: safeRight.map((t) => ({ type: "same", text: t })),
    };
  }

  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      if (safeLeft[i] === safeRight[j]) dp[i][j] = dp[i + 1][j + 1] + 1;
      else dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const leftOut: LineOp[] = [];
  const rightOut: LineOp[] = [];
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    if (safeLeft[i] === safeRight[j]) {
      leftOut.push({ type: "same", text: safeLeft[i] });
      rightOut.push({ type: "same", text: safeRight[j] });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      leftOut.push({ type: "del", text: safeLeft[i] });
      rightOut.push({ type: "same", text: "" });
      i++;
    } else {
      leftOut.push({ type: "same", text: "" });
      rightOut.push({ type: "add", text: safeRight[j] });
      j++;
    }
  }
  while (i < m) {
    leftOut.push({ type: "del", text: safeLeft[i++] });
    rightOut.push({ type: "same", text: "" });
  }
  while (j < n) {
    leftOut.push({ type: "same", text: "" });
    rightOut.push({ type: "add", text: safeRight[j++] });
  }
  return { left: leftOut, right: rightOut };
}

function Side({ ops, side }: { ops?: LineOp[]; side: "a" | "b" }) {
  const safeOps = Array.isArray(ops) ? ops : [];
  return (
    <pre className="text-xs bg-muted/40 rounded-md overflow-x-auto p-2">
      {safeOps.map((o, i) => (
        <div
          key={i}
          className={cn(
            "px-2 leading-5 whitespace-pre-wrap",
            o?.type === "del" && side === "a" && "bg-destructive/15 text-destructive-foreground",
            o?.type === "add" && side === "b" && "bg-emerald-500/15",
            o?.type === "same" && o?.text === "" && "h-5",
          )}
        >
          {o?.text || "\u00A0"}
        </div>
      ))}
    </pre>
  );
}

export function PromptDiff({ a, b }: Props) {
  const safeA = typeof a === "string" ? a : String(a ?? "");
  const safeB = typeof b === "string" ? b : String(b ?? "");
  const { left, right } = useMemo(
    () => diffLines(safeA.split("\n"), safeB.split("\n")),
    [safeA, safeB],
  );
  return (
    <div className="grid grid-cols-2 gap-3">
      <Side ops={left} side="a" />
      <Side ops={right} side="b" />
    </div>
  );
}
