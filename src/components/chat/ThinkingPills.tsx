import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { BookOpen, Check, ChevronDown, Circle, Loader2 } from 'lucide-react';

import { useWisdomTips } from '@/hooks/useWisdomTips';

export interface PipelineStep {
  id: string;
  label: string;
  status: 'pending' | 'active' | 'done';
}

interface ThinkingPillsProps {
  steps?: PipelineStep[];
  visible: boolean;
  heartbeat?: boolean;
  /** Fallback label used before any pipeline event arrives (e.g. "Analyzing your question…"). */
  fallbackLabel?: string;
  /** E6.1: spiritual tradition being searched (e.g. "Ekam — Sri Preethaji & Sri Krishnaji"). */
  tradition?: string;
  /** E6.2: the user's query text, surfaced as an optimistic "searching on <topic>" hint. */
  searchContext?: string;
}

/**
 * Map a raw backend status string to a stable, short stage label.
 * Kept exported for tests + ChatInterface.
 */
export const mapStatusToLabel = (raw: string): string => {
  const lower = raw.toLowerCase();
  if (lower.includes('queued')) return 'Queued';
  if (lower.includes('still processing') || lower.includes('heartbeat')) return 'heartbeat';
  if (lower.includes('safety') || lower.includes('message safety')) return 'Safety check';
  if (lower.includes('understanding') || lower.includes('translating') || lower.includes('language'))
    return 'Understanding';
  if (lower.includes('searching') || lower.includes('knowledge base') || lower.includes('retrieving'))
    return 'Searching wisdom';
  if (lower.includes('generat')) return 'Generating';
  if (lower.includes('composing') || lower.includes('analyz')) return 'Composing';
  if (lower.includes('verif')) return 'Verifying';
  if (lower.includes('query received') || lower.includes('starting pipeline')) return 'Safety check';
  return 'Processing';
};

/**
 * Single, unified ChatGPT/Claude-style thinking indicator.
 *
 * Shows ONE row at a time:
 *   • guru avatar
 *   • shimmer "Thinking" + current sub-status (instant → pipeline → still working)
 *   • subtle chevron to expand the full pipeline checklist
 *
 * Replaces the previous stack of three overlapping indicators.
 */
export const ThinkingPills = ({
  steps = [],
  visible,
  heartbeat,
  fallbackLabel = 'Reflecting on the teachings…',
  tradition,
  searchContext,
}: ThinkingPillsProps) => {
  const [expanded, setExpanded] = useState(false);

  // Rotating wisdom tip — turns the wait into a moment of teaching.
  const wisdomTip = useWisdomTips(visible);

  // Elapsed seconds — gives a gentle "still working" reassurance after a while.
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!visible) {
      setElapsed(0);
      return;
    }
    const t = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [visible]);

  if (!visible) return null;

  const displaySteps = steps.filter((s) => s.label !== 'heartbeat');
  const activeStep = [...displaySteps].reverse().find((s) => s.status === 'active');
  const lastDone = [...displaySteps].reverse().find((s) => s.status === 'done');
  const latestStep = activeStep ?? lastDone ?? displaySteps[displaySteps.length - 1];

  // Choose the single line of sub-status, in priority order.
  let subLabel = latestStep?.label ?? fallbackLabel;
  if (heartbeat) subLabel = 'Still working on it…';
  else if (!latestStep && elapsed >= 10) subLabel = 'Drawing from the teachings…';

  // E6.1/E6.2: when no concrete pipeline step has landed yet, enrich the fallback
  // with the tradition + the user's query topic so the wait feels purposeful.
  if (!latestStep && !heartbeat) {
    const topic = searchContext?.trim();
    if (topic && tradition) {
      subLabel = `Searching ${tradition} on “${topic.slice(0, 60)}”…`;
    } else if (topic) {
      subLabel = `Searching the teachings on “${topic.slice(0, 60)}”…`;
    } else if (tradition) {
      subLabel = `Drawing from ${tradition}…`;
    }
  }

  const hasSteps = displaySteps.length > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4, transition: { duration: 0.2 } }}
      className="flex items-start gap-2.5 justify-start my-2"
      data-testid="thinking-pills"
    >
      {/* Guru avatar — matches ChatMessage */}
      <div className="w-7 h-7 rounded-full bg-ojas/12 border border-ojas/20 flex items-center justify-center flex-shrink-0 mt-0.5">
        <BookOpen className="w-3 h-3 text-ojas" />
      </div>

      <div className="flex flex-col items-start gap-1 min-w-0 max-w-[85%] sm:max-w-[75%]">
        <button
          type="button"
          onClick={() => hasSteps && setExpanded((v) => !v)}
          disabled={!hasSteps}
          className={`group inline-flex items-center gap-2 text-[13px] leading-none ${
            hasSteps ? 'cursor-pointer' : 'cursor-default'
          }`}
          aria-expanded={expanded}
          aria-label="Toggle thinking details"
        >
          {/* Shimmer "Thinking" — ChatGPT-style sweeping gradient */}
          <span className="thinking-shimmer font-serif italic text-foreground/80">Thinking</span>

          {/* Tiny pulsing dot — subtle activity cue */}
          <motion.span
            className="w-1.5 h-1.5 rounded-full bg-ojas/70"
            animate={{ opacity: [0.35, 1, 0.35], scale: [1, 1.25, 1] }}
            transition={{ duration: 1.4, repeat: Infinity, ease: 'easeInOut' }}
          />

          {/* Rotating sub-status */}
          <AnimatePresence mode="wait">
            <motion.span
              key={subLabel}
              initial={{ opacity: 0, y: 3 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -3 }}
              transition={{ duration: 0.25 }}
              className="font-serif italic text-muted-foreground truncate max-w-[180px] sm:max-w-[260px]"
            >
              · {subLabel}
            </motion.span>
          </AnimatePresence>

          {/* Elapsed counter — only after 5s, to avoid flicker */}
          {elapsed >= 5 && (
            <span className="text-[10px] tabular-nums font-sans text-muted-foreground/60">
              {elapsed}s
            </span>
          )}

          {hasSteps && (
            <ChevronDown
              className={`w-3 h-3 text-muted-foreground/60 transition-transform ${
                expanded ? 'rotate-180' : ''
              } group-hover:text-muted-foreground`}
            />
          )}
        </button>

        <AnimatePresence initial={false}>
          {expanded && hasSteps && (
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
                  return (
                    <li key={step.id} className="flex items-center gap-2 text-[12px]">
                      <span className="w-3.5 h-3.5 flex items-center justify-center flex-shrink-0">
                        {isDone ? (
                          <Check className="w-3 h-3 text-prana" />
                        ) : isActive ? (
                          <Loader2 className="w-3 h-3 text-ojas animate-spin" />
                        ) : (
                          <Circle className="w-2 h-2 text-muted-foreground/60" />
                        )}
                      </span>
                      <span
                        className={
                          isActive
                            ? 'text-foreground/90 font-medium'
                            : isDone
                            ? 'text-foreground/65'
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

        {/* Wisdom tip while waiting — appears after ~2s, rotates every 8s */}
        <AnimatePresence mode="wait">
          {wisdomTip && (
            <motion.blockquote
              key={wisdomTip.id}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.6, ease: 'easeOut' }}
              className="mt-2 max-w-[52ch] border-l-2 border-ojas/30 pl-3 py-0.5"
              data-testid="wisdom-tip"
            >
              <p className="font-serif italic text-[12.5px] leading-relaxed text-muted-foreground">
                “{wisdomTip.text}”
              </p>
              <footer className="mt-1 text-[10px] tracking-wide text-muted-foreground/60">
                🪷 {wisdomTip.teacher}
              </footer>
            </motion.blockquote>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
};

export default ThinkingPills;
