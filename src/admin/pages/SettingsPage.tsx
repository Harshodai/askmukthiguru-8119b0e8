import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useModelPricing,
  useQueries,
  useEvalRuns,
  useAlertRules,
} from "@/admin/hooks/useAdminData";
import { Download } from "lucide-react";
import { toast } from "sonner";

function downloadCsv(filename: string, rows: Array<Record<string, unknown>> | unknown[]) {
  rows = rows as Array<Record<string, unknown>>;
  if (!rows.length) {
    toast.error("Nothing to export");
    return;
  }
  const headers = Object.keys(rows[0]);
  const escape = (v: unknown) => {
    const s = v == null ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = [
    headers.join(","),
    ...rows.map((r) => headers.map((h) => escape(r[h])).join(",")),
  ].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
  toast.success(`Exported ${filename}`);
}

export default function SettingsPage() {
  const [retention, setRetention] = useState([90]);
  const [redactPii, setRedactPii] = useState(true);
  const { data: pricing } = useModelPricing();
  const { data: queries } = useQueries({ limit: 1000 });
  const { data: runs } = useEvalRuns();
  const { data: rules } = useAlertRules();

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Retention, redaction, and model cost configuration.
        </p>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Retention & privacy</CardTitle></CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div>
            <div className="flex justify-between mb-2">
              <span>Telemetry retention (days)</span>
              <span className="tabular-nums font-medium">{retention[0]}</span>
            </div>
            <Slider value={retention} onValueChange={setRetention} min={7} max={365} step={1} />
          </div>
          <div className="flex items-center justify-between">
            <span>PII redaction before persistence</span>
            <Switch checked={redactPii} onCheckedChange={setRedactPii} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Exports</CardTitle></CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              downloadCsv(
                "queries.csv",
                (queries ?? []).map((q) => ({
                  id: q.id,
                  created_at: q.created_at,
                  model: q.model,
                  prompt_tokens: q.prompt_tokens,
                  completion_tokens: q.completion_tokens,
                  cost: q.cost_estimate,
                  latency_ms: q.latency_ms,
                  status: q.status,
                  query_text: q.query_text,
                })),
              )
            }
          >
            <Download className="h-4 w-4" /> Queries CSV
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => downloadCsv("eval_runs.csv", runs?.map((r) => ({ id: r.id, ...r.summary, started_at: r.started_at })) ?? [])}
          >
            <Download className="h-4 w-4" /> Eval runs CSV
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => downloadCsv("alert_rules.csv", rules ?? [])}
          >
            <Download className="h-4 w-4" /> Alert rules CSV
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => downloadCsv("model_pricing.csv", pricing ?? [])}
          >
            <Download className="h-4 w-4" /> Model pricing CSV
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Model pricing (USD per 1k tokens)</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Model</TableHead>
                <TableHead className="text-right">Input</TableHead>
                <TableHead className="text-right">Output</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pricing?.map((p) => (
                <TableRow key={p.model}>
                  <TableCell className="font-mono text-xs">{p.model}</TableCell>
                  <TableCell className="text-right tabular-nums">${p.input_per_1k.toFixed(4)}</TableCell>
                  <TableCell className="text-right tabular-nums">${p.output_per_1k.toFixed(4)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
