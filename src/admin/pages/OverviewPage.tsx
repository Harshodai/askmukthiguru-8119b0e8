import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { KpiCard } from "@/admin/components/KpiCard";
import { TimeseriesChart } from "@/admin/components/TimeseriesChart";
import { Info } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  useKpis,
  useTimeseries,
  useQueries,
  useRetrievalHealth,
  useTopFailures,
} from "@/admin/hooks/useAdminData";
import {
  fmtInt,
  fmtMs,
  fmtPct,
  fmtInr,
  fmtUsd,
  truncate,
  fmtDateTime,
} from "@/admin/lib/formatters";
import { AskDataPanel } from "@/admin/components/AskDataPanel";
import { LiveFeed } from "@/admin/components/LiveFeed";
import { SeedDemoButton } from "@/admin/components/SeedDemoButton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";

export default function OverviewPage() {
  const { data: kpis, isLoading } = useKpis();
  const { data: queriesTs } = useTimeseries("queries", 24);
  const { data: latencyTs } = useTimeseries("p95_latency_ms", 24);
  const { data: hallucTs } = useTimeseries("hallucination_rate", 24);
  const { data: costTs } = useTimeseries("cost_usd", 24);
  const { data: recentQueries } = useQueries({ limit: 10 });
  const { data: retr } = useRetrievalHealth();
  const { data: failures } = useTopFailures(6);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold">Overview</h1>
            <TooltipProvider delayDuration={200}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button className="text-muted-foreground hover:text-foreground">
                    <Info className="h-4 w-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent className="max-w-xs text-xs p-2">
                  Welcome to the AskMukthiGuru Admin Console. Use the date preset buttons in the header to filter all analytics charts. The "Ask the data" panel below allows you to query analytics metrics using natural language.
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
          <p className="text-sm text-muted-foreground">
            Health & usage of the AskMukthiGuru assistant.
          </p>
        </div>
        <SeedDemoButton />
      </div>


      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
        <KpiCard label="Queries" value={isLoading ? "…" : fmtInt(kpis?.total_queries ?? 0)} tooltip="Total number of chat queries processed across all channels." />
        <KpiCard label="Total Seekers" value={isLoading ? "…" : fmtInt(kpis?.total_seekers ?? 0)} tone="good" tooltip="Unique individuals who have asked at least one question." />
        <KpiCard label="p50 latency" value={isLoading ? "…" : fmtMs(kpis?.p50_latency_ms ?? 0)} tooltip="Median end-to-end response time for the RAG pipeline." />
        <KpiCard
          label="p95 latency"
          value={isLoading ? "…" : fmtMs(kpis?.p95_latency_ms ?? 0)}
          tone={(kpis?.p95_latency_ms ?? 0) > 5000 ? "warn" : "default"}
          tooltip="95th percentile latency — tail-end worst-case response times."
        />
        <KpiCard
          label="Hallucination rate"
          value={isLoading ? "…" : fmtPct(kpis?.hallucination_rate ?? 0)}
          tone={(kpis?.hallucination_rate ?? 0) > 0.15 ? "bad" : "default"}
          tooltip="Percentage of responses flagged as hallucinated by Self-RAG verification."
        />
        <KpiCard
          label="Serene Mind triggered"
          value={isLoading ? "…" : fmtPct(kpis?.serene_mind_trigger_rate ?? 0)}
          tooltip="Percentage of queries that triggered the Serene Mind distress-detection meditation flow."
        />
        <KpiCard
          label="Thumbs up rate"
          value={isLoading ? "…" : fmtPct(kpis?.thumbs_up_rate ?? 0)}
          tone="good"
          tooltip="Positive feedback (thumbs up) as a fraction of rated responses."
        />
        <KpiCard
          label="Estimated cost"
          value={isLoading ? "…" : fmtInr(kpis?.estimated_cost_inr ?? kpis?.estimated_cost_usd ?? 0)}
          tooltip="Approximate total inference cost for processed queries."
        />
        <KpiCard
          label="Error rate"
          value={isLoading ? "…" : fmtPct(kpis?.error_rate ?? 0)}
          tone={(kpis?.error_rate ?? 0) > 0.02 ? "bad" : "default"}
          tooltip="Percentage of requests that failed (circuit breaker, timeout, or exception)."
        />
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <Card>
          <CardHeader><CardTitle className="text-base">Query volume</CardTitle></CardHeader>
          <CardContent><TimeseriesChart data={queriesTs} /></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">p95 latency</CardTitle></CardHeader>
          <CardContent><TimeseriesChart data={latencyTs} formatter={fmtMs} /></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Hallucination rate</CardTitle></CardHeader>
          <CardContent>
            <TimeseriesChart
              data={hallucTs}
              formatter={(v) => fmtPct(v)}
              color="hsl(var(--destructive))"
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Cost</CardTitle></CardHeader>
          <CardContent>
            <TimeseriesChart data={costTs} formatter={fmtUsd} color="hsl(var(--secondary))" />
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="recent">
        <TabsList>
          <TabsTrigger value="recent">Recent queries</TabsTrigger>
          <TabsTrigger value="sources">Top sources</TabsTrigger>
          <TabsTrigger value="failures">Top failures</TabsTrigger>
          <TabsTrigger value="live">Live feed</TabsTrigger>
        </TabsList>

        <TabsContent value="recent" className="grid md:grid-cols-3 gap-4">
          <Card className="md:col-span-2">
            <CardHeader><CardTitle className="text-base">Recent queries</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {recentQueries?.map((q) => (
                <Link
                  key={q.id}
                  to={`/admin/queries?trace=${q.id}`}
                  className="flex items-center justify-between gap-3 text-sm border-b border-border last:border-0 pb-2 hover:bg-muted/40 -mx-2 px-2 rounded-sm"
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate">{truncate(q.query_text, 70)}</div>
                    <div className="text-xs text-muted-foreground">
                      {fmtDateTime(q.created_at)} · {q.model?.split("/").pop() || "unknown"}
                    </div>
                  </div>
                  <div className="text-xs tabular-nums text-muted-foreground">
                    {fmtMs(q.latency_ms)}
                  </div>
                </Link>
              ))}
            </CardContent>
          </Card>
          <AskDataPanel kpiContext={kpis ? [
            `Total queries: ${kpis.total_queries ?? 0}`,
            `Total seekers: ${kpis.total_seekers ?? 0}`,
            `p50 latency: ${kpis.p50_latency_ms ?? 0}ms`,
            `p95 latency: ${kpis.p95_latency_ms ?? 0}ms`,
            `Hallucination rate: ${((kpis.hallucination_rate ?? 0) * 100).toFixed(1)}%`,
            `Serene Mind trigger rate: ${((kpis.serene_mind_trigger_rate ?? 0) * 100).toFixed(1)}%`,
            `Thumbs up rate: ${((kpis.thumbs_up_rate ?? 0) * 100).toFixed(1)}%`,
            `Estimated cost: ₹${(kpis.estimated_cost_inr ?? kpis.estimated_cost_usd ?? 0).toFixed(4)} INR`,
            `Error rate: ${((kpis.error_rate ?? 0) * 100).toFixed(2)}%`,
          ].join('\n') : undefined} />
        </TabsContent>

        <TabsContent value="sources">
          <Card>
            <CardHeader><CardTitle className="text-base">Top retrieved sources</CardTitle></CardHeader>
            <CardContent className="space-y-1.5">
              {retr?.sources ? retr.sources.slice(0, 10).map((s: { source: string; count: number; avgFaith: number }) => (
                <div key={s.source} className="flex items-center justify-between text-sm border-b border-border/40 pb-1.5 last:border-0">
                  <span className="font-mono text-xs truncate flex-1">{s.source}</span>
                  <span className="tabular-nums text-xs text-muted-foreground w-20 text-right">{fmtInt(s.count)}</span>
                  <span className="tabular-nums text-xs w-20 text-right">{fmtPct(s.avgFaith)}</span>
                </div>
              )) : (
                <div className="text-xs text-muted-foreground py-4 text-center">No source data available</div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="failures">
          <Card>
            <CardHeader><CardTitle className="text-base">Lowest-faithfulness responses</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {failures?.map((f) => (
                <Link
                  key={f.query_id}
                  to={`/admin/queries?trace=${f.query_id}`}
                  className="block border border-border rounded-md p-3 text-sm hover:bg-muted/40"
                >
                  <div className="flex items-center gap-2">
                    <Badge variant="destructive">{fmtPct(f.faithfulness)}</Badge>
                    <span className="truncate flex-1">{truncate(f.query_text, 80)}</span>
                    <span className="text-xs text-muted-foreground">{fmtDateTime(f.created_at)}</span>
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">{f.reason}</div>
                </Link>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="live">
          <LiveFeed />
        </TabsContent>
      </Tabs>
    </div>
  );
}
