import { useMemo } from 'react';
import { Flame, Clock, Calendar, Wind } from 'lucide-react';
import type { MeditationSession, MeditationStats } from '@/lib/meditationStorage';

interface Props {
  stats: MeditationStats;
  sessions: MeditationSession[];
}

/**
 * ChatGPT/Claude-caliber stat tiles + a compact 7-day SVG sparkline.
 * No chart library, semantic tokens only.
 */
export const ProfileStatTiles = ({ stats, sessions }: Props) => {
  const tiles = [
    { icon: Flame, label: 'Sessions', value: stats.totalSessions },
    { icon: Clock, label: 'Minutes', value: stats.totalMinutes },
    { icon: Calendar, label: 'Streak', value: `${stats.streakDays}d` },
    { icon: Wind, label: 'Breaths', value: stats.totalCycles },
  ];

  const last7 = useMemo(() => {
    const days: { label: string; minutes: number }[] = [];
    const now = new Date();
    for (let i = 6; i >= 0; i--) {
      const d = new Date(now);
      d.setHours(0, 0, 0, 0);
      d.setDate(d.getDate() - i);
      const next = new Date(d);
      next.setDate(next.getDate() + 1);
      const mins = sessions
        .filter((s) => {
          const t = new Date(s.completedAt ?? s.startedAt).getTime();
          return t >= d.getTime() && t < next.getTime() && s.completed;
        })
        .reduce((sum, s) => sum + Math.round((s.durationSeconds ?? 0) / 60), 0);
      days.push({ label: d.toLocaleDateString(undefined, { weekday: 'narrow' }), minutes: mins });
    }
    return days;
  }, [sessions]);

  const max = Math.max(1, ...last7.map((d) => d.minutes));
  const w = 280;
  const h = 56;
  const step = w / (last7.length - 1);
  const pts = last7.map((d, i) => {
    const x = i * step;
    const y = h - (d.minutes / max) * (h - 6) - 3;
    return { x, y, ...d };
  });
  const linePath = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  const areaPath = `${linePath} L${w},${h} L0,${h} Z`;
  const hasData = last7.some((d) => d.minutes > 0);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {tiles.map((s, idx) => (
          <div
            key={idx}
            className="rounded-2xl border border-hairline bg-card px-4 py-3.5 flex flex-col gap-1 transition-colors hover:border-ojas/30"
          >
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <s.icon className="w-3.5 h-3.5" />
              <span className="text-[10px] uppercase tracking-[0.14em] font-medium">{s.label}</span>
            </div>
            <p className="text-2xl font-serif font-semibold text-foreground tabular-nums leading-none mt-1">
              {s.value}
            </p>
          </div>
        ))}
      </div>

      <div className="rounded-2xl border border-hairline bg-card p-4">
        <div className="flex items-baseline justify-between mb-3">
          <div>
            <p className="text-[10px] uppercase tracking-[0.14em] font-medium text-muted-foreground">
              This week
            </p>
            <p className="text-sm font-serif text-foreground mt-0.5">
              {hasData ? `${last7.reduce((s, d) => s + d.minutes, 0)} minutes over 7 days` : 'No practice this week'}
            </p>
          </div>
        </div>

        <svg
          viewBox={`0 0 ${w} ${h + 18}`}
          preserveAspectRatio="none"
          className="w-full h-16"
          aria-hidden
        >
          <defs>
            <linearGradient id="spark-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="hsl(var(--ojas))" stopOpacity="0.28" />
              <stop offset="100%" stopColor="hsl(var(--ojas))" stopOpacity="0" />
            </linearGradient>
          </defs>
          {hasData && (
            <>
              <path d={areaPath} fill="url(#spark-fill)" />
              <path
                d={linePath}
                fill="none"
                stroke="hsl(var(--ojas))"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              {pts.map((p, i) => (
                <circle
                  key={i}
                  cx={p.x}
                  cy={p.y}
                  r={p.minutes > 0 ? 2.2 : 0}
                  fill="hsl(var(--ojas))"
                />
              ))}
            </>
          )}
          {!hasData && (
            <line
              x1="0"
              y1={h - 3}
              x2={w}
              y2={h - 3}
              stroke="hsl(var(--hairline))"
              strokeDasharray="3 4"
              strokeWidth="1"
            />
          )}
        </svg>

        <div className="grid grid-cols-7 mt-1 text-[10px] text-muted-foreground/70 tabular-nums">
          {last7.map((d, i) => (
            <span key={i} className="text-center">{d.label}</span>
          ))}
        </div>
      </div>
    </div>
  );
};
