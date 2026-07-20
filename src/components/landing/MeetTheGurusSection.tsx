import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { Heart, Sparkles } from 'lucide-react';
import gurusPhoto from '@/assets/gurus-photo.jpg';

export const MeetTheGurusSection = () => {
  const { t } = useTranslation();
  return (
    <section id="gurus" className="scroll-mt-28 py-16 sm:py-24 relative overflow-hidden bg-background">
      {/* Ambient radial glow */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 60% 40% at 50% 0%, hsl(var(--ojas-gold) / 0.07), transparent 70%)',
        }}
      />

      <div className="relative z-10 container mx-auto px-6">
        {/* Section Header */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.1 }}
          transition={{ duration: 0.7 }}
          className="text-center mb-16"
        >
          <h2 className="text-4xl md:text-5xl font-sacred font-bold mb-4">
            <span className="text-foreground">{t('landing.meetGurus.heading1')}</span>{' '}
            <span className="text-gradient-gold">{t('landing.meetGurus.heading2')}</span>
          </h2>
          <p className="text-muted-foreground text-base sm:text-lg max-w-2xl mx-auto font-sans italic">
            {t('landing.meetGurus.subtitle')}
          </p>
        </motion.div>

        {/* Social Proof Stats */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.1 }}
          transition={{ duration: 0.7, delay: 0.1 }}
          className="max-w-4xl mx-auto mb-16"
        >
          <div className="grid grid-cols-2 md:grid-cols-4 gap-y-8 md:gap-y-0 py-8 bg-card/30 backdrop-blur-xl ring-1 ring-border/40 rounded-2xl shadow-xl">
            {[
              { value: '30M+', label: t('landing.meetGurus.stat1', 'Souls Guided'), sub: t('landing.meetGurus.stat1Sub', 'Worldwide') },
              { value: '#1', label: t('landing.meetGurus.stat2', 'Bestseller'), sub: t('landing.meetGurus.stat2Sub', 'USA Today & More') },
              { value: 'TEDx', label: t('landing.meetGurus.stat3', 'TEDx Speaker'), sub: t('landing.meetGurus.stat3Sub', 'Global Leaders') },
              { value: '800K+', label: t('landing.meetGurus.stat4', 'Ekam Meditators'), sub: t('landing.meetGurus.stat4Sub', 'Mass Gatherings') },
            ].map((stat, i) => (
              <div key={i} className="text-center px-4 flex flex-col justify-center border-border/30 border-r last:border-0 odd:border-r even:border-r-0 md:even:border-r md:last:border-r-0">
                <span className="font-sacred text-3xl sm:text-4xl md:text-5xl font-bold text-saffron-gold mb-1.5 block">{stat.value}</span>
                <span className="text-[13px] font-semibold text-foreground/90 leading-tight block">{stat.label}</span>
                <span className="text-[11px] text-muted-foreground mt-0.5 block">{stat.sub}</span>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Guru Card */}
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.1 }}
          transition={{ duration: 0.7, delay: 0.2 }}
          className="max-w-2xl md:max-w-3xl lg:max-w-5xl mx-auto"
        >
          <div className="relative overflow-hidden rounded-[2rem] bg-card/45 backdrop-blur-xl ring-1 ring-border/40 p-8 md:p-12 shadow-2xl transition-all duration-500 hover:ring-white/10 group">
            <div className="flex flex-col md:flex-row gap-8 lg:gap-12 items-center">
              {/* Guru Photo */}
              <motion.div
                className="relative shrink-0"
                whileHover={{ scale: 1.03 }}
                transition={{ duration: 0.4 }}
              >
                {/* Aura shadow effect */}
                <div className="absolute inset-0 rounded-full bg-ojas/10 blur-xl opacity-80 group-hover:scale-110 transition-transform duration-500" />
                <div className="w-40 h-40 md:w-48 md:h-48 rounded-full overflow-hidden p-[3px] bg-gradient-to-tr from-ojas via-ojas-light to-ojas-dark shadow-2xl relative">
                  <div className="w-full h-full rounded-full overflow-hidden bg-background">
                    <img
                      src={gurusPhoto}
                      alt="Sri Preethaji & Sri Krishnaji"
                      width={192}
                      height={192}
                      loading="lazy"
                      decoding="async"
                      className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                    />
                  </div>
                  {/* Gradient overlay */}
                  <div className="absolute inset-0 rounded-full bg-gradient-to-t from-background/10 to-transparent pointer-events-none" />
                </div>
                <div className="absolute -top-1 -right-1 w-9 h-9 rounded-full bg-gradient-to-br from-ojas to-ojas-light flex items-center justify-center shadow-lg">
                  <Heart className="w-4.5 h-4.5 text-primary-foreground fill-primary-foreground" />
                </div>
              </motion.div>

              {/* Content */}
              <div className="flex-1 text-center md:text-left">
                <h3 className="text-2xl md:text-3xl font-sacred font-bold text-foreground mb-2">
                  {t('landing.meetGurus.name')}
                </h3>
                <p className="text-ojas font-semibold text-sm uppercase tracking-wider mb-4">
                  {t('landing.meetGurus.title')}
                </p>
                <p className="text-muted-foreground text-sm sm:text-base leading-relaxed mb-6 font-sans">
                  {t('landing.meetGurus.description')}
                </p>


                {/* Key Teachings */}
                <div className="flex flex-wrap gap-3 justify-center md:justify-start">
                  {['Beautiful State', 'Consciousness', 'Inner Peace', 'Oneness'].map((tag) => (
                    <span
                      key={tag}
                      className="px-3 py-1 rounded-full text-sm bg-ojas/10 text-ojas border border-ojas/20 font-medium"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Teachings Quote */}
            <div className="mt-8 pt-8 border-t border-border">
              <div className="flex items-start gap-4">
                <Sparkles className="w-6 h-6 text-ojas flex-shrink-0 mt-1" />
                <blockquote className="text-lg italic text-foreground">
                  {t('landing.meetGurus.quote')}
                </blockquote>
              </div>
            </div>
          </div>
        </motion.div>

        {/* AI Disclosure */}
        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, delay: 0.5 }}
          className="text-center mt-8 text-sm text-muted-foreground"
        >
          <Heart className="w-4 h-4 inline mr-2 text-ojas" />
          {t('landing.meetGurus.disclosure')}
        </motion.p>
      </div>
    </section>
  );
};
