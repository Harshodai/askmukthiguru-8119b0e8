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
import { Skeleton } from "@/components/ui/skeleton";
import { Copy, ExternalLink, ShieldCheck, ShieldAlert, Cpu, Hash, FileCode, CheckCircle2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { useCorpusProvenance } from "@/admin/hooks/useAdminData";
import { fmtDateTime } from "@/admin/lib/formatters";

interface Props {
  pointId: string | null;
  onClose: () => void;
}

function formatAudioTime(ms?: number): string {
  if (ms == null || isNaN(ms)) return "—";
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  const remMs = ms % 1000;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(remMs).padStart(3, "0")}`;
}

export function CorpusProvenanceModal({ pointId, onClose }: Props) {
  const { data, isLoading, error, refetch } = useCorpusProvenance(pointId);

  const copyText = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success(`${label} copied to clipboard`);
  };

  const isLicensed = data?.rights_status === "licensed";

  return (
    <Sheet open={!!pointId} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full sm:max-w-xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="text-base flex items-center gap-2">
            <Cpu className="h-4 w-4 text-primary" /> Corpus Point Provenance
          </SheetTitle>
          <SheetDescription className="sr-only">
            Corpus point metadata, chunking algorithm, licensing rights, and ASR coordinates
          </SheetDescription>
        </SheetHeader>

        {isLoading ? (
          <div className="space-y-4 py-6" aria-busy="true">
            <Skeleton className="h-6 w-3/4" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-32 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : error ? (
          <div className="py-8 text-center space-y-3">
            <AlertTriangle className="h-8 w-8 text-destructive mx-auto" />
            <p className="text-sm font-medium text-destructive">
              Failed to load point provenance
            </p>
            <p className="text-xs text-muted-foreground">
              {error instanceof Error ? error.message : "Point not found or vector store unavailable"}
            </p>
            <Button size="sm" variant="outline" onClick={() => void refetch()}>
              Retry
            </Button>
          </div>
        ) : !data ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            No provenance data found for point ID.
          </div>
        ) : (
          <div className="space-y-5 mt-4 text-sm">
            {/* Point ID Banner */}
            <div className="rounded-lg border border-border bg-muted/40 p-3 space-y-1">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">
                  Point ID
                </span>
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1 font-sans"
                  onClick={() => copyText(data.point_id, "Point ID")}
                >
                  <Copy className="h-3 w-3" /> copy
                </button>
              </div>
              <p className="font-mono text-xs break-all select-all font-semibold text-foreground">
                {data.point_id}
              </p>
            </div>

            {/* Rights & Licensing Status */}
            <section className="space-y-2">
              <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Rights & Governance
              </h3>
              <div className="rounded-lg border p-3 bg-card space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Licensing Status</span>
                  <Badge
                    variant={isLicensed ? "default" : "destructive"}
                    className="gap-1 text-xs capitalize"
                  >
                    {isLicensed ? (
                      <ShieldCheck className="h-3 w-3" />
                    ) : (
                      <ShieldAlert className="h-3 w-3" />
                    )}
                    {data.rights_status || "unverified"}
                  </Badge>
                </div>
                {data.source_release_version != null && (
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">Source Release Version</span>
                    <Badge variant="outline" className="font-mono">
                      v{String(data.source_release_version)}
                    </Badge>
                  </div>
                )}
                {data.gate_verdict && (
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">Ingest Gate Verdict</span>
                    <Badge variant={data.gate_verdict === "pass" ? "secondary" : "outline"} className="capitalize">
                      {data.gate_verdict}
                    </Badge>
                  </div>
                )}
                {data.gate_reason && (
                  <div className="text-xs text-muted-foreground italic pt-1 border-t">
                    Gate reason: {data.gate_reason}
                  </div>
                )}
              </div>
            </section>

            <Separator />

            {/* Chunker & Embedding Pipeline */}
            <section className="space-y-2">
              <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Chunking & Embeddings
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                <div className="rounded-lg border p-2.5 bg-card">
                  <div className="text-muted-foreground flex items-center gap-1 mb-1">
                    <FileCode className="h-3.5 w-3.5" /> Chunker Version
                  </div>
                  <div className="font-mono font-medium truncate" title={data.chunker_version || "unknown"}>
                    {data.chunker_version || "unknown_legacy"}
                  </div>
                </div>
                <div className="rounded-lg border p-2.5 bg-card">
                  <div className="text-muted-foreground flex items-center gap-1 mb-1">
                    <Cpu className="h-3.5 w-3.5" /> Embedding Model
                  </div>
                  <div className="font-mono font-medium truncate" title={data.embedding_model || "unknown"}>
                    {data.embedding_model || "unknown"}
                  </div>
                  {data.embedding_dimension && (
                    <div className="text-[11px] text-muted-foreground mt-0.5">
                      {data.embedding_dimension} dimensions
                    </div>
                  )}
                </div>
              </div>
            </section>

            <Separator />

            {/* ASR & Audio Coordinates */}
            <section className="space-y-2">
              <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                ASR & Alignment Coordinates
              </h3>
              <div className="rounded-lg border p-3 bg-card space-y-2 text-xs">
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <span className="text-muted-foreground block mb-0.5">Start Time (ASR)</span>
                    <span className="font-mono font-medium">
                      {formatAudioTime(data.audio_start_ms)}
                      {data.audio_start_ms != null && (
                        <span className="text-muted-foreground text-[10px] ml-1">
                          ({data.audio_start_ms}ms)
                        </span>
                      )}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground block mb-0.5">End Time (ASR)</span>
                    <span className="font-mono font-medium">
                      {formatAudioTime(data.audio_end_ms)}
                      {data.audio_end_ms != null && (
                        <span className="text-muted-foreground text-[10px] ml-1">
                          ({data.audio_end_ms}ms)
                        </span>
                      )}
                    </span>
                  </div>
                </div>
                {(data.asr_method || data.align_method) && (
                  <div className="pt-2 border-t grid grid-cols-2 gap-2 text-[11px] text-muted-foreground">
                    <div>ASR: <span className="font-mono text-foreground">{data.asr_method || "—"}</span></div>
                    <div>Align: <span className="font-mono text-foreground">{data.align_method || "—"}</span></div>
                  </div>
                )}
              </div>
            </section>

            <Separator />

            {/* Content Checksum & Integrity */}
            <section className="space-y-2">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                  <Hash className="h-3 w-3" /> Content Checksum
                </h3>
                {data.content_checksum && (
                  <button
                    type="button"
                    className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1 font-sans"
                    onClick={() => copyText(data.content_checksum!, "Checksum")}
                  >
                    <Copy className="h-3 w-3" /> copy
                  </button>
                )}
              </div>
              <div className="rounded-lg border bg-card p-2.5 font-mono text-xs break-all text-muted-foreground select-all">
                {data.content_checksum || "No checksum recorded"}
              </div>
            </section>

            <Separator />

            {/* Source & Parent Hierarchy */}
            <section className="space-y-2 text-xs">
              <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Source Document & Hierarchy
              </h3>
              <div className="space-y-1.5">
                {data.source_url && (
                  <div className="flex items-center justify-between gap-2 border rounded-md p-2">
                    <span className="truncate text-muted-foreground font-mono">{data.source_url}</span>
                    <a
                      href={data.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-primary hover:underline inline-flex items-center gap-1 shrink-0 font-sans"
                    >
                      Open <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                )}
                {data.parent_id && (
                  <div className="flex items-center justify-between border rounded-md p-2">
                    <span className="text-muted-foreground">Parent Unit:</span>
                    <span className="font-mono text-foreground">{data.parent_id}</span>
                  </div>
                )}
                {data.ingested_at && (
                  <div className="flex items-center justify-between text-muted-foreground text-[11px] px-1">
                    <span>Ingested</span>
                    <span>{fmtDateTime(data.ingested_at)}</span>
                  </div>
                )}
              </div>
            </section>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
