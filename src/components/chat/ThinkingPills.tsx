import { useTranslation } from 'react-i18next';
import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, ChevronDown, Circle, Loader2 } from 'lucide-react';

export interface PipelineStep {
  id: string;
  label: string;
  status: 'pending' | 'active' | 'done';
}

interface ThinkingPillsProps {
  steps?: PipelineStep[];
  visible: boolean;
  heartbeat?: boolean;
  fallbackLabel?: string;
  tradition?: string;
  searchContext?: string;
}

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

export const ThinkingPills = ({
  steps = [],
  visible,
  heartbeat,
  fallbackLabel,
  tradition,
  searchContext,
}: ThinkingPillsProps) => {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!visible) {
      setElapsed(0);
      return;
    }
    const interval = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(interval);
  }, [visible]);

  if (!visible) return null;

  const displaySteps = steps.filter((s) => s.label !== 'heartbeat');
  const activeStep = [...displaySteps].reverse().find((s) => s.status === 'active');
  const lastDone = [...displaySteps].reverse().find((s) => s.status === 'done');
  const latestStep = activeStep ?? lastDone ?? displaySteps[displaySteps.length - 1];

  let subLabel = latestStep?.label ?? fallbackLabel ?? t('chat.reflecting');
  if (heartbeat) subLabel = t('chat.stillWorking');
  else if (!latestStep && elapsed >= 10) subLabel = t('chat.drawingFromTeachings');

  if (!latestStep && !heartbeat) {
    const topic = searchContext?.trim();
    if (topic && tradition) {
      subLabel = t('chat.searchingTradition', { tradition, topic: topic.slice(0, 60) });
    } else if (topic) {
      subLabel = t('chat.searchingTeachings', { topic: topic.slice(0, 60) });
    } else if (tradition) {
      subLabel = t('chat.drawingFrom', { tradition });
    }
  }

  const hasSteps = displaySteps.length > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4, transition: { duration: 0.2 } }}
      className="flex flex-col items-start gap-1 my-2 min-w-0"
      data-testid="thinking-pills"
    >
      <button
        type="button"
        onClick={() => hasSteps && setExpanded((v) => !v)}
        disabled={!hasSteps}
        className={`group inline-flex items-center gap-2 min-h-[32px] text-sm font-sans text-muted-foreground ${
          hasSteps ? 'cursor-pointer' : 'cursor-default'
        }`}
        aria-expanded={expanded}
        aria-label={t('chat.toggleThinking') === 'chat.toggleThinking' ? 'Toggle thinking details' : t('chat.toggleThinking')}
      >
        <Loader2 className="w-3.5 h-3.5 text-ojas animate-spin flex-shrink-0" />

        <AnimatePresence mode="wait">
          <motion.span
            key={subLabel}
            initial={{ opacity: 0, y: 3 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -3 }}
            transition={{ duration: 0.25 }}
            className="truncate max-w-[220px] sm:max-w-[420px]"
          >
            {subLabel}
          </motion.span>
        </AnimatePresence>

        {elapsed >= 5 && (
          <span className="text-xs tabular-nums text-muted-foreground/50">{elapsed}s</span>
        )}

        {hasSteps && (
          <ChevronDown
            className={`w-3.5 h-3.5 text-muted-foreground/50 transition-transform ${
              expanded ? 'rotate-180' : ''
            }`}
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
            <ul className="ml-1.5 border-l border-border/40 pl-3 py-1 space-y-1.5">
              {displaySteps.map((step) => {
                const isDone = step.status === 'done';
                const isActive = step.status === 'active';
                return (
                  <li key={step.id} className="flex items-center gap-2 text-xs font-sans">
                    <span className="w-3.5 h-3.5 flex items-center justify-center flex-shrink-0">
                      {isDone ? (
                        <Check className="w-3 h-3 text-prana" />
                      ) : isActive ? (
                        <Loader2 className="w-3 h-3 text-ojas animate-spin" />
                      ) : (
                        <Circle className="w-2 h-2 text-muted-foreground/60" />
                      )}
                    </span>
                    <span className={isActive ? 'text-foreground' : isDone ? 'text-foreground/60' : 'text-muted-foreground'}>
                      {step.label}
                    </span>
                  </li>
                );
              })}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default ThinkingPills;
