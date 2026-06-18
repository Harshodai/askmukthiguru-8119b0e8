import { useState, useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import { useTelemetryEvents } from "@/admin/hooks/useAdminData";
import { EmptyState } from "@/admin/components/EmptyState";
import { fmtDateTime, truncate } from "@/admin/lib/formatters";
import { Search, X, Download } from "lucide-react";

const PAGE_SIZE = 50;

const METRIC_TYPES = [
  "ai_response_time",
  "token_usage",
  "embed_latency",
  "retrieval_latency",
  "rerank_latency",
  "llm_latency",
  "judge_latency",
  "guardrails_in",
  "guardrails_out",
];

function csvEscape(v: unknown): string {
  const s = String(v ?? "");
  return s.includes(",") || s.includes('"') || s.includes("\n")
    ? `"${s.replace(/"/g, '""')}"`
    : s;
}

export default function TelemetryPage() {
  const [search, setSearch] = useState("");
  const [userId, setUserId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [metricType, setMetricType] = useState<string | undefined>();
  const [page, setPage] = useState(0);

  const { data, isLoading } = useTelemetryEvents({
    user_id: userId || undefined,
    session_id: sessionId || undefined,
    metric_type: metricType,
    user_message_id: search || undefined,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });

  const totalPages = data ? Math.ceil((data.count ?? 0) / PAGE_SIZE) : 0;

  const clearFilters = useCallback(() => {
    setSearch("");
    setUserId("");
    setSessionId("");
    setMetricType(undefined);
    setPage(0);
  }, []);

  const hasFilters = !!search || !!userId || !!sessionId || !!metricType;

  const handleExportCSV = useCallback(() => {
    if (!data?.data?.length) return;
    const rows = data.data;
    const headers = ["Time", "User ID", "Session ID", "Message ID", "Metric Type", "Metric Value", "Tags"];
    const csv = [
      headers.join(","),
      ...rows.map((r) =>
        [
          csvEscape(r.created_at),
          csvEscape(r.user_id),
          csvEscape(r.session_id),
          csvEscape(r.user_message_id),
          csvEscape(r.metric_type),
          r.metric_value,
          csvEscape(JSON.stringify(r.tags ?? {})),
        ].join(","),
      ),
    ].join("\n");

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `telemetry_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [data]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Telemetry Events</h1>
          <p className="text-sm text-muted-foreground">
            Raw telemetry events — AI response times, token usage, and pipeline latencies.
          </p>
        </div>
        {data && data.data.length > 0 && (
          <Button variant="outline" size="sm" onClick={handleExportCSV}>
            <Download className="h-4 w-4 mr-1" />
            Export CSV
          </Button>
        )}
      </div>

      {/* Filter bar */}
      <Card>
        <CardContent className="p-4 grid md:grid-cols-12 gap-3 items-end">
          <div className="md:col-span-3">
            <label className="text-xs text-muted-foreground">Search message ID</label>
            <div className="relative mt-1">
              <Search className="h-4 w-4 absolute left-2 top-2.5 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(0); }}
                className="pl-8"
                placeholder="msg_abc123…"
              />
            </div>
          </div>

          <div className="md:col-span-2">
            <label className="text-xs text-muted-foreground">User ID</label>
            <Input
              value={userId}
              onChange={(e) => { setUserId(e.target.value); setPage(0); }}
              className="mt-1 font-mono text-xs"
              placeholder="uuid…"
            />
          </div>

          <div className="md:col-span-2">
            <label className="text-xs text-muted-foreground">Session ID</label>
            <Input
              value={sessionId}
              onChange={(e) => { setSessionId(e.target.value); setPage(0); }}
              className="mt-1 font-mono text-xs"
              placeholder="uuid…"
            />
          </div>

          <div className="md:col-span-3">
            <label className="text-xs text-muted-foreground">Metric type</label>
            <Select
              value={metricType ?? "__all__"}
              onValueChange={(v) => { setMetricType(v === "__all__" ? undefined : v); setPage(0); }}
            >
              <SelectTrigger className="mt-1">
                <SelectValue placeholder="All metrics" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All metrics</SelectItem>
                {METRIC_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>{t}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="md:col-span-2 flex justify-end gap-2">
            {hasFilters && (
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                <X className="h-4 w-4" /> Clear
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Data table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 text-sm text-muted-foreground">Loading…</div>
          ) : !data?.data?.length ? (
            <EmptyState title="No telemetry events match your filters" />
          ) : (
            <>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Time</TableHead>
                      <TableHead>Metric</TableHead>
                      <TableHead className="text-right">Value</TableHead>
                      <TableHead>Tags</TableHead>
                      <TableHead>Message ID</TableHead>
                      <TableHead>User ID</TableHead>
                      <TableHead>Session ID</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.data.map((ev) => (
                      <TableRow key={ev.id}>
                        <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                          {fmtDateTime(ev.created_at)}
                        </TableCell>
                        <TableCell className="text-xs font-mono">{ev.metric_type}</TableCell>
                        <TableCell className="text-right tabular-nums text-xs">
                          {ev.metric_type === "ai_response_time"
                            ? `${ev.metric_value.toFixed(0)}ms`
                            : ev.metric_value.toLocaleString()}
                        </TableCell>
                        <TableCell className="text-xs max-w-[160px]">
                          <span className="truncate block" title={JSON.stringify(ev.tags ?? {})}>
                            {truncate(JSON.stringify(ev.tags ?? {}), 40)}
                          </span>
                        </TableCell>
                        <TableCell className="text-xs font-mono max-w-[100px]">
                          <span className="truncate block" title={ev.user_message_id}>
                            {truncate(ev.user_message_id, 16)}
                          </span>
                        </TableCell>
                        <TableCell className="text-xs font-mono max-w-[100px]">
                          {ev.user_id ? (
                            <span className="truncate block" title={ev.user_id}>
                              {truncate(ev.user_id, 12)}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </TableCell>
                        <TableCell className="text-xs font-mono max-w-[100px]">
                          {ev.session_id ? (
                            <span className="truncate block" title={ev.session_id}>
                              {truncate(ev.session_id, 12)}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between px-4 py-3 border-t border-border">
                  <span className="text-xs text-muted-foreground">
                    {data.count} total events · page {page + 1} of {totalPages}
                  </span>
                  <Pagination>
                    <PaginationContent>
                      <PaginationItem>
                        <PaginationPrevious
                          onClick={(e) => { e.preventDefault(); setPage(Math.max(0, page - 1)); }}
                          className={page <= 0 ? "pointer-events-none opacity-50" : "cursor-pointer"}
                        />
                      </PaginationItem>
                      {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                        let pageNum: number;
                        if (totalPages <= 7) {
                          pageNum = i;
                        } else if (page < 3) {
                          pageNum = i;
                        } else if (page > totalPages - 4) {
                          pageNum = totalPages - 7 + i;
                        } else {
                          pageNum = page - 3 + i;
                        }
                        return (
                          <PaginationItem key={pageNum}>
                            <PaginationLink
                              onClick={(e) => { e.preventDefault(); setPage(pageNum); }}
                              isActive={pageNum === page}
                              className="cursor-pointer"
                            >
                              {pageNum + 1}
                            </PaginationLink>
                          </PaginationItem>
                        );
                      })}
                      <PaginationItem>
                        <PaginationNext
                          onClick={(e) => { e.preventDefault(); setPage(Math.min(totalPages - 1, page + 1)); }}
                          className={page >= totalPages - 1 ? "pointer-events-none opacity-50" : "cursor-pointer"}
                        />
                      </PaginationItem>
                    </PaginationContent>
                  </Pagination>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
