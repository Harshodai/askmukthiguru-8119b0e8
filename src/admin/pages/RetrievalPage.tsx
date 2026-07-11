import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { KpiCard } from "@/admin/components/KpiCard";
import {
  useRetrievalHealth,
  useEmptyRetrievals,
  useDeadDocs,
  useSimilarityTrend,
} from "@/admin/hooks/useAdminData";
import { fmtInt, fmtPct, fmtDateTime, truncate } from "@/admin/lib/formatters";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TimeseriesChart } from "@/admin/components/TimeseriesChart";
import { Link } from "react-router-dom";
import { EmptyState } from "@/admin/components/EmptyState";
import { Badge } from "@/components/ui/badge";
import { AlertCircle, Server, Info } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";

export default function RetrievalPage() {
  const { data, isLoading, error } = useRetrievalHealth();
  const { data: empties } = useEmptyRetrievals();
  const { data: dead } = useDeadDocs();
  const { data: sim } = useSimilarityTrend(14);

  const backendDown = !!error;

  const simTs = sim?.map((p) => ({ bucket: p.bucket, value: p.avg_top_score })) ?? [];

  if (backendDown) {
    return (
      <div className="space-y-4">
        <div>
          <h1 className="text-2xl font-semibold">Retrieval health</h1>
          <p className="text-sm text-muted-foreground">
            Vector-search quality and per-source contribution.
          </p>
        </div>
        <Card className="border-destructive/30">
          <CardContent className="flex flex-col items-center justify-center py-16 gap-4 text-center">
            <Server className="w-10 h-10 text-muted-foreground/60" />
            <div>
              <h3 className="text-lg font-medium flex items-center gap-2 justify-center">
                <AlertCircle className="w-5 h-5 text-destructive" />
                Backend unavailable
              </h3>
              <p className="text-sm text-muted-foreground mt-1 max-w-md">
                Could not connect to the backend API. The retrieval health data requires a running backend.
                Ensure the backend container is healthy and <code className="text-xs bg-muted px-1 py-0.5 rounded">VITE_BACKEND_URL</code> is configured.
              </p>
            </div>
            <Button variant="outline" onClick={() => window.location.reload()}>
              Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold">Retrieval health</h1>
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <button className="text-muted-foreground hover:text-foreground">
                  <Info className="h-4 w-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs text-xs p-2">
                Analyze vector-search performance. Hit rate measures how often the search returned document chunks. Average top score measures the semantic similarity of matches. A low hit rate indicates that you should upload more relevant context in the Ingestion tab.
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        <p className="text-sm text-muted-foreground">
          Vector-search quality and per-source contribution.
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard
          label="Retrievals"
          value={isLoading ? "…" : fmtInt(data?.total_retrievals ?? 0)}
          tooltip="Total number of vector search operations performed in the selected time window."
        />
        <KpiCard
          label="Hit rate"
          value={isLoading ? "…" : fmtPct(data?.hit_rate ?? 0)}
          tone={(data?.hit_rate ?? 0) < 0.8 ? "warn" : "good"}
          tooltip="Percentage of queries that returned at least one retrieved document. Below 80% suggests coverage gaps in the knowledge base."
        />
        <KpiCard
          label="Empty retrievals"
          value={isLoading ? "…" : fmtInt(data?.empty_retrievals ?? 0)}
          tone={(data?.empty_retrievals ?? 0) > 0 ? "warn" : "default"}
          tooltip="Number of queries where vector search returned zero results. These queries fall back to generic responses."
        />
        <KpiCard
          label="Avg top score"
          value={isLoading ? "…" : (data?.avg_top_score ?? 0).toFixed(3)}
          tooltip="Average cosine similarity score of the top retrieved document. Higher scores (closer to 1.0) indicate better semantic matches."
        />
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Avg top similarity score</CardTitle></CardHeader>
        <CardContent>
          <TimeseriesChart data={simTs} formatter={(v) => (typeof v === 'number' ? v.toFixed(3) : '')} />
        </CardContent>
      </Card>

      <Tabs defaultValue="sources">
        <TabsList>
          <TabsTrigger value="sources">Source contribution</TabsTrigger>
          <TabsTrigger value="empty">Empty retrievals</TabsTrigger>
          <TabsTrigger value="dead">Dead docs</TabsTrigger>
        </TabsList>

        <TabsContent value="sources">
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Source</TableHead>
                    <TableHead className="text-right">Times retrieved</TableHead>
                    <TableHead className="text-right">Avg faithfulness contributed</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data?.sources?.length ? (
                    data.sources.map((s: { source: string; count: number; avgFaith: number }) => (
                      <TableRow key={s.source}>
                        <TableCell className="font-mono text-xs">{s.source}</TableCell>
                        <TableCell className="text-right tabular-nums">{fmtInt(s.count)}</TableCell>
                        <TableCell className="text-right tabular-nums">{fmtPct(s.avgFaith)}</TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell colSpan={3} className="text-center text-muted-foreground py-6">
                        No retrieval data available yet
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="empty">
          <Card>
            <CardContent className="p-3 space-y-2">
              {!empties?.length ? (
                <EmptyState title="No empty retrievals" />
              ) : (
                empties.map((e: { query_id: string; top_score: number; query_text: string; created_at: string }) => (
                  <Link
                    key={e.query_id}
                    to={`/admin/queries?trace=${e.query_id}`}
                    className="block border border-border rounded-md p-3 text-sm hover:bg-muted/40"
                  >
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">top {typeof e.top_score === 'number' ? e.top_score.toFixed(3) : 'N/A'}</Badge>
                      <span className="flex-1 truncate">{truncate(e.query_text, 80)}</span>
                      <span className="text-xs text-muted-foreground">{fmtDateTime(e.created_at)}</span>
                    </div>
                  </Link>
                ))
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="dead">
          <Card>
            <CardHeader><CardTitle className="text-base">Sources never retrieved in window</CardTitle></CardHeader>
            <CardContent className="space-y-1.5">
              {!dead?.length ? (
                <EmptyState title="Every source was retrieved at least once" />
              ) : (
                dead.map((d: { source: string }) => (
                  <div key={d.source} className="text-sm font-mono text-muted-foreground">
                    {d.source}
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
