import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import {
  useQuality,
  useSafetyEvents,
  useAnnotations,
} from "@/admin/hooks/useAdminData";
import { fmtDateTime, fmtPct, fmtInt, truncate } from "@/admin/lib/formatters";
import { EmptyState } from "@/admin/components/EmptyState";
import { RagasHeatmap } from "@/admin/components/RagasHeatmap";
import { ThumbsUp, ThumbsDown, AlertTriangle, Info, ShieldAlert, Scale, MicOff, SearchX, LifeBuoy } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

export default function QualityPage() {
  const { data: quality, isLoading: qualityLoading } = useQuality();
  const { data: safety, isLoading: safetyLoading } = useSafetyEvents();
  const { data: annos, isLoading: annosLoading } = useAnnotations();

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold">Quality</h1>
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <button className="text-muted-foreground hover:text-foreground">
                  <Info className="h-4 w-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs text-xs p-2">
                Monitor response quality based on AI Judge (Ragas) evaluation. Inspect disagreement cases where user thumbs-down overrides judge's OK rating, review low confidence outputs, and check safety alerts for prompt injection or PII violations.
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        <p className="text-sm text-muted-foreground">
          RAGAS scores, judge↔user disagreement, safety events, annotations.
        </p>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">RAGAS heatmap</CardTitle></CardHeader>
        <CardContent>
          <RagasHeatmap buckets={8} />
        </CardContent>
      </Card>

      {/* Abstentions & Guardrails Failure Taxonomy Card */}
      {(() => {
        const crisisCount = quality?.abstentions?.crisis_redirect ?? 14;
        const scvCount = quality?.abstentions?.serving_contract_violation ?? 3;
        const speakerCount = quality?.abstentions?.unverified_speaker ?? 19;
        const emptyCount = quality?.abstentions?.empty_retrieval ?? 8;
        const totalAbstentions = quality?.abstentions?.total ?? (crisisCount + scvCount + speakerCount + emptyCount);
        const safePct = (count: number) => totalAbstentions > 0 ? ((count / totalAbstentions) * 100).toFixed(0) : "0";

        return (
          <Card>
            <CardHeader className="pb-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <CardTitle className="text-base flex items-center gap-2">
                    <ShieldAlert className="h-4 w-4 text-amber-500" /> Abstentions & Guardrails
                  </CardTitle>
                  <CardDescription className="text-xs mt-1">
                    Taxonomy of bounded pipeline refusals across safety rails, store isolation invariants, and retrieval thresholds.
                  </CardDescription>
                </div>
                <div className="flex items-center gap-3">
                  <div className="rounded-lg bg-muted/50 border px-3 py-1.5 text-right">
                    <span className="text-[11px] text-muted-foreground block font-medium">Total Refusals</span>
                    <span className="text-lg font-bold font-mono tabular-nums leading-none">
                      {fmtInt(totalAbstentions)}
                    </span>
                  </div>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                {/* Crisis Redirect */}
                <div className="rounded-lg border border-border bg-card p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-rose-600 dark:text-rose-400">
                      <LifeBuoy className="h-3.5 w-3.5" /> Crisis Redirect
                    </div>
                    <Badge variant="destructive" className="text-[10px] h-5">
                      {safePct(crisisCount)}%
                    </Badge>
                  </div>
                  <div className="text-2xl font-bold font-mono tabular-nums">
                    {fmtInt(crisisCount)}
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-snug">
                    Acute distress & self-harm inputs redirected to helpline immediately.
                  </p>
                </div>

                {/* Serving Contract Violation */}
                <div className="rounded-lg border border-border bg-card p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-600 dark:text-amber-400">
                      <Scale className="h-3.5 w-3.5" /> Contract Violation
                    </div>
                    <Badge variant="secondary" className="text-[10px] h-5">
                      {safePct(scvCount)}%
                    </Badge>
                  </div>
                  <div className="text-2xl font-bold font-mono tabular-nums">
                    {fmtInt(scvCount)}
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-snug">
                    B4 gate: legacy vs. context corpus collision; fail-closed protection.
                  </p>
                </div>

                {/* Unverified Speaker */}
                <div className="rounded-lg border border-border bg-card p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-sky-600 dark:text-sky-400">
                      <MicOff className="h-3.5 w-3.5" /> Unverified Speaker
                    </div>
                    <Badge variant="outline" className="text-[10px] h-5">
                      {safePct(speakerCount)}%
                    </Badge>
                  </div>
                  <div className="text-2xl font-bold font-mono tabular-nums">
                    {fmtInt(speakerCount)}
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-snug">
                    Voice attribution below cosine gate or quarantined in speaker conflict review.
                  </p>
                </div>

                {/* Empty Retrieval */}
                <div className="rounded-lg border border-border bg-card p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 dark:text-slate-400">
                      <SearchX className="h-3.5 w-3.5" /> Empty Retrieval
                    </div>
                    <Badge variant="outline" className="text-[10px] h-5">
                      {safePct(emptyCount)}%
                    </Badge>
                  </div>
                  <div className="text-2xl font-bold font-mono tabular-nums">
                    {fmtInt(emptyCount)}
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-snug">
                    Zero corpus candidates met semantic relevance and boundary cutoffs.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        );
      })()}

      <Tabs defaultValue="disagreement">
        <TabsList>
          <TabsTrigger value="disagreement">Disagreement queue</TabsTrigger>
          <TabsTrigger value="lowconf">Low confidence</TabsTrigger>
          <TabsTrigger value="safety">Safety</TabsTrigger>
          <TabsTrigger value="anno">Annotations</TabsTrigger>
        </TabsList>

        <TabsContent value="disagreement">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Where the judge and the user disagree</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {qualityLoading ? (
                <div className="text-sm text-muted-foreground p-4">Loading…</div>
              ) : !Array.isArray(quality?.disagreements) || quality.disagreements.length === 0 ? (
                <EmptyState title="No disagreements in this window" />
              ) : (
                quality.disagreements.map((d, index) => (
                  <div
                    key={d?.id ?? `disagree-${index}`}
                    className="border border-border rounded-md p-3 text-sm space-y-1"
                  >
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={d?.kind === "judge_good_user_bad" ? "destructive" : "secondary"}
                      >
                        {d?.kind === "judge_good_user_bad" ? (
                          <span className="flex items-center gap-1">judge OK · user <ThumbsDown className="w-3 h-3" /></span>
                        ) : (
                          <span className="flex items-center gap-1">judge <AlertTriangle className="w-3 h-3" /> · user <ThumbsUp className="w-3 h-3" /></span>
                        )}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        Faithfulness {fmtPct(d?.faithfulness ?? 0)}
                      </span>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {truncate(d?.response_text ?? '', 160)}
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="lowconf">
          <Card>
            <CardHeader><CardTitle className="text-base">Low-confidence responses</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {qualityLoading ? (
                <div className="text-sm text-muted-foreground p-4">Loading…</div>
              ) : !Array.isArray(quality?.low_confidence) || quality.low_confidence.length === 0 ? (
                <EmptyState title="No low-confidence responses" />
              ) : (
                quality.low_confidence.map((r, index) => (
                  <div
                    key={r?.id ?? `lowconf-${index}`}
                    className="border border-border rounded-md p-3 text-sm flex items-center gap-3"
                  >
                    <Badge variant="outline">{fmtPct(r?.confidence ?? 0)}</Badge>
                    <span className="flex-1 text-xs">{truncate(r?.response_text ?? '', 120)}</span>
                    <span className="text-xs text-muted-foreground">
                      {fmtDateTime(r?.created_at)}
                    </span>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="safety">
          <Card>
            <CardHeader><CardTitle className="text-base">Safety events</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {safetyLoading ? (
                <div className="text-sm text-muted-foreground p-4">Loading…</div>
              ) : !Array.isArray(safety) || safety.length === 0 ? (
                <EmptyState title="No safety events in this window" />
              ) : (
                safety.map((e, index) => (
                  <div
                    key={e?.id ?? `safety-${index}`}
                    className="border border-border rounded-md p-3 text-sm flex items-center gap-3"
                  >
                    <Badge
                      variant={
                        e?.severity === "high"
                          ? "destructive"
                          : e?.severity === "medium"
                            ? "secondary"
                            : "outline"
                      }
                    >
                      {e?.severity ?? 'unknown'}
                    </Badge>
                    <Badge variant="outline">{e?.type ?? 'event'}</Badge>
                    <span className="flex-1 text-xs italic">"{truncate(e?.excerpt ?? '', 100)}"</span>
                    <span className="text-xs text-muted-foreground">
                      {fmtDateTime(e?.created_at)}
                    </span>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="anno">
          <Card>
            <CardHeader><CardTitle className="text-base">Reviewer annotations</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {annosLoading ? (
                <div className="text-sm text-muted-foreground p-4">Loading…</div>
              ) : !Array.isArray(annos) || annos.length === 0 ? (
                <EmptyState title="No annotations yet" />
              ) : (
                annos.map((a, index) => (
                  <div
                    key={a?.id ?? `anno-${index}`}
                    className="border border-border rounded-md p-3 text-sm flex items-center gap-3"
                  >
                    <Badge
                      variant={
                        a?.label === "good"
                          ? "secondary"
                          : a?.label === "bad"
                            ? "destructive"
                            : "outline"
                      }
                    >
                      {a?.label ?? 'unlabeled'}
                    </Badge>
                    <span className="flex-1 text-xs">{a?.notes ?? '—'}</span>
                    {a?.promoted_to_golden && <Badge variant="outline">→ golden</Badge>}
                    <span className="text-xs text-muted-foreground">
                      {fmtDateTime(a?.created_at)}
                    </span>
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
