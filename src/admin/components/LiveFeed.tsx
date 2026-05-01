import { useState } from "react";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { useLiveFeed } from "@/admin/hooks/useAdminData";
import { fmtMs, truncate } from "@/admin/lib/formatters";
import { Activity } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function LiveFeed() {
  const [on, setOn] = useState(true);
  const { data, isFetching } = useLiveFeed(on);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base flex items-center gap-2">
          <Activity className={`h-4 w-4 ${on && isFetching ? "text-primary animate-pulse" : "text-muted-foreground"}`} />
          Live feed
        </CardTitle>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {on ? "polling 3s" : "paused"}
          <Switch checked={on} onCheckedChange={setOn} />
        </div>
      </CardHeader>
      <CardContent className="space-y-1.5 max-h-72 overflow-y-auto">
        {data?.map((e) => (
          <div
            key={e.id + e.created_at}
            className="text-xs flex items-center gap-2 border-b border-border/50 pb-1.5 last:border-0"
          >
            {e.status === 'error' ? (
              <Badge variant="destructive" className="h-4 text-[10px]">⚠</Badge>
            ) : (
              <Badge variant="secondary" className="h-4 text-[10px]">ok</Badge>
            )}
            <span className="flex-1 truncate">{truncate(e.query_text, 50)}</span>
            <span className="font-mono text-muted-foreground">{e.model.split("/").pop()}</span>
            <span className="tabular-nums text-muted-foreground">{fmtMs(e.latency_ms)}</span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
