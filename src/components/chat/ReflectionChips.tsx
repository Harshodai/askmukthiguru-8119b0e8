import React from 'react';
import { motion } from 'framer-motion';
import { Sparkles, ArrowRight } from 'lucide-react';
import { hapticAudio } from '@/lib/audio/hapticAudio';

interface ReflectionChipsProps {
  suggestions: string[];
  onSelectPrompt: (prompt: string) => void;
}

export const ReflectionChips: React.FC<ReflectionChipsProps> = ({ suggestions, onSelectPrompt }) => {
  if (!suggestions || suggestions.length === 0) return null;

  return (
    <div className="mt-3 flex flex-col gap-1.5">
      <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/75">
        <Sparkles className="h-3 w-3 text-saffron-gold" /> Deepen Your Contemplation
      </p>
      <div className="flex flex-wrap gap-2">
        {suggestions.map((prompt, idx) => (
          <motion.button
            key={idx}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: idx * 0.05 }}
            whileHover={{ scale: 1.02, y: -1 }}
            whileTap={{ scale: 0.96 }}
            onClick={() => {
              hapticAudio.playTapTick();
              onSelectPrompt(prompt);
            }}
            className="group inline-flex items-center gap-1.5 rounded-xl border border-saffron-gold/25 bg-card/70 px-3 py-1.5 text-xs text-foreground/90 shadow-sm backdrop-blur-sm transition-all hover:border-saffron-gold/50 hover:bg-saffron-gold/10 hover:text-foreground"
          >
            <span>{prompt}</span>
            <ArrowRight className="h-3 w-3 text-saffron-gold/60 transition-transform group-hover:translate-x-0.5 group-hover:text-saffron-gold" />
          </motion.button>
        ))}
      </div>
    </div>
  );
};
