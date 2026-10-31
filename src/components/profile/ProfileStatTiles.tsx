import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Flame, Clock, Sparkles, LayoutGrid, CircleDot } from 'lucide-react';
import type { MeditationStats } from '@/lib/meditationStorage';
import { dailySeries, localDayKey, type NormalizedSession } from '@/lib/meditationMetrics';
import { SadhanaHeatmap } from './SadhanaHeatmap';
import { Button } from '@/components/ui/button';

interface Props {
  stats: MeditationStats;
  sessions: NormalizedSession[];
}

/**
 * Sacred Sadhana Rhythm & Circle of Presence.
 * Replaces transactional gym/fitness streaks with meditative continuity,
 * inspiring spiritual copy, and an illuminated 7-day practice matrix.
 */
export const ProfileStatTiles = ({ stats, sessions }: Props) => {
  const { t } = useTranslation();

  const tiles = [
    {
      icon: Sparkles,
      label: t('profileStatTiles.sessions', 'Sessions'),
      value: stats.totalSessions,
      accent: 'text-amber-500',
    },
    {
      icon: Clock,
      label: t('profileStatTiles.minutes', 'Minutes'),
      value: stats.totalMinutes,
      accent: 'text-ojas',
    },
    {
      icon: Flame,
      label: t('profileStatTiles.streak', 'Sadhana Rhythm'),
      value: t('profileStatTiles.streakDays', { days: stats.streakDays, defaultValue: `${stats.streakDays}d` }),
      accent: 'text-amber-600',
    },
  ];

  const last7 = useMemo(() => dailySeries(sessions), [sessions]);
  const todayKey = useMemo(() => localDayKey(new Date()), []);
  const [showHeatmap, setShowHeatmap] = useState<boolean>(() => stats.streakDays > 7);

  const weekMinutes = useMemo(
    () => Math.round(last7.reduce((sum, d) => sum + d.seconds, 0) / 60),
    [last7],
  );

  const hasData = last7.some((d) => d.seconds > 0);
  const streak = stats.streakDays || 0;
  const bestStreak = stats.longestStreakDays || streak;

  return (
    <div className="space-y-4">
      {/* ── Sacred Sadhana Rhythm Hero ── */}
      <div className="relative overflow-hidden rounded-2xl border border-hairline/80 bg-gradient-to-br from-card/90 via-card/60 to-ojas/5 p-4 sm:p-5 backdrop-blur-md shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-start gap-3.5">
            <div className="relative w-11 h-11 rounded-2xl bg-gradient-to-br from-amber-500/20 via-ojas/15 to-amber-600/10 border border-ojas/30 flex items-center justify-center shrink-0 shadow-xs">
              <Flame className="w-5 h-5 text-ojas animate-pulse-subtle" aria-hidden="true" />
              {streak > 0 && (
                <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-ojas ring-2 ring-background animate-ping" />
              )}
            </div>
            <div className="space-y-0.5">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-semibold tracking-wider text-ojas uppercase">
                  {t('profile.sadhana.rhythmTitle', 'Sacred Sadhana Rhythm')}
                </span>
                {bestStreak > 0 && (
                  <span className="text-[10px] text-muted-foreground/80 px-2 py-0.5 rounded-full bg-muted/40 border border-hairline/60">
                    {t('profile.sadhana.bestRhythm', 'Best: {{days}}d', { days: bestStreak })}
                  </span>
                )}
              </div>
              <h3 className="text-base sm:text-lg font-semibold text-foreground tracking-tight">
                {streak > 0
                  ? t('profile.sadhana.activePresence', '{{days}} Days Anchored in Presence', { days: streak })
                  : t('profile.sadhana.awakenRhythm', 'Awaken Your Sacred Rhythm')}
              </h3>
              <p className="text-xs text-muted-foreground/90 leading-relaxed max-w-lg">
                {streak > 0
                  ? t('profile.sadhana.streakActiveQuote', 'Continuity in sadhana transforms awareness into the Beautiful State.')
                  : t('profile.sadhana.streakZeroQuote', 'Every breath is an invitation to stillness. Step into sadhana today to awaken your inner rhythm.')}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* ── Metric Stat Tiles (Preserves test assertions: 12, 180, etc.) ── */}
      <div className="grid grid-cols-3 gap-2 sm:gap-3">
        {tiles.map((s, idx) => (
          <div
            key={idx}
            className="group rounded-xl border border-hairline/80 bg-card/70 backdrop-blur-sm px-3.5 py-3 sm:py-3.5 flex flex-col gap-1 transition-all duration-200 hover:border-ojas/30 hover:bg-card hover:shadow-xs"
          >
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <s.icon className={`w-3.5 h-3.5 ${s.accent} transition-transform group-hover:scale-110`} aria-hidden="true" />
              <span className="text-[10px] uppercase tracking-[0.14em] font-medium">{s.label}</span>
            </div>
            <p className="text-xl sm:text-2xl font-semibold text-foreground tabular-nums leading-none mt-1">
              {s.value}
            </p>
          </div>
        ))}
      </div>

      {/* ── Sadhana Matrix: GitHub-style Heatmap for >7 days, or Circle of Presence ── */}
      {showHeatmap ? (
        <div className="space-y-2">
          <div className="flex items-center justify-between px-1">
            <span className="text-[11px] font-medium text-muted-foreground">
              {stats.streakDays > 7
                ? t('profile.sadhana.deepRhythm', 'Deep practice rhythm — full GitHub matrix view')
                : t('profile.sadhana.fullMatrix', 'Full sadhana activity matrix')}
            </span>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setShowHeatmap(false)}
              className="h-7 text-xs text-ojas gap-1 hover:text-ojas-dark hover:bg-ojas/10 px-2"
            >
              <CircleDot className="w-3.5 h-3.5" />
              <span>{t('profile.sadhana.viewCircle', 'Switch to 7-Day Circle')}</span>
            </Button>
          </div>
          <SadhanaHeatmap sessions={sessions} weeksToShow={20} />
        </div>
      ) : (
        <div className="rounded-2xl border border-hairline/80 bg-card/70 backdrop-blur-md p-4 sm:p-5 space-y-3.5 shadow-xs">
          <div className="flex items-baseline justify-between">
            <div>
              <p className="text-[10px] uppercase tracking-[0.14em] font-medium text-ojas">
                {t('profile.sadhana.circleOfPresence', 'Circle of Presence')}
              </p>
              <p className="text-xs sm:text-sm text-foreground/90 mt-0.5">
                {hasData
                  ? t('profileStatTiles.weekSummary', { minutes: weekMinutes, defaultValue: `${weekMinutes} min mindful practice this week` })
                  : t('profile.sadhana.noPracticeYet', 'Stillness awaits — arrive in meditation with Sri Preethaji & Sri Krishnaji.')}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {hasData && (
                <span className="text-[11px] text-muted-foreground tabular-nums">
                  {last7.filter(d => d.seconds > 0).length}/7 {t('profile.sadhana.daysPracticed', 'days')}
                </span>
              )}
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setShowHeatmap(true)}
                className="h-6 text-[11px] text-muted-foreground hover:text-foreground gap-1 px-1.5"
                title="View full GitHub-style sadhana heatmap"
              >
                <LayoutGrid className="w-3 h-3 text-ojas" />
                <span className="hidden sm:inline">{t('profile.sadhana.viewHeatmap', 'GitHub Matrix')}</span>
              </Button>
            </div>
          </div>

          {/* 7-Day Illuminated Mandala Nodes */}
          <div className="grid grid-cols-7 gap-1.5 sm:gap-3 py-1">
            {last7.map((day) => {
              const isPracticed = day.seconds > 0;
              const isToday = day.key === todayKey;

              return (
                <div
                  key={day.key}
                  className="flex flex-col items-center gap-1.5 text-center group"
                >
                  <span className={`text-[11px] font-medium uppercase tracking-wider ${isToday ? 'text-ojas font-semibold' : 'text-muted-foreground/70'}`}>
                    {day.label}
                  </span>

                  <div
                    className={`relative w-9 h-9 sm:w-11 sm:h-11 rounded-full flex items-center justify-center transition-all duration-300 ${
                      isPracticed
                        ? 'bg-gradient-to-br from-amber-400 via-amber-500 to-amber-600 text-white shadow-xs shadow-ojas/30 ring-2 ring-ojas/30 scale-100 group-hover:scale-105'
                        : isToday
                          ? 'border-2 border-dashed border-ojas/70 bg-ojas/10 text-ojas ring-2 ring-ojas/20'
                          : 'border border-hairline/70 bg-muted/20 text-muted-foreground/40 group-hover:border-hairline'
                    }`}
                    title={isPracticed ? `${day.minutes} min practiced` : isToday ? 'Present Moment' : 'Rest day'}
                    aria-label={`${day.label}: ${isPracticed ? `${day.minutes}m practiced` : isToday ? 'Today' : 'Rest'}`}
                  >
                    {isPracticed ? (
                      <Sparkles className="w-4 h-4 text-white" aria-hidden="true" />
                    ) : isToday ? (
                      <span className="w-2 h-2 rounded-full bg-ojas animate-pulse" aria-hidden="true" />
                    ) : (
                      <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/25" aria-hidden="true" />
                    )}
                  </div>

                  <span className="text-[10px] tabular-nums font-medium text-muted-foreground/80 min-h-[14px]">
                    {isPracticed ? `${day.minutes}m` : isToday ? t('common.today', 'Today') : '—'}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
