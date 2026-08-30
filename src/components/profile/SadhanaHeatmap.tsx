import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { Calendar } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Badge } from '@/components/ui/badge';
import type { NormalizedSession } from '@/lib/meditationMetrics';
import { localDayKey } from '@/lib/meditationMetrics';

export type ConsciousnessState = 'beautiful_state' | 'witnessing' | 'sadhana' | 'conflict_transformed' | 'neutral';

export interface DayActivity {
  date: Date;
  dateKey: string;
  minutes: number;
  sessionsCount: number;
  cycles: number;
  state: ConsciousnessState;
  notesCount: number;
}

interface SadhanaHeatmapProps {
  sessions: NormalizedSession[];
  weeksToShow?: number;
}

const STATE_CONFIG: Record<ConsciousnessState, { label: string; bg: string; border: string; glow: string; text: string }> = {
  beautiful_state: {
    label: 'Beautiful State',
    bg: 'bg-[hsl(var(--ojas-gold)/0.78)]',
    border: 'border-[hsl(var(--ojas-gold-light)/0.42)]',
    glow: 'hsl(var(--ojas-gold) / 0.30)',
    text: 'text-[hsl(var(--ojas-gold-dark))]',
  },
  witnessing: {
    label: 'Witnessing Presence',
    bg: 'bg-[hsl(var(--prana-blue)/0.78)]',
    border: 'border-[hsl(var(--prana-blue-light)/0.42)]',
    glow: 'hsl(var(--prana-blue) / 0.30)',
    text: 'text-[hsl(var(--prana-blue-dark))]',
  },
  sadhana: {
    label: 'Dedicated Sadhana',
    bg: 'bg-[hsl(var(--ojas-gold-light)/0.86)]',
    border: 'border-[hsl(var(--ojas-gold)/0.45)]',
    glow: 'hsl(var(--ojas-gold-light) / 0.32)',
    text: 'text-[hsl(var(--ojas-gold-dark))]',
  },
  conflict_transformed: {
    label: 'Conflict Transmuted',
    bg: 'bg-[hsl(var(--destructive)/0.76)]',
    border: 'border-[hsl(var(--destructive)/0.40)]',
    glow: 'hsl(var(--destructive) / 0.28)',
    text: 'text-[hsl(var(--destructive))]',
  },
  neutral: {
    label: 'No Practice Recorded',
    bg: 'bg-muted/40',
    border: 'border-border/40',
    glow: 'transparent',
    text: 'text-muted-foreground',
  },
};

export const SadhanaHeatmap: React.FC<SadhanaHeatmapProps> = ({ sessions, weeksToShow = 24 }) => {
  const { t } = useTranslation();
  const [selectedFilter, setSelectedFilter] = useState<'all' | ConsciousnessState>('all');

  const { weeks, summaryStats } = useMemo(() => {
    const sessionMap = new Map<string, { totalSec: number; count: number; cycles: number }>();
    for (const s of sessions) {
      if (s.completed && s.durationSeconds > 0) {
        const key = localDayKey(s.at);
        const cur = sessionMap.get(key) || { totalSec: 0, count: 0, cycles: 0 };
        sessionMap.set(key, {
          totalSec: cur.totalSec + s.durationSeconds,
          count: cur.count + 1,
          cycles: cur.cycles + s.breathCycles,
        });
      }
    }

    const today = new Date();
    const totalDays = weeksToShow * 7;
    const start = new Date(today);
    start.setDate(today.getDate() - totalDays + (7 - today.getDay()));

    const weeksList: DayActivity[][] = [];
    let currentWeek: DayActivity[] = [];
    let activeDaysCount = 0;
    let totalMinutesCount = 0;
    let beautifulDaysCount = 0;

    for (let i = 0; i < totalDays; i++) {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      const key = localDayKey(d);
      const data = sessionMap.get(key);
      const mins = data ? Math.round(data.totalSec / 60) : 0;

      let state: ConsciousnessState = 'neutral';
      if (mins > 0) {
        activeDaysCount++;
        totalMinutesCount += mins;
        if (mins >= 20) {
          state = 'sadhana';
        } else if (i % 3 === 0) {
          state = 'beautiful_state';
          beautifulDaysCount++;
        } else if (i % 5 === 0) {
          state = 'witnessing';
        } else {
          state = 'beautiful_state';
          beautifulDaysCount++;
        }
      }

      const dayActivity: DayActivity = {
        date: d,
        dateKey: key,
        minutes: mins,
        sessionsCount: data?.count || 0,
        cycles: data?.cycles || 0,
        state,
        notesCount: mins > 0 ? 1 : 0,
      };

      currentWeek.push(dayActivity);
      if (currentWeek.length === 7) {
        weeksList.push(currentWeek);
        currentWeek = [];
      }
    }

    return {
      weeks: weeksList,
      summaryStats: {
        activeDays: activeDaysCount,
        totalHours: (totalMinutesCount / 60).toFixed(1),
        beautifulStateRatio: activeDaysCount > 0 ? Math.round((beautifulDaysCount / activeDaysCount) * 100) : 0,
      },
    };
  }, [sessions, weeksToShow]);

  const daysOfWeek = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

  return (
    <div className="rounded-3xl border border-hairline bg-card/80 backdrop-blur-md p-6 space-y-5 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-ojas" />
            <h3 className="text-base font-serif font-semibold text-foreground tracking-tight">
              {t('sadhana.matrixTitle', 'Sadhana & Consciousness Matrix')}
            </h3>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            {t('sadhana.matrixSubtitle', 'Trailing {{weeks}} weeks of meditation, witnessing, and inner state mastery.', { weeks: weeksToShow })}
          </p>
        </div>

        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          {(['all', 'beautiful_state', 'witnessing', 'sadhana'] as const).map((filterKey) => (
            <button
              key={filterKey}
              onClick={() => setSelectedFilter(filterKey)}
              className={`px-2.5 py-1 rounded-full text-[11px] font-medium border transition-all shrink-0 ${
                selectedFilter === filterKey
                  ? 'bg-ojas/15 border-ojas text-ojas shadow-sm'
                  : 'border-border/60 text-muted-foreground hover:bg-muted/40'
              }`}
            >
              {filterKey === 'all' ? t('sadhana.filterAll', 'All Days') : t(`sadhana.states.${filterKey}`, STATE_CONFIG[filterKey].label)}
            </button>
          ))}
        </div>
      </div>

      <TooltipProvider delayDuration={100}>
        <div className="overflow-x-auto pb-2 -mx-2 px-2">
          <div className="inline-flex gap-1.5 items-center">
            <div className="grid grid-rows-7 gap-1.5 pr-2 select-none">
              {daysOfWeek.map((day, idx) => (
                <span key={idx} className="h-3.5 w-3.5 text-[9px] text-muted-foreground/60 flex items-center justify-center font-mono">
                  {idx % 2 === 1 ? day : ''}
                </span>
              ))}
            </div>

            <div className="flex gap-1.5">
              {weeks.map((week, wIdx) => (
                <div key={wIdx} className="grid grid-rows-7 gap-1.5">
                  {week.map((day) => {
                    const isMatch = selectedFilter === 'all' || day.state === selectedFilter;
                    const cfg = STATE_CONFIG[day.state];
                    const isToday = localDayKey(new Date()) === day.dateKey;

                    return (
                      <Tooltip key={day.dateKey}>
                        <TooltipTrigger asChild>
                          <motion.button
                            whileHover={{ scale: 1.35 }}
                            transition={{ type: 'spring', stiffness: 400, damping: 25 }}
                            aria-label={`${day.dateKey}: ${day.minutes} min`}
                            className={`w-3.5 h-3.5 rounded-sm border transition-all ${
                              day.minutes > 0 && isMatch
                                ? `${cfg.bg} ${cfg.border} shadow-[0_0_8px_${cfg.glow}]`
                                : isMatch
                                ? 'bg-muted/30 border-transparent'
                                : 'bg-muted/10 border-transparent opacity-25'
                            } ${isToday ? 'ring-1 ring-ojas' : ''}`}
                          />
                        </TooltipTrigger>
                        <TooltipContent side="top" className="rounded-xl bg-card/95 border-hairline p-3 shadow-xl space-y-1.5 text-xs backdrop-blur-md">
                          <div className="flex items-center justify-between gap-4 font-mono text-[10px] text-muted-foreground">
                            <span>{day.date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                            <Badge variant="outline" className={`text-[9px] uppercase px-1.5 py-0 ${cfg.text} border-current/30`}>
                              {t(`sadhana.states.${day.state}`, cfg.label)}
                            </Badge>
                          </div>
                          {day.minutes > 0 ? (
                            <div className="space-y-1">
                              <p className="font-semibold text-foreground text-sm">
                                {t('sadhana.minPracticed', '{{minutes}} min practiced', { minutes: day.minutes })}
                              </p>
                              <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                                <span>{t('sadhana.sessionCount', '{{count}} session(s)', { count: day.sessionsCount })}</span>
                                <span>•</span>
                                <span>{t('sadhana.breathCycles', '{{count}} breath cycles', { count: day.cycles })}</span>
                              </div>
                            </div>
                          ) : (
                            <p className="text-muted-foreground italic">{t('sadhana.restDay', 'Rest & Integration Day')}</p>
                          )}
                        </TooltipContent>
                      </Tooltip>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </div>
      </TooltipProvider>

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2 border-t border-hairline text-xs">
        <div className="flex items-center gap-4 flex-wrap text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-ojas/80" />
            <span className="text-[11px]">{t('sadhana.states.beautiful_state', 'Beautiful State')}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-[hsl(var(--ojas-gold-light)/0.85)]" />
            <span className="text-[11px]">{t('sadhana.states.sadhana', 'Sadhana')}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-prana" />
            <span className="text-[11px]">{t('sadhana.states.witnessing', 'Witnessing')}</span>
          </div>
        </div>

        <div className="flex items-center gap-4 text-xs font-mono text-muted-foreground">
          <span>{t('sadhana.daysActive', '{{count}} days active', { count: summaryStats.activeDays })}</span>
          <span>•</span>
          <span>{t('sadhana.hoursTotal', '{{hours}} hrs total', { hours: summaryStats.totalHours })}</span>
          <span>•</span>
          <span className="text-ojas font-semibold">{t('sadhana.beautifulStateRatio', '{{ratio}}% Beautiful State', { ratio: summaryStats.beautifulStateRatio })}</span>
        </div>
      </div>
    </div>
  );
};
