import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Shield,
  Brain,
  Search,
  Lightbulb,
  PenTool,
  Sparkles,
  Check,
  BookOpen,
  Circle,
  Loader2,
  ChevronDown,
} from 'lucide-react';

export interface PipelineStep {
  id: string;
  label: string;
  status: 'pending' | 'active' | 'done';
}

interface ThinkingPillsProps {
  steps: PipelineStep[];
  visible: boolean;
  heartbeat?: boolean; // When true, pulse the active step to indicate "still processing"
}

interface StageConfig {
  icon: React.ReactNode;
  shortLabel: string;
  color: string;
}

const STAGE_CONFIG: Record<string, StageConfig> = {
  'Safety check': { icon: <Shield className="w-3 h-3" />, shortLabel: 'Safety', color: 'text-amber-400' },
  Understanding: { icon: <Brain className="w-3 h-3" />, shortLabel: 'Understanding', color: 'text-ojas' },
  'Searching wisdom': { icon: <Search className="w-3 h-3" />, shortLabel: 'Searching', color: 'text-prana' },
  Generating: { icon: <Lightbulb className="w-3 h-3" />, shortLabel: 'Analyzing', color: 'text-teal-400' },
  Composing: { icon: <PenTool className="w-3 h-3" />, shortLabel: 'Composing', color: 'text-indigo-400' },
  Verifying: { icon: <Sparkles className="w-3 h-3" />, shortLabel: 'Verifying', color: 'text-ojas' },
};

export const mapStatusToLabel = (raw: string): string => {
  const lower = raw.toLowerCase();
  if (lower.includes('still processing') || lower.includes('heartbeat')) return 'heartbeat'; // Special marker for heartbeat
  if (lower.includes('safety') || lower.includes('message safety')) return 'Safety check';
  if (lower.includes('understanding') || lower.includes('translating')) return 'Understanding';
  if (lower.includes('searching') || lower.includes('knowledge base') || lower.includes('retrieving')) return 'Searching wisdom';
  if (lower.includes('generat')) return 'Generating';
  if (lower.includes('composing') || lower.includes('analyz')) return 'Composing';
  if (lower.includes('verif')) return 'Verifying';
  if (lower.includes('query received') || lower.includes('starting pipeline')) return 'Safety check';
  if (lower.includes('translating') || lower.includes('language')) return 'Understanding';
  return 'Processing';
};

/**
 * Claude/ChatGPT/Gemini-style thinking indicator.
 * Compact, left-aligned, shares the same row geometry as guru ChatMessage
 * (avatar 28px + gap 10px). Click to expand and see the full pipeline.
 */
export const ThinkingPills = ({ steps, visible, heartbeat }: ThinkingPillsProps) => {
  const [expanded, setExpanded] = useState(false);

  if (!visible || steps.length === 0) return null;

  // Filter out 'heartbeat' steps — they're handled via the heartbeat prop
  const displaySteps = steps.filter((s) => s.label !== 'heartbeat');
  if (displaySteps.length === 0) return null;

  // Prefer the currently active step; fall back to last done; else last entry.
  const activeStep = [...displaySteps].reverse().find((s) => s.status === 'active');
  const lastDone = [...displaySteps].reverse().find((s) => s.status === 'done');
  const latestStep = activeStep ?? lastDone ?? displaySteps[displaySteps.length - 1];
  const doneCount = displaySteps.filter((s) => s.status === 'done').length;

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4, transition: { duration: 0.2 } }}
          className="group flex items-start gap-2.5 justify-start my-2"
          data-testid="thinking-pills"
        >
          {/* Avatar — identical to guru avatar in ChatMessage */}
          <div className="w-7 h-7 rounded-full bg-ojas/12 border border-ojas/20 flex items-center justify-center flex-shrink-0 mt-0.5">
            <BookOpen className="w-3 h-3 text-ojas" />
          </div>

          {/* Compact pill column — aligns flush with assistant bubbles */}
          <div className="flex flex-col items-start gap-1 max-w-[85%] sm:max-w-[75%] min-w-0">
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="inline-flex items-center gap-2 rounded-full border border-border/40 bg-muted/30 hover:bg-muted/50 transition-colors px-2.5 py-1 text-[12px] text-foreground/80"
              aria-expanded={expanded}
              aria-label="Toggle thinking details"
            >
              <Loader2 className="w-3 h-3 text-ojas animate-spin" />
              <span className="font-medium">Thinking</span>
              <span className="text-muted-foreground">·</span>
              <span className="text-muted-foreground truncate max-w-[140px] sm:max-w-[220px]">
                {latestStep.label}
              </span>
              <span className="text-muted-foreground/70 text-[10px] tabular-nums">
                {doneCount}/{Math.max(displaySteps.length, 6)}
              </span>
              <ChevronDown
                className={`w-3 h-3 text-muted-foreground transition-transform ${expanded ? 'rotate-180' : ''}`}
              />
            </button>

            <AnimatePresence initial={false}>
              {expanded && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.22, ease: 'easeOut' }}
                  className="overflow-hidden w-full"
                >
                  <ul className="mt-1 ml-1 border-l border-border/40 pl-3 py-1 space-y-1.5">
                    {displaySteps.map((step) => {
                      const isDone = step.status === 'done';
                      const isActive = step.status === 'active';
                      const config = STAGE_CONFIG[step.label] || {
                        icon: <Circle className="w-3 h-3" />,
                        shortLabel: step.label,
                        color: 'text-muted-foreground',
                      };
                      // Heartbeat pulse: when heartbeat prop is true and this is the active step,
                      // add a pulsing ring animation
                      const showHeartbeatPulse = heartbeat && isActive;
                      return (
                        <li key={step.id} className="flex items-center gap-2 text-[12px] relative">
                          {showHeartbeatPulse && (
                            <motion.div
                              className="absolute left-[-8px] top-1/2 -translate-y-1/2 w-5 h-5 rounded-full border-2 border-ojas/30"
                              animate={{ scale: [1, 1.8], opacity: [0.6, 0] }}
                              transition={{ duration: 1.5, repeat: Infinity, ease: 'easeOut' }}
                            />
                          )}
                          <span className="w-3.5 h-3.5 flex items-center justify-center flex-shrink-0">
                            {isDone ? (
                              <Check className="w-3 h-3 text-prana" />
                            ) : isActive ? (
                              <>
                                <Loader2 className="w-3 h-3 text-ojas animate-spin" />
                                {showHeartbeatPulse && (
                                  <motion.div
                                    className="absolute w-3 h-3 rounded-full bg-ojas/30"
                                    animate={{ scale: [1, 1.5], opacity: [0.5, 0] }}
                                    transition={{ duration: 1, repeat: Infinity, delay: 0.5 }}
                                  />
                                )}
                              </>
                            ) : (
                              <Circle className="w-2 h-2 text-muted-foreground/50" />
                            )}
                          </span>
                          <span className={config.color}>{config.icon}</span>
                          <span
                            className={
                              isActive
                                ? 'text-foreground/90 font-medium'
                                : isDone
                                ? 'text-foreground/70'
                                : 'text-muted-foreground'
                            }
                          >
                            {step.label}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default ThinkingPills;
