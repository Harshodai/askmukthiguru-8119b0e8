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

export default function RetrievalPage() {
  const { data, isLoading } = useRetrievalHealth();
  const { data: empties } = useEmptyRetrievals();
  const { data: dead } = useDeadDocs();
  const { data: sim } = useSimilarityTrend(14);

  const simTs = sim?.map((p) => ({ bucket: p.bucket, value: p.avg_top_score })) ?? [];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Retrieval health</h1>
        <p className="text-sm text-muted-foreground">
          Vector-search quality and per-source contribution.
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="Retrievals" value={isLoading ? "…" : fmtInt(data?.total_retrievals ?? 0)} />
        <KpiCard
          label="Hit rate"
          value={isLoading ? "…" : fmtPct(data?.hit_rate ?? 0)}
          tone={(data?.hit_rate ?? 0) < 0.8 ? "warn" : "good"}
        />
        <KpiCard
          label="Empty retrievals"
          value={isLoading ? "…" : fmtInt(data?.empty_retrievals ?? 0)}
          tone={(data?.empty_retrievals ?? 0) > 0 ? "warn" : "default"}
        />
        <KpiCard label="Avg top score" value={isLoading ? "…" : (data?.avg_top_score ?? 0).toFixed(3)} />
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Avg top similarity score</CardTitle></CardHeader>
        <CardContent>
          <TimeseriesChart data={simTs} formatter={(v) => v.toFixed(3)} />
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
                  {data?.sources.map((s) => (
                    <TableRow key={s.source}>
                      <TableCell className="font-mono text-xs">{s.source}</TableCell>
                      <TableCell className="text-right tabular-nums">{fmtInt(s.count)}</TableCell>
                      <TableCell className="text-right tabular-nums">{fmtPct(s.avgFaith)}</TableCell>
                    </TableRow>
                  ))}
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
                empties.map((e) => (
                  <Link
                    key={e.query_id}
                    to={`/admin/queries?trace=${e.query_id}`}
                    className="block border border-border rounded-md p-3 text-sm hover:bg-muted/40"
                  >
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">top {e.top_score.toFixed(3)}</Badge>
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
                dead.map((d) => (
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
