import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Activity, Cpu, HardDrive, Zap, DollarSign, ShieldCheck, RefreshCw } from 'lucide-react';
import { fetchObservabilitySummary } from '@/admin/lib/api';
import { Button } from '@/components/ui/button';

interface ObservabilitySummary {
  timestamp: number;
  uptime_s: number;
  process_rss_mb: number;
  process_cpu_pct: number;
  queue_depth: number;
  total_queries: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  error_rate_pct: number;
  total_cost_usd: number;
  budget_remaining_usd: number;
  cache_hit_rate: number;
  circuit_breaker_state: string;
  avg_faithfulness: number;
  qdrant_healthy: boolean;
  redis_healthy: boolean;
  neo4j_healthy: boolean;
}

function formatUptime(s: number): string {
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const mins = Math.floor((s % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m`;
}

function HealthDot({ healthy, label }: { healthy: boolean; label: string }) {
  return (
    <span
      role="status"
      aria-label={`${label}: ${healthy ? 'healthy' : 'unhealthy'}`}
      className={`inline-block w-2 h-2 rounded-full ${healthy ? 'bg-emerald-400' : 'bg-red-400'}`}
    />
  );
}

function HealthCard({ label, healthy, detail }: { label: string; healthy: boolean; detail?: string }) {
  return (
    <div
      className={`p-3 rounded-lg border text-sm ${
        healthy
          ? 'bg-emerald-500/10 border-emerald-500/20'
          : 'bg-red-500/10 border-red-500/20'
      }`}
    >
      <div className="flex items-center gap-2">
        <HealthDot healthy={healthy} label={label} />
        <span className="font-medium">{label}</span>
      </div>
      {detail && <div className="text-xs text-muted-foreground mt-1 ml-4">{detail}</div>}
    </div>
  );
}

function MetricItem({ label, value, icon: Icon }: { label: string; value: string; icon?: React.ComponentType<{ className?: string }> }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {Icon && <Icon className="h-3 w-3" />}
        {label}
      </div>
      <div className="text-xl font-bold tabular-nums">{value}</div>
    </div>
  );
}

export function ObservabilityDashboard() {
  const [summary, setSummary] = useState<ObservabilitySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setError(null);
      const data = await fetchObservabilitySummary();
      setSummary(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      await fetchData();
      if (!cancelled) {
        timer = setTimeout(poll, 30000);
      }
    };
    poll();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground p-8 justify-center">
        <RefreshCw className="h-4 w-4 animate-spin" />
        Loading observability data...
      </div>
    );
  }

  if (error || !summary) {
    return (
      <Card className="border-red-500/20 bg-red-500/5">
        <CardContent className="p-6 text-center text-red-400 text-sm">
          {error || 'Failed to load observability data'}
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Health Status */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <ShieldCheck className="h-4 w-4" />
            System Health
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <HealthCard label="Qdrant" healthy={summary.qdrant_healthy} />
            <HealthCard label="Redis" healthy={summary.redis_healthy} />
            <HealthCard label="Neo4j" healthy={summary.neo4j_healthy} />
            <HealthCard
              label="Circuit Breaker"
              healthy={summary.circuit_breaker_state === 'closed'}
              detail={summary.circuit_breaker_state}
            />
          </div>
        </CardContent>
      </Card>

      {/* Performance Metrics */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Activity className="h-4 w-4" />
            Performance
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-6">
            <MetricItem label="Uptime" value={formatUptime(summary.uptime_s)} icon={Activity} />
            <MetricItem label="Memory" value={`${summary.process_rss_mb.toFixed(0)} MB`} icon={HardDrive} />
            <MetricItem label="CPU" value={`${summary.process_cpu_pct.toFixed(1)}%`} icon={Cpu} />
            <MetricItem label="Queue Depth" value={summary.queue_depth.toString()} icon={Zap} />
            <MetricItem label="Total Queries" value={summary.total_queries.toLocaleString()} icon={Activity} />
          </div>
        </CardContent>
      </Card>

      {/* Latency & Error Metrics */}
      <div className="grid md:grid-cols-2 gap-6">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Latency</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-4">
              <MetricItem label="P50" value={`${summary.p50_latency_ms.toFixed(0)}ms`} />
              <MetricItem label="P95" value={`${summary.p95_latency_ms.toFixed(0)}ms`} />
              <MetricItem
                label="Error Rate"
                value={`${summary.error_rate_pct.toFixed(1)}%`}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Quality</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4">
              <MetricItem
                label="Faithfulness"
                value={`${(summary.avg_faithfulness * 100).toFixed(0)}%`}
              />
              <MetricItem
                label="Cache Hit Rate"
                value={`${(summary.cache_hit_rate * 100).toFixed(1)}%`}
              />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Cost */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <DollarSign className="h-4 w-4" />
            Cost
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-6">
            <MetricItem label="Total Spent" value={`$${summary.total_cost_usd.toFixed(2)}`} icon={DollarSign} />
            <MetricItem label="Budget Remaining" value={`$${summary.budget_remaining_usd.toFixed(2)}`} icon={DollarSign} />
            <MetricItem label="Queries Served" value={summary.total_queries.toLocaleString()} icon={Activity} />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default ObservabilityDashboard;
