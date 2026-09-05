import { useState, useMemo } from "react";
import { motion } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  GitBranch,
  Zap,
  Activity,
  Clock,
  AlertTriangle,
  RefreshCw,
  Layers,
  ShieldCheck,
  Split,
  ChevronRight,
} from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
  PieChart,
  Pie,
  Legend,
  AreaChart,
  Area,
  CartesianGrid,
} from "recharts";
import {
  useRoutingDistribution,
  useRoutingTiers,
  useRoutingTimeseries,
  useRoutingLayers,
  useRoutingConfidence,
} from "@/admin/hooks/useAdminData";
import { EmptyState } from "@/admin/components/EmptyState";
import { useQueryClient } from "@tanstack/react-query";

interface DistributionItem {
  route_decision: string;
  count: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
}

interface TierItem {
  tier: string;
  method: string;
  count: number;
  avg_confidence: number;
  shadow_tier_distribution?: Record<string, number>;
}

interface TimeseriesItem {
  bucket: string;
  route_decision: string;
  count: number;
}

interface LayerItem {
  layer: string;
  decision_count: number;
  avg_latency_ms: number;
  top_decisions: Array<{ decision: string; count: number }>;
}

interface ConfidenceHeatmapItem {
  tier: string;
  method: string;
  buckets: Record<string, number>;
}

interface ConfidenceResponse {
  heatmap: ConfidenceHeatmapItem[];
  alert: {
    level: string;
    message: string;
    low_confidence_pct: number;
  } | null;
  total_decisions: number;
}

const HOURS_OPTIONS = [
  { label: "1h", value: 1 },
  { label: "6h", value: 6 },
  { label: "24h", value: 24 },
  { label: "7d", value: 168 },
];

const ROUTE_CATEGORY_COLORS: Record<string, string> = {
  hot_cache: "#10b981",
  vector_cache_p90: "#34d399",
  semantic_cache: "#059669",
  doctrine_cache: "#6ee7b7",
  instant_greeting: "#f59e0b",
  crisis_preempted: "#ef4444",
  bounded_comparison_short_circuit: "#eab308",
  no_context_short_circuit: "#f97316",
  query: "#3b82f6",
  factual: "#60a5fa",
  casual: "#a855f7",
  distress: "#dc2626",
  meditation: "#8b5cf6",
  adversarial: "#b91c1c",
  safety_violation: "#991b1b",
  live_logistics: "#06b6d4",
  comparative: "#6366f1",
  limited_comparison_fallback: "#d97706",
  reflective_fallback: "#d97706",
  reflective_peace_meaning_fallback: "#d97706",
  reflective_meaning_fallback: "#d97706",
  reflective_practice_fallback: "#d97706",
  grounded_partial_evidence: "#0ea5e9",
  grounded_partial_fast_tier: "#0ea5e9",
  grounded_partial_fallback: "#0ea5e9",
  official_live_web_results: "#0284c7",
  blocked: "#ef4444",
  error: "#b91c1c",
  timeout: "#f43f5e",
};


const TIER_COLORS: Record<string, string> = {
  fast: "#10b981",
  tier2_simple: "#3b82f6",
  standard: "#6366f1",
  tier3_complex: "#f59e0b",
  deep: "#ef4444",
  tier4_deep: "#b91c1c",
  unknown: "#64748b",
};

const CACHE_DECISIONS = new Set([
  "hot_cache",
  "vector_cache_p90",
  "semantic_cache",
  "doctrine_cache",
]);

export default function RoutingPage() {
  const [hours, setHours] = useState(24);
  const queryClient = useQueryClient();

  const { data: distData, isLoading: distLoading, isFetching: distFetching } = useRoutingDistribution(hours);
  const { data: tiersData, isLoading: tiersLoading } = useRoutingTiers(hours);
  const { data: tsData, isLoading: tsLoading } = useRoutingTimeseries(hours, hours > 24 ? 360 : 60);
  const { data: layersData, isLoading: layersLoading } = useRoutingLayers(hours);
  const { data: confData, isLoading: confLoading } = useRoutingConfidence(hours);

  const distribution = (distData as DistributionItem[] | undefined) || [];
  const tiers = (tiersData as TierItem[] | undefined) || [];
  const timeseries = (tsData as TimeseriesItem[] | undefined) || [];
  const layers = (layersData as LayerItem[] | undefined) || [];
  const confidence = confData as ConfidenceResponse | undefined;

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ["admin", "routing"] });
  };

  // KPI calculations
  const kpis = useMemo(() => {
    const totalRouted = distribution.reduce((sum, item) => sum + item.count, 0);
    const cacheCount = distribution
      .filter((item) => CACHE_DECISIONS.has(item.route_decision))
      .reduce((sum, item) => sum + item.count, 0);
    const cacheHitRate = totalRouted > 0 ? (cacheCount / totalRouted) * 100 : 0;

    const weightedLatencyTotal = distribution.reduce(
      (sum, item) => sum + item.avg_latency_ms * item.count,
      0
    );
    const avgLatency = totalRouted > 0 ? weightedLatencyTotal / totalRouted : 0;

    const topRoute = distribution.length > 0 ? distribution[0] : null;
    const topRoutePct = topRoute && totalRouted > 0 ? (topRoute.count / totalRouted) * 100 : 0;

    return {
      totalRouted,
      cacheHitRate,
      avgLatency,
      topRoute: topRoute ? `${topRoute.route_decision} (${topRoutePct.toFixed(1)}%)` : "—",
    };
  }, [distribution]);

  // Transform Timeseries data for stacked area chart
  const { chartData, uniqueRoutes } = useMemo(() => {
    if (!timeseries.length) return { chartData: [], uniqueRoutes: [] };

    const routesSet = new Set<string>();
    const bucketMap: Record<string, Record<string, number>> = {};

    timeseries.forEach((item) => {
      routesSet.add(item.route_decision);
      if (!bucketMap[item.bucket]) {
        bucketMap[item.bucket] = {};
      }
      bucketMap[item.bucket][item.route_decision] =
        (bucketMap[item.bucket][item.route_decision] || 0) + item.count;
    });

    const formatted = Object.keys(bucketMap)
      .sort()
      .map((b) => {
        const d = new Date(b);
        const timeLabel =
          hours > 24
            ? d.toLocaleDateString([], { month: "short", day: "numeric" }) +
              " " +
              d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
            : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        return {
          time: timeLabel,
          ...bucketMap[b],
        };
      });

    return { chartData: formatted, uniqueRoutes: Array.from(routesSet) };
  }, [timeseries, hours]);

  // Aggregate tiers by tier name for PieChart
  const tierPieData = useMemo(() => {
    const map: Record<string, number> = {};
    tiers.forEach((item) => {
      map[item.tier] = (map[item.tier] || 0) + item.count;
    });
    return Object.entries(map).map(([name, value]) => ({ name, value }));
  }, [tiers]);

  // Shadow tier data
  const shadowTierPieData = useMemo(() => {
    const map: Record<string, number> = {};
    tiers.forEach((item) => {
      if (item.shadow_tier_distribution) {
        Object.entries(item.shadow_tier_distribution).forEach(([sTier, count]) => {
          map[sTier] = (map[sTier] || 0) + count;
        });
      }
    });
    return Object.entries(map).map(([name, value]) => ({ name, value }));
  }, [tiers]);

  const isLoading = distLoading || tiersLoading || tsLoading;

  return (
    <div className="space-y-6 pb-12">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <GitBranch className="h-6 w-6 text-primary" />
            Routing Analytics &amp; Decisions
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Real-time telemetry across all 7 routing layers, intent cascades, and cache tiers.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Time range selector */}
          <div className="flex items-center bg-muted p-1 rounded-lg">
            {HOURS_OPTIONS.map((opt) => (
              <Button
                key={opt.value}
                size="sm"
                variant={hours === opt.value ? "secondary" : "ghost"}
                className="h-7 text-xs px-3"
                onClick={() => setHours(opt.value)}
              >
                {opt.label}
              </Button>
            ))}
          </div>

          <Button
            size="sm"
            variant="outline"
            className="h-9 gap-1.5"
            onClick={handleRefresh}
            disabled={distFetching}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${distFetching ? "animate-spin" : ""}`} />
            <span className="hidden sm:inline">Refresh</span>
          </Button>
        </div>
      </div>

      {/* Confidence Alert Banner */}
      {confidence?.alert && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-amber-900 dark:text-amber-200 flex items-start gap-3"
        >
          <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <h4 className="text-sm font-semibold">Routing Confidence Warning</h4>
            <p className="text-xs opacity-90">{confidence.alert.message}</p>
          </div>
        </motion.div>
      )}

      {/* North Star KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Total Queries Routed
            </CardTitle>
            <Activity className="h-4 w-4 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {isLoading ? "—" : kpis.totalRouted.toLocaleString()}
            </div>
            <p className="text-xs text-muted-foreground mt-1">In last {hours} hours</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Cache Hit Rate
            </CardTitle>
            <Zap className="h-4 w-4 text-emerald-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {isLoading ? "—" : `${kpis.cacheHitRate.toFixed(1)}%`}
            </div>
            <p className="text-xs text-muted-foreground mt-1">Hot, P90, Exact, &amp; Doctrine</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Avg Routing Latency
            </CardTitle>
            <Clock className="h-4 w-4 text-indigo-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {isLoading ? "—" : `${kpis.avgLatency.toFixed(1)} ms`}
            </div>
            <p className="text-xs text-muted-foreground mt-1">End-to-end pipeline response</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Dominant Route
            </CardTitle>
            <Split className="h-4 w-4 text-amber-500" />
          </CardHeader>
          <CardContent>
            <div className="text-xl font-bold truncate">
              {isLoading ? "—" : kpis.topRoute}
            </div>
            <p className="text-xs text-muted-foreground mt-1">Top destination share</p>
          </CardContent>
        </Card>
      </div>

      {/* Main Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Route Decision Distribution (BarChart) */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base font-semibold flex items-center justify-between">
              <span>Route Decision Distribution</span>
              <span className="text-xs font-normal text-muted-foreground">Volume &amp; Latency</span>
            </CardTitle>
            <CardDescription className="text-xs">
              Queries handled by each cache tier, short-circuit, and graph route.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {distribution.length === 0 ? (
              <EmptyState title="No routing decisions yet" hint="Run some chat queries to see data" />
            ) : (
              <div className="h-[280px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={distribution.slice(0, 10)}
                    layout="vertical"
                    margin={{ top: 5, right: 30, left: 120, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                    <XAxis type="number" />
                    <YAxis
                      dataKey="route_decision"
                      type="category"
                      tick={{ fontSize: 11 }}
                      width={110}
                    />
                    <Tooltip
                      formatter={(val: number, name: string) => [
                        name === "count" ? `${val} queries` : `${val} ms`,
                        name === "count" ? "Volume" : "Avg Latency",
                      ]}
                    />
                    <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                      {distribution.slice(0, 10).map((entry, idx) => (
                        <Cell
                          key={`cell-${idx}`}
                          fill={ROUTE_CATEGORY_COLORS[entry.route_decision] || "#64748b"}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Query Tier Breakdown (PieChart) */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-semibold flex items-center justify-between">
              <span>Query Tier Split</span>
              <span className="text-xs font-normal text-muted-foreground">Complexity</span>
            </CardTitle>
            <CardDescription className="text-xs">
              Fast, simple, complex, and deep tier allocation.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {tierPieData.length === 0 ? (
              <EmptyState title="No tier data" hint="Waiting for router decisions" />
            ) : (
              <div className="h-[280px] w-full flex flex-col items-center justify-center">
                <ResponsiveContainer width="100%" height={210}>
                  <PieChart>
                    <Pie
                      data={tierPieData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      innerRadius={50}
                      outerRadius={80}
                      paddingAngle={4}
                    >
                      {tierPieData.map((entry, idx) => (
                        <Cell
                          key={`tier-cell-${idx}`}
                          fill={TIER_COLORS[entry.name] || "#64748b"}
                        />
                      ))}
                    </Pie>
                    <Tooltip formatter={(val: number) => [`${val} queries`, "Count"]} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex flex-wrap items-center justify-center gap-3 text-xs text-muted-foreground mt-2">
                  {tierPieData.map((t) => (
                    <div key={t.name} className="flex items-center gap-1.5">
                      <div
                        className="w-2.5 h-2.5 rounded-full"
                        style={{ backgroundColor: TIER_COLORS[t.name] || "#64748b" }}
                      />
                      <span>{t.name}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Timeseries Stacked Area Chart */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">Routing Timeseries Trend</CardTitle>
          <CardDescription className="text-xs">
            Volume of routing decisions over time in {hours > 24 ? "6-hour" : "1-hour"} intervals.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {chartData.length === 0 ? (
            <EmptyState title="No timeseries data" hint="Check back after more queries are logged" />
          ) : (
            <div className="h-[260px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                  <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  {uniqueRoutes.map((routeKey) => (
                    <Area
                      key={routeKey}
                      type="monotone"
                      dataKey={routeKey}
                      stackId="1"
                      stroke={ROUTE_CATEGORY_COLORS[routeKey] || "#64748b"}
                      fill={ROUTE_CATEGORY_COLORS[routeKey] || "#64748b"}
                      fillOpacity={0.6}
                    />
                  ))}
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Layer Statistics & Shadow Mode Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Layer Performance Table */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <Layers className="h-4 w-4 text-primary" />
              Pipeline Layer Performance
            </CardTitle>
            <CardDescription className="text-xs">
              Requests resolved at each architectural stage before fallback.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {layers.length === 0 ? (
              <EmptyState title="No layer stats" hint="Layer data will populate as queries run" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border/60 text-muted-foreground text-left">
                      <th className="pb-2 font-medium">Layer</th>
                      <th className="pb-2 font-medium text-right">Decisions</th>
                      <th className="pb-2 font-medium text-right">Avg Latency</th>
                      <th className="pb-2 font-medium pl-4">Top Outcomes</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/30">
                    {layers.map((l) => (
                      <tr key={l.layer} className="hover:bg-muted/40 transition-colors">
                        <td className="py-2.5 font-medium flex items-center gap-1.5">
                          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                          {l.layer}
                        </td>
                        <td className="py-2.5 text-right font-semibold">
                          {l.decision_count.toLocaleString()}
                        </td>
                        <td className="py-2.5 text-right text-muted-foreground">
                          {l.avg_latency_ms} ms
                        </td>
                        <td className="py-2.5 pl-4">
                          <div className="flex flex-wrap gap-1">
                            {l.top_decisions.map((td) => (
                              <Badge
                                key={td.decision}
                                variant="outline"
                                className="text-[10px] px-1.5 py-0"
                              >
                                {td.decision}: {td.count}
                              </Badge>
                            ))}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Shadow Tier Comparison / Confidence Grid */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-primary" />
              Shadow Mode &amp; Calibration
            </CardTitle>
            <CardDescription className="text-xs">
              A/B shadow routing agreement and classifier confidence distributions.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {shadowTierPieData.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-muted-foreground mb-2">
                  Shadow Tier Distribution (A/B)
                </h4>
                <div className="flex items-center gap-2">
                  {shadowTierPieData.map((st) => (
                    <Badge key={st.name} variant="secondary" className="text-xs">
                      {st.name}: {st.value}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            <div>
              <h4 className="text-xs font-medium text-muted-foreground mb-2">
                Classifier Confidence Heatmap
              </h4>
              {!confidence?.heatmap.length ? (
                <EmptyState title="No calibration data" hint="Will populate from router decisions" />
              ) : (
                <div className="space-y-2">
                  {confidence.heatmap.slice(0, 5).map((item, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between text-xs p-2 rounded-lg bg-muted/40"
                    >
                      <span className="font-medium">
                        {item.tier} · <span className="text-muted-foreground">{item.method}</span>
                      </span>
                      <div className="flex items-center gap-1">
                        {Object.entries(item.buckets).map(([bucket, cnt]) => (
                          <div
                            key={bucket}
                            title={`Range ${bucket}: ${cnt} calls`}
                            className="px-1.5 py-0.5 rounded text-[10px] bg-primary/10 text-primary font-mono"
                          >
                            {bucket}: {cnt}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Live Routing Feed Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">Live Routing Decision Breakdown</CardTitle>
          <CardDescription className="text-xs">
            Aggregated routing decisions with percentile latencies.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {distribution.length === 0 ? (
            <EmptyState title="No route records" hint="Run queries to view the routing audit log" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border/60 text-muted-foreground text-left">
                    <th className="pb-2 font-medium">Route Decision</th>
                    <th className="pb-2 font-medium text-right">Volume</th>
                    <th className="pb-2 font-medium text-right">Avg Latency</th>
                    <th className="pb-2 font-medium text-right">P95 Latency</th>
                    <th className="pb-2 font-medium pl-4">Classification</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/30">
                  {distribution.map((row) => (
                    <tr key={row.route_decision} className="hover:bg-muted/40 transition-colors">
                      <td className="py-2.5 font-medium flex items-center gap-2">
                        <div
                          className="w-2.5 h-2.5 rounded-full shrink-0"
                          style={{
                            backgroundColor:
                              ROUTE_CATEGORY_COLORS[row.route_decision] || "#64748b",
                          }}
                        />
                        <code className="text-xs">{row.route_decision}</code>
                      </td>
                      <td className="py-2.5 text-right font-semibold">
                        {row.count.toLocaleString()}
                      </td>
                      <td className="py-2.5 text-right text-muted-foreground">
                        {row.avg_latency_ms} ms
                      </td>
                      <td className="py-2.5 text-right text-muted-foreground">
                        {row.p95_latency_ms} ms
                      </td>
                      <td className="py-2.5 pl-4">
                        <Badge
                          variant={CACHE_DECISIONS.has(row.route_decision) ? "default" : "secondary"}
                          className="text-[10px]"
                        >
                          {CACHE_DECISIONS.has(row.route_decision)
                            ? "Cache"
                            : row.route_decision.includes("short_circuit") ||
                              row.route_decision === "instant_greeting"
                            ? "Short-Circuit"
                            : "Graph"}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
