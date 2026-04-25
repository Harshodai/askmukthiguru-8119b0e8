import { useMemo, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useQuery } from "@tanstack/react-query";
import { listLogs } from "@/admin/lib/mockData";
import { fmtDateTime } from "@/admin/lib/formatters";
import { useAdminFilters } from "@/admin/lib/filtersStore";
import { ChevronDown, ChevronRight, X } from "lucide-react";

export default function LogsPage() {
  const [level, setLevel] = useState<string | undefined>();
  const [search, setSearch] = useState("");
  const [groupedRequestId, setGroupedRequestId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const { filters } = useAdminFilters();
  const { data } = useQuery({
    queryKey: ["admin", "logs", level, search, filters.from, filters.to],
    queryFn: () => listLogs({ level, search, from: filters.from, to: filters.to }),
    refetchInterval: 5000,
  });

  const visible = useMemo(() => {
    if (!data) return [];
    if (groupedRequestId) return data.filter((l) => l.request_id === groupedRequestId);
    return data;
  }, [data, groupedRequestId]);

  const requestCounts = useMemo(() => {
    const m = new Map<string, number>();
    data?.forEach((l) => m.set(l.request_id, (m.get(l.request_id) ?? 0) + 1));
    return m;
  }, [data]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Logs</h1>
        <p className="text-sm text-muted-foreground">
          Structured app logs (auto-refresh 5s). Click a request-id to group all logs for that trace.
        </p>
      </div>
      <Card>
        <CardContent className="p-4 flex gap-2 items-end">
          <div className="flex-1">
            <label className="text-xs text-muted-foreground">Search</label>
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="message contains…"
              className="mt-1"
            />
          </div>
          <div className="w-44">
            <label className="text-xs text-muted-foreground">Level</label>
            <Select
              value={level ?? "__all__"}
              onValueChange={(v) => setLevel(v === "__all__" ? undefined : v)}
            >
              <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All</SelectItem>
                <SelectItem value="debug">debug</SelectItem>
                <SelectItem value="info">info</SelectItem>
                <SelectItem value="warn">warn</SelectItem>
                <SelectItem value="error">error</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {groupedRequestId && (
            <Button variant="outline" size="sm" onClick={() => setGroupedRequestId(null)}>
              <X className="h-4 w-4" /> Clear group
            </Button>
          )}
        </CardContent>
      </Card>

      {groupedRequestId && (
        <div className="text-xs text-muted-foreground">
          Showing {visible.length} log(s) for request <code>{groupedRequestId}</code>.
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          <div className="font-mono text-xs divide-y divide-border max-h-[60vh] overflow-y-auto">
            {visible.map((l) => {
              const isOpen = expanded.has(String(l.id));
              const hasContext = Object.keys(l.context).length > 0;
              return (
                <div key={l.id} className="px-3 py-1.5">
                  <div className="flex gap-3 items-center">
                    <button
                      onClick={() => {
                        const next = new Set(expanded);
                        if (isOpen) next.delete(String(l.id));
                        else next.add(String(l.id));
                        setExpanded(next);
                      }}
                      className="text-muted-foreground"
                    >
                      {hasContext ? (isOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />) : <span className="inline-block w-3" />}
                    </button>
                    <span className="text-muted-foreground tabular-nums shrink-0">
                      {fmtDateTime(l.created_at)}
                    </span>
                    <Badge
                      variant={
                        l.level === "error"
                          ? "destructive"
                          : l.level === "warn"
                            ? "outline"
                            : "secondary"
                      }
                      className="h-4 text-[10px]"
                    >
                      {l.level}
                    </Badge>
                    <span className="flex-1">{l.message}</span>
                    <button
                      onClick={() => setGroupedRequestId(l.request_id)}
                      className="text-muted-foreground hover:text-primary"
                      title={`Group ${requestCounts.get(l.request_id) ?? 1} log(s) by this request`}
                    >
                      {l.request_id}
                    </button>
                  </div>
                  {isOpen && hasContext && (
                    <pre className="mt-1 ml-6 p-2 bg-muted/30 rounded text-[10px] overflow-x-auto">
                      {JSON.stringify(l.context, null, 2)}
                    </pre>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
