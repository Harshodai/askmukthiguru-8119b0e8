import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useTopics } from "@/admin/hooks/useAdminData";
import { EmptyState } from "@/admin/components/EmptyState";
import { AlertCircle, RefreshCw } from "lucide-react";
import {
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  Tooltip,
  CartesianGrid,
  Cell,
} from "recharts";

interface TopicPayload {
  label: string;
  size: number;
  faith: number;
}

export default function TopicsPage() {
  const { data, isLoading, isError, refetch } = useTopics();

  const points = useMemo(() => {
    return (data ?? []).map((c, i) => {
      const faith = typeof c?.avg_faithfulness === 'number' ? c.avg_faithfulness : 0;
      const size = typeof c?.size === 'number' ? c.size : 0;
      const label = c?.cluster_label ?? `Topic ${i + 1}`;
      return {
        x: i + 1,
        y: faith,
        z: size,
        label,
        size,
        faith,
      };
    });
  }, [data]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Topic clusters</h1>
        <p className="text-sm text-muted-foreground">
          Bubble = topic. Size = volume. Color = avg faithfulness.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Clusters</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="h-[400px] flex items-center justify-center text-sm text-muted-foreground gap-2">
              <RefreshCw className="w-4 h-4 animate-spin" />
              Loading topic clusters…
            </div>
          ) : isError ? (
            <div className="h-[400px] flex flex-col items-center justify-center gap-2 text-sm text-destructive">
              <AlertCircle className="w-6 h-6" />
              <p>Failed to load topic clusters</p>
              <Button variant="outline" size="sm" onClick={() => void refetch()}>
                Retry
              </Button>
            </div>
          ) : points.length === 0 ? (
            <div className="py-12">
              <EmptyState title="No topic clusters available yet" />
            </div>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={400}>
                <ScatterChart margin={{ top: 16, right: 16, left: 4, bottom: 16 }}>
                  <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" />
                  <XAxis type="number" dataKey="x" hide />
                  <YAxis
                    type="number"
                    dataKey="y"
                    domain={[0.5, 1]}
                    tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                    label={{
                      value: "Avg faithfulness",
                      angle: -90,
                      position: "insideLeft",
                      fill: "hsl(var(--muted-foreground))",
                      fontSize: 11,
                    }}
                  />
                  <ZAxis type="number" dataKey="z" range={[60, 800]} />
                  <Tooltip
                    cursor={{ strokeDasharray: "3 3" }}
                    contentStyle={{
                      background: "hsl(var(--popover))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                    content={({ payload }) => {
                      const p = payload?.[0]?.payload as TopicPayload | undefined;
                      if (!p) return null;
                      const faithPct = typeof p.faith === 'number' ? (p.faith * 100).toFixed(1) : '0.0';
                      return (
                        <div className="bg-popover border border-border rounded-md p-2 text-xs">
                          <div className="font-medium">{p.label ?? 'Topic'}</div>
                          <div className="text-muted-foreground">
                            {p.size ?? 0} queries · faithfulness {faithPct}%
                          </div>
                        </div>
                      );
                    }}
                  />
                  <Scatter data={points}>
                    {points.map((p, i) => (
                      <Cell
                        key={i}
                        fill={
                          p.faith > 0.85
                            ? "hsl(var(--secondary))"
                            : p.faith > 0.7
                              ? "hsl(var(--primary))"
                              : "hsl(var(--destructive))"
                        }
                        fillOpacity={0.7}
                      />
                    ))}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
              <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                {(data ?? []).map((c, idx) => {
                  const queryStr = c?.centroid_query
                    ? c.centroid_query.split(" ").slice(0, 2).join(" ")
                    : (c?.cluster_label ?? "");
                  const faithPct = typeof c?.avg_faithfulness === 'number'
                    ? (c.avg_faithfulness * 100).toFixed(0)
                    : '0';
                  return (
                    <a
                      key={c?.cluster_id ?? `cluster-${idx}`}
                      href={`/admin/queries?search=${encodeURIComponent(queryStr)}`}
                      className="border border-border rounded p-2 hover:bg-muted/50 transition-colors block"
                    >
                      <div className="font-medium truncate">{c?.cluster_label ?? 'Unknown Topic'}</div>
                      <div className="text-muted-foreground">{c?.size ?? 0} queries · {faithPct}%</div>
                    </a>
                  );
                })}
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

