import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Flame, Sparkles, Play, CheckCircle2 } from 'lucide-react';
import { useSereneMind } from '@/components/common/SereneMindProvider';

interface SacredPracticeWidgetProps {
  practiceType?: 'serene_mind' | 'soul_sync' | 'heart_contemplation';
  title?: string;
  durationMinutes?: number;
  sourceTeaching?: string;
}

export const SacredPracticeWidget: React.FC<SacredPracticeWidgetProps> = ({
  practiceType = 'serene_mind',
  title = '3-Minute Serene Mind Reset',
  durationMinutes = 3,
  sourceTeaching = 'Settling inner turbulence into pure unshakeable stillness',
}) => {
  const { open } = useSereneMind();

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -2 }}
      className="my-3 overflow-hidden rounded-2xl border border-saffron-gold/30 bg-gradient-to-br from-saffron-gold/10 via-card to-card p-4 shadow-sm backdrop-blur-md"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          {/* Animated Breathing Mandala Icon */}
          <div className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-saffron-gold to-amber-400 text-primary-foreground shadow-sm">
            <motion.span
              animate={{ scale: [1, 1.25, 1], opacity: [0.3, 0.7, 0.3] }}
              transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
              className="absolute inset-0 rounded-xl bg-amber-300/40"
            />
            <Flame className="relative h-5 w-5 text-white" />
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-saffron-gold/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-saffron-gold">
                Guided Practice
              </span>
              <span className="text-[11px] text-muted-foreground">{durationMinutes} min practice</span>
            </div>
            <h4 className="mt-1 font-serif text-sm font-semibold text-foreground">{title}</h4>
            <p className="mt-0.5 text-xs text-muted-foreground/90">{sourceTeaching}</p>
          </div>
        </div>

        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.94 }}
          type="button"
          onClick={() => open('audio', true)}
          className="flex shrink-0 items-center gap-1.5 rounded-full bg-gradient-to-r from-saffron-gold to-amber-500 px-3.5 py-1.5 text-xs font-semibold text-primary-foreground shadow-sm hover:shadow-md transition-shadow"
        >
          <Play className="h-3 w-3 fill-current" />
          <span>Begin</span>
        </motion.button>
      </div>
    </motion.div>
  );
};
