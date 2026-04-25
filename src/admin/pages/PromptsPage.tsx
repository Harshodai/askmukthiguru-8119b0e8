import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { usePromptVersions, usePromptMetrics } from "@/admin/hooks/useAdminData";
import { activatePromptVersion } from "@/admin/lib/mockData";
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
  const { data: prompts } = usePromptVersions();
  const { data: metrics } = usePromptMetrics();
  const qc = useQueryClient();
  const [a, setA] = useState<string | null>(null);
  const [b, setB] = useState<string | null>(null);

  const pa = prompts?.find((p) => p.id === a);
  const pb = prompts?.find((p) => p.id === b);

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
          {prompts?.map((p) => (
            <div
              key={p.id}
              className="flex items-center gap-3 border border-border rounded-md p-3 text-sm"
            >
              <div className="flex-1">
                <div className="font-medium">
                  {p.name} <Badge variant="outline">v{p.version}</Badge>
                  {p.active && <Badge className="ml-1">active</Badge>}
                </div>
                <div className="text-xs text-muted-foreground">{fmtDate(p.created_at)}</div>
              </div>
              <Button
                size="sm"
                variant="outline"
                disabled={p.active}
                onClick={async () => {
                  await activatePromptVersion(p.id);
                  qc.invalidateQueries({ queryKey: ["admin", "prompts"] });
                  qc.invalidateQueries({ queryKey: ["admin", "prompt-metrics"] });
                  toast.success(`${p.name} v${p.version} activated`);
                }}
              >
                {p.active ? "Active" : "Activate"}
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Per-version metrics</CardTitle></CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={metrics ?? []}>
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
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Side-by-side diff</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Select value={a ?? ""} onValueChange={setA}>
              <SelectTrigger><SelectValue placeholder="Select version A" /></SelectTrigger>
              <SelectContent>
                {prompts?.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.name} v{p.version}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={b ?? ""} onValueChange={setB}>
              <SelectTrigger><SelectValue placeholder="Select version B" /></SelectTrigger>
              <SelectContent>
                {prompts?.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.name} v{p.version}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {pa && pb && <PromptDiff a={pa.content} b={pb.content} />}
        </CardContent>
      </Card>
    </div>
  );
}
