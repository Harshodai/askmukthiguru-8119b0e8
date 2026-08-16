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
import { Pencil, Plus, Trash2, Play, Loader2, RefreshCw, AlertCircle } from "lucide-react";
import { fmtDateTime, fmtPct } from "@/admin/lib/formatters";
import { MetricDelta } from "@/admin/components/MetricDelta";
import { GoldenQuestionDialog } from "@/admin/components/GoldenQuestionDialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { deleteGoldenQuestion, runEval } from "@/admin/lib/api";
import { useQueryClient } from "@tanstack/react-query";
import type { GoldenQuestion } from "@/admin/types";
import { toast } from "sonner";

export default function EvalsPage() {
  const {
    data: runs,
    isLoading: runsLoading,
    isError: runsError,
    refetch: refetchRuns,
  } = useEvalRuns();
  const {
    data: golden,
    isLoading: goldenLoading,
    isError: goldenError,
    refetch: refetchGolden,
  } = useGoldenQuestions();
  const qc = useQueryClient();
  const [editing, setEditing] = useState<GoldenQuestion | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [running, setRunning] = useState(false);

  const runsList = runs ?? [];
  const goldenList = golden ?? [];

  async function handleRunEval() {
    setRunning(true);
    try {
      const res = await runEval();
      const passed = res?.summary?.passed ?? 0;
      const total = res?.summary?.total ?? 0;
      toast.success(`Eval complete — ${passed}/${total} passed`);
      qc.invalidateQueries({ queryKey: ["admin", "eval-runs"] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Eval failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Evals</h1>
          <p className="text-sm text-muted-foreground">
            Golden dataset and regression history. See <code>docs/admin/evals.md</code>.
          </p>
        </div>
        <Button onClick={handleRunEval} disabled={running} size="sm">
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          {running ? "Running…" : "Run eval"}
        </Button>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Run history</CardTitle></CardHeader>
        <CardContent className="p-0">
          {runsLoading ? (
            <div className="py-12 flex items-center justify-center text-sm text-muted-foreground gap-2">
              <RefreshCw className="w-4 h-4 animate-spin" />
              Loading eval runs…
            </div>
          ) : runsError ? (
            <div className="py-12 flex flex-col items-center justify-center gap-2 text-sm text-destructive">
              <AlertCircle className="w-6 h-6" />
              <p>Failed to load eval runs</p>
              <Button variant="outline" size="sm" onClick={() => void refetchRuns()}>
                Retry
              </Button>
            </div>
          ) : runsList.length === 0 ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              No eval runs recorded yet. Click "Run eval" to trigger an evaluation.
            </div>
          ) : (
            <div className="overflow-x-auto">
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
                  {runsList.map((r, i) => {
                    const prior = runsList[i + 1];
                    const summary = r?.summary ?? {
                      passed: 0,
                      total: 0,
                      avg_faithfulness: 0,
                      avg_answer_relevancy: 0,
                      avg_context_precision: 0,
                    };
                    const priorSummary = prior?.summary;
                    return (
                      <TableRow key={r?.id ?? `run-${i}`}>
                        <TableCell className="text-xs">{fmtDateTime(r?.started_at)}</TableCell>
                        <TableCell><Badge variant="outline">{r?.triggered_by ?? "manual"}</Badge></TableCell>
                        <TableCell className="tabular-nums">
                          {summary.passed ?? 0}/{summary.total ?? 0}
                        </TableCell>
                        <TableCell className="tabular-nums">{fmtPct(summary.avg_faithfulness ?? 0)}</TableCell>
                        <TableCell>
                          <MetricDelta
                            current={summary.avg_faithfulness ?? 0}
                            prior={priorSummary?.avg_faithfulness ?? null}
                            format={(v) => fmtPct(v, 2)}
                          />
                        </TableCell>
                        <TableCell className="tabular-nums">{fmtPct(summary.avg_answer_relevancy ?? 0)}</TableCell>
                        <TableCell>
                          <MetricDelta
                            current={summary.avg_answer_relevancy ?? 0}
                            prior={priorSummary?.avg_answer_relevancy ?? null}
                            format={(v) => fmtPct(v, 2)}
                          />
                        </TableCell>
                        <TableCell className="tabular-nums">{fmtPct(summary.avg_context_precision ?? 0)}</TableCell>
                        <TableCell>
                          <MetricDelta
                            current={summary.avg_context_precision ?? 0}
                            prior={priorSummary?.avg_context_precision ?? null}
                            format={(v) => fmtPct(v, 2)}
                          />
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Golden questions ({goldenList.length})</CardTitle>
          <Button size="sm" onClick={() => { setEditing(null); setDialogOpen(true); }}>
            <Plus className="h-4 w-4" /> New
          </Button>
        </CardHeader>
        <CardContent className="space-y-2">
          {goldenLoading ? (
            <div className="py-8 flex items-center justify-center text-sm text-muted-foreground gap-2">
              <RefreshCw className="w-4 h-4 animate-spin" />
              Loading golden questions…
            </div>
          ) : goldenError ? (
            <div className="py-8 flex flex-col items-center justify-center gap-2 text-sm text-destructive">
              <AlertCircle className="w-6 h-6" />
              <p>Failed to load golden questions</p>
              <Button variant="outline" size="sm" onClick={() => void refetchGolden()}>
                Retry
              </Button>
            </div>
          ) : goldenList.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No golden questions defined yet. Click "New" to create one.
            </div>
          ) : (
            goldenList.map((g) => (
              <div
                key={g.id}
                className="border border-border rounded-md p-3 text-sm flex items-center gap-3"
              >
                <div className="flex-1 min-w-0">
                  <div className="truncate font-medium">{g?.question ?? "Untitled question"}</div>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {(g?.tags ?? []).map((t, tidx) => (
                      <Badge key={`${t}-${tidx}`} variant="outline" className="text-[10px]">{t}</Badge>
                    ))}
                  </div>
                </div>
                {g.active && <Badge variant="secondary">active</Badge>}
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label="Edit golden question"
                  onClick={() => { setEditing(g); setDialogOpen(true); }}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button size="icon" variant="ghost" aria-label="Delete golden question">
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Delete this golden question?</AlertDialogTitle>
                      <AlertDialogDescription>
                        &ldquo;{g.question}&rdquo; will be permanently removed from the regression-scoring dataset. This cannot be undone.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={async () => {
                          try {
                            await deleteGoldenQuestion(g.id);
                            qc.invalidateQueries({ queryKey: ["admin", "golden"] });
                            toast.success("Deleted");
                          } catch (err) {
                            toast.error(err instanceof Error ? err.message : "Failed to delete question");
                          }
                        }}
                      >
                        Delete
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            ))
          )}
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

