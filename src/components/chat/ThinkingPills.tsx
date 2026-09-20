import { useTranslation } from 'react-i18next';
import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { TeachingPreview } from '@/lib/chat/types';
import { Check, ChevronDown, Circle, Loader2 } from 'lucide-react';

export interface PipelineStep {
  id: string;
  label: string;
  status: 'pending' | 'active' | 'done';
  step?: number;
  totalSteps?: number;
  node?: string;
}

interface ThinkingPillsProps {
  steps?: PipelineStep[];
  visible: boolean;
  heartbeat?: boolean;
  fallbackLabel?: string;
  tradition?: string;
  searchContext?: string;
  currentStep?: number;
  totalSteps?: number;
  teachingPreview?: TeachingPreview[];
}

export const mapNodeToLabel = (node: string): string => {
  const lower = node.toLowerCase();
  if (lower.includes('distress') || lower.includes('guardrail') || lower.includes('safety')) return 'Safety check';
  if (lower.includes('intent') || lower.includes('followup')) return 'Understanding query';
  if (
    lower.includes('retriev') ||
    lower.includes('decompose') ||
    lower.includes('hyde') ||
    lower.includes('search') ||
    lower.includes('traversal')
  )
    return 'Searching sacred wisdom';
  if (lower.includes('rerank')) return 'Refining relevance';
  if (lower.includes('grade') || lower.includes('cross_teacher')) return 'Filtering relevance';
  if (lower.includes('enrich') || lower.includes('context')) return 'Synthesizing wisdom';
  if (lower.includes('generate') || lower.includes('reflect')) return 'Composing guidance';
  if (lower.includes('verify') || lower.includes('format') || lower.includes('citation'))
    return 'Verifying sacred teachings';
  if (lower.includes('casual')) return 'Saying hello';
  if (lower.includes('meditation')) return 'Guiding practice';
  return 'Contemplating';
};

export const mapStatusToLabel = (raw: string): string => {
  const lower = raw.toLowerCase();
  if (lower.includes('queued')) return 'Queued';
  if (lower.includes('still processing') || lower.includes('heartbeat')) return 'heartbeat';
  if (lower.includes('safety') || lower.includes('guardrail') || lower.includes('message safety')) return 'Safety check';
  if (lower.includes('understanding') || lower.includes('translating') || lower.includes('language') || lower.includes('resolve_followup'))
    return 'Understanding query';
  if (
    lower.includes('searching') ||
    lower.includes('knowledge base') ||
    lower.includes('retriev') ||
    lower.includes('neo4j') ||
    lower.includes('graph') ||
    lower.includes('breaking the question') ||
    lower.includes('imagining the shape') ||
    lower.includes('walking the teaching')
  )
    return 'Searching sacred wisdom';
  if (lower.includes('rerank') || lower.includes('ranking the most relevant')) return 'Refining relevance';
  if (lower.includes('filtering for relevance') || lower.includes('grade')) return 'Filtering relevance';
  if (lower.includes('gathering surrounding context') || lower.includes('enrich')) return 'Synthesizing wisdom';
  if (lower.includes('generat') || lower.includes('synthesiz')) return 'Synthesizing wisdom';
  if (lower.includes('composing') || lower.includes('analyz') || lower.includes('reviewing the response')) return 'Composing guidance';
  if (lower.includes('verif') || lower.includes('faithfulness') || lower.includes('grounding') || lower.includes('finalizing your response'))
    return 'Verifying sacred teachings';
  if (lower.includes('query received') || lower.includes('starting pipeline')) return 'Safety check';
  return 'Contemplating';
};

export const ThinkingPills = ({
  steps = [],
  visible,
  heartbeat,
  fallbackLabel,
  tradition,
  searchContext,
  currentStep,
  totalSteps,
  teachingPreview = [],
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

  let rawLabel = latestStep?.label ?? fallbackLabel ?? t('chat.reflecting');
  if (heartbeat) rawLabel = t('chat.stillWorking');
  else if (!latestStep && elapsed >= 10) rawLabel = t('chat.drawingFromTeachings');

  if (!latestStep && !heartbeat) {
    const topic = searchContext?.trim();
    if (topic && tradition) {
      rawLabel = t('chat.searchingTradition', { tradition, topic: topic.slice(0, 60) });
    } else if (topic) {
      rawLabel = t('chat.searchingTeachings', { topic: topic.slice(0, 60) });
    } else if (tradition) {
      rawLabel = t('chat.drawingFrom', { tradition });
    }
  }

  // Track step / total_steps for honest percentage/fraction progress
  const stepIndex = currentStep ?? latestStep?.step;
  const totalCount = totalSteps ?? latestStep?.totalSteps;

  const translatedLabel = (() => {
    const keyByLabel: Record<string, string> = {
      'Safety check': 'chat.thinking.safety',
      'Understanding query': 'chat.thinking.understanding',
      'Searching sacred wisdom': 'chat.thinking.searching',
      'Refining relevance': 'chat.thinking.reranking',
      'Filtering relevance': 'chat.thinking.filtering',
      'Synthesizing wisdom': 'chat.thinking.synthesizing',
      'Composing guidance': 'chat.thinking.composing',
      'Verifying sacred teachings': 'chat.thinking.verifying',
      'Saying hello': 'chat.thinking.hello',
      'Guiding practice': 'chat.thinking.practice',
      'Contemplating': 'chat.thinking.contemplating',
      'Queued': 'chat.thinking.queued',
    };
    const key = keyByLabel[rawLabel];
    return key ? t(key, { defaultValue: rawLabel }) : rawLabel;
  })();

  let subLabel = translatedLabel;
  if (stepIndex !== undefined && totalCount !== undefined && totalCount > 0) {
    const boundedStep = Math.max(1, Math.min(stepIndex, totalCount));
    const rawPercentage = Math.floor((boundedStep / totalCount) * 100);
    // Honest progress: prevent false 100% completion before tokens arrive by capping at 95%
    const percentage = Math.min(95, Math.max(1, rawPercentage));
    subLabel = t('chat.thinking.stepProgress', {
      step: boundedStep,
      total: totalCount,
      label: translatedLabel,
      percentage,
    });
  }

  const hasSteps = displaySteps.length > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4, transition: { duration: 0.2 } }}
      className="flex flex-col items-start gap-2 my-2 min-w-0"
      data-testid="thinking-pills"
    >
      <button
        type="button"
        onClick={() => hasSteps && setExpanded((v) => !v)}
        disabled={!hasSteps}
        className={`group inline-flex items-center gap-2 min-h-[32px] text-[15px] leading-5 font-sans font-normal text-muted-foreground ${
          hasSteps ? 'cursor-pointer' : 'cursor-default'
        }`}
        aria-expanded={expanded}
        aria-label={t('chat.toggleThinking', 'Toggle thinking details')}
      >
        <Loader2 className="w-3.5 h-3.5 text-ojas animate-spin flex-shrink-0" />

        <AnimatePresence mode="wait">
          <motion.span
            key={subLabel}
            initial={{ opacity: 0, y: 3 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -3 }}
            transition={{ duration: 0.25 }}
            className="truncate max-w-[240px] sm:max-w-[460px]"
          >
            {subLabel}
          </motion.span>
        </AnimatePresence>

        {elapsed >= 5 && (
          <span className="text-[15px] leading-5 tabular-nums text-muted-foreground/60">{elapsed}s</span>
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
            <ul className="ml-1.5 border-l border-border/40 pl-3 py-1 space-y-2.5">
              {displaySteps.map((step, idx) => {
                const isDone = step.status === 'done';
                const isActive = step.status === 'active';
                const translatedStepLabel = (() => {
                  const keyByLabel: Record<string, string> = {
                    'Safety check': 'chat.thinking.safety',
                    'Understanding query': 'chat.thinking.understanding',
                    'Searching sacred wisdom': 'chat.thinking.searching',
                    'Refining relevance': 'chat.thinking.reranking',
                    'Filtering relevance': 'chat.thinking.filtering',
                    'Synthesizing wisdom': 'chat.thinking.synthesizing',
                    'Composing guidance': 'chat.thinking.composing',
                    'Verifying sacred teachings': 'chat.thinking.verifying',
                    'Saying hello': 'chat.thinking.hello',
                    'Guiding practice': 'chat.thinking.practice',
                    'Contemplating': 'chat.thinking.contemplating',
                    'Queued': 'chat.thinking.queued',
                  };
                  const key = keyByLabel[step.label];
                  return key ? t(key, { defaultValue: step.label }) : step.label;
                })();
                const stepLabel = step.step && step.totalSteps
                  ? t('chat.thinking.stepLabel', { step: step.step, total: step.totalSteps, label: translatedStepLabel })
                  : translatedStepLabel;
                return (
                  <li key={step.id || `step-${idx}`} className="flex items-center gap-2 text-[15px] leading-5 font-sans">
                    <span className="w-3.5 h-3.5 flex items-center justify-center flex-shrink-0">
                      {isDone ? (
                        <Check className="w-3 h-3 text-prana" />
                      ) : isActive ? (
                        <Loader2 className="w-3 h-3 text-ojas animate-spin" />
                      ) : (
                        <Circle className="w-2 h-2 text-muted-foreground/60" />
                      )}
                    </span>
                    <span className={isActive ? 'text-foreground font-medium' : isDone ? 'text-foreground/60' : 'text-muted-foreground'}>
                      {stepLabel}
                    </span>
                  </li>
                );
              })}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>

      {teachingPreview.length > 0 && (
        <div className="w-full max-w-xl rounded-xl border border-ojas/15 bg-ojas/[0.035] px-3 py-2.5">
          <div className="flex items-center gap-2 text-[15px] leading-5 font-medium text-foreground">
            <span className="inline-flex h-5 w-5 items-center justify-center rounded-md bg-ojas/10 text-ojas">◈</span>
            <span>{t('chat.teachingContext.title')}</span>
            <span className="text-[15px] leading-5 font-normal text-muted-foreground/70">
              {t('chat.teachingContext.sourceCount', { count: teachingPreview.length })}
            </span>
          </div>
          <div className="mt-2 space-y-1.5">
            {teachingPreview.slice(0, 3).map((item) => (
              <div key={item.url ?? item.title} className="min-w-0">
                <div className="truncate text-[15px] leading-5 font-medium text-foreground">
                  {item.url ? (
                    <a href={item.url} target="_blank" rel="noopener noreferrer" className="hover:text-ojas hover:underline underline-offset-2">
                      {item.title}
                    </a>
                  ) : item.title}
                  {item.teacher ? <span className="font-normal text-muted-foreground"> · {item.teacher}</span> : null}
                </div>
                {item.excerpt && (
                  <div className="line-clamp-2 text-[15px] leading-6 text-muted-foreground">
                    “{item.excerpt}”
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
};

export default ThinkingPills;
