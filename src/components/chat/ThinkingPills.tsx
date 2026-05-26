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
} from 'lucide-react';

export interface PipelineStep {
  id: string;
  label: string;
  status: 'pending' | 'active' | 'done';
}

interface ThinkingPillsProps {
  steps: PipelineStep[];
  visible: boolean;
}

// ── Pipeline stage definitions ────────────────────────────────────────────────
interface StageConfig {
  icon: React.ReactNode;
  shortLabel: string;
  description: string;
  color: string;
}

const STAGE_CONFIG: Record<string, StageConfig> = {
  'Safety check': {
    icon: <Shield className="w-3.5 h-3.5" />,
    shortLabel: 'Safety',
    description: 'Verifying message content',
    color: 'text-amber-400',
  },
  Understanding: {
    icon: <Brain className="w-3.5 h-3.5" />,
    shortLabel: 'Intent',
    description: 'Understanding your intent',
    color: 'text-ojas',
  },
  'Searching wisdom': {
    icon: <Search className="w-3.5 h-3.5" />,
    shortLabel: 'Retrieving',
    description: 'Searching sacred teachings',
    color: 'text-prana',
  },
  Generating: {
    icon: <Lightbulb className="w-3.5 h-3.5" />,
    shortLabel: 'Analyzing',
    description: 'Analyzing retrieved wisdom',
    color: 'text-teal-400',
  },
  Composing: {
    icon: <PenTool className="w-3.5 h-3.5" />,
    shortLabel: 'Composing',
    description: 'Composing the response',
    color: 'text-indigo-400',
  },
  Verifying: {
    icon: <Sparkles className="w-3.5 h-3.5" />,
    shortLabel: 'Verifying',
    description: 'Verifying faithfulness',
    color: 'text-ojas',
  },
};

export const mapStatusToLabel = (raw: string): string => {
  const lower = raw.toLowerCase();
  if (lower.includes('safety') || lower.includes('message safety')) return 'Safety check';
  if (lower.includes('understanding') || lower.includes('translating')) return 'Understanding';
  if (lower.includes('searching') || lower.includes('knowledge base') || lower.includes('retrieving')) return 'Searching wisdom';
  if (lower.includes('generat')) return 'Generating';
  if (lower.includes('composing') || lower.includes('analyz')) return 'Composing';
  if (lower.includes('verif')) return 'Verifying';
  return 'Processing';
};

export const ThinkingPills = ({ steps, visible }: ThinkingPillsProps) => {
  if (!visible || steps.length === 0) return null;

  const latestStep = steps[steps.length - 1];
  const progress = steps.length > 0 ? ((steps.filter(s => s.status === 'done').length + (latestStep.status === 'active' ? 0.5 : 0)) / 6) * 100 : 0;

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: 16, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -12, scale: 0.95, transition: { duration: 0.35 } }}
          className="w-full flex justify-start my-3 pl-0 sm:pl-12"
        >
          <div className="relative w-full max-w-md rounded-2xl border border-ojas/15 bg-gradient-to-br from-card/90 to-card/70 backdrop-blur-xl shadow-xl shadow-ojas/5 p-5">
            {/* Glowing accent ring */}
            <div className="absolute -inset-px rounded-2xl bg-gradient-to-br from-ojas/10 via-transparent to-ojas/5 pointer-events-none" />

            {/* Header */}
            <div className="relative flex items-center gap-3 mb-4">
              <div className="relative">
                <motion.div
                  className="w-10 h-10 rounded-xl bg-gradient-to-br from-ojas/20 to-ojas/5 border border-ojas/20 flex items-center justify-center"
                  animate={{
                    boxShadow: [
                      '0 0 0 0 rgba(218, 165, 32, 0)',
                      '0 0 0 8px rgba(218, 165, 32, 0.15)',
                      '0 0 0 0 rgba(218, 165, 32, 0)',
                    ],
                  }}
                  transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
                >
                  <BookOpen className="w-5 h-5 text-ojas" />
                </motion.div>
                <div className="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-ojas animate-pulse" />
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground/90">
                  Guru is contemplating
                  <motion.span
                    animate={{ opacity: [1, 0.3, 1] }}
                    transition={{ duration: 1.5, repeat: Infinity }}
                    className="ml-1"
                  >
                    …
                  </motion.span>
                </p>
                <p className="text-[11px] text-muted-foreground">
                  {latestStep.label}
                </p>
              </div>
            </div>

            {/* Vertical Stepper */}
            <div className="relative space-y-0">
              {steps.map((step, idx, arr) => {
                const isDone = step.status === 'done';
                const isActive = step.status === 'active';
                const isLast = idx === arr.length - 1;
                const config = STAGE_CONFIG[step.label] || {
                  icon: <Circle className="w-3.5 h-3.5" />,
                  shortLabel: step.label,
                  description: 'Processing',
                  color: 'text-muted-foreground',
                };

                return (
                  <motion.div
                    key={step.id}
                    initial={{ opacity: 0, x: -16 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: idx * 0.05, duration: 0.3 }}
                    className="relative flex items-start gap-3"
                  >
                    {/* Connector line */}
                    {idx < arr.length - 1 && (
                      <div className="absolute left-[19px] top-7 w-px h-6 bg-border/30" />
                    )}

                    {/* Status icon */}
                    <div className="relative flex-shrink-0 mt-0.5">
                      <div
                        className={`w-8 h-8 rounded-full flex items-center justify-center border ${
                          isDone
                            ? 'bg-prana/15 border-prana/30 text-prana'
                            : isActive
                            ? 'bg-ojas/20 border-ojas/40 text-ojas'
                            : 'bg-muted/40 border-border/30 text-muted-foreground'
                        }`}
                      >
                        {isDone ? (
                          <Check className="w-3.5 h-3.5" />
                        ) : isActive ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <span className="text-[10px] font-medium">{idx + 1}</span>
                        )}
                      </div>
                      {isActive && (
                        <motion.div
                          className="absolute inset-0 rounded-full border-2 border-ojas/40"
                          animate={{ scale: [1, 1.3, 1], opacity: [0.8, 0, 0.8] }}
                          transition={{ duration: 1.5, repeat: Infinity }}
                        />
                      )}
                    </div>

                    {/* Step content */}
                    <div className="flex-1 min-w-0 pb-1 pt-0.5">
                      <div className="flex items-center gap-2">
                        <span className={`flex items-center gap-1.5 ${config.color}`}>
                          {config.icon}
                          <span className={`text-[13px] font-medium ${
                            isActive ? 'text-ojas' : isDone ? 'text-foreground/80' : 'text-muted-foreground'
                          }`}>
                            {step.label}
                          </span>
                        </span>
                      </div>
                      {isActive && (
                        <motion.p
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          className="text-[11px] text-muted-foreground mt-0.5"
                        >
                          {config.description}
                        </motion.p>
                      )}
                    </div>
                  </motion.div>
                );
              })}
            </div>

            {/* Bottom progress bar */}
            <div className="mt-4 pt-3 border-t border-border/20">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60">
                  Pipeline Progress
                </span>
                <span className="text-[10px] font-medium text-ojas">
                  {Math.min(Math.round(progress), 100)}%
                </span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-muted/50 overflow-hidden">
                <motion.div
                  className="h-full rounded-full bg-gradient-to-r from-ojas/60 to-ojas"
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.min(progress, 100)}%` }}
                  transition={{ duration: 0.5, ease: 'easeOut' }}
                />
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default ThinkingPills;
