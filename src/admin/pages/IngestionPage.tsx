import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useIngestionRuns, useIngestionHealth } from "@/admin/hooks/useAdminData";
import { triggerReingest } from "@/admin/lib/mockData";
import { KpiCard } from "@/admin/components/KpiCard";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fmtDateTime, fmtInt, fmtMs } from "@/admin/lib/formatters";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { RefreshCw } from "lucide-react";

export default function IngestionPage() {
  const { data } = useIngestionRuns();
  const { data: health } = useIngestionHealth();
  const qc = useQueryClient();

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Ingestion</h1>
        <p className="text-sm text-muted-foreground">
          Recent transcript and document ingestion runs.
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <KpiCard label="Total runs" value={fmtInt(health?.total_runs ?? 0)} />
        <KpiCard label="Ok" value={fmtInt(health?.ok ?? 0)} tone="good" />
        <KpiCard label="Partial" value={fmtInt(health?.partial ?? 0)} tone="warn" />
        <KpiCard label="Failed" value={fmtInt(health?.failed ?? 0)} tone={health?.failed ? "bad" : "default"} />
        <KpiCard label="Chunks added" value={fmtInt(health?.total_chunks ?? 0)} />
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Runs</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Source</TableHead>
                <TableHead className="text-right">Chunks</TableHead>
                <TableHead className="text-right">Duration</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="text-xs">{fmtDateTime(r.created_at)}</TableCell>
                  <TableCell className="text-xs font-mono">{r.source}</TableCell>
                  <TableCell className="text-right tabular-nums">{fmtInt(r.chunks_added)}</TableCell>
                  <TableCell className="text-right tabular-nums text-xs">{fmtMs(r.duration_ms)}</TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        r.status === "ok" ? "secondary" : r.status === "partial" ? "outline" : "destructive"
                      }
                    >
                      {r.status}
                    </Badge>
                    {r.error_log && (
                      <div className="text-xs text-destructive mt-1">{r.error_log}</div>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={async () => {
                        await triggerReingest(r.source);
                        qc.invalidateQueries({ queryKey: ["admin", "ingestion"] });
                        qc.invalidateQueries({ queryKey: ["admin", "ingest-health"] });
                        toast.success(`Re-ingest queued`);
                      }}
                    >
                      <RefreshCw className="h-3 w-3" /> Re-ingest
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
