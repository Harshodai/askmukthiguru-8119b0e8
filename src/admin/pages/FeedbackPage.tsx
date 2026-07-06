import { useState, useMemo } from 'react';
import { ThumbsUp, ThumbsDown, Filter } from 'lucide-react';
import { loadAllFeedback, type MessageFeedback } from '@/lib/chatStorage';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

type FeedbackEntry = { messageId: string } & MessageFeedback;

const ITEMS_PER_PAGE = 10;

const FeedbackPage = () => {
  const [voteFilter, setVoteFilter] = useState<'all' | 'up' | 'down'>('all');
  const [currentPage, setCurrentPage] = useState(1);

  const entries = useMemo<FeedbackEntry[]>(() => {
    const raw = loadAllFeedback();
    return Object.entries(raw)
      .map(([messageId, fb]) => ({ messageId, ...fb }))
      .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  }, []);

  const filtered = useMemo(
    () => (voteFilter === 'all' ? entries : entries.filter((e) => e.vote === voteFilter)),
    [entries, voteFilter],
  );

  const totalPages = Math.ceil(filtered.length / ITEMS_PER_PAGE);

  const paginatedEntries = useMemo(() => {
    const start = (currentPage - 1) * ITEMS_PER_PAGE;
    return filtered.slice(start, start + ITEMS_PER_PAGE);
  }, [filtered, currentPage]);

  const upCount = entries.filter((e) => e.vote === 'up').length;
  const downCount = entries.filter((e) => e.vote === 'down').length;

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
          <p className="text-2xl font-bold mt-1">{entries.length}</p>
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
      {filtered.length === 0 ? (
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
                </tr>
              </thead>
              <tbody className="divide-y">
                {paginatedEntries.map((entry) => (
                  <tr key={entry.messageId} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      {entry.vote === 'up' ? (
                        <ThumbsUp className="w-4 h-4 text-green-500" />
                      ) : (
                        <ThumbsDown className="w-4 h-4 text-red-500" />
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {entry.tags.map((tag) => (
                          <Badge key={tag} variant="secondary" className="text-xs">
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 max-w-[200px] truncate text-muted-foreground">
                      {entry.comment || '—'}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                      {entry.messageId.slice(0, 10)}…
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {new Date(entry.timestamp).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 py-3">
              <p className="text-sm text-muted-foreground">
                Showing <span className="font-medium">{(currentPage - 1) * ITEMS_PER_PAGE + 1}</span> to{" "}
                <span className="font-medium">
                  {Math.min(currentPage * ITEMS_PER_PAGE, filtered.length)}
                </span>{" "}
                of <span className="font-medium">{filtered.length}</span> entries
              </p>
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
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default FeedbackPage;
