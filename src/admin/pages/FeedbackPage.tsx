import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { ThumbsUp, ThumbsDown, Filter, ShieldAlert, ExternalLink, Activity } from 'lucide-react';
import { useFeedback } from '@/admin/hooks/useAdminData';
import { AdminPageError } from '@/admin/components/AdminPageStates';
import { TraceDrawer } from '@/admin/components/TraceDrawer';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { fmtDateTime } from '@/admin/lib/formatters';

type FeedbackEntry = {
  messageId: string;
  queryId: string;
  vote: 'up' | 'down';
  tags: string[];
  comment?: string;
  timestamp: Date;
};

const ITEMS_PER_PAGE = 10;

const FeedbackPage = () => {
  const [voteFilter, setVoteFilter] = useState<'all' | 'up' | 'down'>('all');
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedQueryId, setSelectedQueryId] = useState<string | null>(null);

  const { data: feedbackRows, isLoading, isError, error, refetch } = useFeedback(200);
  const denied =
    isError && /admin access required|session expired|not allowlisted|401|403/i.test(
      error instanceof Error ? error.message : String(error ?? ''),
    );

  const entries = useMemo<FeedbackEntry[]>(() => {
    if (!Array.isArray(feedbackRows)) return [];
    return feedbackRows.map((row) => {
      const qId = (row.metadata_json?.query_id || row.metadata_json?.trace_id || row.metadata_json?.id || row.id) as string;
      return {
        messageId: row.id,
        queryId: qId,
        vote: row.rating > 0 ? 'up' : 'down',
        tags: [],
        comment: row.feedback_text || row.comment || undefined,
        timestamp: row.created_at ? new Date(row.created_at) : new Date(0),
      };
    });
  }, [feedbackRows]);

  const filtered = useMemo(
    () => (voteFilter === 'all' ? entries : (entries ?? []).filter((e) => e?.vote === voteFilter)),
    [entries, voteFilter],
  );

  const totalPages = Math.max(1, Math.ceil((filtered?.length ?? 0) / ITEMS_PER_PAGE));

  const paginatedEntries = useMemo(() => {
    const start = (currentPage - 1) * ITEMS_PER_PAGE;
    return (filtered ?? []).slice(start, start + ITEMS_PER_PAGE);
  }, [filtered, currentPage]);

  const upCount = (entries ?? []).filter((e) => e?.vote === 'up').length;
  const downCount = (entries ?? []).filter((e) => e?.vote === 'down').length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">User Feedback</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Thumbs up/down feedback from chat users to improve persona quality and RAG retrieval.
        </p>
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-xl border bg-card p-4">
          <p className="text-sm text-muted-foreground">Total Feedback</p>
          <p className="text-2xl font-bold mt-1">{(entries ?? []).length}</p>
        </div>
        <div className="rounded-xl border bg-card p-4">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <ThumbsUp className="w-4 h-4 text-green-500" /> Positive
          </div>
          <p className="text-2xl font-bold mt-1 text-green-600">{upCount}</p>
        </div>
        <div className="rounded-xl border bg-card p-4">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <ThumbsDown className="w-4 h-4 text-red-500" /> Negative
          </div>
          <p className="text-2xl font-bold mt-1 text-red-600">{downCount}</p>
        </div>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-3">
        <Filter className="w-4 h-4 text-muted-foreground" />
        <Select
          value={voteFilter}
          onValueChange={(v) => {
            setVoteFilter(v as 'all' | 'up' | 'down');
            setCurrentPage(1);
          }}
        >
          <SelectTrigger className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All votes</SelectItem>
            <SelectItem value="up">Thumbs up</SelectItem>
            <SelectItem value="down">Thumbs down</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="text-center py-12 text-muted-foreground">Loading feedback…</div>
      ) : denied ? (
        <div className="text-center py-12 space-y-3">
          <ShieldAlert className="h-8 w-8 mx-auto text-muted-foreground opacity-60" />
          <p className="text-sm font-medium">You do not have access to this area.</p>
          <p className="text-xs text-muted-foreground">
            {error instanceof Error ? error.message : String(error ?? '')}
          </p>
          <Button variant="outline" size="sm" asChild>
            <a href="/admin/login">Admin Login</a>
          </Button>
        </div>
      ) : isError ? (
        <AdminPageError
          message={error instanceof Error ? error.message : String(error ?? '')}
          onRetry={() => refetch()}
        />
      ) : (filtered?.length ?? 0) === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          No feedback entries yet. Users can rate guru responses in the chat.
        </div>
      ) : (
        <div className="space-y-4">
          <div className="border rounded-xl overflow-hidden overflow-x-auto">
            <table className="w-full text-sm min-w-[640px]">
              <thead className="bg-muted/50">
                <tr>
                  <th className="text-left px-4 py-3 font-medium w-16">Vote</th>
                  <th className="text-left px-4 py-3 font-medium">Tags</th>
                  <th className="text-left px-4 py-3 font-medium">Comment</th>
                  <th className="text-left px-4 py-3 font-medium w-32">Message ID</th>
                  <th className="text-left px-4 py-3 font-medium w-48">Time</th>
                  <th className="text-right px-4 py-3 font-medium w-40">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {paginatedEntries.map((entry, index) => (
                  <tr
                    key={entry?.messageId || `fb-${index}`}
                    className="hover:bg-muted/30 transition-colors cursor-pointer group"
                    onClick={() => setSelectedQueryId(entry.queryId || entry.messageId)}
                    title="Click to view query trace"
                  >
                    <td className="px-4 py-3">
                      {entry?.vote === 'up' ? (
                        <ThumbsUp className="w-4 h-4 text-green-500" />
                      ) : (
                        <ThumbsDown className="w-4 h-4 text-red-500" />
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {Array.isArray(entry?.tags) && entry.tags.length > 0 ? (
                          entry.tags.map((tag, tagIndex) => (
                            <Badge key={tag || `tag-${tagIndex}`} variant="secondary" className="text-xs">
                              {tag}
                            </Badge>
                          ))
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 max-w-[200px] truncate text-muted-foreground">
                      {entry?.comment || '—'}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground group-hover:text-primary transition-colors">
                      {typeof entry?.messageId === 'string' ? `${entry.messageId.slice(0, 10)}…` : '—'}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {entry?.timestamp ? fmtDateTime(entry.timestamp instanceof Date ? entry.timestamp.toISOString() : String(entry.timestamp)) : '—'}
                    </td>
                    <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-1.5">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 text-xs px-2"
                          onClick={() => setSelectedQueryId(entry.queryId || entry.messageId)}
                        >
                          View Trace
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          asChild
                          className="h-7 text-xs px-2 text-muted-foreground hover:text-foreground"
                        >
                          <Link
                            to={`/admin/queries?traceId=${encodeURIComponent(entry.queryId || entry.messageId)}`}
                            title="Inspect in Queries page"
                          >
                            <ExternalLink className="h-3.5 w-3.5" />
                          </Link>
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4 py-3">
            <p className="text-sm text-muted-foreground">
              Showing {filtered.length > 0 ? (currentPage - 1) * ITEMS_PER_PAGE + 1 : 0} to {Math.min(currentPage * ITEMS_PER_PAGE, filtered.length)} of {filtered.length} entries
            </p>
            {totalPages > 1 && (
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={currentPage === 1}
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                >
                  Previous
                </Button>
                <span className="text-xs text-muted-foreground px-2">
                  Page {currentPage} of {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={currentPage === totalPages}
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                >
                  Next
                </Button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Deep-linked Query Trace Drawer */}
      {selectedQueryId && (
        <TraceDrawer
          queryId={selectedQueryId}
          onClose={() => setSelectedQueryId(null)}
        />
      )}
    </div>
  );
};

export default FeedbackPage;
