import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  getRuns,
  getActiveRun,
  computeStats,
  clearRuns,
  type AuthRun,
  type AuthStats,
} from '@/lib/authTelemetry';
import { Activity, AlertTriangle, CheckCircle2, Clock, RefreshCw, Trash2 } from 'lucide-react';
import { usePageMeta } from '@/hooks/usePageMeta';

const fmtMs = (ms: number | null): string => {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
};

const fmtTime = (epoch: number): string => new Date(epoch).toLocaleTimeString();

const SLOW_THRESHOLD_MS = 5000; // anything over 5s is flagged "slow"

const StatusBadge = ({ status }: { status: AuthRun['status'] }) => {
  if (status === 'ok') return <Badge className="bg-emerald-500/15 text-emerald-300 border-emerald-500/30">OK</Badge>;
  if (status === 'error') return <Badge variant="destructive">Error</Badge>;
  return <Badge variant="outline">In progress</Badge>;
};

const AuthLatencyDashboard = () => {
  usePageMeta({
    title: 'Auth Latency Dashboard — AskMukthiGuru',
    description: 'Per-step authentication latency and slow-run diagnostics for AskMukthiGuru sign-in.',
    canonical: 'https://askmukthiguru.lovable.app/auth/latency',
  });
  const [runs, setRuns] = useState<AuthRun[]>([]);
  const [active, setActive] = useState<AuthRun | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const refresh = () => {
      setRuns(getRuns());
      setActive(getActiveRun());
    };
    refresh();
    const id = window.setInterval(refresh, 2000);
    return () => window.clearInterval(id);
  }, [tick]);

  const stats: AuthStats = useMemo(() => computeStats(runs), [runs]);

  const slowRuns = runs.filter((r) => (r.totalMs ?? 0) > SLOW_THRESHOLD_MS);
  const errorRuns = runs.filter((r) => r.status === 'error');

  return (
    <div className="min-h-dvh bg-background text-foreground p-6 max-w-5xl mx-auto space-y-6">
      <header className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <Activity className="w-6 h-6 text-ojas" />
            Auth Latency Dashboard
          </h1>
          <p className="text-sm text-muted-foreground">
            Per-step OAuth timing captured in this browser. Open the devtools console and filter on{' '}
            <code className="text-xs bg-muted px-1 rounded">[AuthTelemetry]</code> for live logs.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setTick((t) => t + 1)}>
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              clearRuns();
              setTick((t) => t + 1);
            }}
          >
            <Trash2 className="w-4 h-4 mr-1" /> Clear
          </Button>
          <Link to="/auth"><Button size="sm">Back to Sign-in</Button></Link>
        </div>
      </header>

      {active && (
        <Card className="p-4 border-ojas/40 bg-ojas/5">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Clock className="w-4 h-4 animate-pulse text-ojas" />
            Sign-in in progress · {active.provider} · started {fmtTime(active.startedAt)}
          </div>
          <ol className="mt-3 space-y-1 text-xs">
            {active.steps.map((s, i) => (
              <li key={i} className="flex items-center justify-between">
                <span>{s.name}</span>
                <span className={s.status === 'error' ? 'text-destructive' : 'text-muted-foreground'}>
                  {s.status} {s.durationMs != null ? `· ${fmtMs(s.durationMs)}` : ''}
                </span>
              </li>
            ))}
          </ol>
        </Card>
      )}

      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Total runs" value={String(stats.totalRuns)} />
        <Stat label="Success rate" value={`${Math.round(stats.successRate * 100)}%`} tone={stats.successRate < 0.9 && stats.totalRuns > 2 ? 'warn' : 'ok'} />
        <Stat label="P50 total" value={fmtMs(stats.p50TotalMs)} />
        <Stat label="P95 total" value={fmtMs(stats.p95TotalMs)} tone={stats.p95TotalMs > SLOW_THRESHOLD_MS ? 'warn' : 'ok'} />
      </section>

      {(slowRuns.length > 0 || errorRuns.length > 0) && (
        <Card className="p-4 border-amber-500/40 bg-amber-500/5">
          <div className="flex items-center gap-2 text-sm font-medium text-amber-200">
            <AlertTriangle className="w-4 h-4" />
            {errorRuns.length} failed · {slowRuns.length} slow ({'>'}{SLOW_THRESHOLD_MS / 1000}s)
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            If Google sign-in is consistently slow, check: network throttling, third-party cookies blocked,
            Lovable Cloud project status, or a stuck redirect from <code>oauth.lovable.app</code>.
          </p>
        </Card>
      )}

      <section>
        <h2 className="text-sm font-semibold mb-2">Per-step performance</h2>
        <Card className="divide-y divide-border/40">
          <div className="grid grid-cols-5 px-4 py-2 text-xs text-muted-foreground font-medium">
            <div>Step</div>
            <div className="text-right">Avg</div>
            <div className="text-right">P95</div>
            <div className="text-right">Errors</div>
            <div className="text-right">Samples</div>
          </div>
          {stats.perStep.length === 0 && (
            <div className="px-4 py-6 text-center text-sm text-muted-foreground">
              No data yet — sign in via /auth to capture timings.
            </div>
          )}
          {stats.perStep.map((s) => (
            <div key={s.name} className="grid grid-cols-5 px-4 py-2 text-xs">
              <div className="font-mono">{s.name}</div>
              <div className="text-right">{fmtMs(s.avgMs)}</div>
              <div className={`text-right ${s.p95Ms > SLOW_THRESHOLD_MS ? 'text-amber-400' : ''}`}>{fmtMs(s.p95Ms)}</div>
              <div className={`text-right ${s.errorRate > 0 ? 'text-destructive' : ''}`}>
                {Math.round(s.errorRate * 100)}%
              </div>
              <div className="text-right text-muted-foreground">{s.samples}</div>
            </div>
          ))}
        </Card>
      </section>

      <section>
        <h2 className="text-sm font-semibold mb-2">Recent runs</h2>
        <Card className="divide-y divide-border/40">
          {runs.length === 0 && (
            <div className="px-4 py-6 text-center text-sm text-muted-foreground">No runs captured.</div>
          )}
          {[...runs].reverse().map((run) => {
            const isOpen = expanded === run.id;
            return (
              <div key={run.id} className="px-4 py-3 text-xs">
                <button
                  onClick={() => setExpanded(isOpen ? null : run.id)}
                  className="w-full flex items-center justify-between gap-2 text-left"
                >
                  <div className="flex items-center gap-2">
                    {run.status === 'ok' ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    ) : (
                      <AlertTriangle className="w-4 h-4 text-amber-400" />
                    )}
                    <span className="font-medium">{run.provider}</span>
                    <span className="text-muted-foreground">{fmtTime(run.startedAt)}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={(run.totalMs ?? 0) > SLOW_THRESHOLD_MS ? 'text-amber-400' : ''}>
                      {fmtMs(run.totalMs)}
                    </span>
                    <StatusBadge status={run.status} />
                  </div>
                </button>
                {isOpen && (
                  <div className="mt-3 ml-6 space-y-1">
                    {run.steps.map((s, i) => (
                      <div key={i} className="flex items-start justify-between gap-2">
                        <div className="flex-1">
                          <div className="font-mono">{s.name}</div>
                          {s.error && <div className="text-destructive">{s.error}</div>}
                          {s.meta && (
                            <div className="text-muted-foreground">{JSON.stringify(s.meta)}</div>
                          )}
                        </div>
                        <div className={s.status === 'error' ? 'text-destructive' : 'text-muted-foreground'}>
                          {s.status} · {fmtMs(s.durationMs)}
                        </div>
                      </div>
                    ))}
                    <div className="text-muted-foreground pt-1 border-t border-border/30 mt-2">
                      UA: {run.userAgent}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </Card>
      </section>
    </div>
  );
};

const Stat = ({ label, value, tone = 'ok' }: { label: string; value: string; tone?: 'ok' | 'warn' }) => (
  <Card className="p-3">
    <div className="text-xs text-muted-foreground">{label}</div>
    <div className={`text-lg font-semibold ${tone === 'warn' ? 'text-amber-400' : ''}`}>{value}</div>
  </Card>
);

export default AuthLatencyDashboard;
