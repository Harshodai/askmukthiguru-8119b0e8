import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, Compass, BookOpen, ShieldCheck, ChevronDown, Activity } from 'lucide-react';

export type ThoughtStage = 
  | 'connecting'     // Connecting to sacred scriptures
  | 'synthesizing'   // Synthesizing discourse teachings
  | 'attributing'    // Attributing verified sources
  | 'composing';     // Composing compassionate guidance

interface StreamingStatusPillProps {
  visible: boolean;
  statusText?: string;
  heartbeat?: boolean;
  latencyMs?: number;
  modelUsed?: string;
  retrievedCount?: number;
}

const STAGES: { id: ThoughtStage; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: 'connecting', label: 'Connecting to sacred scriptures…', icon: Compass },
  { id: 'synthesizing', label: 'Synthesizing discourse teachings…', icon: Sparkles },
  { id: 'attributing', label: 'Attributing verified sources…', icon: ShieldCheck },
  { id: 'composing', label: 'Composing compassionate guidance…', icon: BookOpen },
];

export const StreamingStatusPill: React.FC<StreamingStatusPillProps> = ({
  visible,
  statusText,
  heartbeat,
  latencyMs,
  modelUsed = 'GraphRAG Dual-Level',
  retrievedCount = 3,
}) => {
  const [currentStageIdx, setCurrentStageIdx] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [showInspector, setShowInspector] = useState(false);

  useEffect(() => {
    if (!visible) {
      setElapsed(0);
      setCurrentStageIdx(0);
      return;
    }
    const timer = setInterval(() => setElapsed((prev) => prev + 1), 1000);
    const stageTimer = setInterval(() => {
      setCurrentStageIdx((prev) => (prev < STAGES.length - 1 ? prev + 1 : prev));
    }, 2800);

    return () => {
      clearInterval(timer);
      clearInterval(stageTimer);
    };
  }, [visible]);

  if (!visible) return null;

  const currentStage = STAGES[currentStageIdx];
  const Icon = currentStage.icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -6, scale: 0.95 }}
      transition={{ type: 'spring', stiffness: 380, damping: 26 }}
      className="my-3 flex flex-col items-start gap-1.5"
    >
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setShowInspector((prev) => !prev)}
          className="group relative inline-flex items-center gap-2.5 rounded-full border border-saffron-gold/30 bg-gradient-to-r from-saffron-gold/10 via-card to-saffron-gold/5 px-3.5 py-1.5 shadow-sm backdrop-blur-md transition-all hover:border-saffron-gold/50"
        >
          {/* Glowing Animated Halo */}
          <span className="relative flex h-4 w-4 items-center justify-center">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-saffron-gold/30 opacity-75" />
            <Icon className="relative h-3.5 w-3.5 text-saffron-gold" />
          </span>

          <AnimatePresence mode="wait">
            <motion.span
              key={currentStage.id}
              initial={{ opacity: 0, y: 3 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -3 }}
              transition={{ duration: 0.2 }}
              className="font-serif text-xs font-medium tracking-wide text-foreground"
            >
              {statusText || currentStage.label}
            </motion.span>
          </AnimatePresence>

          <span className="font-mono text-[10px] tabular-nums text-muted-foreground/70">
            {elapsed}s
          </span>

          <ChevronDown
            className={`h-3 w-3 text-muted-foreground/60 transition-transform ${
              showInspector ? 'rotate-180' : ''
            }`}
          />
        </button>
      </div>

      {/* Expandable Pipeline Diagnostics Inspector */}
      <AnimatePresence>
        {showInspector && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="w-full max-w-md overflow-hidden rounded-xl border border-border/40 bg-card/60 p-3 text-xs backdrop-blur-lg"
          >
            <div className="space-y-2">
              <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                <span className="flex items-center gap-1.5 font-medium">
                  <Activity className="h-3 w-3 text-saffron-gold" /> Pipeline Diagnostics
                </span>
                <span className="rounded-full bg-saffron-gold/10 px-2 py-0.5 font-mono text-[10px] text-saffron-gold">
                  Active
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 font-mono text-[10px]">
                <div className="rounded-lg bg-background/50 p-2">
                  <span className="text-muted-foreground">Retrieval Engine</span>
                  <p className="font-semibold text-foreground">{modelUsed}</p>
                </div>
                <div className="rounded-lg bg-background/50 p-2">
                  <span className="text-muted-foreground">Discourse Sources</span>
                  <p className="font-semibold text-foreground">{retrievedCount} Verified Chunks</p>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};
