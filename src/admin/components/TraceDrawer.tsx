import { useState } from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
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
import { ChevronDown, Copy, Download, ThumbsUp, ThumbsDown, Info, Cpu } from "lucide-react";
import { toast } from "sonner";
import { useQueryTrace } from "@/admin/hooks/useAdminData";
import { upsertGoldenQuestion } from "@/admin/lib/api";
import { CorpusProvenanceModal } from "./CorpusProvenanceModal";
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
  const { data: trace, isLoading, error, refetch } = useQueryTrace(queryId);
  const [provenancePointId, setProvenancePointId] = useState<string | null>(null);
  const [promoting, setPromoting] = useState(false);

  const handlePromoteToGolden = async () => {
    if (!trace?.query?.query_text) {
      toast.error("No query text available to promote");
      return;
    }
    setPromoting(true);
    try {
      const sources = trace.retrieval?.source_docs || [];
      await upsertGoldenQuestion({
        question: trace.query.query_text,
        expected_answer: trace.response?.response_text || "",
        expected_sources: sources,
        tags: ["promoted_from_trace", trace.query.model || "rag"].filter(Boolean),
        active: true,
      });
      toast.success("Successfully promoted query to golden evaluation set");
    } catch (err) {
      toast.error(`Failed to promote: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setPromoting(false);
    }
  };

  return (
    <Sheet open={!!queryId} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full sm:max-w-2xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="text-base">Query trace</SheetTitle>
          <SheetDescription className="sr-only">
            Detailed pipeline trace for the selected query
          </SheetDescription>
        </SheetHeader>

        {isLoading ? (
          <div className="text-sm text-muted-foreground py-10 text-center">Loading…</div>
        ) : error ? (
          <div className="py-10 text-center space-y-3">
            <p className="text-sm text-destructive">
              Failed to load trace: {(error as Error)?.message || "Unknown error"}
            </p>
            <Button size="sm" variant="outline" onClick={() => void refetch()}>
              Retry
            </Button>
          </div>
        ) : !trace || !trace.query ? (
          <div className="text-sm text-muted-foreground py-10 text-center">
            Trace not found. The query row may have been deleted or never recorded.
          </div>
        ) : (
          <div className="space-y-5 mt-3">
            {/* Header strip */}
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium leading-snug">
                  {trace.query?.query_text ?? "(no query text)"}
                </div>
                <div className="text-xs text-muted-foreground mt-1 flex flex-wrap gap-x-3 gap-y-1">
                  <span>{trace.query?.created_at ? fmtDateTime(trace.query.created_at) : "—"}</span>
                  <span className="font-mono">{trace.query?.id ?? "—"}</span>
                  {trace.query?.id && (
                    <button
                      className="hover:text-foreground inline-flex items-center gap-1"
                      onClick={() => {
                        if (trace.query?.id) {
                          navigator.clipboard.writeText(trace.query.id);
                          toast.success("Query ID copied");
                        }
                      }}
                    >
                      <Copy className="h-3 w-3" /> copy
                    </button>
                  )}
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
              {(trace.spans?.length ?? 0) > 0 ? (
                <SpanWaterfall spans={trace.spans ?? []} />
              ) : (
                <div className="text-xs text-muted-foreground">No spans recorded.</div>
              )}
            </section>

            <Separator />

            {/* Prompt + model */}
            <section className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <div className="text-xs text-muted-foreground">Prompt</div>
                <div className="font-medium">
                  {trace.prompt?.name || "v0 (default)"}{" "}
                  {trace.prompt?.version && <Badge variant="secondary">v{trace.prompt.version}</Badge>}
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Model</div>
                <div className="font-mono text-xs">{trace.query?.model || "unknown"}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Tokens</div>
                <div className="tabular-nums">
                  {trace.query?.prompt_tokens ?? 0} in · {trace.query?.completion_tokens ?? 0} out
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Cost · Latency</div>
                <div className="tabular-nums">
                  {fmtUsd(trace.query?.cost_estimate)} · {fmtMs(trace.query?.latency_ms)}
                </div>
              </div>
            </section>

            <Separator />

            {/* Judge */}
            <section>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-medium">Judge scores (RAGAS)</h3>
                {trace.response && (
                  <HallucinationBadge flag={!!trace.response.hallucination_flag} />
                )}
              </div>
              {trace.response ? (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <JudgeScoreBar label="Faithfulness" value={trace.response.faithfulness ?? 0} />
                    <JudgeScoreBar label="Answer relevancy" value={trace.response.answer_relevancy ?? 0} />
                    <JudgeScoreBar label="Context precision" value={trace.response.context_precision ?? 0} />
                    <JudgeScoreBar label="Context recall" value={trace.response.context_recall ?? 0} />
                  </div>
                  {trace.response.judge_reasoning && (
                    <div className="text-xs text-muted-foreground mt-3 italic">
                      Judge: "{trace.response.judge_reasoning}" (confidence{" "}
                      {fmtPct(trace.response.confidence ?? 0)})
                    </div>
                  )}
                </>
              ) : (
                <div className="text-xs text-muted-foreground">No response or judge scores recorded.</div>
              )}
            </section>

            <Separator />

            {/* Retrieved chunks */}
            <section>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-medium">Retrieved chunks</h3>
                <span className="text-[11px] text-muted-foreground">Click chunk to inspect provenance</span>
              </div>
              {trace.retrieval?.source_docs && trace.retrieval.source_docs.length > 0 ? (
                <div className="space-y-1.5 text-xs">
                  {(trace.retrieval.source_docs ?? []).map((src: string, i: number) => {
                    const chunkId = trace.retrieval?.chunk_ids?.[i] || src;
                    return (
                      <div
                        key={i}
                        className="flex items-center gap-2 border border-border hover:border-primary/50 hover:bg-muted/40 transition-colors rounded px-2.5 py-1.5 cursor-pointer group"
                        onClick={() => setProvenancePointId(chunkId)}
                        title={`Click to inspect provenance for ${chunkId}`}
                      >
                        <Badge variant="outline" className="text-[10px] h-5">
                          #{i + 1}
                        </Badge>
                        <span className="font-mono truncate flex-1 text-foreground/90 group-hover:text-primary">
                          {truncate(src ?? "", 55)}
                        </span>
                        <span className="tabular-nums text-muted-foreground">
                          {typeof trace.retrieval?.scores?.[i] === "number" && !Number.isNaN(trace.retrieval.scores[i])
                            ? trace.retrieval.scores[i].toFixed(3)
                            : (trace.retrieval?.scores?.[i] ?? "0.000")}
                        </span>
                        <Info className="h-3.5 w-3.5 text-muted-foreground opacity-60 group-hover:opacity-100 group-hover:text-primary shrink-0 ml-1" />
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-xs text-muted-foreground">No retrieval recorded.</div>
              )}
            </section>

            <Separator />

            {/* Response */}
            <section>
              <h3 className="text-sm font-medium mb-2">Response</h3>
              {trace.response?.response_text ? (
                <>
                  <div className="text-sm bg-muted/50 rounded-md p-3 whitespace-pre-wrap">
                    {trace.response.response_text}
                  </div>
                  {Array.isArray(trace.response.citations) && trace.response.citations.length > 0 && (
                    <div className="mt-2 text-xs text-muted-foreground">
                      Cited:{" "}
                      {(trace.response.citations as Array<{ source?: string; title?: string }>).map((c, i: number) => (
                        <Badge key={i} variant="outline" className="mr-1">
                          {c?.source ?? c?.title ?? `#${i + 1}`}
                        </Badge>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <div className="text-xs text-muted-foreground">No response recorded.</div>
              )}
            </section>

            {/* Triggers + feedback */}
            {(((trace.triggers?.length ?? 0) > 0) || !!trace.feedback) && (
              <>
                <Separator />
                <section className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <div className="text-xs text-muted-foreground mb-1">Triggers</div>
                    {(trace.triggers?.length ?? 0) > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {(trace.triggers ?? []).map((t: { id?: string; trigger_name?: string; trigger_type?: string }, idx: number) => (
                          <Badge key={t?.id ?? idx} variant="secondary">
                            {t?.trigger_name ?? t?.trigger_type ?? "trigger"}
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
                        {trace.feedback.rating === 1 ? (
                          <span className="flex items-center gap-1"><ThumbsUp className="w-3 h-3" /> thumbs up</span>
                        ) : trace.feedback.rating === -1 ? (
                          <span className="flex items-center gap-1"><ThumbsDown className="w-3 h-3" /> thumbs down</span>
                        ) : (
                          "neutral"
                        )}
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
                disabled={promoting}
                onClick={handlePromoteToGolden}
              >
                {promoting ? "Promoting…" : "Promote to golden"}
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

      {/* Corpus Point Provenance Drawer */}
      {provenancePointId && (
        <CorpusProvenanceModal
          pointId={provenancePointId}
          onClose={() => setProvenancePointId(null)}
        />
      )}
    </Sheet>
  );
}
