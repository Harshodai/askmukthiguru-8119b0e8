import { useState } from "react";
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
import { useQuery } from "@tanstack/react-query";
import { listLogs } from "@/admin/lib/mockData";
import { fmtDateTime } from "@/admin/lib/formatters";
import { useAdminFilters } from "@/admin/lib/filtersStore";

export default function LogsPage() {
  const [level, setLevel] = useState<string | undefined>();
  const [search, setSearch] = useState("");
  const { filters } = useAdminFilters();
  const { data } = useQuery({
    queryKey: ["admin", "logs", level, search, filters.from, filters.to],
    queryFn: () => listLogs({ level, search, from: filters.from, to: filters.to }),
    refetchInterval: 5000,
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Logs</h1>
        <p className="text-sm text-muted-foreground">
          Structured app logs (auto-refresh 5s).
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
              <SelectTrigger className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All</SelectItem>
                <SelectItem value="debug">debug</SelectItem>
                <SelectItem value="info">info</SelectItem>
                <SelectItem value="warn">warn</SelectItem>
                <SelectItem value="error">error</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <div className="font-mono text-xs divide-y divide-border max-h-[60vh] overflow-y-auto">
            {data?.map((l) => (
              <div key={l.id} className="px-3 py-1.5 flex gap-3">
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
                <span className="text-muted-foreground">{l.request_id}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
