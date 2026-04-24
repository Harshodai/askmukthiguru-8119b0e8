import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useTriggers } from "@/admin/hooks/useAdminData";
import { Badge } from "@/components/ui/badge";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { useMemo } from "react";
import { fmtInt } from "@/admin/lib/formatters";

export default function TriggersPage() {
  const { data: triggers } = useTriggers();

  const counts = useMemo(() => {
    const map = new Map<string, number>();
    triggers?.forEach((t) => map.set(t.trigger_name, (map.get(t.trigger_name) ?? 0) + 1));
    return Array.from(map.entries()).map(([name, count]) => ({ name, count }));
  }, [triggers]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Triggers</h1>
        <p className="text-sm text-muted-foreground">
          Special flows fired during chat — Serene Mind, fallbacks, handoffs.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">By type</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={counts}>
              <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" />
              <XAxis
                dataKey="name"
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              />
              <YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} />
              <Tooltip
                contentStyle={{
                  background: "hsl(var(--popover))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: 8,
                  fontSize: 12,
                }}
              />
              <Bar dataKey="count" fill="hsl(var(--primary))" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Serene Mind highlight</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-3">
            <Badge className="text-lg px-3 py-1">
              {fmtInt(triggers?.filter((t) => t.trigger_name === "serene_mind").length ?? 0)}
            </Badge>
            <div className="text-sm text-muted-foreground">
              Times the Serene Mind meditation was offered in the selected window.
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
