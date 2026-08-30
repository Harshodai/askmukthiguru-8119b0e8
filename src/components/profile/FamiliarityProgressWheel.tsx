import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { BookOpen, Volume2, ChevronRight } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { hapticAudio } from '@/lib/audio/hapticAudio';

export type FamiliarityLevel = 'seeker' | 'practitioner' | 'advanced_meditator';

interface SanskritConcept {
  term: string;
  transliteration: string;
  translation: string;
  explanation: string;
}

interface FamiliarityProgressWheelProps {
  /** User-configured guidance depth; this is not a measured mastery score. */
  level: FamiliarityLevel;
  /** Retained for API compatibility; not interpreted as mastery evidence. */
  totalConversations?: number;
  /** Retained for API compatibility; not interpreted as mastery evidence. */
  totalReflections?: number;
  onUpdateLevel?: (newLevel: FamiliarityLevel) => void;
}

const SANSKRIT_LEXICON: SanskritConcept[] = [
  {
    term: 'आनन्द',
    transliteration: 'Ananda',
    translation: 'Inner joy',
    explanation: 'A teaching term used in the tradition to describe a quality of joy not dependent on changing external circumstances.',
  },
  {
    term: 'साधना',
    transliteration: 'Sadhana',
    translation: 'Dedicated practice',
    explanation: 'A sustained practice of meditation, contemplation, or related disciplines.',
  },
  {
    term: 'दीक्षा',
    transliteration: 'Deeksha',
    translation: 'Initiation / transmission',
    explanation: 'A traditional term for spiritual initiation or transmission within a lineage.',
  },
  {
    term: 'अन्तःकरण',
    transliteration: 'Antahkarana',
    translation: 'Inner instrument',
    explanation: 'A classical term for the inner faculties involved in perception, thought, discernment, memory, and sense of self.',
  },
  {
    term: 'मुक्ति',
    transliteration: 'Mukthi',
    translation: 'Liberation',
    explanation: 'A traditional term for freedom from bondage and suffering, understood differently across spiritual schools.',
  },
];

export const FamiliarityProgressWheel: React.FC<FamiliarityProgressWheelProps> = ({
  level = 'practitioner',
}) => {
  const [showLexicon, setShowLexicon] = useState(false);

  const levelConfigs: Record<
    FamiliarityLevel,
    { title: string; subtitle: string; depth: number; guidanceTone: string }
  > = {
    seeker: {
      title: 'Seeker (Sadhaka)',
      subtitle: 'Clear explanations with accessible analogies and introductory Sanskrit.',
      depth: 33,
      guidanceTone: 'Foundational guidance',
    },
    practitioner: {
      title: 'Practitioner (Abhyasi)',
      subtitle: 'Balanced philosophical depth with practical meditation and inquiry cues.',
      depth: 66,
      guidanceTone: 'Experiential guidance',
    },
    advanced_meditator: {
      title: 'Advanced Meditator (Jnani)',
      subtitle: 'Denser philosophical language and fewer introductory explanations.',
      depth: 100,
      guidanceTone: 'Advanced guidance',
    },
  };

  const currentCfg = levelConfigs[level];

  return (
    <div className="rounded-3xl border border-border/50 bg-card/80 backdrop-blur-md p-6 shadow-sm space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="relative w-16 h-16 shrink-0 flex items-center justify-center" aria-label={`Guidance depth: ${currentCfg.depth}%`}>
            <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36" aria-hidden="true">
              <path className="text-muted/30" strokeWidth="3.5" stroke="currentColor" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              <motion.path
                className="text-saffron-gold"
                strokeDasharray={`${currentCfg.depth}, 100`}
                strokeWidth="3.5"
                strokeLinecap="round"
                stroke="currentColor"
                fill="none"
                initial={{ strokeDasharray: '0, 100' }}
                animate={{ strokeDasharray: `${currentCfg.depth}, 100` }}
                transition={{ duration: 1.2, ease: 'easeOut' }}
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              />
            </svg>
            <span className="absolute font-mono text-xs font-semibold text-foreground">{currentCfg.depth}%</span>
          </div>

          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-serif text-base font-semibold text-foreground">{currentCfg.title}</h3>
              <Badge variant="outline" className="text-[10px] text-saffron-gold border-saffron-gold/40">
                {currentCfg.guidanceTone}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5 max-w-md">{currentCfg.subtitle}</p>
            <p className="text-[10px] text-muted-foreground/70 mt-1">This reflects your guidance preference, not a claim of spiritual mastery.</p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => {
            hapticAudio.playTapTick();
            setShowLexicon((prev) => !prev);
          }}
          className="inline-flex items-center gap-2 rounded-2xl border border-saffron-gold/30 bg-saffron-gold/10 px-4 py-2 text-xs font-medium text-saffron-gold transition-all hover:bg-saffron-gold/20 shrink-0 min-h-[44px]"
        >
          <BookOpen className="w-3.5 h-3.5" />
          <span>Sanskrit Lexicon</span>
          <ChevronRight className={`w-3.5 h-3.5 transition-transform ${showLexicon ? 'rotate-90' : ''}`} />
        </button>
      </div>

      <AnimatePresence>
        {showLexicon && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden rounded-2xl border border-border/40 bg-background/50 p-4 space-y-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground border-b border-border/40 pb-2 gap-3">
              <span className="font-semibold uppercase tracking-wider text-[10px]">Core spiritual terms</span>
              <span className="text-[10px] text-muted-foreground">Reference glossary</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {SANSKRIT_LEXICON.map((concept) => (
                <div key={concept.transliteration} className="rounded-xl border border-border/40 bg-card/60 p-3 space-y-1.5 backdrop-blur-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-serif text-sm font-semibold text-foreground">{concept.term} ({concept.transliteration})</span>
                    <button type="button" onClick={() => hapticAudio.playDispatchChime()} className="text-muted-foreground hover:text-saffron-gold transition-colors p-2 min-w-[40px] min-h-[40px] inline-flex items-center justify-center" title="Pronounce term" aria-label={`Pronounce ${concept.transliteration}`}>
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
