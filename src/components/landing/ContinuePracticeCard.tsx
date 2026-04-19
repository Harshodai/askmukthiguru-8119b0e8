import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowRight, Clock, PlayCircle, Star } from 'lucide-react';
import { useFavorites } from '@/hooks/useFavorites';
import { practices, getPracticeBySlug, type Practice } from '@/lib/practicesContent';

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
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.6, duration: 0.5 }}
      className="mt-8 max-w-xl mx-auto"
    >
      <Link
        to={`/practices/${practice.slug}`}
        className="group block glass-card p-4 rounded-2xl hover:shadow-lg transition-all hover:-translate-y-0.5"
      >
        <div className="flex items-center gap-3 text-left">
          <div className="w-12 h-12 rounded-xl bg-ojas/15 flex items-center justify-center shrink-0">
            <PlayCircle className="w-6 h-6 text-ojas" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-muted-foreground">
              <Star className="w-3 h-3 fill-ojas text-ojas" />
              <span>Continue your practice</span>
            </div>
            <p className="font-semibold text-foreground truncate">{practice.title}</p>
            <p className="text-xs text-muted-foreground inline-flex items-center gap-1 mt-0.5">
              <Clock className="w-3 h-3" /> {practice.durationLabel}
            </p>
          </div>
          <ArrowRight className="w-5 h-5 text-ojas group-hover:translate-x-0.5 transition-transform shrink-0" />
        </div>
      </Link>
    </motion.div>
  );
};
