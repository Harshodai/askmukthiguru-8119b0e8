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
          <h2 className="text-4xl md:text-5xl font-bold mb-4 text-foreground font-serif">Daily practices</h2>
          <p className="text-muted-foreground text-lg">
            Guided meditations rooted in the teachings of Sri Preethaji & Sri Krishnaji.
            Pick the one that meets you today — star your favorites to pin them here.
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
                  aria-label={fav ? `Unstar ${p.title}` : `Star ${p.title}`}
                  aria-pressed={fav}
                  title={fav ? 'Remove from favorites' : 'Add to favorites'}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    toggle(p.slug);
                    toast({
                      title: fav ? 'Removed from favorites' : 'Added to favorites',
                      description: `${p.title} has been ${fav ? 'removed from' : 'added to'} your list.`,
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
                  className="glass-card-hover p-5 h-full flex flex-col group"
                >
                  <div className="w-11 h-11 rounded-xl bg-ojas/15 flex items-center justify-center mb-3">
                    <Icon className="w-5 h-5 text-ojas" />
                  </div>
                  <h3 className="font-semibold text-foreground pr-6">{p.title}</h3>
                  <p className="text-xs text-muted-foreground mt-1 flex-1">{p.tagline}</p>
                  <div className="flex items-center justify-between mt-4 text-[11px] text-muted-foreground">
                    <span className="inline-flex items-center gap-1">
                      <Clock className="w-3 h-3" /> {p.durationLabel}
                    </span>
                    <ArrowRight className="w-4 h-4 text-ojas group-hover:translate-x-0.5 transition-transform" />
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
            Explore all practices <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    </section>
  );
};
