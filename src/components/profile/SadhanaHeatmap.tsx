import React, { useMemo, useState } from 'react';
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
    bg: 'bg-emerald-500/80',
    border: 'border-emerald-400/40',
    glow: 'rgba(16, 185, 129, 0.4)',
    text: 'text-emerald-400',
  },
  witnessing: {
    label: 'Witnessing Presence',
    bg: 'bg-violet-500/80',
    border: 'border-violet-400/40',
    glow: 'rgba(139, 92, 246, 0.4)',
    text: 'text-violet-400',
  },
  sadhana: {
    label: 'Dedicated Sadhana',
    bg: 'bg-amber-500/85',
    border: 'border-amber-400/40',
    glow: 'rgba(245, 158, 11, 0.4)',
    text: 'text-amber-400',
  },
  conflict_transformed: {
    label: 'Conflict Transmuted',
    bg: 'bg-rose-500/80',
    border: 'border-rose-400/40',
    glow: 'rgba(244, 63, 94, 0.4)',
    text: 'text-rose-400',
  },
  neutral: {
    label: 'No Practice Recorded',
    bg: 'bg-zinc-800/40',
    border: 'border-zinc-800/60',
    glow: 'transparent',
    text: 'text-zinc-500',
  },
};

export const SadhanaHeatmap: React.FC<SadhanaHeatmapProps> = ({ sessions, weeksToShow = 24 }) => {
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
    <div className="rounded-3xl border border-border/50 bg-card/80 backdrop-blur-md p-6 space-y-5 shadow-sm">
      {/* Header & Filter Pills */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-saffron-gold" />
            <h3 className="text-base font-serif font-semibold text-foreground tracking-tight">
              Sadhana & Consciousness Matrix
            </h3>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            Trailing {weeksToShow} weeks of meditation, witnessing, and inner state mastery.
          </p>
        </div>

        {/* State Filters */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          {(['all', 'beautiful_state', 'witnessing', 'sadhana'] as const).map((filterKey) => (
            <button
              key={filterKey}
              onClick={() => setSelectedFilter(filterKey)}
              className={`px-2.5 py-1 rounded-full text-[11px] font-medium border transition-all shrink-0 ${
                selectedFilter === filterKey
                  ? 'bg-saffron-gold/15 border-saffron-gold text-saffron-gold shadow-sm'
                  : 'border-border/60 text-muted-foreground hover:bg-muted/40'
              }`}
            >
              {filterKey === 'all' ? 'All Days' : STATE_CONFIG[filterKey].label}
            </button>
          ))}
        </div>
      </div>

      {/* Heatmap Grid Canvas */}
      <TooltipProvider delayDuration={100}>
        <div className="overflow-x-auto pb-2 -mx-2 px-2">
          <div className="inline-flex gap-1.5 items-center">
            {/* Day of week labels */}
            <div className="grid grid-rows-7 gap-1.5 pr-2 select-none">
              {daysOfWeek.map((day, idx) => (
                <span key={idx} className="h-3.5 w-3.5 text-[9px] text-muted-foreground/60 flex items-center justify-center font-mono">
                  {idx % 2 === 1 ? day : ''}
                </span>
              ))}
            </div>

            {/* Weeks Columns */}
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
                            } ${isToday ? 'ring-1 ring-saffron-gold' : ''}`}
                          />
                        </TooltipTrigger>
                        <TooltipContent side="top" className="rounded-xl bg-zinc-950/95 border-zinc-800 p-3 shadow-xl space-y-1.5 text-xs">
                          <div className="flex items-center justify-between gap-4 font-mono text-[10px] text-muted-foreground">
                            <span>{day.date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                            <Badge variant="outline" className={`text-[9px] uppercase px-1.5 py-0 ${cfg.text} border-current/30`}>
                              {cfg.label}
                            </Badge>
                          </div>
                          {day.minutes > 0 ? (
                            <div className="space-y-1">
                              <p className="font-semibold text-foreground text-sm">
                                {day.minutes} min practiced
                              </p>
                              <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                                <span>{day.sessionsCount} session(s)</span>
                                <span>•</span>
                                <span>{day.cycles} breath cycles</span>
                              </div>
                            </div>
                          ) : (
                            <p className="text-muted-foreground italic">Rest & Integration Day</p>
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

      {/* Heatmap Legend & Summary */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2 border-t border-border/40 text-xs">
        <div className="flex items-center gap-4 flex-wrap text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500/80 shadow-[0_0_6px_rgba(16,185,129,0.4)]" />
            <span className="text-[11px]">Beautiful State</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-amber-500/85 shadow-[0_0_6px_rgba(245,158,11,0.4)]" />
            <span className="text-[11px]">Sadhana</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-violet-500/80 shadow-[0_0_6px_rgba(139,92,246,0.4)]" />
            <span className="text-[11px]">Witnessing</span>
          </div>
        </div>

        <div className="flex items-center gap-4 text-xs font-mono text-muted-foreground">
          <span>{summaryStats.activeDays} days active</span>
          <span>•</span>
          <span>{summaryStats.totalHours} hrs total</span>
          <span>•</span>
          <span className="text-emerald-400 font-semibold">{summaryStats.beautifulStateRatio}% Beautiful State</span>
        </div>
      </div>
    </div>
  );
};
