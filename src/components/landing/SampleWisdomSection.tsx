import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronLeft, ChevronRight, Quote, Youtube, Sparkles } from 'lucide-react';

interface Teaching {
  title: string;
  teacher: string;
  quote: string;
  resource: string;
}

export const SampleWisdomSection = () => {
  const { t } = useTranslation();
  const [currentIndex, setCurrentIndex] = useState(0);

  const teachings: Teaching[] = [
    {
      title: t('wisdom.teaching1.title', 'The Beautiful State'),
      teacher: t('wisdom.teaching1.teacher', 'Sri Preethaji'),
      quote: t(
        'wisdom.teaching1.quote',
        'Anger, fear, hurt, loneliness, and frustration are all stressful states. A beautiful state is a state of connection, joy, love, compassion, vitality, and passion. If you are not in a beautiful state, your default state is stress.'
      ),
      resource: 'https://www.youtube.com/watch?v=TqxxCYnAxo8',
    },
    {
      title: t('wisdom.teaching2.title', 'Awakening to Compassion'),
      teacher: t('wisdom.teaching2.teacher', 'Sri Krishnaji'),
      quote: t(
        'wisdom.teaching2.quote',
        'Compassion is not a moral choice or a religious duty, but a natural property of a consciousness that no longer experiences itself as separate. When separation ends, the suffering of another is felt as one\'s own — and action arises spontaneously to meet it.'
      ),
      resource: 'https://www.youtube.com/watch?v=x-mTRlE0TC4',
    },
    {
      title: t('wisdom.teaching3.title', 'The Inner Truth of Suffering'),
      teacher: t('wisdom.teaching3.teacher', 'Sri Preethaji'),
      quote: t(
        'wisdom.teaching3.quote',
        'What keeps suffering alive for days, months, and years after a stressful event is over is obsessive, self-centric thinking — a total, incessant preoccupation with oneself. Realizing that all lingering suffering is self-centric preoccupation is the most powerful antidote.'
      ),
      resource: 'https://www.youtube.com/watch?v=TqxxCYnAxo8',
    },
    {
      title: t('wisdom.teaching4.title', 'The Voice Within'),
      teacher: t('wisdom.teaching4.teacher', 'Sri Preethaji'),
      quote: t(
        'wisdom.teaching4.quote',
        'There is a voice within every person that speaks truth and offers guidance. The reason most people do not hear it is not that the voice is silent — it is that they are not in a state where they can listen. The beautiful state is the condition for hearing.'
      ),
      resource: 'https://www.youtube.com/watch?v=-yGLiryVQoQ',
    },
    {
      title: t('wisdom.teaching5.title', 'Three-Question Meditation'),
      teacher: t('wisdom.teaching5.teacher', 'Sri Preethaji'),
      quote: t(
        'wisdom.teaching5.quote',
        'Meditation is not about a religion; it is about being human — about returning to a beautiful state. Simply observing your state, time, and self-preoccupation without trying to change anything loosens the grip of self-centric thinking and lets the beautiful state return.'
      ),
      resource: 'https://www.youtube.com/watch?v=TqxxCYnAxo8',
    },
  ];

  const handleNext = () => {
    setCurrentIndex((prevIndex) => (prevIndex + 1) % teachings.length);
  };

  const handlePrev = () => {
    setCurrentIndex((prevIndex) => (prevIndex - 1 + teachings.length) % teachings.length);
  };

  return (
    <section id="wisdom" className="py-20 md:py-28 relative overflow-hidden bg-background">
      {/* Background radial gradient */}
      <div className="absolute inset-0 bg-gradient-to-b from-background via-saffron-gold/5 to-background pointer-events-none" />

      <div className="relative z-10 container mx-auto px-6 max-w-4xl">
        {/* Header */}
        <div className="text-center mb-16">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-saffron-gold/10 border border-saffron-gold/20 mb-4"
          >
            <Sparkles className="w-3.5 h-3.5 text-saffron-gold animate-pulse" />
            <span className="text-xs uppercase tracking-widest font-semibold text-saffron-gold">
              {t('wisdom.curatedTeachings', 'Curated Teachings')}
            </span>
          </motion.div>
          <h2 className="font-sacred text-4xl md:text-5xl font-light text-foreground mb-4">
            {t('wisdom.heading', 'Wisdom & Insights')}
          </h2>
          <p className="text-muted-foreground text-sm max-w-md mx-auto">
            {t('wisdom.subheading', 'Explore core concepts from the teachings of Sri Preethaji and Sri Krishnaji.')}
          </p>
        </div>

        {/* Carousel Container */}
        <div className="relative glass-card border border-border/80 p-8 md:p-12 shadow-md rounded-2xl min-h-[360px] flex flex-col justify-between overflow-hidden">
          {/* Quote watermark icon */}
          <div className="absolute top-6 right-8 text-saffron-gold/10 dark:text-saffron-gold/5 pointer-events-none">
            <Quote className="w-24 h-24 stroke-[1]" />
          </div>

          <AnimatePresence mode="wait">
            <motion.div
              key={currentIndex}
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -15 }}
              transition={{ duration: 0.4 }}
              className="flex-1 flex flex-col justify-center"
            >
              <h3 className="font-sacred text-2xl md:text-3xl font-light text-gradient-gold mb-6">
                {teachings[currentIndex].title}
              </h3>
              
              <blockquote className="font-sacred text-lg md:text-xl italic text-foreground/90 leading-relaxed mb-8 border-l-2 border-saffron-gold/30 pl-4 md:pl-6">
                "{teachings[currentIndex].quote}"
              </blockquote>

              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mt-auto pt-4 border-t border-border/50">
                <div>
                  <span className="text-xs text-muted-foreground uppercase tracking-widest">
                    {t('wisdom.teacherLabel', 'Teacher')}
                  </span>
                  <p className="text-sm font-semibold text-deep-earth dark:text-foreground/90">
                    {teachings[currentIndex].teacher}
                  </p>
                </div>

                <a
                  href={teachings[currentIndex].resource}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 text-xs font-semibold text-saffron-gold hover:text-pale-gold transition-colors self-start sm:self-auto bg-saffron-gold/10 hover:bg-saffron-gold/20 px-3.5 py-2 rounded-full border border-saffron-gold/20"
                >
                  <Youtube className="w-4 h-4" />
                  <span>{t('wisdom.watchYoutube', 'Watch Teaching on YouTube')}</span>
                </a>
              </div>
            </motion.div>
          </AnimatePresence>

          {/* Navigation Controls */}
          <div className="flex items-center justify-between mt-8 pt-4">
            {/* Dots */}
            <div className="flex gap-1.5">
              {teachings.map((_, index) => (
                <button
                  key={index}
                  onClick={() => setCurrentIndex(index)}
                  className={`w-2 h-2 rounded-full transition-all duration-300 ${
                    index === currentIndex
                      ? 'bg-saffron-gold w-6'
                      : 'bg-border hover:bg-muted-foreground/30'
                  }`}
                  aria-label={t('wisdom.goToSlide', 'Go to slide {{index}}', { index: index + 1 })}
                />
              ))}
            </div>

            {/* Arrows */}
            <div className="flex gap-2">
              <button
                onClick={handlePrev}
                className="w-10 h-10 rounded-full border border-border bg-background/50 hover:border-saffron-gold/40 flex items-center justify-center text-foreground hover:text-saffron-gold transition-all"
                aria-label={t('wisdom.prevTeaching', 'Previous teaching')}
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <button
                onClick={handleNext}
                className="w-10 h-10 rounded-full border border-border bg-background/50 hover:border-saffron-gold/40 flex items-center justify-center text-foreground hover:text-saffron-gold transition-all"
                aria-label={t('wisdom.nextTeaching', 'Next teaching')}
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
