import { ArrowRight, Clock, PlayCircle, Star } from 'lucide-react';
import { useFavorites } from '@/hooks/useFavorites';
import { practices, getPracticeBySlug, type Practice } from '@/lib/practicesContent';
import { ActionCard } from '@/components/common/ui/ActionCard';

/**
 * "Continue your practice" hero card.
 * Picks the most recently opened practice if it is in the user's favorites,
 * otherwise the first favorite, otherwise renders nothing.
 */
export const ContinuePracticeCard = () => {
  const { favorites, recent } = useFavorites();

  if (favorites.length === 0) return null;

  let practice: Practice | undefined;
  if (recent && favorites.includes(recent)) {
    practice = getPracticeBySlug(recent);
  }
  if (!practice) {
    practice = practices.find((p) => p.slug === favorites[0]);
  }
  if (!practice) return null;

  return (
    <ActionCard
      to={`/practices/${practice.slug}`}
      icon={<PlayCircle className="w-6 h-6 text-ojas" />}
      eyebrow={
        <>
          <Star className="w-3 h-3 fill-ojas text-ojas" />
          <span>Continue your practice</span>
        </>
      }
      title={practice.title}
      subtitle={
        <>
          <Clock className="w-3 h-3" />
          <span>{practice.durationLabel}</span>
        </>
      }
      arrow={<ArrowRight className="w-5 h-5 text-ojas group-hover:translate-x-0.5 transition-transform shrink-0" />}
    />
  );
};
