import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useEvalRuns, useGoldenQuestions } from "@/admin/hooks/useAdminData";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ArrowDown, ArrowUp } from "lucide-react";
import { fmtDateTime, fmtPct } from "@/admin/lib/formatters";

export default function EvalsPage() {
  const { data: runs } = useEvalRuns();
  const { data: golden } = useGoldenQuestions();

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Evals</h1>
        <p className="text-sm text-muted-foreground">
          Golden dataset and regression history. See <code>docs/admin/evals.md</code>.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Run history</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Triggered by</TableHead>
                <TableHead>Pass rate</TableHead>
                <TableHead>Faithfulness</TableHead>
                <TableHead>Δ vs prior</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs?.map((r, i) => {
                const prior = runs[i + 1];
                const delta = prior
                  ? r.summary.avg_faithfulness - prior.summary.avg_faithfulness
                  : null;
                return (
                  <TableRow key={r.id}>
                    <TableCell className="text-xs">{fmtDateTime(r.started_at)}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{r.triggered_by}</Badge>
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {r.summary.passed}/{r.summary.total}
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {fmtPct(r.summary.avg_faithfulness)}
                    </TableCell>
                    <TableCell>
                      {delta == null ? (
                        <span className="text-xs text-muted-foreground">—</span>
                      ) : (
                        <span
                          className={`text-xs inline-flex items-center gap-0.5 ${
                            delta >= 0
                              ? "text-emerald-600 dark:text-emerald-400"
                              : "text-destructive"
                          }`}
                        >
                          {delta >= 0 ? (
                            <ArrowUp className="h-3 w-3" />
                          ) : (
                            <ArrowDown className="h-3 w-3" />
                          )}
                          {fmtPct(Math.abs(delta), 2)}
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Golden questions ({golden?.length ?? 0})</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {golden?.map((g) => (
            <div
              key={g.id}
              className="border border-border rounded-md p-3 text-sm flex items-center gap-3"
            >
              <div className="flex-1">
                <div>{g.question}</div>
                <div className="flex gap-1 mt-1">
                  {g.tags.map((t) => (
                    <Badge key={t} variant="outline" className="text-[10px]">
                      {t}
                    </Badge>
                  ))}
                </div>
              </div>
              {g.active && <Badge variant="secondary">active</Badge>}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
