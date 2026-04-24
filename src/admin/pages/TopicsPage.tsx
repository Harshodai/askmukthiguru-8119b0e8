import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useTopics } from "@/admin/hooks/useAdminData";
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

export default function TopicsPage() {
  const { data } = useTopics();

  const points =
    data?.map((c, i) => ({
      x: i + 1,
      y: c.avg_faithfulness,
      z: c.size,
      label: c.cluster_label,
      size: c.size,
      faith: c.avg_faithfulness,
    })) ?? [];

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
                  const p = payload?.[0]?.payload as any;
                  if (!p) return null;
                  return (
                    <div className="bg-popover border border-border rounded-md p-2 text-xs">
                      <div className="font-medium">{p.label}</div>
                      <div className="text-muted-foreground">
                        {p.size} queries · faithfulness {(p.faith * 100).toFixed(1)}%
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
            {data?.map((c) => (
              <div key={c.cluster_id} className="border border-border rounded p-2">
                <div className="font-medium">{c.cluster_label}</div>
                <div className="text-muted-foreground">{c.size} queries</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
