import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowRight, Clock, Flame, Heart, Moon, Sparkles, Star } from 'lucide-react';
import { practices, type Practice } from '@/lib/practicesContent';
import { useFavorites } from '@/hooks/useFavorites';
import { cn } from '@/lib/utils';
import { useToast } from '@/hooks/use-toast';

const iconFor: Record<Practice['slug'], typeof Flame> = {
  'soul-sync': Sparkles,
  'serene-mind': Flame,
  'beautiful-state': Heart,
  'daily-reflection': Moon,
};

export const PracticesSection = () => {
  const { t } = useTranslation();
  const { favorites, toggle, isFavorited } = useFavorites();
  const { toast } = useToast();
  const favoritePractices = practices.filter((p) => favorites.includes(p.slug));
  const otherPractices = practices.filter((p) => !favorites.includes(p.slug));
  const ordered = [...favoritePractices, ...otherPractices];

  return (
    <section id="practices" className="scroll-mt-28 py-12 sm:py-20 md:py-24 relative overflow-hidden">
      <div className="container mx-auto px-4 relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="text-center max-w-2xl mx-auto mb-12"
        >
          <h2 className="text-4xl md:text-5xl font-bold mb-4 text-foreground font-serif">{t('landing.practices.heading')}</h2>
          <p className="text-muted-foreground text-lg">
            {t('landing.practices.subtitle')}
          </p>
        </motion.div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 max-w-6xl mx-auto">
          {ordered.map((p, i) => {
            const Icon = iconFor[p.slug as Practice['slug']] ?? Sparkles;
            const fav = isFavorited(p.slug);
            return (
              <motion.div
                key={p.slug}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.4, delay: i * 0.08 }}
                className="relative"
              >
                <button
                  type="button"
                  aria-label={fav ? `Remove ${p.title} from favorites` : `Add ${p.title} to favorites`}
                  aria-pressed={fav}
                  title={fav ? t('common.removeFavorites') : t('common.addFavorites')}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    toggle(p.slug);
                    toast({
                      title: fav ? t('landing.practices.removedFav') : t('landing.practices.addedFav'),
                      description: fav ? t('landing.practices.removedDesc', { title: p.title }) : t('landing.practices.addedDesc', { title: p.title }),
                    });
                  }}
                  className="absolute top-3 right-3 z-10 p-1.5 rounded-full bg-background/70 backdrop-blur-sm hover:bg-background transition-colors"
                >
                  <Star
                    className={cn(
                      'w-3.5 h-3.5 transition-colors',
                      fav ? 'fill-ojas text-ojas' : 'text-muted-foreground',
                    )}
                  />
                </button>
                <Link
                  to={`/practices/${p.slug}`}
                  className="relative p-5 h-full flex flex-col group rounded-3xl border border-border/40 bg-card/80 backdrop-blur-md hover:border-saffron-gold/50 transition-all duration-300 shadow-sm hover:shadow-xl hover:-translate-y-1 overflow-hidden"
                >
                  {/* Breath Pacing Orb on Hover */}
                  <motion.div
                    animate={{
                      scale: [1, 1.4, 1],
                      opacity: [0.08, 0.22, 0.08],
                    }}
                    transition={{
                      duration: 6,
                      repeat: Infinity,
                      ease: 'easeInOut',
                    }}
                    className="absolute -right-12 -top-12 w-36 h-36 rounded-full bg-saffron-gold blur-2xl pointer-events-none group-hover:opacity-40 transition-opacity"
                  />

                  <div className="w-12 h-12 rounded-2xl bg-saffron-gold/15 flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                    <Icon className="w-6 h-6 text-saffron-gold" />
                  </div>
                  <h3 className="font-serif text-lg font-bold text-foreground pr-6">{p.title}</h3>
                  <p className="text-xs text-muted-foreground mt-1.5 leading-relaxed flex-1">{p.tagline}</p>
                  <div className="flex items-center justify-between mt-5 pt-3 border-t border-border/40 text-xs text-muted-foreground">
                    <span className="inline-flex items-center gap-1.5 font-mono">
                      <Clock className="w-3.5 h-3.5 text-saffron-gold" /> {p.durationLabel}
                    </span>
                    <span className="inline-flex items-center gap-1 text-saffron-gold font-semibold text-xs group-hover:translate-x-1 transition-transform">
                      Practice <ArrowRight className="w-3.5 h-3.5" />
                    </span>
                  </div>
                </Link>
              </motion.div>
            );
          })}
        </div>

        <div className="text-center mt-10">
          <Link
            to="/practices"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-medium shadow-md hover:scale-105 transition-transform"
          >
            {t('landing.practices.exploreAll')} <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    </section>
  );
};
