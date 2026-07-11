import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { MessageCircle, Heart, Sparkles, Flower } from 'lucide-react';

export const HowItWorksSection = () => {
  const { t } = useTranslation();

  const handlePlayClick = () => {
    // Video not yet available — card is non-interactive
  };

  const steps = [
    {
      icon: MessageCircle,
      title: t('landing.howItWorks.step1Title'),
      description: t('landing.howItWorks.step1Desc'),
    },
    {
      icon: Heart,
      title: t('landing.howItWorks.step2Title'),
      description: t('landing.howItWorks.step2Desc'),
    },
    {
      icon: Sparkles,
      title: t('landing.howItWorks.step3Title'),
      description: t('landing.howItWorks.step3Desc'),
    },
    {
      icon: Flower,
      title: t('landing.howItWorks.step4Title'),
      description: t('landing.howItWorks.step4Desc'),
    },
  ];

  return (
    <section id="how-it-works" className="scroll-mt-28 py-12 sm:py-20 md:py-24 relative overflow-hidden bg-muted/30">
      <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-ojas/30 to-transparent" />
      <div className="absolute bottom-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-prana/30 to-transparent" />

      <div className="relative z-10 container mx-auto px-6">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.1 }}
          transition={{ duration: 0.7 }}
          className="text-center mb-16"
        >
          <h2 className="text-4xl md:text-5xl font-bold mb-4">
            <span className="text-foreground">{t('landing.howItWorks.heading1')}</span>{' '}
            <span className="text-gradient-gold">{t('landing.howItWorks.heading2')}</span>
          </h2>
          <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
            {t('landing.howItWorks.subtitle')}
          </p>
        </motion.div>

        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 max-w-6xl mx-auto">
          {steps.map((step, index) => (
            <motion.div
              key={step.title}
              initial={{ opacity: 0, y: 40 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.1 }}
              transition={{ duration: 0.5, delay: index * 0.15 }}
            >
              <div className="glass-card-hover p-6 h-full text-center group shadow-md">
                <div className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-ojas/20 text-ojas text-sm font-bold mb-4 border border-ojas/30">
                  {index + 1}
                </div>

                <div className="relative w-16 h-16 mx-auto mb-4">
                  <div className="absolute inset-0 rounded-full bg-ojas/10 group-hover:bg-ojas/20 group-hover:scale-110 transition-all duration-300 border border-ojas/20" />
                  <div className="relative w-full h-full flex items-center justify-center">
                    <step.icon className="w-8 h-8 text-ojas group-hover:text-ojas-dark transition-colors duration-300" />
                  </div>
                </div>

                <h3 className="text-lg font-semibold text-foreground mb-2">{step.title}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{step.description}</p>
              </div>
            </motion.div>
          ))}
        </div>

        <div className="hidden lg:block absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-3/4 h-px bg-gradient-to-r from-transparent via-ojas/30 to-transparent pointer-events-none" />

        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.1 }}
          transition={{ duration: 0.7, delay: 0.4 }}
          className="max-w-4xl mx-auto mt-16 text-center"
        >
          <button
            className="aspect-video rounded-xl border border-ojas/20 bg-gradient-to-b from-ojas/5 to-transparent flex flex-col items-center justify-center group"
            disabled
            aria-label={t('landing.howItWorks.videoAlt')}
          >
            <motion.div
              animate={{ scale: [1, 1.1, 1] }}
              transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
              className="w-16 h-16 rounded-full bg-ojas/80 hover:bg-ojas flex items-center justify-center text-white text-2xl transition-colors group-hover:bg-ojas"
            >
              ▶
            </motion.div>
            <p className="text-muted-foreground text-sm mt-4">{t('landing.howItWorks.videoPlaceholder')}</p>
          </button>
        </motion.div>
      </div>
    </section>
  );
};
