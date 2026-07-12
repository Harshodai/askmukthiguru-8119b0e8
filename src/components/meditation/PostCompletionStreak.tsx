import { useMemo } from 'react';
import { getMeditationStats } from '@/lib/meditationStorage';
import { Sparkles } from 'lucide-react';

export const PostCompletionStreak = () => {
  const streakDays = useMemo(() => {
    try { return getMeditationStats().streakDays ?? 0; } catch { return 0; }
  }, []);

  if (streakDays === 0) return null;

  return (
    <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-ojas/10 border border-ojas/25 text-xs font-semibold text-ojas">
      <Sparkles className="w-3 h-3" />
      <span>{streakDays} {streakDays === 1 ? 'day' : 'days'} streak — keep it going!</span>
    </div>
  );
};
