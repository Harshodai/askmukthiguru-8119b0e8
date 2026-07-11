import React from 'react';
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { Flame, Wind, Brain, Heart } from 'lucide-react';
import { Link } from 'react-router-dom';

export const AboutMeditationSection = React.forwardRef<HTMLElement>(
  function AboutMeditationSection(_props, ref) {
    const { t } = useTranslation();

    const benefits = [
      { icon: Brain, text: t('landing.meditation.benefit1') },
      { icon: Heart, text: t('landing.meditation.benefit2') },
      { icon: Wind, text: t('landing.meditation.benefit3') },
      { icon: Flame, text: t('landing.meditation.benefit4') },
    ];

    return (
      <section ref={ref} id="meditation" className="scroll-mt-28 py-12 sm:py-20 md:py-24 relative overflow-hidden">
        <div className="absolute inset-0 bg-celestial-gradient" />

        <div className="relative z-10 container mx-auto px-6">
          <div className="max-w-6xl mx-auto">
            <div className="grid lg:grid-cols-2 gap-12 items-center">
              <motion.div
                initial={{ opacity: 0, x: -30 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, amount: 0.1 }}
                transition={{ duration: 0.7 }}
              >
                <h2 className="text-4xl md:text-5xl font-bold mb-6">
                  <span className="text-foreground">{t('landing.meditation.heading1')}</span>{' '}
                  <span className="text-gradient-gold">{t('landing.meditation.heading2')}</span>
                  <br />
                  <span className="text-foreground">{t('landing.meditation.heading3')}</span>
                </h2>

                <p className="text-muted-foreground text-lg leading-relaxed mb-6">
                  {t('landing.meditation.para1')}
                </p>

                <p className="text-muted-foreground leading-relaxed mb-8">
                  {t('landing.meditation.para2')}
                </p>

                <div className="grid grid-cols-2 gap-4 mb-8">
                  {benefits.map((benefit, index) => (
                    <motion.div
                      key={benefit.text}
                      initial={{ opacity: 0, y: 20 }}
                      whileInView={{ opacity: 1, y: 0 }}
                      viewport={{ once: true }}
                      transition={{ delay: index * 0.1 }}
                      className="flex items-center gap-3"
                    >
                      <div className="w-10 h-10 rounded-lg bg-ojas/10 flex items-center justify-center border border-ojas/20">
                        <benefit.icon className="w-5 h-5 text-ojas" />
                      </div>
                      <span className="text-sm text-foreground font-medium">{benefit.text}</span>
                    </motion.div>
                  ))}
                </div>

                <Link
                  to="/chat"
                  className="inline-flex items-center gap-2 px-6 py-3 bg-ojas/20 hover:bg-ojas/30 text-foreground font-medium rounded-full transition-all duration-300 hover:scale-105 border border-ojas/30 shadow-md"
                >
                  <Flame className="w-5 h-5 text-ojas" />
                  {t('landing.meditation.cta')}
                </Link>
              </motion.div>

              <motion.div
                initial={{ opacity: 0, x: 30 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, amount: 0.1 }}
                transition={{ duration: 0.7, delay: 0.2 }}
                className="relative"
              >
                <div className="glass-card p-8 md:p-12 shadow-lg">
                  <div className="aspect-square max-w-sm mx-auto relative flex items-center justify-center">
                    <motion.div
                      animate={{ scale: [1, 1.2, 1], opacity: [0.3, 0.1, 0.3] }}
                      transition={{ duration: 4, repeat: Infinity }}
                      className="absolute inset-0 rounded-full border-2 border-ojas/30"
                    />
                    <motion.div
                      animate={{ scale: [1, 1.15, 1], opacity: [0.4, 0.15, 0.4] }}
                      transition={{ duration: 4, repeat: Infinity, delay: 0.5 }}
                      className="absolute inset-8 rounded-full border-2 border-ojas/40"
                    />
                    <motion.div
                      animate={{ scale: [1, 1.1, 1], opacity: [0.5, 0.2, 0.5] }}
                      transition={{ duration: 4, repeat: Infinity, delay: 1 }}
                      className="absolute inset-16 rounded-full border-2 border-ojas/50"
                    />

                    <motion.div
                      animate={{
                        scale: [1, 1.05, 0.98, 1.02, 1],
                        rotate: [-1, 1, -0.5, 0.5, -1]
                      }}
                      transition={{ duration: 2, repeat: Infinity }}
                      className="relative"
                    >
                      <div className="w-16 h-24 relative">
                        <div className="absolute inset-0 blur-xl bg-ojas/50 rounded-full" />
                        <svg viewBox="0 0 64 96" className="w-full h-full relative">
                          <defs>
                            <linearGradient id="flameGradient" x1="0%" y1="100%" x2="0%" y2="0%">
                              <stop offset="0%" stopColor="hsl(30, 100%, 50%)" />
                              <stop offset="50%" stopColor="hsl(43, 96%, 56%)" />
                              <stop offset="100%" stopColor="hsl(45, 100%, 85%)" />
                            </linearGradient>
                          </defs>
                          <path
                            d="M32 0 C32 0, 64 40, 64 65 C64 82, 50 96, 32 96 C14 96, 0 82, 0 65 C0 40, 32 0, 32 0Z"
                            fill="url(#flameGradient)"
                          />
                          <path
                            d="M32 30 C32 30, 48 55, 48 68 C48 80, 42 88, 32 88 C22 88, 16 80, 16 68 C16 55, 32 30, 32 30Z"
                            fill="hsl(45, 100%, 95%)"
                            opacity="0.8"
                          />
                        </svg>
                      </div>
                    </motion.div>
                  </div>

                  <div className="text-center mt-6">
                    <p className="text-muted-foreground text-sm">
                      {t('landing.meditation.breathingCue')}
                    </p>
                  </div>
                </div>
              </motion.div>
            </div>
          </div>
        </div>
      </section>
    );
  }
);
