import { useMemo } from 'react';
import { getMeditationStats } from '@/lib/meditationStorage';
import { Sparkles } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

export const PostCompletionStreak = () => {
  const streakDays = useMemo(() => {
    try { return getMeditationStats().streakDays ?? 0; } catch { return 0; }
  }, []);

  if (streakDays === 0) return null;

  return (
    <Badge variant="outline" className="gap-1.5 px-3 py-1 bg-ojas/10 border-ojas/25 text-ojas">
      <Sparkles className="w-3 h-3" aria-hidden="true" />
      <span>{streakDays} {streakDays === 1 ? 'day' : 'days'} streak — keep it going!</span>
    </Badge>
  );
};
