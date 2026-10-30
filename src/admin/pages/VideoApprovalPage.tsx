import { useCallback, useEffect, useMemo, useState } from "react";
import { ExternalLink, RefreshCw, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { getVideoReview, listVideoReview, saveVideoDecision } from "@/admin/lib/api";
import { fmtDateTime } from "@/admin/lib/formatters";
import type {
  HumanSpeakerCheck,
  VideoApprovalState,
  VideoAuditEntry,
  VideoGrade,
  VideoReviewFilters,
  VideoReviewList,
  VideoReviewRow,
} from "@/admin/types";

const PAGE_SIZE = 25;
const GRADES: VideoGrade[] = ["A", "B", "C", "D", "F"];
const SELECT_CLASS =
  "h-9 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

type ApprovalChoice = "approved" | "rejected" | "undecided";
type CheckChoice = "confirmed" | "rejected" | "none";

interface Draft {
  approval: ApprovalChoice;
  speakerCheck: CheckChoice;
  grade: VideoGrade | "";
  notes: string;
  reason: string;
}

function draftFrom(row: VideoReviewRow): Draft {
  const d = row.decision;
  return {
    approval: d?.admin_approved === true ? "approved" : d?.admin_approved === false ? "rejected" : "undecided",
    speakerCheck: d?.human_speaker_check ?? "none",
    grade: d?.grade ?? "",
    notes: d?.notes ?? "",
    reason: "",
  };
}

function gateFieldsChanged(row: VideoReviewRow, draft: Draft): boolean {
  const before = draftFrom(row);
  return before.approval !== draft.approval || before.speakerCheck !== draft.speakerCheck;
}

const STATE_LABEL: Record<VideoApprovalState, string> = {
  approved: "Approved",
  rejected: "Rejected",
  undecided: "No decision",
};

function StateBadge({ row }: { row: VideoReviewRow }) {
  const variant = row.approval_state === "rejected" ? "destructive" : row.approval_state === "approved" ? "default" : "outline";
  return (
    <div className="flex flex-wrap items-center gap-1">
      <Badge variant={variant}>{STATE_LABEL[row.approval_state]}</Badge>
      {row.decision?.human_speaker_check && (
        <Badge variant="outline">speaker {row.decision.human_speaker_check}</Badge>
      )}
      {row.decision?.grade && <Badge variant="secondary">grade {row.decision.grade}</Badge>}
      {row.serving === "blocked_by_admin" && <Badge variant="destructive">not served</Badge>}
    </div>
  );
}

function MachineCell({ row }: { row: VideoReviewRow }) {
  const m = row.machine;
  if (!row.in_v10) return <span className="text-xs text-muted-foreground">not in v10</span>;
  return (
    <div className="text-xs space-y-0.5">
      <div>
        <span className="font-medium">{m.speaker_verified_spans}</span> / {m.child_spans} spans verified
        <span className="text-muted-foreground"> ({m.speaker_status})</span>
      </div>
      <div className="text-muted-foreground">
        voice method on {m.spans_with_voice_method}
        {m.min_window_cosine !== null && <> · min window cosine {m.min_window_cosine.toFixed(2)}</>}
      </div>
      {m.source !== "live" && <div className="text-amber-600">snapshot, not live</div>}
    </div>
  );
}

function ReviewPanel({
  row,
  audit,
  onSaved,
  onClose,
}: {
  row: VideoReviewRow;
  audit: VideoAuditEntry[];
  onSaved: () => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<Draft>(() => draftFrom(row));
  const [saving, setSaving] = useState(false);
  const needsReason = gateFieldsChanged(row, draft);
  const reasonOk = !needsReason || draft.reason.trim().length >= 3;

  useEffect(() => setDraft(draftFrom(row)), [row]);

  const save = async () => {
    setSaving(true);
    try {
      await saveVideoDecision(row.video_id, {
        admin_approved: draft.approval === "approved" ? true : draft.approval === "rejected" ? false : null,
        human_speaker_check: draft.speakerCheck === "none" ? null : (draft.speakerCheck as HumanSpeakerCheck),
        grade: draft.grade === "" ? null : draft.grade,
        notes: draft.notes.trim() === "" ? null : draft.notes,
        reason: draft.reason.trim() === "" ? null : draft.reason,
      });
      toast.success("Decision saved");
      onSaved();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save the decision");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card aria-label={`Review ${row.video_id}`}>
      <CardContent className="space-y-4 p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">{row.title || row.video_id}</h2>
            <p className="text-xs text-muted-foreground">
              {row.video_id} · {row.channel}{" "}
              <a className="inline-flex items-center gap-1 underline" href={row.youtube_url} target="_blank" rel="noreferrer">
                open on YouTube <ExternalLink className="h-3 w-3" />
              </a>
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border p-3 space-y-1">
            <div className="text-xs font-semibold uppercase text-muted-foreground">Machine check (read-only)</div>
            <MachineCell row={row} />
            <p className="text-xs text-muted-foreground">
              Set by the voice-verification tools. This page never changes it.
            </p>
          </div>
          <div className="rounded-lg border p-3 space-y-1">
            <div className="text-xs font-semibold uppercase text-muted-foreground">What your decision does</div>
            <p className="text-xs text-muted-foreground">
              <b>Rejected</b> (video or speaker) stops every clip of this video being served. <b>Approved</b> only records
              your intent: a clip still has to pass every machine gate. No decision keeps today&apos;s behaviour.
            </p>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-sm space-y-1">
            <span className="block font-medium">Serve this video?</span>
            <select
              className={SELECT_CLASS + " w-full"}
              value={draft.approval}
              onChange={(e) => setDraft({ ...draft, approval: e.target.value as ApprovalChoice })}
            >
              <option value="undecided">No decision (current behaviour)</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected (do not serve)</option>
            </select>
          </label>
          <label className="text-sm space-y-1">
            <span className="block font-medium">My speaker check</span>
            <select
              className={SELECT_CLASS + " w-full"}
              value={draft.speakerCheck}
              onChange={(e) => setDraft({ ...draft, speakerCheck: e.target.value as CheckChoice })}
            >
              <option value="none">Not checked</option>
              <option value="confirmed">Confirmed: it is the teacher</option>
              <option value="rejected">Rejected: wrong speaker</option>
            </select>
          </label>
          <label className="text-sm space-y-1">
            <span className="block font-medium">Grade (info only)</span>
            <select
              className={SELECT_CLASS + " w-full"}
              value={draft.grade}
              onChange={(e) => setDraft({ ...draft, grade: e.target.value as VideoGrade | "" })}
            >
              <option value="">Not graded</option>
              {GRADES.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="text-sm space-y-1 block">
          <span className="block font-medium">Notes</span>
          <Textarea
            maxLength={2000}
            value={draft.notes}
            onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
            placeholder="What you heard, where, anything the next reviewer should know"
          />
        </label>

        <label className="text-sm space-y-1 block">
          <span className="block font-medium">
            Reason {needsReason ? <span className="text-destructive">(required for this change)</span> : "(optional)"}
          </span>
          <Input
            maxLength={500}
            value={draft.reason}
            onChange={(e) => setDraft({ ...draft, reason: e.target.value })}
            placeholder="Why are you changing the decision?"
          />
        </label>

        <div className="flex items-center gap-2">
          <Button onClick={save} disabled={saving || !reasonOk}>
            {saving ? "Saving…" : "Save decision"}
          </Button>
          {!reasonOk && <span className="text-xs text-muted-foreground">Add a reason (3+ characters).</span>}
        </div>

        <div>
          <div className="text-xs font-semibold uppercase text-muted-foreground mb-1">History</div>
          {audit.length === 0 ? (
            <p className="text-xs text-muted-foreground">No changes recorded yet.</p>
          ) : (
            <ul className="space-y-1 text-xs">
              {audit.map((a, i) => (
                <li key={`${a.ts}-${i}`} className="rounded border p-2">
                  <span className="font-medium">{fmtDateTime(a.ts)}</span> · {a.actor} ·{" "}
                  {a.after
                    ? `approved=${String(a.after.admin_approved)}, speaker=${a.after.human_speaker_check ?? "-"}, grade=${a.after.grade ?? "-"}`
                    : "decision cleared"}
                  {a.reason && <div className="text-muted-foreground">Reason: {a.reason}</div>}
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export default function VideoApprovalPage() {
  const [filters, setFilters] = useState<VideoReviewFilters>({});
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [data, setData] = useState<VideoReviewList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<{ row: VideoReviewRow; audit: VideoAuditEntry[] } | null>(null);

  const query = useMemo<VideoReviewFilters>(
    () => ({ ...filters, q: search.trim() || undefined, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
    [filters, search, page],
  );

  const load = useCallback(
    async (refresh = false) => {
      setLoading(true);
      setError(null);
      try {
        setData(await listVideoReview({ ...query, refresh: refresh || undefined }));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load videos");
      } finally {
        setLoading(false);
      }
    },
    [query],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const open = async (row: VideoReviewRow) => {
    try {
      const detail = await getVideoReview(row.video_id);
      setSelected({ row: detail.video, audit: detail.audit });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not load the video");
    }
  };

  const setFilter = (patch: Partial<VideoReviewFilters>) => {
    setPage(0);
    setFilters((f) => ({ ...f, ...patch }));
  };

  const rows = data?.rows ?? [];
  const total = data?.total ?? 0;
  const summary = data?.summary;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Video approval</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Choose which videos may be served to users. Your decision is kept apart from the machine speaker check, and every
          change is logged with who, when and why.
        </p>
        <div className="mt-2 flex items-start gap-2 rounded-xl border border-border bg-card p-3 text-xs text-muted-foreground">
          <ShieldAlert className="h-4 w-4 mt-0.5 shrink-0" />
          <span>
            Rejecting a video stops it being served within seconds. Approving never overrides a failed machine check.
            {data && !data.live && " Live evidence is unavailable: machine columns show the last inventory snapshot."}
          </span>
        </div>
      </div>

      {summary && (
        <div className="flex flex-wrap gap-2 text-xs" aria-label="Summary">
          <Badge variant="outline">{summary.videos} videos</Badge>
          <Badge variant="outline">{summary.in_v10} in v10</Badge>
          <Badge variant="outline">{summary.missing_in_v10} missing in v10</Badge>
          <Badge variant="outline">{summary.approved} approved</Badge>
          <Badge variant="outline">{summary.rejected} rejected</Badge>
          <Badge variant="outline">{summary.undecided} no decision</Badge>
        </div>
      )}

      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs space-y-1">
          <span className="block">Search</span>
          <Input
            className="h-9 w-56"
            placeholder="Title or video id"
            value={search}
            onChange={(e) => {
              setPage(0);
              setSearch(e.target.value);
            }}
          />
        </label>
        <label className="text-xs space-y-1">
          <span className="block">Channel</span>
          <select
            aria-label="Channel"
            className={SELECT_CLASS}
            value={filters.channel ?? ""}
            onChange={(e) => setFilter({ channel: e.target.value || undefined })}
          >
            <option value="">All channels</option>
            {(data?.channels ?? []).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs space-y-1">
          <span className="block">Machine speaker check</span>
          <select
            aria-label="Machine speaker check"
            className={SELECT_CLASS}
            value={filters.verified ?? ""}
            onChange={(e) => setFilter({ verified: (e.target.value || undefined) as VideoReviewFilters["verified"] })}
          >
            <option value="">Any</option>
            <option value="full">All spans verified</option>
            <option value="partial">Some spans verified</option>
            <option value="none">No spans verified</option>
          </select>
        </label>
        <label className="text-xs space-y-1">
          <span className="block">My decision</span>
          <select
            aria-label="My decision"
            className={SELECT_CLASS}
            value={filters.approved ?? ""}
            onChange={(e) => setFilter({ approved: (e.target.value || undefined) as VideoReviewFilters["approved"] })}
          >
            <option value="">Any</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="undecided">No decision</option>
          </select>
        </label>
        <label className="text-xs space-y-1">
          <span className="block">In v10</span>
          <select
            aria-label="In v10"
            className={SELECT_CLASS}
            value={filters.in_v10 === undefined ? "" : String(filters.in_v10)}
            onChange={(e) => setFilter({ in_v10: e.target.value === "" ? undefined : e.target.value === "true" })}
          >
            <option value="">Any</option>
            <option value="true">In v10</option>
            <option value="false">Missing in v10</option>
          </select>
        </label>
        <Button variant="outline" size="sm" onClick={() => void load(true)} disabled={loading}>
          <RefreshCw className="h-4 w-4 mr-1" /> Refresh
        </Button>
      </div>

      {error && (
        <div role="alert" className="rounded-xl border border-destructive/40 bg-destructive/5 p-3 text-sm">
          {error}{" "}
          <Button variant="link" size="sm" onClick={() => void load()}>
            Retry
          </Button>
        </div>
      )}

      {selected && (
        <ReviewPanel
          row={selected.row}
          audit={selected.audit}
          onClose={() => setSelected(null)}
          onSaved={() => {
            void open(selected.row);
            void load(true);
          }}
        />
      )}

      <Card>
        <CardContent className="p-0 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th className="p-3">Video</th>
                <th className="p-3">Channel</th>
                <th className="p-3">Machine speaker check</th>
                <th className="p-3">My decision</th>
                <th className="p-3" />
              </tr>
            </thead>
            <tbody>
              {loading && rows.length === 0 && (
                <tr>
                  <td className="p-3 text-muted-foreground" colSpan={5}>
                    Loading…
                  </td>
                </tr>
              )}
              {!loading && !error && rows.length === 0 && (
                <tr>
                  <td className="p-3 text-muted-foreground" colSpan={5}>
                    No videos match these filters.
                  </td>
                </tr>
              )}
              {rows.map((row) => (
                <tr key={row.video_id} className="border-t align-top">
                  <td className="p-3">
                    <div className="font-medium">{row.title || row.video_id}</div>
                    <div className="text-xs text-muted-foreground">{row.video_id}</div>
                    {row.status_note && <div className="text-xs text-amber-600">{row.status_note}</div>}
                  </td>
                  <td className="p-3 text-xs">{row.channel}</td>
                  <td className="p-3">
                    <MachineCell row={row} />
                  </td>
                  <td className="p-3">
                    <StateBadge row={row} />
                  </td>
                  <td className="p-3 text-right">
                    <Button size="sm" variant="outline" onClick={() => void open(row)}>
                      Review
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {total === 0 ? "0 videos" : `${page * PAGE_SIZE + 1}–${Math.min(total, (page + 1) * PAGE_SIZE)} of ${total}`}
        </span>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={page === 0 || loading} onClick={() => setPage((p) => p - 1)}>
            Previous
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={(page + 1) * PAGE_SIZE >= total || loading}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}
