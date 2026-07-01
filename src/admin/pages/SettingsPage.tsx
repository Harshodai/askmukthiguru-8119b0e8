import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import { useEffect, useState } from "react";
import { getGlobalSettings, updateGlobalSettings } from "@/admin/lib/api";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useQueries,
  useEvalRuns,
  useAlertRules,
} from "@/admin/hooks/useAdminData";
import { Download, Info } from "lucide-react";
import { toast } from "sonner";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const SARVAM_PRICING = [
  {
    model: "sarvam-30b",
    input: "₹2.5",
    cachedInput: "₹1.5",
    output: "₹10",
    unit: "per 1M tokens",
    tooltip: "Chat completion pricing from Sarvam API docs: input, cached input, and output are billed separately.",
  },
  {
    model: "sarvam-105b",
    input: "₹4",
    cachedInput: "₹2.5",
    output: "₹16",
    unit: "per 1M tokens",
    tooltip: "Higher-capability chat model. Use for complex reasoning and agentic workloads.",
  },
  {
    model: "mayura:v1",
    input: "₹20",
    cachedInput: "—",
    output: "—",
    unit: "per 10K characters",
    tooltip: "Translation is billed per character and rounded to the nearest character per request.",
  },
  {
    model: "saaras:v3",
    input: "₹30",
    cachedInput: "—",
    output: "—",
    unit: "per audio hour",
    tooltip: "Speech-to-text is billed per second of audio, shown here as the hourly equivalent.",
  },
  {
    model: "bulbul:v3",
    input: "₹30",
    cachedInput: "—",
    output: "—",
    unit: "per 10K characters",
    tooltip: "Text-to-speech beta pricing. Billed per character and rounded per request.",
  },
  {
    model: "document-digitization",
    input: "₹0.5",
    cachedInput: "—",
    output: "—",
    unit: "per page",
    tooltip: "Document digitization API price from Sarvam docs. Maximum page limits can apply by endpoint.",
  },
];

function downloadCsv(filename: string, rowsIn: Array<Record<string, unknown>> | unknown[]) {
  const rows = rowsIn as Array<Record<string, unknown>>;
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
    ...rows.map((r: Record<string, unknown>) => headers.map((h) => escape(r[h])).join(",")),
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
  const [allowedDomains, setAllowedDomains] = useState<string>("");
  const [isSaving, setIsSaving] = useState(false);
  const { data: queries } = useQueries({ limit: 1000 });
  const { data: runs } = useEvalRuns();
  const { data: rules } = useAlertRules();
  const pricingRows = SARVAM_PRICING;

  useEffect(() => {
    getGlobalSettings()
      .then((data) => {
        if (data && data.web_search_allowed_domains) {
          setAllowedDomains(data.web_search_allowed_domains.join(", "));
        }
      })
      .catch((err) => {
        console.error("Failed to load settings:", err);
      });
  }, []);

  const handleSaveDomains = async () => {
    setIsSaving(true);
    try {
      const domainsArray = allowedDomains
        .split(",")
        .map((d) => d.trim().toLowerCase())
        .filter((d) => d.length > 0);
      
      const res = await updateGlobalSettings({
        web_search_allowed_domains: domainsArray
      });
      
      if (res.status === "success") {
        setAllowedDomains(res.web_search_allowed_domains.join(", "));
        toast.success("Web search allowed domains saved successfully!");
      } else {
        toast.error("Failed to save allowed domains");
      }
    } catch (err) {
      console.error("Failed to save domains:", err);
      toast.error("Failed to save settings: " + (err as Error).message);
    } finally {
      setIsSaving(false);
    }
  };

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
        <CardHeader><CardTitle className="text-base">Web Search allowed domains</CardTitle></CardHeader>
        <CardContent className="space-y-4 text-sm">
          <p className="text-xs text-muted-foreground">
            Configure comma-separated domains allowed for DuckDuckGo/SearXNG web search fallbacks.
          </p>
          <div className="flex flex-col gap-2">
            <textarea
              className="min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              placeholder="ekam.org, theonenessmovement.org"
              value={allowedDomains}
              onChange={(e) => setAllowedDomains(e.target.value)}
            />
            <div className="flex justify-end">
              <Button size="sm" onClick={handleSaveDomains} disabled={isSaving}>
                {isSaving ? "Saving..." : "Save domains"}
              </Button>
            </div>
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
            onClick={() => downloadCsv("model_pricing.csv", pricingRows)}
          >
            <Download className="h-4 w-4" /> Model pricing CSV
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Sarvam pricing (INR)</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <TooltipProvider>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Service</TableHead>
                  <TableHead className="text-right">Input</TableHead>
                  <TableHead className="text-right">Cached input</TableHead>
                  <TableHead className="text-right">Output</TableHead>
                  <TableHead>Unit</TableHead>
                  <TableHead className="w-10"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pricingRows.map((p) => (
                  <TableRow key={p.model}>
                    <TableCell className="font-mono text-xs">{p.model}</TableCell>
                    <TableCell className="text-right tabular-nums">{p.input}</TableCell>
                    <TableCell className="text-right tabular-nums">{p.cachedInput}</TableCell>
                    <TableCell className="text-right tabular-nums">{p.output}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{p.unit}</TableCell>
                    <TableCell className="text-right">
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground">
                            <Info className="h-4 w-4" />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent className="max-w-72">
                          {p.tooltip}
                        </TooltipContent>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TooltipProvider>
        </CardContent>
      </Card>
    </div>
  );
}
