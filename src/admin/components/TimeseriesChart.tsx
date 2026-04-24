import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import type { TimeseriesPoint } from "@/admin/types";

interface Props {
  data: TimeseriesPoint[] | undefined;
  height?: number;
  formatter?: (v: number) => string;
  color?: string;
}

export function TimeseriesChart({
  data,
  height = 220,
  formatter,
  color = "hsl(var(--primary))",
}: Props) {
  const chartData = (data ?? []).map((d) => ({
    bucket: new Date(d.bucket).toLocaleString(undefined, {
      month: "short",
      day: "2-digit",
      hour: "2-digit",
    }),
    value: d.value,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData} margin={{ top: 8, right: 16, left: 4, bottom: 4 }}>
        <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" />
        <XAxis
          dataKey="bucket"
          tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
          tickLine={false}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
          tickLine={false}
          axisLine={false}
          tickFormatter={formatter ? (v) => formatter(Number(v)) : undefined}
          width={60}
        />
        <Tooltip
          formatter={(v: number) => (formatter ? formatter(v) : v)}
          contentStyle={{
            background: "hsl(var(--popover))",
            border: "1px solid hsl(var(--border))",
            borderRadius: 8,
            fontSize: 12,
          }}
        />
        <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
