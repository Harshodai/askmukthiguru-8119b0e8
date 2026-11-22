import { useTranslation } from 'react-i18next';
import { useState } from 'react';
import { motion, MotionConfig, AnimatePresence } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowRight, Play, Sprout, Cloud, Activity, Compass, Heart, ChevronDown } from 'lucide-react';
import heroImage from '@/assets/hero-spiritual.webp';
import { ContinuePracticeCard } from './ContinuePracticeCard';
import { DemoModal, recordTourOutcome } from './DemoModal';
import { WaitlistForm } from './WaitlistForm';

const MandalaSVG = ({ className }: { className?: string }) => (
  <svg
    viewBox="0 0 200 200"
    className={className}
    fill="none"
    stroke="currentColor"
    strokeWidth="0.5"
  >
    <circle cx="100" cy="100" r="90" strokeDasharray="2,2" />
    <circle cx="100" cy="100" r="70" />
    <circle cx="100" cy="100" r="50" strokeDasharray="4,4" />
    <circle cx="100" cy="100" r="30" />
    <circle cx="100" cy="100" r="10" />
    {Array.from({ length: 16 }).map((_, i) => {
      const angle = (i * 360) / 16;
      return (
        <g key={i} transform={`rotate(${angle} 100 100)`}>
          <path d="M100 30 Q95 65 100 100 Q105 65 100 30" />
          <circle cx="100" cy="30" r="1.5" fill="currentColor" />
          <path d="M100 10 Q97 55 100 100" strokeDasharray="1,2" />
        </g>
      );
    })}
  </svg>
);

export const HeroSection = () => {
  const { t } = useTranslation();
  const [demoOpen, setDemoOpen] = useState(false);
  const [moodsOpen, setMoodsOpen] = useState(false);
  const [selectedMood, setSelectedMood] = useState('anxious');
  const configuredDemoVideoUrl = import.meta.env.VITE_LANDING_DEMO_VIDEO_URL?.trim();
  const productDemoVideoUrl = configuredDemoVideoUrl || '/media/askmukthiguru-logo-reveal.mp4';

  const startTour = () => {
    setDemoOpen(true);
  };

  const skipTour = () => {
    recordTourOutcome('skipped');
    setDemoOpen(false);
  };

  const completeTour = () => {
    recordTourOutcome('completed');
    setDemoOpen(false);
  };

  return (
    <MotionConfig reducedMotion="user">
      <section className="relative min-h-dvh flex items-center justify-center overflow-hidden">
        {/* Background Image — calm steady presence */}
        <div className="absolute inset-0">
          <img
            src={heroImage}
            alt=""
            width={1920}
            height={1080}
            fetchPriority="high"
            decoding="async"
            className="w-full h-full object-cover"
          />

          <div className="absolute inset-0 bg-gradient-to-b from-black/45 via-black/38 to-background/82" />
          <div className="absolute inset-0 bg-gradient-to-r from-black/14 via-transparent to-black/14" />
        </div>

        {/* Mandala Corner Motifs */}
        <MandalaSVG className="absolute -top-24 -left-24 w-72 h-72 text-saffron-gold/30 dark:text-saffron-gold/20 opacity-[0.08] pointer-events-none z-10" />
        <MandalaSVG className="absolute -top-24 -right-24 w-72 h-72 text-saffron-gold/30 dark:text-saffron-gold/20 opacity-[0.08] pointer-events-none z-10" />

        {/* Content */}
        <div className="relative z-10 container mx-auto px-6 text-center pt-36 sm:pt-40 md:pt-44 pb-16">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
            className="max-w-2xl md:max-w-3xl lg:max-w-5xl mx-auto"
          >
            {/* Badge */}
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.2, duration: 0.5 }}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass-card mb-8 shadow-md"
            >
              <Sprout className="w-4 h-4 text-ojas" />
              <span className="text-sm text-foreground font-medium">{t('landing.hero.badge')}</span>
            </motion.div>

            {/* Main Headline */}
            <motion.h1
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3, duration: 0.7 }}
              className="font-sacred text-center mb-8 leading-[1.1] tracking-tight relative"
            >
              <span className="text-white font-light text-4xl sm:text-5xl md:text-6xl lg:text-7xl block drop-shadow-[0_2px_16px_rgba(0,0,0,0.85)]">{t('landing.hero.heading1')}</span>
              <span className="text-gradient-sacred-gold font-bold text-6xl sm:text-7xl md:text-8xl lg:text-9xl block mt-2">{t('landing.hero.heading2')}</span>
            </motion.h1>

            {/* Subtitle */}
            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5, duration: 0.7 }}
              className="text-lg md:text-xl text-white drop-shadow-[0_2px_14px_rgba(0,0,0,0.9)] mb-8 max-w-2xl mx-auto leading-relaxed font-sans"
            >
              {t('landing.hero.subtitle')}
            </motion.p>

            {/* State Check-In */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.6, duration: 0.7 }}
              className="mb-8 max-w-2xl mx-auto"
            >
              <div className="flex justify-center mb-3">
                <button
                  type="button"
                  onClick={() => setMoodsOpen(!moodsOpen)}
                  aria-expanded={moodsOpen}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-black/50 backdrop-blur-md border border-white/20 text-[11px] sm:text-xs uppercase tracking-[0.15em] font-medium text-amber-200 hover:text-white hover:border-white/40 transition-colors shadow-md min-h-[44px]"
                >
                  <Sprout className="w-3.5 h-3.5 text-saffron-gold shrink-0" aria-hidden="true" />
                  <span>{t('landing.hero.stateCheckIn', 'What would support you right now?')}</span>
                  <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-200 ${moodsOpen ? 'rotate-180' : ''}`} />
                </button>
              </div>

              <AnimatePresence>
                {moodsOpen && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.25 }}
                    className="overflow-hidden pt-2"
                  >
                    <div className="grid grid-cols-2 sm:flex sm:justify-center gap-2 sm:gap-3 mb-4 w-full max-w-sm sm:max-w-none mx-auto px-1 sm:px-0">
                      {[
                        { key: 'anxious', label: t('landing.hero.moods.anxious.label', 'Anxiety & Overwhelm'), icon: Cloud, color: 'text-amber-400', practice: '3-Min Serene Mind Pranayama', action: '/practices/serene-mind' },
                        { key: 'restless', label: t('landing.hero.moods.restless.label', 'Restless Thoughts'), icon: Activity, color: 'text-orange-400', practice: 'Witnessing Presence (Sakshi)', action: '/practices/wisdom-reflection' },
                        { key: 'peace', label: t('landing.hero.moods.peace.label', 'Seeking Inner Peace'), icon: Compass, color: 'text-saffron-gold', practice: 'Soul Sync Meditation', action: '/practices/soul-sync' },
                        { key: 'gratitude', label: t('landing.hero.moods.gratitude.label', 'Cultivating Love'), icon: Heart, color: 'text-rose-400', practice: 'Beautiful State Contemplation', action: '/practices/beautiful-state' },
                      ].map((mood) => {
                        const Icon = mood.icon;
                        const isSelected = selectedMood === mood.key;
                        return (
                          <button
                            key={mood.key}
                            type="button"
                            onClick={() => setSelectedMood(mood.key)}
                            className={`inline-flex items-center justify-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-2 sm:py-2.5 rounded-full text-[11px] sm:text-xs font-medium transition-all backdrop-blur-md border select-none min-h-[44px] leading-tight text-center ${
                              isSelected
                                ? 'bg-saffron-gold/25 border-saffron-gold text-white shadow-[0_0_20px_rgba(234,179,8,0.35)] scale-102 ring-1 ring-saffron-gold/40'
                                : 'bg-black/50 border-white/15 text-white/80 hover:bg-black/70 hover:text-white hover:border-white/25 active:scale-95'
                            }`}
                          >
                            <Icon className={`w-3.5 h-3.5 ${mood.color} shrink-0`} />
                            <span className="whitespace-normal leading-tight">{mood.label}</span>
                          </button>
                        );
                      })}
                    </div>

                    {/* Dynamic State Contemplation Preview Card */}
                    {(() => {
                      const moodConfigs: Record<string, { title: string; subtitle: string; practice: string; link: string }> = {
                        anxious: {
                          title: t('landing.hero.moods.anxious.title', 'A Calming Pause for Racing Thoughts'),
                          subtitle: t('landing.hero.moods.anxious.subtitle', 'Slow, steady 4s/6s breathing to help you meet racing thoughts with more space.'),
                          practice: t('landing.hero.moods.anxious.cta', 'Begin 3-Min Serene Mind'),
                          link: '/practices/serene-mind',
                        },
                        restless: {
                          title: t('landing.hero.moods.restless.title', 'Resting as the Detached Witness'),
                          subtitle: t('landing.hero.moods.restless.subtitle', 'Observe the stream of restless thoughts without identifying or reacting.'),
                          practice: t('landing.hero.moods.restless.cta', 'Begin Sakshi Contemplation'),
                          link: '/practices/wisdom-reflection',
                        },
                        peace: {
                          title: t('landing.hero.moods.peace.title', 'Cultivating Quiet Harmony'),
                          subtitle: t('landing.hero.moods.peace.subtitle', 'A contemplation on aligning personal intent with quiet inner coherence.'),
                          practice: t('landing.hero.moods.peace.cta', 'Begin Soul Sync'),
                          link: '/practices/soul-sync',
                        },
                        gratitude: {
                          title: t('landing.hero.moods.gratitude.title', 'Radiating from the Beautiful State'),
                          subtitle: t('landing.hero.moods.gratitude.subtitle', 'A quiet reflection on heartfelt presence, gratitude, and connection.'),
                          practice: t('landing.hero.moods.gratitude.cta', 'Begin Beautiful State'),
                          link: '/practices/beautiful-state',
                        },
                      };
                      const current = moodConfigs[selectedMood] || moodConfigs.anxious;

                      return (
                        <div
                          className="rounded-2xl border border-saffron-gold/30 bg-zinc-950/70 p-3.5 shadow-xl backdrop-blur-lg text-left flex items-center justify-between gap-3"
                        >
                          <div className="min-w-0 flex-1">
                            <span className="font-mono text-[10px] uppercase tracking-wider text-saffron-gold">
                              {t('landing.hero.recommendedPractice', 'Recommended Sacred Practice')}
                            </span>
                            <h2 className="font-display text-sm font-semibold text-white tracking-tight truncate mt-0.5">
                              {current.title}
                            </h2>
                            <p className="text-xs text-white/70 line-clamp-1 mt-0.5">
                              {current.subtitle}
                            </p>
                          </div>
                          <Link
                            to={current.link}
                            className="shrink-0 inline-flex items-center gap-1.5 rounded-full bg-saffron-gold px-3.5 py-1.5 text-xs font-bold text-zinc-950 hover:bg-amber-400 transition-all shadow-md"
                          >
                            <Play className="w-3 h-3 fill-current" />
                            <span>{t('landing.hero.start', 'Start')}</span>
                          </Link>
                        </div>
                      );
                    })()}
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>

            {/* Primary Action Hierarchy */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.7, duration: 0.5 }}
              className="flex flex-col items-center gap-3.5"
            >
              {/* Primary CTA */}
              <Link
                to="/chat"
                className="group inline-flex min-h-12 items-center pl-7 pr-3 py-2.5 bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-bold rounded-full transition-all duration-300 hover:scale-105 shadow-xl"
              >
                <span>{t('landing.hero.cta')}</span>
                <span className="w-8 h-8 rounded-full bg-black/10 flex items-center justify-center ml-3.5 transition-transform duration-300 group-hover:translate-x-1">
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </span>
              </Link>

              {/* Alternative Recovery CTA */}
              <Link
                to="/practices/serene-mind?source=landing-hero&path=three-minute-pause"
                className="inline-flex min-h-11 items-center gap-2 rounded-full border border-white/35 bg-black/25 px-4 py-2 text-sm font-semibold text-white transition-colors hover:border-ojas/70 hover:bg-black/45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ojas focus-visible:ring-offset-2 focus-visible:ring-offset-black"
              >
                <Heart className="h-4 w-4 text-ojas" aria-hidden="true" />
                <span>{t('landing.hero.pauseCta', 'Start with a 3-minute pause')}</span>
              </Link>

              {/* Gentle Tour Link */}
              <button
                type="button"
                onClick={startTour}
                className="inline-flex items-center gap-1.5 text-xs font-medium text-white/75 hover:text-white transition-colors py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ojas rounded-sm mt-1"
                aria-label={t('landing.hero.tourAria', 'See how AskMukthiGuru works in a three-step tour')}
              >
                <Play className="w-3 h-3 fill-current" />
                <span>{t('landing.hero.seeHowThisWorks', 'See how this works')}</span>
              </button>
            </motion.div>

            {/* Microcopy */}
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.8, duration: 0.5 }}
              className="mt-4 text-xs font-medium text-white/85 tracking-wide drop-shadow-[0_1px_8px_rgba(0,0,0,0.9)]"
            >
              {t('landing.hero.microcopy', 'No account needed. Your peace is private.')}
            </motion.p>
            <WaitlistForm />

            {/* Continue your practice (only if user has favorites) */}
            <ContinuePracticeCard />

            {/* AI Disclosure / Trust Badge */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 1, duration: 0.5 }}
              className="mt-8 inline-flex items-center gap-2 text-xs text-white/90 bg-black/35 ring-1 ring-white/20 backdrop-blur-md px-4 py-2.5 rounded-full"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 motion-safe:animate-pulse" />
              <span>{t('landing.hero.disclaimer')}</span>
            </motion.div>

          </motion.div>
        </div>

        {/* Scroll Indicator */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.2, duration: 0.5 }}
          className="absolute bottom-8 left-1/2 -translate-x-1/2"
        >
          <motion.div
            animate={{ y: [0, 10, 0] }}
            transition={{ duration: 2, repeat: Infinity }}
            className="w-6 h-10 border-2 border-ojas/40 rounded-full flex justify-center pt-2"
          >
            <motion.div className="w-1.5 h-1.5 bg-ojas rounded-full" />
          </motion.div>
        </motion.div>
      </section>

      <DemoModal
        isOpen={demoOpen}
        onComplete={completeTour}
        onDismiss={skipTour}
        productVideoUrl={productDemoVideoUrl}
        videoCaption={
          configuredDemoVideoUrl
            ? undefined
            : 'A short cinematic AskMukthiGuru brand reveal. The interactive tour below remains available if you prefer to explore at your own pace.'
        }
      />
    </MotionConfig>
  );
};
