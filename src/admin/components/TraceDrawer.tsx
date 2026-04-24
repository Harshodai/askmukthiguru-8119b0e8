import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ChevronDown, Copy, Download } from "lucide-react";
import { toast } from "sonner";
import { useQueryTrace } from "@/admin/hooks/useAdminData";
import { SpanWaterfall } from "./SpanWaterfall";
import { JudgeScoreBar } from "./JudgeScoreBar";
import { HallucinationBadge } from "./HallucinationBadge";
import {
  fmtDateTime,
  fmtMs,
  fmtPct,
  fmtUsd,
  truncate,
} from "@/admin/lib/formatters";
import { exportTraceCSV, exportTraceJSON } from "@/admin/lib/exportTrace";

interface Props {
  queryId: string | null;
  onClose: () => void;
}

export function TraceDrawer({ queryId, onClose }: Props) {
  const { data: trace, isLoading } = useQueryTrace(queryId);

  return (
    <Sheet open={!!queryId} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full sm:max-w-2xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="text-base">Query trace</SheetTitle>
        </SheetHeader>

        {isLoading || !trace ? (
          <div className="text-sm text-muted-foreground py-10 text-center">Loading…</div>
        ) : (
          <div className="space-y-5 mt-3">
            {/* Header strip */}
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium leading-snug">{trace.query.query_text}</div>
                <div className="text-xs text-muted-foreground mt-1 flex flex-wrap gap-x-3 gap-y-1">
                  <span>{fmtDateTime(trace.query.created_at)}</span>
                  <span className="font-mono">{trace.query.id}</span>
                  <button
                    className="hover:text-foreground inline-flex items-center gap-1"
                    onClick={() => {
                      navigator.clipboard.writeText(trace.query.id);
                      toast.success("Query ID copied");
                    }}
                  >
                    <Copy className="h-3 w-3" /> copy
                  </button>
                </div>
              </div>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button size="sm" variant="outline">
                    <Download className="h-4 w-4" />
                    Export
                    <ChevronDown className="h-3 w-3" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem
                    onClick={() => {
                      exportTraceJSON(trace);
                      toast.success("Trace exported as JSON");
                    }}
                  >
                    Download JSON
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() => {
                      exportTraceCSV(trace);
                      toast.success("Trace exported as CSV");
                    }}
                  >
                    Download CSV
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            <Separator />

            {/* Span waterfall */}
            <section>
              <h3 className="text-sm font-medium mb-2">Span waterfall</h3>
              <SpanWaterfall spans={trace.spans} />
            </section>

            <Separator />

            {/* Prompt + model */}
            <section className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <div className="text-xs text-muted-foreground">Prompt</div>
                <div className="font-medium">
                  {trace.prompt.name} <Badge variant="secondary">v{trace.prompt.version}</Badge>
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Model</div>
                <div className="font-mono text-xs">{trace.query.model}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Tokens</div>
                <div className="tabular-nums">
                  {trace.query.prompt_tokens} in · {trace.query.completion_tokens} out
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Cost · Latency</div>
                <div className="tabular-nums">
                  {fmtUsd(trace.query.cost_estimate)} · {fmtMs(trace.query.latency_ms)}
                </div>
              </div>
            </section>

            <Separator />

            {/* Judge */}
            {trace.response && (
              <section>
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-medium">Judge scores (RAGAS)</h3>
                  <HallucinationBadge flag={trace.response.hallucination_flag} />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <JudgeScoreBar label="Faithfulness" value={trace.response.faithfulness} />
                  <JudgeScoreBar
                    label="Answer relevancy"
                    value={trace.response.answer_relevancy}
                  />
                  <JudgeScoreBar
                    label="Context precision"
                    value={trace.response.context_precision}
                  />
                  <JudgeScoreBar label="Context recall" value={trace.response.context_recall} />
                </div>
                <div className="text-xs text-muted-foreground mt-3 italic">
                  Judge: “{trace.response.judge_reasoning}” (confidence{" "}
                  {fmtPct(trace.response.confidence)})
                </div>
              </section>
            )}

            <Separator />

            {/* Retrieved chunks */}
            <section>
              <h3 className="text-sm font-medium mb-2">Retrieved chunks</h3>
              {trace.retrieval ? (
                <div className="space-y-1.5 text-xs">
                  {trace.retrieval.source_docs.map((src, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2 border border-border rounded px-2 py-1"
                    >
                      <Badge variant="outline" className="text-[10px] h-5">
                        #{i + 1}
                      </Badge>
                      <span className="font-mono truncate flex-1">{truncate(src, 60)}</span>
                      <span className="tabular-nums text-muted-foreground">
                        {trace.retrieval!.scores[i]?.toFixed(3)}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-muted-foreground">No retrieval recorded.</div>
              )}
            </section>

            <Separator />

            {/* Response */}
            {trace.response && (
              <section>
                <h3 className="text-sm font-medium mb-2">Response</h3>
                <div className="text-sm bg-muted/50 rounded-md p-3 whitespace-pre-wrap">
                  {trace.response.response_text}
                </div>
                {trace.response.citations.length > 0 && (
                  <div className="mt-2 text-xs text-muted-foreground">
                    Cited:{" "}
                    {trace.response.citations.map((c, i) => (
                      <Badge key={i} variant="outline" className="mr-1">
                        {c.source}
                      </Badge>
                    ))}
                  </div>
                )}
              </section>
            )}

            {/* Triggers + feedback */}
            {(trace.triggers.length > 0 || trace.feedback) && (
              <>
                <Separator />
                <section className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <div className="text-xs text-muted-foreground mb-1">Triggers</div>
                    {trace.triggers.length ? (
                      <div className="flex flex-wrap gap-1">
                        {trace.triggers.map((t) => (
                          <Badge key={t.id} variant="secondary">
                            {t.trigger_name}
                          </Badge>
                        ))}
                      </div>
                    ) : (
                      <span className="text-muted-foreground text-xs">none</span>
                    )}
                  </div>
                  <div>
                    <div className="text-xs text-muted-foreground mb-1">Feedback</div>
                    {trace.feedback ? (
                      <Badge
                        variant={
                          trace.feedback.rating === 1
                            ? "secondary"
                            : trace.feedback.rating === -1
                              ? "destructive"
                              : "outline"
                        }
                      >
                        {trace.feedback.rating === 1
                          ? "👍 thumbs up"
                          : trace.feedback.rating === -1
                            ? "👎 thumbs down"
                            : "neutral"}
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground text-xs">none</span>
                    )}
                  </div>
                </section>
              </>
            )}

            <Separator />

            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => toast.info("UI preview — wire to evals API when Cloud is on")}
              >
                Promote to golden
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => toast.info("UI preview — annotation API not wired yet")}
              >
                Add annotation
              </Button>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
