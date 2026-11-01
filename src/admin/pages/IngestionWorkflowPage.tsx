import { useCallback, useEffect, useRef, useState } from "react";
import { Search, Youtube, Activity } from "lucide-react";
import { toast } from "sonner";
import { IngestionWorkflowDAG, type IngestionJobView } from "@/admin/components/IngestionWorkflowDAG";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { getFirstPersonIngestJob, listVideoReview } from "@/admin/lib/api";
import { normalizeJobPhase, stageForDisplay, stageToNodeId } from "@/admin/lib/ingestionStages";
import { rowToVideoContext } from "@/admin/lib/videoContext";
import type { VideoReviewRow } from "@/admin/types";

const POLL_MS = 2500;
const LIST_LIMIT = 100;
const SEARCH_DEBOUNCE_MS = 300;
// A single dropped poll is not a dead job; give up only after repeated failures.
const MAX_POLL_FAILURES = 3;

export default function IngestionWorkflowPage() {
  const [rows, setRows] = useState<VideoReviewRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  // Held as a row, not an id, so filtering the list never blanks the DAG.
  const [selected, setSelected] = useState<VideoReviewRow | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const [jobIdInput, setJobIdInput] = useState("");
  const [trackedJobId, setTrackedJobId] = useState<string | null>(null);
  // Bumped on every Track click so re-tracking the same id restarts the poll.
  const [trackNonce, setTrackNonce] = useState(0);
  const [jobVideoUrl, setJobVideoUrl] = useState<string | null>(null);
  const lastStageRef = useRef<string | null>(null);
  const [job, setJob] = useState<IngestionJobView | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async (q = "") => {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await listVideoReview({ limit: LIST_LIMIT, q: q.trim() || undefined });
      setRows(res.rows);
      setTotal(res.total);
      setSelected(
        (current) => res.rows.find((r) => r.video_id === current?.video_id) ?? current ?? res.rows[0] ?? null,
      );
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Failed to load videos");
    } finally {
      setLoading(false);
    }
  }, []);

  // Search runs on the server so videos past the first page stay reachable.
  useEffect(() => {
    const handle = setTimeout(() => void load(searchQuery), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [load, searchQuery]);

  // Poll the tracked job until it reaches a terminal state. A fetch failure stops the poll
  // and is shown, so a dead endpoint never looks like a job that is still running.
  useEffect(() => {
    if (!trackedJobId) return undefined;
    let cancelled = false;
    let failures = 0;
    lastStageRef.current = null;

    const stopPolling = () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };

    const tick = async () => {
      try {
        const res = await getFirstPersonIngestJob(trackedJobId);
        if (cancelled) return;
        failures = 0;
        setJobError(null);
        setJobVideoUrl(res.video_url ?? null);
        if (stageToNodeId(res.stage)) lastStageRef.current = res.stage ?? null;
        setJob({
          jobId: res.job_id,
          status: res.status,
          stage: stageForDisplay(res.status, res.stage, lastStageRef.current),
          progressPct: res.progress_pct,
          errorMessage: res.error_message,
          updatedAt: res.updated_at,
        });
        if (normalizeJobPhase(res.status) !== "running") stopPolling();
      } catch (e) {
        if (cancelled) return;
        failures += 1;
        setJobError(e instanceof Error ? e.message : "Could not read the job status");
        if (failures >= MAX_POLL_FAILURES) stopPolling();
      }
    };

    void tick();
    pollRef.current = setInterval(() => void tick(), POLL_MS);
    return () => {
      cancelled = true;
      stopPolling();
    };
  }, [trackedJobId, trackNonce]);

  const startTracking = () => {
    const id = jobIdInput.trim();
    if (!id) return;
    setJob(null);
    setJobError(null);
    setTrackedJobId(id);
    setTrackNonce((n) => n + 1);
    toast.success("Tracking job");
  };

  const stopTracking = () => {
    setTrackedJobId(null);
    setJob(null);
    setJobError(null);
    setJobVideoUrl(null);
  };

  const selectedId = selected?.video_id ?? null;
  // The status endpoint knows the job's source URL, not which row is selected here.
  const jobMismatch =
    job != null && jobVideoUrl != null && selectedId != null && !jobVideoUrl.includes(selectedId);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          <Youtube className="w-5 h-5 text-red-500 shrink-0" />
          <h2 className="text-sm font-semibold text-foreground">Select video:</h2>
          <div className="flex items-center gap-1.5 flex-wrap">
            {rows.slice(0, 12).map((r) => (
              <Button
                key={r.video_id}
                size="sm"
                variant={selectedId === r.video_id ? "default" : "outline"}
                onClick={() => setSelected(r)}
                className="text-xs h-8 font-mono"
                title={r.title}
              >
                {r.video_id}
              </Button>
            ))}
            {total > 12 && (
              <span className="text-xs text-muted-foreground">
                Showing 12 of {total}. Use the filter to find others.
              </span>
            )}
          </div>
        </div>

        <div className="relative w-64">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-muted-foreground" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Filter by id, title or channel"
            className="h-8 pl-8 text-xs"
            aria-label="Filter videos"
          />
        </div>
      </div>

      <Card>
        <CardContent className="p-3 flex items-center gap-2 flex-wrap">
          <Activity className="w-4 h-4 text-primary" />
          <span className="text-xs font-semibold">Track a running job</span>
          <Input
            value={jobIdInput}
            onChange={(e) => setJobIdInput(e.target.value)}
            placeholder="First-person ingest job id"
            className="h-8 w-72 text-xs font-mono"
            aria-label="Job id"
          />
          <Button size="sm" className="h-8 text-xs" onClick={startTracking} disabled={!jobIdInput.trim()}>
            Track
          </Button>
          {trackedJobId && (
            <Button size="sm" variant="outline" className="h-8 text-xs" onClick={stopTracking}>
              Stop tracking
            </Button>
          )}
          {jobError && <span className="text-xs text-red-600 dark:text-red-400">{jobError}</span>}
          {jobMismatch && (
            <span className="text-xs text-amber-600 dark:text-amber-400" data-testid="job-mismatch">
              This job is for {jobVideoUrl}, not the selected video.
            </span>
          )}
        </CardContent>
      </Card>

      {loading && <p className="text-xs text-muted-foreground">Loading videos…</p>}
      {loadError && (
        <p className="text-xs text-red-600 dark:text-red-400">
          {loadError}{" "}
          <Button variant="link" size="sm" onClick={() => void load(searchQuery)}>
            Retry
          </Button>
        </p>
      )}

      <IngestionWorkflowDAG
        videoContext={selected ? rowToVideoContext(selected) : undefined}
        job={job}
        onRefresh={() => void load(searchQuery)}
        onDecisionSaved={() => void load(searchQuery)}
      />
    </div>
  );
}
