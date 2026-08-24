import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Loader2, RefreshCw, FileText, BookOpen, CheckCircle, XCircle, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import {
  listOkfEntries,
  compileOkfIndex,
  listOkfReviewQueue,
  approveOkfReview,
  rejectOkfReview,
  type OkfEntry,
  type OkfReviewItem,
} from "@/admin/lib/api";

const TYPES = ["teaching", "practice", "glossary", "qa", "reflection"];

type ReviewEntry = {
  type?: string;
  title?: string;
  body?: string;
};

function getReviewEntry(entry: unknown): ReviewEntry {
  if (!entry || typeof entry !== "object") return {};
  const e = entry as Record<string, unknown>;
  return {
    type: typeof e.type === "string" ? e.type : undefined,
    title: typeof e.title === "string" ? e.title : undefined,
    body: typeof e.body === "string" ? e.body : undefined,
  };
}

function VerifiedBadge({ verified }: { verified?: { by?: string; at?: string } }) {
  if (!verified || !verified.by) return <Badge variant="outline" className="text-amber-400 border-amber-500/30">unverified</Badge>;
  const isHuman = typeof verified.by === "string" && verified.by.startsWith("human:");
  const name = typeof verified.by === "string" ? verified.by.replace("human:", "").replace("machine:", "") : "verified";
  return (
    <Badge variant="secondary" className={isHuman ? "text-emerald-400" : "text-blue-400"}>
      {isHuman ? "✓" : "●"} {name || "verified"}
    </Badge>
  );
}

export default function OkfManagerPage() {
  const [entries, setEntries] = useState<OkfEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [compiling, setCompiling] = useState(false);
  const [typeFilter, setTypeFilter] = useState<string>("");

  const [reviewItems, setReviewItems] = useState<OkfReviewItem[]>([]);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [tab, setTab] = useState("entries");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listOkfEntries(typeFilter || undefined);
      setEntries(Array.isArray(res?.entries) ? res.entries : []);
      setTotal(typeof res?.total === "number" ? res.total : (res?.entries?.length ?? 0));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load OKF entries");
      setEntries([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [typeFilter]);

  const loadReviewQueue = useCallback(async () => {
    setReviewLoading(true);
    try {
      const items = await listOkfReviewQueue("pending");
      setReviewItems(Array.isArray(items) ? items : []);
    } catch {
      setReviewItems([]);
    } finally {
      setReviewLoading(false);
    }
  }, []);

  async function compile() {
    setCompiling(true);
    try {
      const res = await compileOkfIndex();
      toast.success(`OKF compiled → ${res?.path ?? "index"}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Compile failed");
    } finally {
      setCompiling(false);
    }
  }

  async function handleApprove(id: string) {
    try {
      const res = await approveOkfReview(id);
      const fileName = res?.file ? res.file.split("/").pop() : "entry";
      toast.success(`Approved → ${fileName ?? "entry"}`);
      loadReviewQueue();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Approve failed");
    }
  }

  async function handleReject(id: string) {
    try {
      await rejectOkfReview(id, "Rejected by admin");
      toast.success("Entry rejected");
      loadReviewQueue();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Reject failed");
    }
  }

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (tab === "review") loadReviewQueue(); }, [tab, loadReviewQueue]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <BookOpen className="w-6 h-6" /> OKF Knowledge Manager
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Open Knowledge Format entries — markdown + YAML frontmatter, compiled to an embedded index.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={tab === "review" ? loadReviewQueue : load} disabled={loading || reviewLoading}>
            {loading || reviewLoading ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <RefreshCw className="w-4 h-4 mr-1" />}
            Refresh
          </Button>
          <Button onClick={compile} disabled={compiling} className="bg-ojas hover:bg-ojas/90">
            {compiling ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <FileText className="w-4 h-4 mr-1" />}
            Compile Index
          </Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="entries">Entries ({total})</TabsTrigger>
          <TabsTrigger value="review" className="relative">
            Review Queue
            {(reviewItems ?? []).length > 0 && (
              <span className="ml-1.5 w-5 h-5 rounded-full bg-ojas text-white text-[10px] flex items-center justify-center">
                {(reviewItems ?? []).length}
              </span>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="entries">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span>All Entries</span>
                <select
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                  className="text-sm border rounded px-2 py-1 bg-background"
                >
                  <option value="">All types</option>
                  {TYPES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {(entries ?? []).length === 0 && !loading ? (
                <p className="text-sm text-muted-foreground text-center py-8">
                  No entries loaded. Click Refresh.
                </p>
              ) : (
                <div className="space-y-3">
                  {(entries ?? []).map((e, idx) => (
                    <div key={e?.title ? `${e.title}-${idx}` : `entry-${idx}`} className="border rounded-lg p-3">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <Badge variant="secondary">{e?.type ?? "entry"}</Badge>
                        <span className="font-medium">{e?.title ?? "Untitled"}</span>
                        <VerifiedBadge verified={e?.verified} />
                      </div>
                      {e?.source && <p className="text-xs text-muted-foreground">{e.source}</p>}
                      {(e?.tags?.length ?? 0) > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {(e?.tags ?? []).map((t, tIdx) => (
                            <span key={`${t}-${tIdx}`} className="text-[10px] px-1.5 py-0.5 bg-muted rounded">{t}</span>
                          ))}
                        </div>
                      )}
                      {e?.body_preview && (
                        <p className="text-xs text-muted-foreground mt-2 line-clamp-2">{e.body_preview}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="review">
          <Card>
            <CardHeader>
              <CardTitle>Pending Review ({(reviewItems ?? []).length})</CardTitle>
            </CardHeader>
            <CardContent>
              {reviewLoading ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="w-6 h-6 animate-spin text-ojas" />
                </div>
              ) : (reviewItems ?? []).length === 0 ? (
                <div className="text-center py-8 space-y-2">
                  <CheckCircle className="w-10 h-10 text-emerald-500/50 mx-auto" />
                  <p className="text-sm text-muted-foreground">No pending entries to review.</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {(reviewItems ?? []).map((item) => {
                    const entry = getReviewEntry(item?.entry_json ?? {});
                    return (
                      <div key={item.id} className="border rounded-lg p-4 space-y-3">
                        <div className="flex items-start justify-between gap-4">
                          <div className="space-y-1 flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <Badge variant="secondary">{entry.type ?? "teaching"}</Badge>
                              <span className="font-medium truncate">{entry.title ?? "Untitled"}</span>
                              <Badge variant="outline" className="text-amber-400 border-amber-500/30">
                                <AlertCircle className="w-3 h-3 mr-1" /> pending
                              </Badge>
                            </div>
                            {item.source_video_title && (
                              <p className="text-xs text-muted-foreground">
                                Source: {item.source_video_title}
                                {item.guru_slug && item.guru_slug !== "default" && ` · ${item.guru_slug}`}
                              </p>
                            )}
                          </div>
                          <div className="flex gap-2 shrink-0">
                            <Button size="sm" variant="default" className="bg-emerald-600 hover:bg-emerald-700 h-8 px-3 text-xs"
                              onClick={() => handleApprove(item.id)}>
                              <CheckCircle className="w-3.5 h-3.5 mr-1" /> Approve
                            </Button>
                            <Button size="sm" variant="destructive" className="h-8 px-3 text-xs"
                              onClick={() => handleReject(item.id)}>
                              <XCircle className="w-3.5 h-3.5 mr-1" /> Reject
                            </Button>
                          </div>
                        </div>
                        {entry.body && (
                          <p className="text-xs text-muted-foreground line-clamp-3">{entry.body}</p>
                        )}
                        {item.reviewer_notes && (
                          <p className="text-[10px] text-amber-400/70 italic">Notes: {item.reviewer_notes}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
