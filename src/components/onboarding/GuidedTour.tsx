import { useTranslation } from 'react-i18next';
import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface Step {
  target: string;
  titleKey: string;
  descriptionKey: string;
}

const STEPS: Step[] = [
  { target: 'chat-input', titleKey: 'onboarding.tour.step1.title', descriptionKey: 'onboarding.tour.step1.description' },
  { target: 'language-selector', titleKey: 'onboarding.tour.step2.title', descriptionKey: 'onboarding.tour.step2.description' },
  { target: 'meditation', titleKey: 'onboarding.tour.step3.title', descriptionKey: 'onboarding.tour.step3.description' },
  { target: 'notebook', titleKey: 'onboarding.tour.step4.title', descriptionKey: 'onboarding.tour.step4.description' },
  { target: 'knowledge-graph', titleKey: 'onboarding.tour.step5.title', descriptionKey: 'onboarding.tour.step5.description' },
  { target: 'profile', titleKey: 'onboarding.tour.step6.title', descriptionKey: 'onboarding.tour.step6.description' },
];

interface GuidedTourProps {
  isOpen: boolean;
  onComplete: () => void;
}

export const GuidedTour = ({ isOpen, onComplete }: GuidedTourProps) => {
  const { t } = useTranslation();
  const [stepIndex, setStepIndex] = useState(0);
  const [tooltipStyle, setTooltipStyle] = useState<React.CSSProperties>({});

  const currentStep = STEPS[stepIndex];

  const positionTooltip = useCallback(() => {
    const el = document.querySelector<HTMLElement>(`[data-tour="${currentStep.target}"]`);
    if (!el) return;

    const rect = el.getBoundingClientRect();
    const tooltipWidth = 320;
    const tooltipHeight = 160;
    const gap = 12;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    let top: number;
    let left: number;

    const spaceBelow = viewportHeight - rect.bottom;
    const spaceAbove = rect.top;

    if (spaceBelow >= tooltipHeight + gap) {
      top = rect.bottom + gap;
    } else if (spaceAbove >= tooltipHeight + gap) {
      top = rect.top - tooltipHeight - gap;
    } else {
      top = Math.max(gap, (viewportHeight - tooltipHeight) / 2);
    }

    left = rect.left + rect.width / 2 - tooltipWidth / 2;
    // Clamp to viewport with gutters
    left = Math.max(gap, Math.min(left, viewportWidth - tooltipWidth - gap));
    // Final safety: ensure tooltip stays fully on-screen
    const clampedWidth = Math.min(tooltipWidth, viewportWidth - gap * 2);

    setTooltipStyle({
      position: 'fixed',
      top,
      left,
      width: clampedWidth,
    });
  }, [currentStep.target]);

  useEffect(() => {
    if (!isOpen) return;
    positionTooltip();
    const onResize = () => positionTooltip();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [isOpen, positionTooltip, stepIndex]);

  useEffect(() => {
    if (!isOpen) return;

    document.querySelectorAll('[data-tour-highlighted]').forEach((el) => {
      el.removeAttribute('data-tour-highlighted');
    });

    const el = document.querySelector<HTMLElement>(`[data-tour="${currentStep.target}"]`);
    if (el) {
      el.setAttribute('data-tour-highlighted', 'true');
    }

    return () => {
      document.querySelectorAll('[data-tour-highlighted]').forEach((el) => {
        el.removeAttribute('data-tour-highlighted');
      });
    };
  }, [isOpen, currentStep.target, stepIndex]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onComplete();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isOpen, onComplete]);

  const handleNext = () => {
    if (stepIndex < STEPS.length - 1) {
      setStepIndex((i) => i + 1);
    }
  };

  const handleComplete = () => {
    onComplete();
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="fixed inset-0 z-50"
        >
          <div className="absolute inset-0 bg-black/50 pointer-events-none" />

          {tooltipStyle.left !== undefined && (
            <motion.div
              key={stepIndex}
              initial={{ opacity: 0, y: 8, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              style={tooltipStyle}
              className="bg-card/95 backdrop-blur-xl border border-border/60 rounded-2xl shadow-2xl p-5 pointer-events-auto"
            >
              <div className="flex items-center gap-2 mb-3">
                <span className="text-[11px] font-mono text-muted-foreground/70 font-medium tabular-nums">
                  {t('onboarding.tour.stepIndicator', { current: stepIndex + 1, total: STEPS.length })}
                </span>
                <div className="flex-1" />
                <button
                  onClick={onComplete}
                  className="text-[11px] text-muted-foreground/60 hover:text-muted-foreground transition-colors font-medium"
                >
                  {t('onboarding.tour.skip')}
                </button>
              </div>

              <h3 className="text-base font-semibold text-foreground mb-1.5">
                {t(currentStep.titleKey)}
              </h3>
              <p className="text-sm text-muted-foreground leading-relaxed mb-5">
                {t(currentStep.descriptionKey)}
              </p>

              <div className="flex items-center gap-2">
                <div className="flex gap-1">
                  {STEPS.map((_, i) => (
                    <div
                      key={i}
                      className={`w-1.5 h-1.5 rounded-full transition-colors ${
                        i === stepIndex ? 'bg-ojas' : 'bg-border'
                      }`}
                    />
                  ))}
                </div>
                <div className="flex-1" />
                {stepIndex < STEPS.length - 1 ? (
                  <button
                    onClick={handleNext}
                    className="px-4 py-2 rounded-xl bg-ojas text-primary-foreground text-sm font-medium hover:bg-ojas-light transition-colors shadow-sm"
                  >
                    {t('onboarding.tour.next')}
                  </button>
                ) : (
                  <button
                    onClick={handleComplete}
                    className="px-4 py-2 rounded-xl bg-ojas text-primary-foreground text-sm font-medium hover:bg-ojas-light transition-colors shadow-sm"
                  >
                    {t('onboarding.tour.gotIt')}
                  </button>
                )}
              </div>
            </motion.div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
};
