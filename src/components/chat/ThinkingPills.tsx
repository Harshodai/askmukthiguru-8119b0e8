import { motion, AnimatePresence } from 'framer-motion';
import { Check, Loader2, Sparkles } from 'lucide-react';

export interface PipelineStep {
  id: string;
  label: string;
  status: 'pending' | 'active' | 'done';
}

interface ThinkingPillsProps {
  steps: PipelineStep[];
  visible: boolean;
}

const statusLabelMap: Record<string, string> = {
  'Checking message safety...': 'Safety check',
  'Understanding your question...': 'Understanding',
  'Searching knowledge base...': 'Searching wisdom',
  'Composing response...': 'Composing',
  'Generating answer...': 'Generating',
  'Verifying answer...': 'Verifying',
};

export const mapStatusToLabel = (raw: string): string =>
  statusLabelMap[raw] ?? raw.replace(/\.\.\.$/, '');

export const ThinkingPills = ({ steps, visible }: ThinkingPillsProps) => {
  if (!visible || steps.length === 0) return null;

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8, transition: { duration: 0.3 } }}
          className="pointer-events-none select-none rounded-xl border border-ojas/15 bg-card/60 backdrop-blur-sm p-3 space-y-2"
        >
          {/* Header */}
          <div className="flex items-center gap-2">
            <motion.div
              animate={{ rotate: [0, 15, -15, 0] }}
              transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
            >
              <Sparkles className="w-3.5 h-3.5 text-ojas" />
            </motion.div>
            <span className="text-[11px] font-medium text-ojas/80">
              Guru is contemplating
              <motion.span
                animate={{ opacity: [1, 0.3, 1] }}
                transition={{ duration: 1.2, repeat: Infinity }}
              >
                …
              </motion.span>
            </span>
          </div>

          {/* Pills */}
          <div className="flex flex-wrap items-center gap-1.5">
            {steps.map((step) => (
              <motion.span
                key={step.id}
                initial={{ opacity: 0, scale: 0.85 }}
                animate={{ opacity: 1, scale: 1 }}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium transition-colors duration-300 ${
                  step.status === 'done'
                    ? 'bg-prana/10 text-prana border border-prana/20'
                    : step.status === 'active'
                    ? 'bg-ojas/10 text-ojas border border-ojas/25'
                    : 'bg-muted/30 text-muted-foreground border border-border/30'
                }`}
              >
                {step.status === 'done' ? (
                  <Check className="w-3 h-3" />
                ) : step.status === 'active' ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : null}
                {step.label}
              </motion.span>
            ))}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
