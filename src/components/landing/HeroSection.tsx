import { useTranslation } from 'react-i18next';
import { useState, useEffect } from 'react';
import { motion, MotionConfig } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowRight, Play, Sparkles, Cloud, Activity, Compass, Heart } from 'lucide-react';
import heroImage from '@/assets/hero-spiritual.webp';
import { FloatingParticles } from './FloatingParticles';
import { ContinuePracticeCard } from './ContinuePracticeCard';
import { DemoModal, hasSeenTour, recordTourOutcome, WelcomePrompt } from './DemoModal';
import { getConsent } from '@/components/common/CookieConsentBanner';

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
  const [welcomeVisible, setWelcomeVisible] = useState(false);

  useEffect(() => {
    // Both this prompt and the cookie banner anchor bottom-right — showing both at
    // once on a first-ever visit stacks them. Consent is the more important ask, so
    // defer the tour prompt until it's resolved; "Take a Tour" stays in the user menu.
    if (!hasSeenTour() && getConsent() !== null) {
      setWelcomeVisible(true);
    }
  }, []);

  const startTour = () => {
    setWelcomeVisible(false);
    setDemoOpen(true);
  };

  const dismissWelcome = () => {
    recordTourOutcome('dismissed');
    setWelcomeVisible(false);
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
        {/* Background Image with Ambient Breath Motion */}
        <motion.div
          className="absolute inset-0"
          animate={{ scale: [1, 1.03, 1] }}
          transition={{ duration: 12, repeat: Infinity, ease: 'easeInOut' }}
        >
          <img
            src={heroImage}
            alt=""
            width={1920}
            height={1080}
            fetchpriority="high"
            decoding="async"
            className="w-full h-full object-cover"
          />

          <div className="absolute inset-0 bg-gradient-to-b from-black/85 via-black/75 to-background" />
          <div className="absolute inset-0 bg-gradient-to-r from-black/35 via-transparent to-black/35" />
        </motion.div>

        {/* Mandala Corner Motifs */}
        <MandalaSVG className="absolute -top-24 -left-24 w-72 h-72 text-saffron-gold/30 dark:text-saffron-gold/20 opacity-[0.08] pointer-events-none z-10" />
        <MandalaSVG className="absolute -top-24 -right-24 w-72 h-72 text-saffron-gold/30 dark:text-saffron-gold/20 opacity-[0.08] pointer-events-none z-10" />

        {/* Floating Particles */}
        <FloatingParticles />

        {/* Content */}
        <div className="relative z-10 container mx-auto px-6 text-center pt-28 md:pt-24 pb-16">
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
              <Sparkles className="w-4 h-4 text-ojas" />
              <span className="text-sm text-foreground font-medium">{t('landing.hero.badge')}</span>
            </motion.div>

            {/* Main Headline */}
            <motion.h1
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3, duration: 0.7 }}
              className="font-sacred text-center mb-8 leading-[1.1] tracking-tight"
            >
              <span className="text-white/85 font-light text-4xl sm:text-5xl md:text-6xl lg:text-7xl block">{t('landing.hero.heading1')}</span>
              <span className="text-gradient-gold font-bold text-6xl sm:text-7xl md:text-8xl lg:text-9xl block mt-2">{t('landing.hero.heading2')}</span>
            </motion.h1>

            {/* Subtitle */}
            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5, duration: 0.7 }}
              className="text-lg md:text-xl text-white/95 drop-shadow-md mb-8 max-w-2xl mx-auto leading-relaxed font-sans"
            >
              {t('landing.hero.subtitle')}
            </motion.p>


            {/* State Check-In */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.6, duration: 0.7 }}
              className="mb-12"
            >
              <h2 className="text-sm uppercase tracking-[0.2em] text-saffron-gold/90 font-sans font-semibold mb-5 drop-shadow">
                {t('landing.hero.stateCheckIn', 'How is your inner state right now?')}
              </h2>
              <div className="flex justify-center gap-3.5 flex-wrap">
                {[
                  { key: 'anxious', label: t('mood.anxious', 'Anxious'), icon: Cloud, color: 'hover:text-amber-500 hover:ring-amber-500/30' },
                  { key: 'restless', label: t('mood.restless', 'Restless'), icon: Activity, color: 'hover:text-orange-500 hover:ring-orange-500/30' },
                  { key: 'peace', label: t('mood.seekingPeace', 'Seeking Peace'), icon: Compass, color: 'hover:text-saffron-gold hover:ring-saffron-gold/30' },
                  { key: 'gratitude', label: t('mood.gratitude', 'Gratitude'), icon: Heart, color: 'hover:text-rose-500 hover:ring-rose-500/30' },
                ].map((mood) => {
                  const Icon = mood.icon;
                  return (
                    <div key={mood.key} className="p-[1px] rounded-full bg-white/[0.04] ring-1 ring-white/10 hover:ring-white/20 transition-all duration-300 hover:-translate-y-0.5 shadow-md">
                      <Link
                        to={`/chat?intent=${mood.key}`}
                        className={`inline-flex items-center gap-2.5 px-5 py-2.5 rounded-full bg-black/45 hover:bg-black/60 text-sm font-medium text-white/90 transition-all ${mood.color}`}
                      >
                        <Icon className="w-4 h-4 shrink-0 opacity-80" />
                        <span>{mood.label}</span>
                      </Link>
                    </div>
                  );
                })}
              </div>
            </motion.div>

            {/* CTA Row — primary CTA + premium play button side by side */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.7, duration: 0.5 }}
              className="flex items-center justify-center gap-6 flex-wrap"
            >
              {/* Primary CTA — Button-in-Button */}
              <Link
                to="/chat"
                className="group inline-flex min-h-12 items-center pl-7 pr-2.5 py-2.5 bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-bold rounded-full transition-all duration-300 hover:scale-105 shadow-xl glow-gold"
              >
                <span>{t('landing.hero.cta')}</span>
                <span className="w-8 h-8 rounded-full bg-black/10 flex items-center justify-center ml-3.5 transition-transform duration-300 group-hover:translate-x-1">
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </span>
              </Link>

              {/* Premium Play Button */}
              <button
                type="button"
                onClick={startTour}
                className="group relative flex min-h-11 items-center gap-3 rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ojas focus-visible:ring-offset-2"
                aria-label="See how AskMukthiGuru works in a three-step tour"
              >
                {/* Animated outer pulse rings */}
                <span className="relative flex-shrink-0">
                  {/* Ring 1 — slow pulse */}
                  <motion.span
                    animate={{ scale: [1, 1.5, 1], opacity: [0.5, 0, 0.5] }}
                    transition={{ duration: 2.8, repeat: Infinity, ease: 'easeOut' }}
                    style={{
                      position: 'absolute',
                      inset: -8,
                      borderRadius: '50%',
                      border: '1.5px solid hsl(var(--ojas-gold) / 0.45)',
                    }}
                  />
                  {/* Ring 2 — faster pulse, offset */}
                  <motion.span
                    animate={{ scale: [1, 1.35, 1], opacity: [0.35, 0, 0.35] }}
                    transition={{ duration: 2.8, repeat: Infinity, ease: 'easeOut', delay: 0.6 }}
                    style={{
                      position: 'absolute',
                      inset: -4,
                      borderRadius: '50%',
                      border: '1px solid hsl(var(--ojas-gold) / 0.25)',
                    }}
                  />

                  {/* Button core — double-bezel */}
                  <motion.span
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.95 }}
                    transition={{ type: 'spring', stiffness: 400, damping: 20 }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      width: 56,
                      height: 56,
                      borderRadius: '50%',
                      background: 'linear-gradient(135deg, hsl(var(--ojas-gold)) 0%, hsl(var(--ojas-gold-light)) 100%)',
                      border: '1.5px solid hsl(var(--ojas-gold-light) / 0.65)',
                      boxShadow: [
                        '0 0 0 1px rgba(255, 255, 255, 0.2) inset',
                        '0 8px 24px hsl(var(--ojas-gold) / 0.55)',
                        '0 2px 8px rgba(0,0,0,0.35)',
                      ].join(', '),
                      position: 'relative',
                    }}
                  >
                    {/* Inner highlight */}
                    <span
                      style={{
                        position: 'absolute',
                        inset: 0,
                        borderRadius: '50%',
                        background: 'radial-gradient(circle at 30% 30%, rgba(255,255,255,0.25), transparent 60%)',
                      }}
                    />
                    <Play
                      style={{
                        width: 18,
                        height: 18,
                        color: '#ffffff',
                        fill: '#ffffff',
                        marginLeft: 2, // optical centering for play icon
                        filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.2))',
                      }}
                    />
                  </motion.span>
                </span>

                {/* Label */}
                <motion.span
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 1, duration: 0.4 }}
                  style={{
                    fontSize: 14,
                    fontWeight: 600,
                    color: 'rgba(255,255,255,0.7)',
                    letterSpacing: '-0.01em',
                    transition: 'color 0.2s',
                  }}
                  className="group-hover:text-white"
                >
                  See how this works
                </motion.span>
              </button>
            </motion.div>

            {/* Microcopy */}
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.8, duration: 0.5 }}
              className="mt-4 text-xs font-light text-muted-foreground/80 tracking-wide"
            >
              {t('landing.hero.microcopy', 'No account needed. Your peace is private.')}
            </motion.p>

            {/* Continue your practice (only if user has favorites) */}
            <ContinuePracticeCard />

            {/* AI Disclosure / Trust Badge */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 1, duration: 0.5 }}
              className="mt-8 inline-flex items-center gap-2 text-xs text-muted-foreground/80 bg-foreground/[0.03] ring-1 ring-border/30 backdrop-blur-md px-4 py-2.5 rounded-full"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
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

      <WelcomePrompt
        isVisible={welcomeVisible}
        onStartTour={startTour}
        onDismiss={dismissWelcome}
      />
      <DemoModal isOpen={demoOpen} onComplete={completeTour} onDismiss={skipTour} />
    </MotionConfig>
  );
};
