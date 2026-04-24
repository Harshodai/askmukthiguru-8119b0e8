import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { KpiCard } from "@/admin/components/KpiCard";
import { useRetrievalHealth } from "@/admin/hooks/useAdminData";
import { fmtInt, fmtPct } from "@/admin/lib/formatters";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function RetrievalPage() {
  const { data, isLoading } = useRetrievalHealth();

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
        <CardHeader>
          <CardTitle className="text-base">Source documents</CardTitle>
        </CardHeader>
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
    </div>
  );
}
