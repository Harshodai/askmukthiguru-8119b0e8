import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { BookOpen, Sparkles, Volume2, ChevronRight, CheckCircle2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { hapticAudio } from '@/lib/audio/hapticAudio';

export type FamiliarityLevel = 'seeker' | 'practitioner' | 'advanced_meditator';

interface SanskritConcept {
  term: string;
  transliteration: string;
  translation: string;
  explanation: string;
  mastered: boolean;
}

interface FamiliarityProgressWheelProps {
  level: FamiliarityLevel;
  totalConversations?: number;
  totalReflections?: number;
  onUpdateLevel?: (newLevel: FamiliarityLevel) => void;
}

const SANSKRIT_LEXICON: SanskritConcept[] = [
  {
    term: 'आनन्द',
    transliteration: 'Ananda',
    translation: 'Uncaused Inner Joy',
    explanation: 'Joy arising not from external stimuli or achievements, but from the unconditioned presence of the soul.',
    mastered: true,
  },
  {
    term: 'साधना',
    transliteration: 'Sadhana',
    translation: 'Dedicated Daily Practice',
    explanation: 'Daily disciplined meditation, pranayama, and contemplation to quiet the default mode network.',
    mastered: true,
  },
  {
    term: 'दीक्षा',
    transliteration: 'Deeksha',
    translation: 'Consciousness Transfer',
    explanation: 'Energy transmission that activates neural transformation from suffering state into Beautiful State.',
    mastered: true,
  },
  {
    term: 'अन्तःकरण',
    transliteration: 'Antahkarana',
    translation: 'Inner Instrument of Mind',
    explanation: 'The fourfold psyche (Manas, Buddhi, Chitta, Ahamkara) that perceives and reacts to experience.',
    mastered: false,
  },
  {
    term: 'मुक्ति',
    transliteration: 'Mukthi',
    translation: 'Enlightenment & Freedom',
    explanation: 'Total freedom from the illusion of the separate, isolated self and merging with Universal Consciousness.',
    mastered: false,
  },
];

export const FamiliarityProgressWheel: React.FC<FamiliarityProgressWheelProps> = ({
  level = 'practitioner',
  totalConversations = 18,
  totalReflections = 9,
}) => {
  const [showLexicon, setShowLexicon] = useState(false);

  const levelConfigs: Record<
    FamiliarityLevel,
    { title: string; subtitle: string; percent: number; guidanceTone: string }
  > = {
    seeker: {
      title: 'Seeker (Sadhaka)',
      subtitle: 'Gentle, clear explanations with accessible analogies and simplified Sanskrit.',
      percent: 33,
      guidanceTone: 'Foundational Contemplation',
    },
    practitioner: {
      title: 'Practitioner (Abhyasi)',
      subtitle: 'Balanced philosophical depth, structured breathwork cues, and direct inquiry.',
      percent: 66,
      guidanceTone: 'Deep Experiential Practice',
    },
    advanced_meditator: {
      title: 'Advanced Meditator (Jnani)',
      subtitle: 'Neurobiological terminology, direct non-dual insight, and esoteric consciousness states.',
      percent: 100,
      guidanceTone: 'Direct Non-Dual Realization',
    },
  };

  const currentCfg = levelConfigs[level];

  return (
    <div className="rounded-3xl border border-border/50 bg-card/80 backdrop-blur-md p-6 shadow-sm space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          {/* Radial SVG Progress Arc */}
          <div className="relative w-16 h-16 shrink-0 flex items-center justify-center">
            <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
              <path
                className="text-muted/30"
                strokeWidth="3.5"
                stroke="currentColor"
                fill="none"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              />
              <motion.path
                className="text-saffron-gold"
                strokeDasharray={`${currentCfg.percent}, 100`}
                strokeWidth="3.5"
                strokeLinecap="round"
                stroke="currentColor"
                fill="none"
                initial={{ strokeDasharray: '0, 100' }}
                animate={{ strokeDasharray: `${currentCfg.percent}, 100` }}
                transition={{ duration: 1.2, ease: 'easeOut' }}
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              />
            </svg>
            <span className="absolute font-mono text-xs font-semibold text-foreground">
              {currentCfg.percent}%
            </span>
          </div>

          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-serif text-base font-semibold text-foreground">{currentCfg.title}</h3>
              <Badge variant="outline" className="text-[10px] text-saffron-gold border-saffron-gold/40">
                {currentCfg.guidanceTone}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5 max-w-md">{currentCfg.subtitle}</p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => {
            hapticAudio.playTapTick();
            setShowLexicon((prev) => !prev);
          }}
          className="inline-flex items-center gap-2 rounded-2xl border border-saffron-gold/30 bg-saffron-gold/10 px-4 py-2 text-xs font-medium text-saffron-gold transition-all hover:bg-saffron-gold/20 shrink-0"
        >
          <BookOpen className="w-3.5 h-3.5" />
          <span>Sanskrit Lexicon</span>
          <ChevronRight className={`w-3.5 h-3.5 transition-transform ${showLexicon ? 'rotate-90' : ''}`} />
        </button>
      </div>

      {/* Sanskrit Lexicon Expandable Drawer */}
      <AnimatePresence>
        {showLexicon && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden rounded-2xl border border-border/40 bg-background/50 p-4 space-y-3"
          >
            <div className="flex items-center justify-between text-xs text-muted-foreground border-b border-border/40 pb-2">
              <span className="font-semibold uppercase tracking-wider text-[10px]">
                Mastered Core Spiritual Concepts
              </span>
              <span className="font-mono text-saffron-gold">
                {SANSKRIT_LEXICON.filter((c) => c.mastered).length} / {SANSKRIT_LEXICON.length} Internalized
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {SANSKRIT_LEXICON.map((concept, idx) => (
                <div
                  key={idx}
                  className="rounded-xl border border-border/40 bg-card/60 p-3 space-y-1.5 backdrop-blur-sm"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-serif text-sm font-semibold text-foreground">
                        {concept.term} ({concept.transliteration})
                      </span>
                      {concept.mastered && (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 fill-emerald-400/20" />
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => hapticAudio.playDispatchChime()}
                      className="text-muted-foreground hover:text-saffron-gold transition-colors p-1"
                      title="Pronounce Term"
                    >
                      <Volume2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <p className="text-xs text-saffron-gold font-medium">{concept.translation}</p>
                  <p className="text-[11px] text-muted-foreground leading-relaxed">{concept.explanation}</p>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
