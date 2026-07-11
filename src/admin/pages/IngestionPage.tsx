import { useState, useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useIngestionRuns, useIngestionHealth } from "@/admin/hooks/useAdminData";
import { triggerReingest } from "@/admin/lib/mockData";
import { submitIngestion, getIngestionStatus } from "@/admin/lib/api";
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
import { RefreshCw, Upload, Loader2, CheckCircle2, AlertCircle, Link2, Info } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

interface IngestionJob {
  status: string;
  message: string;
  progress?: number;
}

export default function IngestionPage() {
  const { data } = useIngestionRuns();
  const { data: health } = useIngestionHealth();
  const qc = useQueryClient();

  // Ingestion form state
  const [url, setUrl] = useState("");
  const [maxAccuracy, setMaxAccuracy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [activeJobs, setActiveJobs] = useState<Record<string, IngestionJob>>({});
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll for active ingestion status
  useEffect(() => {
    if (Object.keys(activeJobs).length === 0) return;

    const hasRunning = Object.values(activeJobs).some(
      (j) => j.status !== "error" && j.status !== "Complete!" && j.progress !== 1
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
            const v = val as { status?: string; message?: string; progress?: number | null };
            mapped[key] = {
              status: v.status || v.message || "processing",
              message: v.message || "",
              progress: v.progress ?? undefined,
            };
          }
          setActiveJobs((prev) => ({ ...prev, ...mapped }));

          // If all jobs are done, invalidate cache
          const allDone = Object.values(mapped).every(
            (j) => j.progress === 1 || j.status === "error"
          );
          if (allDone) {
            qc.invalidateQueries({ queryKey: ["admin", "ingestion"] });
            qc.invalidateQueries({ queryKey: ["admin", "ingest-health"] });
          }
        }
      } catch {
        // silent — backend may not be running
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
      toast.success(res.message || "Ingestion started");
      setActiveJobs((prev) => ({
        ...prev,
        [trimmed]: { status: "processing", message: "Starting...", progress: 0 },
      }));
      setUrl("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to start ingestion");
    } finally {
      setSubmitting(false);
    }
  };

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

          {/* Active Jobs */}
          {Object.keys(activeJobs).length > 0 && (
            <div className="mt-4 space-y-2">
              <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Active Jobs</p>
              {Object.entries(activeJobs).map(([jobUrl, job]) => (
                <div
                  key={jobUrl}
                  className="flex items-center gap-3 p-3 rounded-lg bg-muted/40 border border-border/40"
                >
                  {job.progress === 1 ? (
                    <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
                  ) : job.status === "error" ? (
                    <AlertCircle className="h-4 w-4 text-destructive shrink-0" />
                  ) : (
                    <Loader2 className="h-4 w-4 animate-spin text-primary shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-mono truncate">{jobUrl}</p>
                    <p className="text-[11px] text-muted-foreground">{job.message || job.status}</p>
                  </div>
                  {job.progress !== undefined && job.progress < 1 && job.status !== "error" && (
                    <Badge variant="outline" className="text-[10px] tabular-nums">
                      {Math.round(job.progress * 100)}%
                    </Badge>
                  )}
                  {job.progress === 1 && <Badge variant="secondary">Done</Badge>}
                  {job.status === "error" && <Badge variant="destructive">Error</Badge>}
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

      {/* Runs Table */}
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
