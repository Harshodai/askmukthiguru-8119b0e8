import { useState, useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useIngestionRuns, useIngestionHealth } from "@/admin/hooks/useAdminData";
import { triggerReingest, submitIngestion, getIngestionStatus, clearCache, uploadDocument, ingestBook } from "@/admin/lib/api";
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
import { RefreshCw, Upload, Loader2, CheckCircle2, AlertCircle, Link2, Info, Trash2 } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

interface IngestionJob {
  status: string;
  message: string;
  progress?: number;
}

export default function IngestionPage() {
  const {
    data: runs,
    isLoading: runsLoading,
    isError: runsError,
    refetch: refetchRuns,
  } = useIngestionRuns();
  const {
    data: health,
    isLoading: healthLoading,
    isError: healthError,
    refetch: refetchHealth,
  } = useIngestionHealth();
  const qc = useQueryClient();

  // Ingestion form state
  const [url, setUrl] = useState("");
  const [maxAccuracy, setMaxAccuracy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [bookIngesting, setBookIngesting] = useState(false);
  const [activeJobs, setActiveJobs] = useState<Record<string, IngestionJob>>({});
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Poll for active ingestion status
  useEffect(() => {
    const jobEntries = Object.entries(activeJobs ?? {});
    if (jobEntries.length === 0) return;

    const hasRunning = jobEntries.some(
      ([, j]) => j && j.status !== "error" && j.status !== "Complete!" && j.progress !== 1
    );

    if (!hasRunning) {
      if (pollRef.current) clearInterval(pollRef.current);
      return;
    }

    pollRef.current = setInterval(async () => {
      try {
        const status = await getIngestionStatus();
        if (status && typeof status === "object") {
          const mapped: Record<string, IngestionJob> = {};
          for (const [key, val] of Object.entries(status)) {
            if (val && typeof val === "object") {
              const v = val as { status?: string; message?: string; progress?: number | null };
              mapped[key] = {
                status: v.status || v.message || "processing",
                message: v.message || "",
                progress: typeof v.progress === "number" ? v.progress : undefined,
              };
            }
          }
          setActiveJobs((prev) => ({ ...(prev ?? {}), ...mapped }));

          // If all jobs are done, invalidate cache
          const allDone = Object.values(mapped).every(
            (j) => j && (j.progress === 1 || j.status === "error")
          );
          if (allDone) {
            qc.invalidateQueries({ queryKey: ["admin", "ingestion"] });
            qc.invalidateQueries({ queryKey: ["admin", "ingest-health"] });
          }
        }
      } catch {
        // silent — backend may not be running or transient network glitch
      }
    }, 2500);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [activeJobs, qc]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = url.trim();
    if (!trimmed) return;

    setSubmitting(true);
    try {
      const res = await submitIngestion(trimmed, maxAccuracy);
      toast.success(res?.message || "Ingestion started");
      setActiveJobs((prev) => ({
        ...(prev ?? {}),
        [trimmed]: { status: "processing", message: "Starting...", progress: 0 },
      }));
      setUrl("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to start ingestion");
    } finally {
      setSubmitting(false);
    }
  };

  const handleFileUpload = async (file: File) => {
    setUploading(true);
    try {
      const res = await uploadDocument(file, maxAccuracy);
      toast.success(res?.message || "Document upload queued");
      setActiveJobs((prev) => ({
        ...(prev ?? {}),
        [`upload:${file.name}`]: { status: "processing", message: "Starting...", progress: 0 },
      }));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to upload document");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleBookIngest = async () => {
    setBookIngesting(true);
    try {
      const res = await ingestBook();
      toast.success(`Book ingestion queued. Task ID: ${res?.task_id ?? 'queued'}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to queue book ingestion");
    } finally {
      setBookIngesting(false);
    }
  };

  const activeJobEntries = Object.entries(activeJobs ?? {});
  const runsList = runs ?? [];

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold">Ingestion</h1>
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <button className="text-muted-foreground hover:text-foreground">
                  <Info className="h-4 w-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs text-xs p-2">
                Manage content ingestion. Submit new YouTube videos, playlists, or document URLs. The system automatically downloads, chunks, generates embeddings, and indexes them into the semantic vector DB and graph.
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        <p className="text-sm text-muted-foreground">
          Ingest YouTube videos, playlists, and documents into the knowledge base.
        </p>
      </div>

      {/* Ingestion Form */}
      <Card className="border-primary/20 bg-primary/[0.02]">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Upload className="h-4 w-4 text-primary" />
            Submit New Content
          </CardTitle>
          <CardDescription>
            Enter a YouTube video/playlist URL or image URL. The backend will process, chunk, embed, and index the content.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="flex gap-3">
              <div className="flex-1 space-y-1.5">
                <Label htmlFor="ingest-url" className="text-xs text-muted-foreground">Content URL</Label>
                <div className="relative">
                  <Link2 className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="ingest-url"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="https://youtube.com/watch?v=... or image URL"
                    className="pl-9"
                    disabled={submitting}
                  />
                </div>
              </div>
              <div className="flex flex-col justify-end">
                <Button type="submit" disabled={submitting || !url.trim()} className="gap-2">
                  {submitting ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Upload className="h-4 w-4" />
                  )}
                  Ingest
                </Button>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Switch
                id="max-accuracy"
                checked={maxAccuracy}
                onCheckedChange={setMaxAccuracy}
                disabled={submitting}
              />
              <Label htmlFor="max-accuracy" className="text-sm cursor-pointer">
                Max accuracy mode
                <span className="text-xs text-muted-foreground ml-1.5">
                  (skip auto-captions, use Whisper/manual — slower but higher quality)
                </span>
              </Label>
            </div>
          </form>

          <div className="mt-4 pt-4 border-t border-border/40 flex flex-wrap items-center gap-3">
            <Label htmlFor="ingest-file-upload" className="text-xs text-muted-foreground shrink-0">
              Or upload a PDF directly
            </Label>
            <input
              id="ingest-file-upload"
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              disabled={uploading}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFileUpload(file);
              }}
              className="text-xs text-muted-foreground file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-medium file:bg-secondary file:text-secondary-foreground hover:file:bg-secondary/80 file:cursor-pointer disabled:opacity-50"
            />
            {uploading && <Loader2 className="h-4 w-4 animate-spin text-primary" />}
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="ml-auto gap-2"
              disabled={bookIngesting}
              onClick={handleBookIngest}
            >
              {bookIngesting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              Re-ingest Four Sacred Secrets Book
            </Button>
          </div>

          {/* Active Jobs */}
          {activeJobEntries.length > 0 && (
            <div className="mt-4 space-y-2">
              <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Active Jobs</p>
              {activeJobEntries.map(([jobUrl, job]) => (
                <div
                  key={jobUrl}
                  className="flex items-center gap-3 p-3 rounded-lg bg-muted/40 border border-border/40"
                >
                  {job?.progress === 1 ? (
                    <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
                  ) : job?.status === "error" ? (
                    <AlertCircle className="h-4 w-4 text-destructive shrink-0" />
                  ) : (
                    <Loader2 className="h-4 w-4 animate-spin text-primary shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-mono truncate">{jobUrl}</p>
                    <p className="text-[11px] text-muted-foreground">{job?.message || job?.status || "Processing"}</p>
                  </div>
                  {job?.progress !== undefined && job.progress < 1 && job.status !== "error" && (
                    <Badge variant="outline" className="text-[10px] tabular-nums">
                      {Math.round(job.progress * 100)}%
                    </Badge>
                  )}
                  {job?.progress === 1 && <Badge variant="secondary">Done</Badge>}
                  {job?.status === "error" && <Badge variant="destructive">Error</Badge>}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <KpiCard label="Total runs" value={fmtInt(health?.total_runs ?? 0)} />
        <KpiCard label="Ok" value={fmtInt(health?.ok ?? 0)} tone="good" />
        <KpiCard label="Partial" value={fmtInt(health?.partial ?? 0)} tone="warn" />
        <KpiCard label="Failed" value={fmtInt(health?.failed ?? 0)} tone={health?.failed ? "bad" : "default"} />
        <KpiCard label="Chunks added" value={fmtInt(health?.total_chunks ?? 0)} />
      </div>

      {/* Cache Management */}
      <Card className="border-amber-200/30 bg-amber-50/30 dark:bg-amber-950/10 dark:border-amber-800/20">
        <CardContent className="flex items-center justify-between p-4">
          <div>
            <p className="text-sm font-medium">Cache</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Flush exact (Redis), semantic (Qdrant), and hot (in-memory) caches after ingestion or to force fresh responses.
            </p>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="gap-2 shrink-0 ml-4"
            onClick={async () => {
              try {
                const res = await clearCache();
                const tiersList = res?.tiers && typeof res.tiers === "object" ? Object.values(res.tiers).join(", ") : "All tiers";
                toast.success(`Cache cleared: ${tiersList}`);
                qc.invalidateQueries();
              } catch (err) {
                toast.error(err instanceof Error ? err.message : "Failed to clear cache");
              }
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
            Clear Cache
          </Button>
        </CardContent>
      </Card>

      {/* Runs Table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Runs</CardTitle>
          {(runsError || healthError) && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                void refetchRuns();
                void refetchHealth();
              }}
              className="gap-1.5 text-xs"
            >
              <RefreshCw className="h-3 w-3" /> Retry failed queries
            </Button>
          )}
        </CardHeader>
        <CardContent className="p-0">
          {runsLoading ? (
            <div className="py-12 flex items-center justify-center text-sm text-muted-foreground gap-2">
              <RefreshCw className="w-4 h-4 animate-spin" />
              Loading runs…
            </div>
          ) : runsError ? (
            <div className="py-12 flex flex-col items-center justify-center gap-2 text-sm text-destructive">
              <AlertCircle className="w-6 h-6" />
              <p>Failed to load ingestion runs</p>
              <Button variant="outline" size="sm" onClick={() => void refetchRuns()}>
                Retry
              </Button>
            </div>
          ) : runsList.length === 0 ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              No ingestion runs recorded yet.
            </div>
          ) : (
            <div className="overflow-x-auto">
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
                  {runsList.map((r, idx) => (
                    <TableRow key={r?.id ?? `run-${idx}`}>
                      <TableCell className="text-xs">{fmtDateTime(r?.created_at)}</TableCell>
                      <TableCell className="text-xs font-mono max-w-[200px] truncate" title={r?.source ?? ""}>
                        {r?.source ?? "Unknown"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{fmtInt(r?.chunks_added ?? 0)}</TableCell>
                      <TableCell className="text-right tabular-nums text-xs">{fmtMs(r?.duration_ms ?? 0)}</TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            r?.status === "ok" ? "secondary" : r?.status === "partial" ? "outline" : "destructive"
                          }
                        >
                          {r?.status ?? "unknown"}
                        </Badge>
                        {r?.error_log && (
                          <div className="text-xs text-destructive mt-1 max-w-[250px] truncate" title={r.error_log}>
                            {r.error_log}
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={async () => {
                            if (!r?.source) return;
                            try {
                              await triggerReingest(r.source);
                              qc.invalidateQueries({ queryKey: ["admin", "ingestion"] });
                              qc.invalidateQueries({ queryKey: ["admin", "ingest-health"] });
                              toast.success(`Re-ingest queued`);
                            } catch (err) {
                              toast.error(err instanceof Error ? err.message : "Failed to queue re-ingest");
                            }
                          }}
                        >
                          <RefreshCw className="h-3 w-3" /> Re-ingest
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

