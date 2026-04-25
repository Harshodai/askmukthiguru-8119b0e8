import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useEvalRuns, useGoldenQuestions } from "@/admin/hooks/useAdminData";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { fmtDateTime, fmtPct } from "@/admin/lib/formatters";
import { MetricDelta } from "@/admin/components/MetricDelta";
import { GoldenQuestionDialog } from "@/admin/components/GoldenQuestionDialog";
import { deleteGoldenQuestion } from "@/admin/lib/mockData";
import { useQueryClient } from "@tanstack/react-query";
import type { GoldenQuestion } from "@/admin/types";
import { toast } from "sonner";

export default function EvalsPage() {
  const { data: runs } = useEvalRuns();
  const { data: golden } = useGoldenQuestions();
  const qc = useQueryClient();
  const [editing, setEditing] = useState<GoldenQuestion | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Evals</h1>
        <p className="text-sm text-muted-foreground">
          Golden dataset and regression history. See <code>docs/admin/evals.md</code>.
        </p>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Run history</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Triggered by</TableHead>
                <TableHead>Pass rate</TableHead>
                <TableHead>Faithfulness</TableHead>
                <TableHead>Δ faith</TableHead>
                <TableHead>Answer relevancy</TableHead>
                <TableHead>Δ rel</TableHead>
                <TableHead>Context precision</TableHead>
                <TableHead>Δ prec</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs?.map((r, i) => {
                const prior = runs[i + 1];
                return (
                  <TableRow key={r.id}>
                    <TableCell className="text-xs">{fmtDateTime(r.started_at)}</TableCell>
                    <TableCell><Badge variant="outline">{r.triggered_by}</Badge></TableCell>
                    <TableCell className="tabular-nums">{r.summary.passed}/{r.summary.total}</TableCell>
                    <TableCell className="tabular-nums">{fmtPct(r.summary.avg_faithfulness)}</TableCell>
                    <TableCell>
                      <MetricDelta
                        current={r.summary.avg_faithfulness}
                        prior={prior?.summary.avg_faithfulness ?? null}
                        format={(v) => fmtPct(v, 2)}
                      />
                    </TableCell>
                    <TableCell className="tabular-nums">{fmtPct(r.summary.avg_answer_relevancy)}</TableCell>
                    <TableCell>
                      <MetricDelta
                        current={r.summary.avg_answer_relevancy}
                        prior={prior?.summary.avg_answer_relevancy ?? null}
                        format={(v) => fmtPct(v, 2)}
                      />
                    </TableCell>
                    <TableCell className="tabular-nums">{fmtPct(r.summary.avg_context_precision)}</TableCell>
                    <TableCell>
                      <MetricDelta
                        current={r.summary.avg_context_precision}
                        prior={prior?.summary.avg_context_precision ?? null}
                        format={(v) => fmtPct(v, 2)}
                      />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Golden questions ({golden?.length ?? 0})</CardTitle>
          <Button size="sm" onClick={() => { setEditing(null); setDialogOpen(true); }}>
            <Plus className="h-4 w-4" /> New
          </Button>
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
                    <Badge key={t} variant="outline" className="text-[10px]">{t}</Badge>
                  ))}
                </div>
              </div>
              {g.active && <Badge variant="secondary">active</Badge>}
              <Button
                size="icon"
                variant="ghost"
                onClick={() => { setEditing(g); setDialogOpen(true); }}
              >
                <Pencil className="h-4 w-4" />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                onClick={async () => {
                  await deleteGoldenQuestion(g.id);
                  qc.invalidateQueries({ queryKey: ["admin", "golden"] });
                  toast.success("Deleted");
                }}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>

      <GoldenQuestionDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        initial={editing}
      />
    </div>
  );
}
