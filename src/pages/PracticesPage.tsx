import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowRight, Clock, Sparkles, Flame, Heart, Moon, Star } from 'lucide-react';
import { AppShell } from '@/components/layout/AppShell';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { practices, type Practice } from '@/lib/practicesContent';
import { useFavorites } from '@/hooks/useFavorites';
import { cn } from '@/lib/utils';

const accentMap: Record<Practice['accent'], { icon: typeof Flame; ring: string; bg: string; text: string }> = {
  ojas: { icon: Sparkles, ring: 'ring-ojas/30', bg: 'bg-ojas/10', text: 'text-ojas' },
  prana: { icon: Moon, ring: 'ring-prana/30', bg: 'bg-prana/10', text: 'text-prana' },
  tejas: { icon: Flame, ring: 'ring-ojas/30', bg: 'bg-ojas/10', text: 'text-ojas-dark' },
  lotus: { icon: Heart, ring: 'ring-ojas-light/30', bg: 'bg-ojas-light/10', text: 'text-ojas-light' },
};

interface PracticeCardProps {
  practice: Practice;
  index: number;
  isFavorited: boolean;
  onToggle: (slug: string) => void;
}

const PracticeCard = ({ practice: p, index: i, isFavorited, onToggle }: PracticeCardProps) => {
  const A = accentMap[p.accent];
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: i * 0.06 }}
      className="relative"
    >
      <button
        type="button"
        aria-label={isFavorited ? `Unstar ${p.title}` : `Star ${p.title}`}
        aria-pressed={isFavorited}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onToggle(p.slug);
        }}
        className="absolute top-3 right-3 z-10 p-2 rounded-full bg-background/70 backdrop-blur-sm hover:bg-background transition-colors"
      >
        <Star
          className={cn(
            'w-4 h-4 transition-colors',
            isFavorited ? 'fill-ojas text-ojas' : 'text-muted-foreground',
          )}
        />
      </button>
      <Link to={`/practices/${p.slug}`} className="block group">
        <Card className={`h-full p-5 transition-all hover:shadow-lg ring-1 ${A.ring} hover:-translate-y-0.5`}>
          <div className="flex items-start gap-4">
            <div className={`w-11 h-11 rounded-xl ${A.bg} flex items-center justify-center shrink-0`}>
              <A.icon className={`w-5 h-5 ${A.text}`} />
            </div>
            <div className="flex-1 min-w-0 pr-8">
              <div className="flex items-center justify-between gap-3">
                <h3 className="font-semibold text-foreground truncate">{p.title}</h3>
                <ArrowRight className="w-4 h-4 text-muted-foreground group-hover:text-ojas transition-colors shrink-0" />
              </div>
              <p className="text-sm text-muted-foreground mt-1">{p.tagline}</p>
              <div className="flex flex-wrap gap-2 mt-3">
                <Badge variant="secondary" className="gap-1">
                  <Clock className="w-3 h-3" /> {p.durationLabel}
                </Badge>
                {p.intentions.slice(0, 2).map((tag) => (
                  <Badge key={tag} variant="outline" className="text-[10px]">
                    {tag}
                  </Badge>
                ))}
              </div>
            </div>
          </div>
        </Card>
      </Link>
    </motion.div>
  );
};

const PracticesPage = () => {
  const { favorites, toggle, isFavorited } = useFavorites();
  const favoritePractices = practices.filter((p) => favorites.includes(p.slug));
  const otherPractices = practices.filter((p) => !favorites.includes(p.slug));

  return (
    <AppShell title="Practices">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6 sm:py-10">
        <motion.header
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="mb-8"
        >
          <h1 className="text-2xl sm:text-3xl font-semibold text-foreground">Daily practices</h1>
          <p className="text-sm sm:text-base text-muted-foreground mt-2 max-w-2xl">
            A small library of guided practices rooted in the teachings of
            Sri Preethaji & Sri Krishnaji. Tap the star to pin the ones you return to most.
          </p>
        </motion.header>

        {favoritePractices.length > 0 && (
          <section className="mb-10">
            <div className="flex items-center gap-2 mb-3">
              <Star className="w-4 h-4 fill-ojas text-ojas" />
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Your favorites
              </h2>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-5">
              {favoritePractices.map((p, i) => (
                <PracticeCard
                  key={p.slug}
                  practice={p}
                  index={i}
                  isFavorited
                  onToggle={toggle}
                />
              ))}
            </div>
          </section>
        )}

        {otherPractices.length > 0 && (
          <section>
            {favoritePractices.length > 0 && (
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                All practices
              </h2>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-5">
              {otherPractices.map((p, i) => (
                <PracticeCard
                  key={p.slug}
                  practice={p}
                  index={i}
                  isFavorited={isFavorited(p.slug)}
                  onToggle={toggle}
                />
              ))}
            </div>
          </section>
        )}
      </div>
    </AppShell>
  );
};

export default PracticesPage;
