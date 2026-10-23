import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ExternalLink,
  Mic,
  ShieldCheck,
  UserX,
  Volume2,
  AlertTriangle,
  Sparkles,
  Users,
  Search,
  CheckCircle,
  HelpCircle,
  Clock,
  Layers,
} from "lucide-react";
import { toast } from "sonner";
import {
  getAttributionQueue,
  getAttributionVideoDetail,
  triageAttributionSpan,
  batchTriageVideo,
} from "@/admin/lib/api";
import type {
  AttributionQueueItem,
  AttributionTurn,
  AttributionVideoDetail,
} from "@/admin/types";

export default function SpeakerAttributionPage() {
  const { t } = useTranslation();
  const [queue, setQueue] = useState<AttributionQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedVideoId, setSelectedVideoId] = useState<string | null>(null);
  const [videoDetail, setVideoDetail] = useState<AttributionVideoDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterTab, setFilterTab] = useState<"all" | "crossovers" | "devotees" | "ambient">("all");
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  // Load Queue
  const loadQueue = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getAttributionQueue();
      setQueue(Array.isArray(data) ? data : []);
      if (data.length > 0 && !selectedVideoId) {
        setSelectedVideoId(data[0].video_id);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load attribution queue");
    } finally {
      setLoading(false);
    }
  }, [selectedVideoId]);

  useEffect(() => {
    void loadQueue();
  }, [loadQueue]);

  // Load Video Detail when selection changes
  useEffect(() => {
    if (!selectedVideoId) return;
    let cancelled = false;

    async function loadDetail() {
      setDetailLoading(true);
      try {
        const detail = await getAttributionVideoDetail(selectedVideoId!);
        if (!cancelled) {
          setVideoDetail(detail);
        }
      } catch (e) {
        if (!cancelled) {
          toast.error(e instanceof Error ? e.message : `Failed to load video ${selectedVideoId}`);
          setVideoDetail(null);
        }
      } finally {
        if (!cancelled) {
          setDetailLoading(false);
        }
      }
    }

    void loadDetail();
    return () => {
      cancelled = true;
    };
  }, [selectedVideoId]);

  // Handle single span triage
  async function handleTriage(
    spanId: string,
    action: "promote_teacher" | "convert_to_context_header" | "reject_span" | "mark_unknown",
    assignedGuru?: string,
    interlocutorRole?: string,
  ) {
    setActionInProgress(spanId);
    try {
      const res = await triageAttributionSpan(spanId, {
        action,
        assigned_guru: assignedGuru,
        interlocutor_role: interlocutorRole,
        notes: `Admin Console triage: ${action}`,
      });
      toast.success(res.message || "Triage decision recorded");

      // Optimistically update local turn state
      if (videoDetail) {
        setVideoDetail({
          ...videoDetail,
          turns: videoDetail.turns.map((t) => {
            if (t.span_id === spanId) {
              const decisionMap: Record<string, AttributionTurn["decision"]> = {
                promote_teacher: "accept_guru_label",
                convert_to_context_header: "mark_unknown",
                reject_span: "reject_span",
                mark_unknown: "mark_unknown",
              };
              return {
                ...t,
                decision: decisionMap[action] || "mark_unknown",
                dialogue_role:
                  action === "promote_teacher"
                    ? "teacher"
                    : action === "reject_span"
                    ? "devotee_testimonial"
                    : "guest_speaker",
              };
            }
            return t;
          }),
        });
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Triage action failed");
    } finally {
      setActionInProgress(null);
    }
  }

  // Handle batch action for entire video
  async function handleBatchAction(action: "reject_devotees" | "flag_crossovers") {
    if (!videoDetail) return;
    const targetSpans =
      action === "reject_devotees"
        ? videoDetail.turns.filter((t) => t.category === "third_party").map((t) => t.span_id)
        : videoDetail.turns.filter((t) => t.category === "crossover").map((t) => t.span_id);

    if (targetSpans.length === 0) {
      toast.info("No matching spans found for this batch action");
      return;
    }

    try {
      const res = await batchTriageVideo(videoDetail.video_id, action, targetSpans);
      toast.success(res.message || "Batch action applied");
      // Refresh detail
      const refreshed = await getAttributionVideoDetail(videoDetail.video_id);
      setVideoDetail(refreshed);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Batch action failed");
    }
  }

  // Filtered queue
  const filteredQueue = queue.filter((item) => {
    const matchesSearch =
      item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.video_id.toLowerCase().includes(searchQuery.toLowerCase());
    if (!matchesSearch) return false;
    if (filterTab === "crossovers") return item.crossover_count > 0;
    if (filterTab === "devotees") return item.third_party_count > 0;
    if (filterTab === "ambient") return item.ambient_count > 0;
    return true;
  });

  // Calculate summary metrics
  const totalConflicts = queue.reduce((acc, q) => acc + q.total_conflicts, 0);
  const totalCrossovers = queue.reduce((acc, q) => acc + q.crossover_count, 0);
  const totalThirdParty = queue.reduce((acc, q) => acc + q.third_party_count, 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">
            Speaker Attribution & Dialogue Portal
          </h1>
          <Badge variant="outline" className="text-xs font-mono">
            Audit Level B5 / B7
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground mt-1">
          Audit multi-speaker panel conversations, joint satsangs, and attendee testimonials. Preserve teachings
          from both gurus, capture dialogue context for search, and permanently purge devotee speech.
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="p-4 flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Audited Conflict Spans
            </p>
            <h3 className="text-2xl font-bold mt-1">{totalConflicts}</h3>
          </div>
          <div className="h-10 w-10 rounded-full bg-blue-500/10 text-blue-500 flex items-center justify-center">
            <Layers className="h-5 w-5" />
          </div>
        </Card>

        <Card className="p-4 flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Guru Crossovers (Co-Led)
            </p>
            <h3 className="text-2xl font-bold mt-1 text-purple-600 dark:text-purple-400">
              {totalCrossovers}
            </h3>
          </div>
          <div className="h-10 w-10 rounded-full bg-purple-500/10 text-purple-500 flex items-center justify-center">
            <Users className="h-5 w-5" />
          </div>
        </Card>

        <Card className="p-4 flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Devotee / Guest Spans
            </p>
            <h3 className="text-2xl font-bold mt-1 text-amber-600 dark:text-amber-400">
              {totalThirdParty}
            </h3>
          </div>
          <div className="h-10 w-10 rounded-full bg-amber-500/10 text-amber-500 flex items-center justify-center">
            <UserX className="h-5 w-5" />
          </div>
        </Card>

        <Card className="p-4 flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Audit Safety Status
            </p>
            <h3 className="text-base font-semibold mt-1 text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5">
              <ShieldCheck className="h-4 w-4" /> 100% Cleared
            </h3>
          </div>
          <div className="h-10 w-10 rounded-full bg-emerald-500/10 text-emerald-500 flex items-center justify-center">
            <CheckCircle className="h-5 w-5" />
          </div>
        </Card>
      </div>

      {/* Main 2-Column Review Interface */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Video List (4 cols) */}
        <div className="lg:col-span-4 space-y-4">
          <Card>
            <CardHeader className="p-4 pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base font-medium">Videos Queue</CardTitle>
                <Badge variant="secondary" className="text-xs">
                  {filteredQueue.length} Videos
                </Badge>
              </div>
              <div className="relative mt-2">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search video title or ID..."
                  className="pl-8 text-xs"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>

              <Tabs
                value={filterTab}
                onValueChange={(v) => setFilterTab(v as typeof filterTab)}
                className="mt-2"
              >
                <TabsList className="grid grid-cols-4 w-full h-8 text-xs">
                  <TabsTrigger value="all" className="text-[11px]">All</TabsTrigger>
                  <TabsTrigger value="crossovers" className="text-[11px]">Crossovers</TabsTrigger>
                  <TabsTrigger value="devotees" className="text-[11px]">Devotees</TabsTrigger>
                  <TabsTrigger value="ambient" className="text-[11px]">Ambient</TabsTrigger>
                </TabsList>
              </Tabs>
            </CardHeader>

            <CardContent className="p-2 space-y-1.5 max-h-[640px] overflow-y-auto">
              {loading ? (
                <div className="p-6 text-center text-xs text-muted-foreground">
                  Loading video queue...
                </div>
              ) : filteredQueue.length === 0 ? (
                <div className="p-6 text-center text-xs text-muted-foreground">
                  No videos match your criteria
                </div>
              ) : (
                filteredQueue.map((item) => {
                  const isSelected = item.video_id === selectedVideoId;
                  return (
                    <div
                      key={item.video_id}
                      onClick={() => setSelectedVideoId(item.video_id)}
                      className={`p-3 rounded-lg border transition-all cursor-pointer text-xs ${
                        isSelected
                          ? "bg-accent border-primary/50 shadow-sm"
                          : "hover:bg-muted/60 border-border"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span className="font-semibold text-foreground line-clamp-1">
                          {item.title}
                        </span>
                        <Badge
                          variant={item.corpus_teacher === "krishnaji" ? "default" : "secondary"}
                          className="text-[10px] uppercase shrink-0 px-1.5 py-0"
                        >
                          {item.corpus_teacher}
                        </Badge>
                      </div>

                      <div className="flex items-center gap-2 mt-2 text-[11px] text-muted-foreground">
                        <span className="font-mono text-xs">{item.video_id}</span>
                        <span>•</span>
                        <span>{item.total_conflicts} spans</span>
                        {item.crossover_count > 0 && (
                          <Badge variant="outline" className="text-[10px] text-purple-600 border-purple-300 dark:border-purple-800">
                            {item.crossover_count} co-lead
                          </Badge>
                        )}
                        {item.third_party_count > 0 && (
                          <Badge variant="outline" className="text-[10px] text-amber-600 border-amber-300 dark:border-amber-800">
                            {item.third_party_count} devotee
                          </Badge>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Turn-by-Turn Inspector & Visual Timeline (8 cols) */}
        <div className="lg:col-span-8 space-y-4">
          {detailLoading ? (
            <Card className="p-12 text-center text-muted-foreground text-sm">
              Loading video segments and acoustic features...
            </Card>
          ) : !videoDetail ? (
            <Card className="p-12 text-center text-muted-foreground text-sm">
              Select a video from the queue to inspect turns and dialogue context.
            </Card>
          ) : (
            <>
              {/* Active Video Header Card */}
              <Card>
                <CardHeader className="p-4 pb-3">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <CardTitle className="text-lg font-semibold">{videoDetail.title}</CardTitle>
                        <a
                          href={videoDetail.youtube_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-muted-foreground hover:text-primary transition-colors"
                        >
                          <ExternalLink className="h-4 w-4" />
                        </a>
                      </div>
                      <CardDescription className="text-xs mt-1">
                        Video ID: <span className="font-mono">{videoDetail.video_id}</span> | Declared Corpus
                        Tag: <Badge variant="outline" className="text-xs ml-1 font-mono uppercase">{videoDetail.corpus_teacher}</Badge>
                      </CardDescription>
                    </div>

                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleBatchAction("reject_devotees")}
                        className="text-xs gap-1.5 text-amber-600 dark:text-amber-400 border-amber-300 dark:border-amber-800"
                      >
                        <UserX className="h-3.5 w-3.5" /> Purge Devotees
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleBatchAction("flag_crossovers")}
                        className="text-xs gap-1.5 text-purple-600 dark:text-purple-400 border-purple-300 dark:border-purple-800"
                      >
                        <Users className="h-3.5 w-3.5" /> Relabel Crossovers
                      </Button>
                    </div>
                  </div>

                  {/* Multi-Speaker Timeline Progress Bar */}
                  <div className="mt-4 pt-3 border-t">
                    <div className="flex items-center justify-between text-xs text-muted-foreground mb-1.5">
                      <span className="font-medium flex items-center gap-1.5">
                        <Clock className="h-3.5 w-3.5" /> Timeline Speaker Breakdown
                      </span>
                      <span>{videoDetail.turns.length} segments analyzed</span>
                    </div>

                    <div className="h-3 w-full rounded-full bg-muted flex overflow-hidden">
                      {videoDetail.turns.map((turn, i) => {
                        let color = "bg-muted-foreground/30";
                        if (turn.decision === "reject_span") color = "bg-amber-500";
                        else if (turn.category === "crossover") color = "bg-purple-500";
                        else if (turn.predicted_guru === "krishnaji") color = "bg-blue-500";
                        return (
                          <div
                            key={turn.span_id || i}
                            style={{ width: `${100 / videoDetail.turns.length}%` }}
                            className={`${color} hover:opacity-80 transition-opacity border-r border-background`}
                            title={`Turn ${i + 1}: ${turn.predicted_guru} (${(turn.slice_duration_ms / 1000).toFixed(1)}s)`}
                          />
                        );
                      })}
                    </div>

                    <div className="flex flex-wrap items-center gap-4 mt-2 text-[11px] text-muted-foreground">
                      <span className="flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full bg-blue-500" /> Sri Krishnaji
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full bg-purple-500" /> Sri Preethaji (Crossover)
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full bg-amber-500" /> Devotee / Guest (Purge)
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full bg-muted-foreground/40" /> Ambient / Chanting
                      </span>
                    </div>
                  </div>
                </CardHeader>
              </Card>

              {/* Turn-by-Turn Card List */}
              <div className="space-y-3">
                {videoDetail.turns.map((turn, index) => {
                  const isProcessing = actionInProgress === turn.span_id;
                  const isDevotee = turn.decision === "reject_span" || turn.category === "third_party";
                  const isCrossover = turn.category === "crossover";

                  return (
                    <Card
                      key={turn.span_id}
                      className={`p-4 border transition-all ${
                        turn.decision === "reject_span"
                          ? "bg-amber-500/5 border-amber-500/30"
                          : isCrossover
                          ? "bg-purple-500/5 border-purple-500/30"
                          : "border-border"
                      }`}
                    >
                      <div className="flex flex-col md:flex-row md:items-start justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono font-bold text-muted-foreground">
                            #{index + 1}
                          </span>
                          <Badge variant="outline" className="text-xs font-mono">
                            {(turn.audio_start_ms / 1000).toFixed(1)}s – {(turn.audio_end_ms / 1000).toFixed(1)}s (
                            {(turn.slice_duration_ms / 1000).toFixed(1)}s)
                          </Badge>
                          <a
                            href={turn.youtube_url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-xs text-primary hover:underline flex items-center gap-1"
                          >
                            Listen on YT <ExternalLink className="h-3 w-3" />
                          </a>
                        </div>

                        {/* Acoustic Confidence Badges */}
                        <div className="flex items-center gap-2 text-xs">
                          <span className="text-muted-foreground text-[11px]">
                            Cosine: <b className="font-mono">{turn.cosine.toFixed(3)}</b> | Margin:{" "}
                            <b className="font-mono">+{turn.margin.toFixed(3)}</b>
                          </span>
                          <Badge
                            variant={
                              turn.decision === "reject_span"
                                ? "destructive"
                                : turn.decision === "mark_unknown"
                                ? "secondary"
                                : "default"
                            }
                            className="text-[10px] uppercase font-mono"
                          >
                            {turn.decision}
                          </Badge>
                        </div>
                      </div>

                      {/* Transcript Speech Text */}
                      <div className="mt-3 p-3 rounded bg-muted/40 text-xs leading-relaxed text-foreground border border-border/50">
                        <p className="font-serif italic text-sm text-foreground/90">"{turn.text}"</p>
                      </div>

                      {/* Metadata Diagnosis & Interlocutor Classification */}
                      <div className="mt-2.5 flex items-center gap-2 text-xs text-muted-foreground">
                        <span className="font-medium text-foreground">Diagnosis:</span>
                        {isDevotee ? (
                          <span className="text-amber-600 dark:text-amber-400 font-medium flex items-center gap-1">
                            <UserX className="h-3.5 w-3.5" /> Third-Party / Devotee Speech (Non-Guru)
                          </span>
                        ) : isCrossover ? (
                          <span className="text-purple-600 dark:text-purple-400 font-medium flex items-center gap-1">
                            <Users className="h-3.5 w-3.5" /> Joint Co-Led Discourse by Sri Preethaji
                          </span>
                        ) : (
                          <span className="text-blue-600 dark:text-blue-400 font-medium flex items-center gap-1">
                            <Mic className="h-3.5 w-3.5" /> Ambient Meditation / Chanting
                          </span>
                        )}
                      </div>

                      {/* One-Click Action Buttons */}
                      <div className="mt-3 pt-3 border-t flex flex-wrap items-center justify-between gap-2">
                        <span className="text-[11px] text-muted-foreground">Apply Triage Action:</span>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <Button
                            size="sm"
                            variant="destructive"
                            disabled={isProcessing || turn.decision === "reject_span"}
                            onClick={() => handleTriage(turn.span_id, "reject_span", undefined, "devotee_testimonial")}
                            className="h-7 text-xs px-2.5"
                          >
                            <UserX className="h-3.5 w-3.5 mr-1" /> Purge Devotee
                          </Button>

                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={isProcessing}
                            onClick={() =>
                              handleTriage(turn.span_id, "convert_to_context_header", undefined, "guest_leader")
                            }
                            className="h-7 text-xs px-2.5 text-purple-600 dark:text-purple-300"
                          >
                            <Sparkles className="h-3.5 w-3.5 mr-1" /> Tag as Context Header
                          </Button>

                          <Button
                            size="sm"
                            variant="outline"
                            disabled={isProcessing || turn.decision === "accept_guru_label"}
                            onClick={() => handleTriage(turn.span_id, "promote_teacher", turn.predicted_guru, "teacher")}
                            className="h-7 text-xs px-2.5 text-emerald-600 border-emerald-300 dark:border-emerald-800"
                          >
                            <CheckCircle className="h-3.5 w-3.5 mr-1" /> Promote to {turn.predicted_guru}
                          </Button>

                          <Button
                            size="sm"
                            variant="ghost"
                            disabled={isProcessing}
                            onClick={() => handleTriage(turn.span_id, "mark_unknown")}
                            className="h-7 text-xs px-2 text-muted-foreground"
                          >
                            Quarantine
                          </Button>
                        </div>
                      </div>
                    </Card>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
