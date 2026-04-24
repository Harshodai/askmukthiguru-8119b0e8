import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useIngestionRuns } from "@/admin/hooks/useAdminData";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fmtDateTime, fmtInt, fmtMs } from "@/admin/lib/formatters";

export default function IngestionPage() {
  const { data } = useIngestionRuns();

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Ingestion</h1>
        <p className="text-sm text-muted-foreground">
          Recent transcript and document ingestion runs.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Runs</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Source</TableHead>
                <TableHead className="text-right">Chunks</TableHead>
                <TableHead className="text-right">Duration</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="text-xs">{fmtDateTime(r.created_at)}</TableCell>
                  <TableCell className="text-xs font-mono">{r.source}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {fmtInt(r.chunks_added)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-xs">
                    {fmtMs(r.duration_ms)}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        r.status === "ok"
                          ? "secondary"
                          : r.status === "partial"
                            ? "outline"
                            : "destructive"
                      }
                    >
                      {r.status}
                    </Badge>
                    {r.error_log && (
                      <div className="text-xs text-destructive mt-1">{r.error_log}</div>
                    )}
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
