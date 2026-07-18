import { useTranslation } from 'react-i18next';
import { useState, useEffect } from 'react';
import { motion, MotionConfig } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowRight, Play, Sparkles } from 'lucide-react';
import heroImage from '@/assets/hero-spiritual.webp';
import { FloatingParticles } from './FloatingParticles';
import { ContinuePracticeCard } from './ContinuePracticeCard';
import { DemoModal, hasSeenTour, recordTourOutcome, WelcomePrompt } from './DemoModal';
import { getConsent } from '@/components/common/CookieConsentBanner';

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
        {/* Background Image with Light Overlay */}
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

          <div className="absolute inset-0 bg-gradient-to-b from-background/40 via-background/25 to-background/80" />
          <div className="absolute inset-0 bg-gradient-to-r from-background/20 via-transparent to-background/20" />
        </div>

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
              className="font-sacred text-5xl sm:text-6xl md:text-7xl lg:text-8xl font-light mb-6 leading-[1.05] tracking-tight"
            >
              <span className="text-foreground">{t('landing.hero.heading1')}</span>
              <br />
              <span className="text-gradient-gold">{t('landing.hero.heading2')}</span>
            </motion.h1>

            {/* Subtitle */}
            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5, duration: 0.7 }}
              className="text-lg md:text-xl text-muted-foreground mb-10 max-w-2xl mx-auto leading-relaxed"
            >
              {t('landing.hero.subtitle')}
            </motion.p>

            {/* CTA Row — primary CTA + premium play button side by side */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.7, duration: 0.5 }}
              className="flex items-center justify-center gap-4 flex-wrap"
            >
              {/* Primary CTA */}
              <Link
                to="/chat"
                className="group inline-flex min-h-11 items-center gap-3 px-8 py-4 bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-semibold rounded-full transition-all duration-300 hover:scale-105 shadow-lg glow-gold motion-reduce:transform-none"
              >
                <span>{t('landing.hero.cta')}</span>
                <motion.span
                  animate={{ x: [0, 5, 0] }}
                  transition={{ duration: 1.5, repeat: Infinity }}
                  className="motion-reduce:!transform-none"
                >
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </motion.span>
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

            {/* Continue your practice (only if user has favorites) */}
            <ContinuePracticeCard />

            {/* AI Disclosure */}
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 1, duration: 0.5 }}
              className="mt-8 inline-block text-sm text-foreground bg-background/80 backdrop-blur-sm px-4 py-2 rounded-full"
            >
              {t('landing.hero.disclaimer')}
            </motion.p>
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
