import React, { useMemo } from 'react';
import { motion } from 'framer-motion';
import { Calendar } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import type { NormalizedSession } from '@/lib/meditationMetrics';
import { localDayKey } from '@/lib/meditationMetrics';

export interface DayActivity {
  date: Date;
  dateKey: string;
  minutes: number;
  sessionsCount: number;
  cycles: number;
}

interface SadhanaHeatmapProps {
  sessions: NormalizedSession[];
  weeksToShow?: number;
}

const getIntensityClass = (minutes: number): string => {
  if (minutes <= 0) return 'bg-muted/30 border-transparent';
  if (minutes < 10) return 'bg-ojas/35 border-ojas/20';
  if (minutes < 20) return 'bg-ojas/60 border-ojas/30';
  return 'bg-ojas border-ojas/40';
};

const getIntensityLabel = (minutes: number): string => {
  if (minutes <= 0) return 'Rest day';
  if (minutes < 10) return 'Short sit';
  if (minutes < 20) return 'Steady practice';
  return 'Deep sadhana';
};

const calculateCurrentStreak = (weeks: DayActivity[][]): number => {
  const ordered = weeks.flat().filter((day) => day.date <= new Date()).reverse();
  let streak = 0;
  for (const day of ordered) {
    if (day.minutes <= 0) break;
    streak += 1;
  }
  return streak;
};

export const SadhanaHeatmap: React.FC<SadhanaHeatmapProps> = ({ sessions, weeksToShow = 24 }) => {
  const { weeks, summaryStats } = useMemo(() => {
    const sessionMap = new Map<string, { totalSec: number; count: number; cycles: number }>();
    for (const session of sessions) {
      if (!session.completed || session.durationSeconds <= 0) continue;
      const key = localDayKey(session.at);
      const current = sessionMap.get(key) ?? { totalSec: 0, count: 0, cycles: 0 };
      sessionMap.set(key, {
        totalSec: current.totalSec + session.durationSeconds,
        count: current.count + 1,
        cycles: current.cycles + session.breathCycles,
      });
    }

    const totalDays = weeksToShow * 7;
    const today = new Date();
    const start = new Date(today);
    start.setHours(0, 0, 0, 0);
    start.setDate(today.getDate() - totalDays + (7 - today.getDay()));

    const weeksList: DayActivity[][] = [];
    let currentWeek: DayActivity[] = [];
    let activeDays = 0;
    let totalMinutes = 0;
    let totalSessions = 0;

    for (let i = 0; i < totalDays; i += 1) {
      const date = new Date(start);
      date.setDate(start.getDate() + i);
      const dateKey = localDayKey(date);
      const data = sessionMap.get(dateKey);
      const minutes = data ? Math.round(data.totalSec / 60) : 0;

      if (minutes > 0) {
        activeDays += 1;
        totalMinutes += minutes;
      }
      totalSessions += data?.count ?? 0;

      currentWeek.push({
        date,
        dateKey,
        minutes,
        sessionsCount: data?.count ?? 0,
        cycles: data?.cycles ?? 0,
      });

      if (currentWeek.length === 7) {
        weeksList.push(currentWeek);
        currentWeek = [];
      }
    }

    return {
      weeks: weeksList,
      summaryStats: {
        activeDays,
        totalHours: (totalMinutes / 60).toFixed(1),
        totalSessions,
        currentStreak: calculateCurrentStreak(weeksList),
      },
    };
  }, [sessions, weeksToShow]);

  const daysOfWeek = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

  return (
    <section className="rounded-3xl border border-hairline bg-card/80 backdrop-blur-md p-5 sm:p-6 space-y-5 shadow-sm" aria-label="Meditation practice activity">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-ojas" aria-hidden="true" />
            <h3 className="text-base font-serif font-semibold text-foreground tracking-tight">Sadhana practice activity</h3>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">Measured completed practice — no inferred consciousness state.</p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <span><strong className="text-foreground">{summaryStats.activeDays}</strong> active days</span>
          <span aria-hidden="true">•</span>
          <span><strong className="text-foreground">{summaryStats.totalHours}</strong> hrs</span>
          <span aria-hidden="true">•</span>
          <span><strong className="text-foreground">{summaryStats.currentStreak}</strong> day streak</span>
        </div>
      </div>

      <TooltipProvider delayDuration={100}>
        <div className="overflow-x-auto pb-1 -mx-1 px-1">
          <div className="inline-flex gap-1.5 items-center min-w-max">
            <div className="grid grid-rows-7 gap-1.5 pr-2" aria-hidden="true">
              {daysOfWeek.map((day, index) => (
                <span key={`${day}-${index}`} className="h-3.5 w-3.5 text-[9px] text-muted-foreground/60 flex items-center justify-center font-mono">
                  {index % 2 === 1 ? day : ''}
                </span>
              ))}
            </div>
            <div className="flex gap-1.5">
              {weeks.map((week, weekIndex) => (
                <div key={weekIndex} className="grid grid-rows-7 gap-1.5">
                  {week.map((day) => {
                    const isToday = localDayKey(new Date()) === day.dateKey;
                    const label = getIntensityLabel(day.minutes);
                    return (
                      <Tooltip key={day.dateKey}>
                        <TooltipTrigger asChild>
                          <motion.button
                            whileHover={{ scale: 1.3 }}
                            transition={{ type: 'spring', stiffness: 400, damping: 25 }}
                            type="button"
                            aria-label={`${day.dateKey}: ${label}; ${day.minutes} minutes, ${day.sessionsCount} sessions, ${day.cycles} breath cycles`}
                            className={`w-3.5 h-3.5 rounded-[4px] border transition-transform ${getIntensityClass(day.minutes)} ${isToday ? 'ring-2 ring-ojas/50 ring-offset-1 ring-offset-card' : ''}`}
                            title={`${day.dateKey} · ${label}`}
                          />
                        </TooltipTrigger>
                        <TooltipContent side="top" className="rounded-xl bg-card/95 border-hairline p-3 shadow-xl text-xs backdrop-blur-md">
                          <p className="font-medium text-foreground">{day.date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</p>
                          <p className="text-ojas mt-1 font-medium">{label}</p>
                          {day.minutes > 0 ? (
                            <p className="text-muted-foreground mt-1">{day.minutes} min · {day.sessionsCount} session{day.sessionsCount === 1 ? '' : 's'} · {day.cycles} breath cycles</p>
                          ) : (
                            <p className="text-muted-foreground mt-1">No completed practice recorded.</p>
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

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2 border-t border-hairline text-xs text-muted-foreground">
        <div className="flex flex-wrap items-center gap-2" aria-label="Practice intensity legend">
          <span className="w-2.5 h-2.5 rounded-[4px] bg-muted/30 border border-transparent" aria-hidden="true" />
          <span>Rest</span>
          <span className="w-2.5 h-2.5 rounded-[4px] bg-ojas/35 border border-ojas/20" aria-hidden="true" />
          <span>Short &lt;10m</span>
          <span className="w-2.5 h-2.5 rounded-[4px] bg-ojas/60 border border-ojas/30" aria-hidden="true" />
          <span>Steady 10–19m</span>
          <span className="w-2.5 h-2.5 rounded-[4px] bg-ojas border border-ojas/40" aria-hidden="true" />
          <span>Deep 20m+</span>
        </div>
        <span>{summaryStats.totalSessions} completed sessions</span>
      </div>
    </section>
  );
};
