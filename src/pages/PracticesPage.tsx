import { useState } from 'react';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowRight, Clock, Sprout, Flame, Heart, Moon, Star } from 'lucide-react';
import { PublicShell } from '@/components/layout/PublicShell';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { practices, getLocalizedPractice, type Practice } from '@/lib/practicesContent';
import { useFavorites } from '@/hooks/useFavorites';
import { useDailyTeaching } from '@/hooks/useDailyTeaching';
import { DailyTeachingCard } from '@/components/ritual/DailyTeachingCard';
import { UpcomingEventsCard } from '@/components/ritual/UpcomingEventsCard';
import { cn } from '@/lib/utils';
import { usePageMeta } from '@/hooks/usePageMeta';
import { useToast } from '@/hooks/use-toast';
import { useTranslation } from 'react-i18next';
import { buildCanonical, PRODUCTION_OG_IMAGE } from '@/lib/domain';

const accentMap: Record<Practice['accent'], { icon: typeof Flame; ring: string; bg: string; text: string }> = {
  ojas: { icon: Sprout, ring: 'ring-ojas/30', bg: 'bg-ojas/10', text: 'text-ojas-ink' },
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
  const { t } = useTranslation();
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
        aria-label={isFavorited ? t('practices.detail.removeFavorite') : t('practices.detail.addFavorite')}
        aria-pressed={isFavorited}
        title={isFavorited ? t('practices.detail.removeFavorite') : t('practices.detail.addFavorite')}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onToggle(p.slug);
          toast({
            title: isFavorited ? t('practices.detail.removeFavorite') : t('practices.detail.addFavorite'),
            description: p.title,
          });
        }}
        className="absolute top-3 right-3 z-10 min-w-[44px] min-h-[44px] flex items-center justify-center rounded-full bg-background/80 backdrop-blur-md hover:bg-background transition-colors ring-1 ring-border/20"
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
          isSereneMind ? "bg-gradient-to-br from-ojas/[0.08] via-card/50 to-card/30 hover:ring-ojas/50" : "hover:ring-white/10"
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
                <h3 className="font-display text-xl font-semibold tracking-tight text-foreground truncate">{p.title}</h3>
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
  const [durationFilter, setDurationFilter] = useState<'all' | '3min' | '10min' | '20min'>('all');
  const lang = i18n.language;
  const localizedPractices = practices.map((p) => getLocalizedPractice(p, t, lang));
  const favoritePractices = localizedPractices.filter((p) => favorites.includes(p.slug));
  const otherPractices = localizedPractices.filter((p) => !favorites.includes(p.slug));

  const matchesFilter = (p: Practice) => {
    if (durationFilter === 'all') return true;
    if (durationFilter === '3min') return p.slug === 'serene-mind' || p.slug === 'wisdom-reflection';
    if (durationFilter === '10min') return p.slug === 'daily-reflection' || p.slug === 'beautiful-state';
    if (durationFilter === '20min') return p.slug === 'soul-sync';
    return true;
  };

  const filteredFavorites = favoritePractices.filter(matchesFilter);
  const filteredOther = otherPractices.filter(matchesFilter);

  usePageMeta({
    title: t('seo.practicesTitle') || 'Daily Practices — Guided Meditations | AskMukthiGuru',
    description: t('seo.practicesDescription') || 'Soul Sync, Serene Mind, Beautiful State, and Daily Reflection — short guided practices rooted in the teachings of Sri Preethaji & Sri Krishnaji.',
    canonical: buildCanonical('/practices'),
    ogImage: PRODUCTION_OG_IMAGE,
    jsonLd: {
      '@context': 'https://schema.org',
      '@type': 'ItemList',
      itemListElement: practices.map((p, i) => ({
        '@type': 'ListItem',
        position: i + 1,
        url: buildCanonical(`/practices/${p.slug}`),
        name: p.title,
      })),
    },
  });

  return (
    <PublicShell title={t('practices.title')}>
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

          {/* Quick Decision Filter by Duration */}
          <div className="flex items-center gap-2 flex-wrap mt-5 pt-3 border-t border-border/40">
            <span className="text-xs font-medium text-muted-foreground mr-1">
              {t('practices.filterByTime', 'Filter by duration')}:
            </span>
            {(
              [
                { id: 'all', label: t('practices.filterAll', 'All') },
                { id: '3min', label: t('practices.filterQuick', '3 min (Quick)') },
                { id: '10min', label: t('practices.filterMedium', '5–10 min') },
                { id: '20min', label: t('practices.filterDeep', '15–20 min') },
              ] as const
            ).map((filter) => {
              const active = durationFilter === filter.id;
              return (
                <button
                  key={filter.id}
                  type="button"
                  onClick={() => setDurationFilter(filter.id)}
                  className={cn(
                    "px-3.5 py-1.5 rounded-full text-xs font-medium transition-colors min-h-[36px]",
                    active
                      ? "bg-ojas text-primary-foreground font-semibold shadow-sm"
                      : "bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground"
                  )}
                >
                  {filter.label}
                </button>
              );
            })}
          </div>
        </motion.header>

        {/* Boundary Notice — Non-Clinical Spiritual Wisdom */}
        <div className="mb-8 rounded-2xl border border-border/50 bg-card/60 backdrop-blur-md p-4 sm:p-5 text-left">
          <div className="flex items-start gap-3">
            <Sprout className="w-5 h-5 text-ojas flex-shrink-0 mt-0.5" />
            <div>
              <h2 className="text-xs sm:text-sm font-semibold text-foreground uppercase tracking-wider">
                {t('practices.boundaryNoticeTitle', 'What these practices are and are not')}
              </h2>
              <p className="text-xs sm:text-sm text-muted-foreground mt-1 leading-relaxed">
                {t('practices.boundaryNoticeBody', 'These guided meditations and breathing practices are contemplative spiritual exercises rooted in the wisdom of Sri Preethaji & Sri Krishnaji. They are designed for inner reflection and peaceful awareness, not as medical, clinical, psychiatric, or therapeutic treatments.')}
              </p>
            </div>
          </div>
        </div>

        {/* Core Practice Cards First */}
        {filteredFavorites.length > 0 && (
          <section className="mb-10">
            <div className="flex items-center gap-2 mb-3">
              <Star className="w-4 h-4 fill-ojas text-ojas" />
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                {t('practices.sections.favorites', 'Your favorites')}
              </h2>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-5">
              {filteredFavorites.map((p, i) => (
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

        {filteredOther.length > 0 && (
          <section className="mb-12">
            {filteredFavorites.length > 0 && (
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                {t('practices.sections.all', 'All practices')}
              </h2>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-5">
              {filteredOther.map((p, i) => (
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

        {/* Daily Ritual & Events Section — Placed below core library */}
        <section className="mt-14 pt-8 border-t border-border/50">
          <h2 className="text-base sm:text-lg font-semibold text-foreground mb-6">
            {t('practices.sections.dailyAndEvents', 'Daily Ritual & Community Wisdom')}
          </h2>

          {/* Today's Wisdom — Daily Teaching Card */}
          {dailyTeaching && (
            <div className="mb-8">
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {t('chat.todaysWisdom')}
              </h3>
              <Card className="overflow-hidden border border-ojas/20 bg-card/80 shadow-lg backdrop-blur-lg">
                <div className="flex flex-col md:flex-row">
                  <div className="relative w-full md:w-2/5 aspect-[16/9] md:aspect-auto md:min-h-[200px] overflow-hidden bg-muted/20">
                    <img
                      src={dailyTeaching.image_url}
                      alt={t('chat.teachingAlt')}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t md:bg-gradient-to-r from-card/80 via-transparent to-transparent pointer-events-none" />
                  </div>
                  <div className="flex-1 p-5 sm:p-6 flex flex-col justify-center">
                    <div className="flex items-center gap-1.5 mb-2.5">
                      <Sprout className="w-3.5 h-3.5 text-ojas" />
                      <span className="text-xs font-semibold text-ojas-ink uppercase tracking-widest">
                        {t('practices.dailyWisdom.badge', 'Wisdom of the Day')}
                      </span>
                    </div>
                    {dailyTeaching.caption && (
                      <p className="text-base sm:text-lg text-foreground/90 font-serif leading-relaxed italic">
                        &ldquo;{dailyTeaching.caption}&rdquo;
                      </p>
                    )}
                    <p className="text-xs text-muted-foreground mt-3">
                      {t('common.gurusName', '— Sri Preethaji & Sri Krishnaji')}
                    </p>
                  </div>
                </div>
              </Card>
            </div>
          )}

          {/* Today's Teaching ritual card */}
          <div className="mb-6">
            <DailyTeachingCard />
          </div>

          {/* Upcoming Events */}
          <div className="mb-6 empty:hidden">
            <UpcomingEventsCard />
          </div>
        </section>
      </div>
    </PublicShell>
  );
};

export default PracticesPage;
