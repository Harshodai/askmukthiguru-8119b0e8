import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { usePromptVersions, usePromptMetrics } from "@/admin/hooks/useAdminData";
import { activatePromptVersion } from "@/admin/lib/api";
import { useQueryClient } from "@tanstack/react-query";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { fmtDate } from "@/admin/lib/formatters";
import { PromptDiff } from "@/admin/components/PromptDiff";
import { EmptyState } from "@/admin/components/EmptyState";
import { AlertCircle, RefreshCw, Loader2 } from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";

export default function PromptsPage() {
  const {
    data: prompts,
    isLoading: promptsLoading,
    isError: promptsError,
    refetch: refetchPrompts,
  } = usePromptVersions();
  const {
    data: metrics,
    isLoading: metricsLoading,
    isError: metricsError,
    refetch: refetchMetrics,
  } = usePromptMetrics();
  const qc = useQueryClient();
  const [a, setA] = useState<string | null>(null);
  const [b, setB] = useState<string | null>(null);
  const [activatingId, setActivatingId] = useState<string | null>(null);

  const promptsList = prompts ?? [];
  const metricsList = metrics ?? [];

  const pa = promptsList.find((p) => p.id === a);
  const pb = promptsList.find((p) => p.id === b);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Prompts</h1>
        <p className="text-sm text-muted-foreground">
          Versioned prompt registry with activation, side-by-side diff, and metric comparison.
        </p>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Versions</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {promptsLoading ? (
            <div className="py-8 flex items-center justify-center text-sm text-muted-foreground gap-2">
              <RefreshCw className="w-4 h-4 animate-spin" />
              Loading prompt versions…
            </div>
          ) : promptsError ? (
            <div className="py-8 flex flex-col items-center justify-center gap-2 text-sm text-destructive">
              <AlertCircle className="w-6 h-6" />
              <p>Failed to load prompt versions</p>
              <Button variant="outline" size="sm" onClick={() => void refetchPrompts()}>
                Retry
              </Button>
            </div>
          ) : promptsList.length === 0 ? (
            <EmptyState title="No prompt versions found" />
          ) : (
            promptsList.map((p) => (
              <div
                key={p.id}
                className="flex items-center gap-3 border border-border rounded-md p-3 text-sm"
              >
                <div className="flex-1">
                  <div className="font-medium flex items-center gap-1.5">
                    <span>{p.name ?? "Prompt"}</span>
                    <Badge variant="outline">v{p.version ?? "?"}</Badge>
                    {p.active && <Badge className="ml-1">active</Badge>}
                  </div>
                  <div className="text-xs text-muted-foreground">{fmtDate(p.created_at)}</div>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={p.active || activatingId === p.id}
                  onClick={async () => {
                    setActivatingId(p.id);
                    try {
                      await activatePromptVersion(p.id);
                      qc.invalidateQueries({ queryKey: ["admin", "prompts"] });
                      qc.invalidateQueries({ queryKey: ["admin", "prompt-metrics"] });
                      toast.success(`${p.name ?? "Prompt"} v${p.version ?? ""} activated`);
                    } catch (err) {
                      toast.error(err instanceof Error ? err.message : "Failed to activate prompt");
                    } finally {
                      setActivatingId(null);
                    }
                  }}
                >
                  {activatingId === p.id ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : p.active ? (
                    "Active"
                  ) : (
                    "Activate"
                  )}
                </Button>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Per-version metrics</CardTitle></CardHeader>
        <CardContent>
          {metricsLoading ? (
            <div className="h-[260px] flex items-center justify-center text-sm text-muted-foreground gap-2">
              <RefreshCw className="w-4 h-4 animate-spin" />
              Loading metrics…
            </div>
          ) : metricsError ? (
            <div className="h-[260px] flex flex-col items-center justify-center gap-2 text-sm text-destructive">
              <AlertCircle className="w-6 h-6" />
              <p>Failed to load per-version metrics</p>
              <Button variant="outline" size="sm" onClick={() => void refetchMetrics()}>
                Retry
              </Button>
            </div>
          ) : metricsList.length === 0 ? (
            <EmptyState title="No per-version metrics available" />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={metricsList}>
                <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" />
                <XAxis dataKey="label" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} />
                <YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} domain={[0, 1]} />
                <Tooltip
                  contentStyle={{
                    background: "hsl(var(--popover))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="faithfulness" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                <Bar dataKey="answer_relevancy" fill="hsl(var(--secondary))" radius={[4, 4, 0, 0]} />
                <Bar dataKey="hallucination_rate" fill="hsl(var(--destructive))" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Side-by-side diff</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Select value={a ?? ""} onValueChange={setA}>
              <SelectTrigger><SelectValue placeholder="Select version A" /></SelectTrigger>
              <SelectContent>
                {promptsList.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.name ?? "Prompt"} v{p.version ?? "?"}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={b ?? ""} onValueChange={setB}>
              <SelectTrigger><SelectValue placeholder="Select version B" /></SelectTrigger>
              <SelectContent>
                {promptsList.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.name ?? "Prompt"} v{p.version ?? "?"}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {pa && pb ? (
            <PromptDiff a={pa.content ?? ""} b={pb.content ?? ""} />
          ) : (
            <p className="text-xs text-muted-foreground italic py-2">
              Select two versions above to view side-by-side diff.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

