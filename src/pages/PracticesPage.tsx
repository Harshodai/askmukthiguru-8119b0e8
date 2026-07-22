import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowRight, Clock, Sparkles, Flame, Heart, Moon, Star } from 'lucide-react';
import { AppShell } from '@/components/layout/AppShell';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { practices, getLocalizedPractice, type Practice } from '@/lib/practicesContent';
import { useFavorites } from '@/hooks/useFavorites';
import { useDailyTeaching } from '@/hooks/useDailyTeaching';
import { cn } from '@/lib/utils';
import { usePageMeta } from '@/hooks/usePageMeta';
import { useToast } from '@/hooks/use-toast';
import { useTranslation } from 'react-i18next';

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
  const { toast } = useToast();
  const isSereneMind = p.slug === 'serene-mind';
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: i * 0.06 }}
      className={cn("relative", isSereneMind && "sm:col-span-2")}
    >
      <button
        type="button"
        aria-label={isFavorited ? `Remove ${p.title} from favorites` : `Add ${p.title} to favorites`}
        aria-pressed={isFavorited}
        title={isFavorited ? 'Remove from favorites' : 'Add to favorites'}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onToggle(p.slug);
          toast({
            title: isFavorited ? 'Removed from favorites' : 'Added to favorites',
            description: `${p.title} has been ${isFavorited ? 'removed from' : 'added to'} your list.`,
          });
        }}
        className="absolute top-4 right-4 z-10 p-2 rounded-full bg-background/80 backdrop-blur-md hover:bg-background transition-colors ring-1 ring-border/20"
      >
        <Star
          className={cn(
            'w-4 h-4 transition-colors',
            isFavorited ? 'fill-ojas text-ojas' : 'text-muted-foreground',
          )}
        />
      </button>
      <Link to={`/practices/${p.slug}`} className="block group">
        <Card className={cn(
          "h-full p-6 transition-all duration-500 hover:shadow-2xl ring-1 hover:-translate-y-1 bg-card/40 backdrop-blur-xl",
          A.ring,
          isSereneMind ? "bg-gradient-to-br from-ojas/[0.08] via-card/50 to-card/30 hover:ring-ojas/50 shadow-[0_4px_30px_rgba(245,158,11,0.06)]" : "hover:ring-white/10"
        )}>
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-5">
            <div className={cn(
              "w-12 h-12 rounded-xl flex items-center justify-center shrink-0 shadow-inner",
              A.bg
            )}>
              <A.icon className={cn("w-5.5 h-5.5", A.text)} />
            </div>
            <div className="flex-1 min-w-0 pr-8">
              <div className="flex items-center justify-between gap-3">
                <h3 className="font-sacred text-xl font-semibold text-foreground truncate">{p.title}</h3>
                <span className="w-8 h-8 rounded-full bg-white/5 group-hover:bg-white/10 flex items-center justify-center transition-colors">
                  <ArrowRight className="w-4 h-4 text-muted-foreground group-hover:text-ojas transition-colors shrink-0" />
                </span>
              </div>
              <p className="text-sm text-muted-foreground mt-1.5 font-sans leading-relaxed">{p.tagline}</p>
              <div className="flex flex-wrap gap-2 mt-4">
                <Badge variant="secondary" className="gap-1 bg-white/5 border-none text-[11px]">
                  <Clock className="w-3.5 h-3.5" /> {p.durationLabel}
                </Badge>
                {p.intentions.slice(0, 2).map((tag) => (
                  <Badge key={tag} variant="outline" className="text-[10px] border-border/40 text-muted-foreground">
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
  const { t, i18n } = useTranslation();
  const { favorites, toggle, isFavorited } = useFavorites();
  const { teaching: dailyTeaching } = useDailyTeaching();
  const lang = i18n.language;
  const localizedPractices = practices.map((p) => getLocalizedPractice(p, t, lang));
  const favoritePractices = localizedPractices.filter((p) => favorites.includes(p.slug));
  const otherPractices = localizedPractices.filter((p) => !favorites.includes(p.slug));

  usePageMeta({
    title: t('seo.practicesTitle') || 'Daily Practices — Guided Meditations | AskMukthiGuru',
    description: t('seo.practicesDescription') || 'Soul Sync, Serene Mind, Beautiful State, and Daily Reflection — short guided practices rooted in the teachings of Sri Preethaji & Sri Krishnaji.',
    canonical: 'https://askmukthiguru.lovable.app/practices',
    ogImage: 'https://askmukthiguru.lovable.app/og-image.png',
    jsonLd: {
      '@context': 'https://schema.org',
      '@type': 'ItemList',
      name: 'AskMukthiGuru Practices',
      itemListElement: practices.map((p, i) => ({
        '@type': 'ListItem',
        position: i + 1,
        url: `https://askmukthiguru.lovable.app/practices/${p.slug}`,
        name: p.title,
      })),
    },
  });

  return (
    <AppShell title={t('practices.title')}>
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6 sm:py-10">
        <motion.header
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="mb-8"
        >
          <h1 className="text-2xl sm:text-3xl font-semibold text-foreground">{t('practices.title')}</h1>
          <p className="text-sm sm:text-base text-muted-foreground mt-2 max-w-2xl">
            {t('practices.subtitle')}
          </p>
        </motion.header>

        {/* Today's Wisdom — Daily Teaching Card */}
        {dailyTeaching && (
          <motion.section
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="mb-10"
          >
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="w-4 h-4 text-ojas animate-pulse" />
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Today&apos;s Wisdom
              </h2>
            </div>
            <Card className="overflow-hidden border border-ojas/20 bg-card/80 shadow-xl backdrop-blur-lg">
              <div className="flex flex-col md:flex-row">
                {/* Image side */}
                <div className="relative w-full md:w-2/5 aspect-[16/9] md:aspect-auto md:min-h-[220px] overflow-hidden bg-muted/20">
                  <img
                    src={dailyTeaching.image_url}
                    alt="Today's teaching from the Gurus"
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                  {/* Gradient overlay to blend image into card */}
                  <div className="absolute inset-0 bg-gradient-to-t md:bg-gradient-to-r from-card/80 via-transparent to-transparent pointer-events-none" />
                </div>
                {/* Text side */}
                <div className="flex-1 p-6 sm:p-8 flex flex-col justify-center">
                  <div className="flex items-center gap-1.5 mb-3">
                    <Sparkles className="w-3.5 h-3.5 text-ojas" />
                    <span className="text-xs font-semibold text-ojas uppercase tracking-widest">
                      {t('practices.dailyWisdom.badge', 'Wisdom of the Day')}
                    </span>
                  </div>
                  {dailyTeaching.caption && (
                    <p className="text-lg sm:text-xl text-foreground/90 font-serif leading-relaxed italic">
                      &ldquo;{dailyTeaching.caption}&rdquo;
                    </p>
                  )}
                  <p className="text-xs text-muted-foreground mt-4">
                    — Sri Preethaji &amp; Sri Krishnaji
                  </p>
                </div>
              </div>
            </Card>
          </motion.section>
        )}

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
