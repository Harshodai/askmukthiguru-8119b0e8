import { useTranslation } from 'react-i18next';
import { useState, useEffect, useLayoutEffect, useCallback, useRef } from 'react';
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
  /** Fired only when the user finishes the tour ("Got it") — marks it confirmed. */
  onComplete: () => void;
  /** Fired when the user dismisses without finishing (skip / Escape). Must NOT mark
   *  the tour confirmed, so it can re-show on later visits. Falls back to onComplete. */
  onDismiss?: () => void;
}

const SPOTLIGHT_PAD = 8;

export const GuidedTour = ({ isOpen, onComplete, onDismiss }: GuidedTourProps) => {
  const dismiss = onDismiss ?? onComplete;
  const { t } = useTranslation();
  const [stepIndex, setStepIndex] = useState(0);
  const [tooltipStyle, setTooltipStyle] = useState<React.CSSProperties>({});
  const [spotlight, setSpotlight] = useState<React.CSSProperties | null>(null);
  const [arrow, setArrow] = useState<{ side: 'top' | 'bottom'; left: number } | null>(null);
  const [ready, setReady] = useState(false);
  const tooltipRef = useRef<HTMLDivElement>(null);

  const currentStep = STEPS[stepIndex];

  // Re-reads the target's *current* rect every call — safe to call from a resize
  // handler, a ResizeObserver (content length changed), or after a step change.
  const positionTooltip = useCallback(() => {
    const el = document.querySelector<HTMLElement>(`[data-tour="${currentStep.target}"]`);
    if (!el) return;

    const rect = el.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const gap = 12;
    const tooltipWidth = Math.min(320, viewportWidth - gap * 2);
    const tooltipHeight = tooltipRef.current?.offsetHeight || 160;

    let top: number;
    let side: 'top' | 'bottom';

    const spaceBelow = viewportHeight - rect.bottom;
    const spaceAbove = rect.top;

    if (spaceBelow >= tooltipHeight + gap) {
      top = rect.bottom + gap;
      side = 'bottom';
    } else if (spaceAbove >= tooltipHeight + gap) {
      top = rect.top - tooltipHeight - gap;
      side = 'top';
    } else {
      top = Math.max(gap, (viewportHeight - tooltipHeight) / 2);
      side = 'bottom';
    }

    let left = rect.left + rect.width / 2 - tooltipWidth / 2;
    left = Math.max(gap, Math.min(left, viewportWidth - tooltipWidth - gap));

    setTooltipStyle({ position: 'fixed', top, left, width: tooltipWidth });
    setArrow({
      side,
      left: Math.max(20, Math.min(rect.left + rect.width / 2 - left, tooltipWidth - 20)),
    });
    setSpotlight({
      position: 'fixed',
      top: rect.top - SPOTLIGHT_PAD,
      left: rect.left - SPOTLIGHT_PAD,
      width: rect.width + SPOTLIGHT_PAD * 2,
      height: rect.height + SPOTLIGHT_PAD * 2,
    });
  }, [currentStep.target]);

  // Target changed (step advanced, or tour just opened): bring it on-screen and
  // position synchronously before paint — no flash of the wrong position.
  useLayoutEffect(() => {
    if (!isOpen) return;
    const el = document.querySelector<HTMLElement>(`[data-tour="${currentStep.target}"]`);
    el?.scrollIntoView({ block: 'center', behavior: 'auto' });
    positionTooltip();
    setReady(true);
  }, [isOpen, positionTooltip, stepIndex]);

  // Track the target continuously while the tour is open, instead of trying to
  // enumerate every event that can move it — a modal's entrance animation, the
  // sidebar's own width transition, a late-loading card shifting page height,
  // scroll. A one-shot calculation went stale the moment any of those fired
  // after it ran; a resize/mutation listener still has to guess which events
  // matter. rAF polling is what Shepherd/driver.js do for exactly this reason:
  // it can't miss a layout shift because it never assumes one won't happen.
  useEffect(() => {
    if (!isOpen) return;
    let raf: number;
    const tick = () => {
      positionTooltip();
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [isOpen, positionTooltip]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        dismiss();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isOpen, dismiss]);

  useEffect(() => {
    if (!isOpen) {
      setReady(false);
      setStepIndex(0);
    }
  }, [isOpen]);

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
          className="fixed inset-0 z-50 pointer-events-none"
        >
          {/* Spotlight: a single box-shadow "cutout" over the target, not a
              separate dark overlay + per-element z-index hack — the latter only
              wins visually if every ancestor between the target and <body>
              happens not to create its own stacking context, which broke
              silently for sidebar/nav targets. */}
          {spotlight && (
            <motion.div
              layout
              transition={{ type: 'tween', duration: 0.25, ease: 'easeOut' }}
              className="absolute"
              style={{
                ...spotlight,
                boxShadow: '0 0 0 9999px rgba(0,0,0,0.55)',
                borderRadius: 12,
                border: '2px solid hsl(var(--ojas))',
              }}
            />
          )}

          {ready && tooltipStyle.left !== undefined && (
            <motion.div
              ref={tooltipRef}
              layout
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ layout: { type: 'tween', duration: 0.25, ease: 'easeOut' }, opacity: { duration: 0.2 }, scale: { duration: 0.2 } }}
              style={tooltipStyle}
              className="bg-card/95 backdrop-blur-xl border border-border/60 rounded-2xl shadow-2xl p-5 pointer-events-auto"
            >
              {arrow && (
                <div
                  className={`absolute w-3 h-3 bg-card/95 backdrop-blur-xl rotate-45 ${
                    arrow.side === 'bottom'
                      ? 'border-t border-l border-border/60'
                      : 'border-b border-r border-border/60'
                  }`}
                  style={{ left: arrow.left - 6, [arrow.side === 'bottom' ? 'top' : 'bottom']: -6 }}
                />
              )}
              <div className="flex items-center gap-2 mb-3">
                <span className="text-[11px] font-mono text-muted-foreground/70 font-medium tabular-nums">
                  {t('onboarding.tour.stepIndicator', { current: stepIndex + 1, total: STEPS.length })}
                </span>
                <div className="flex-1" />
                <button
                  onClick={dismiss}
                  className="text-[11px] text-muted-foreground/60 hover:text-muted-foreground transition-colors font-medium"
                >
                  {t('onboarding.tour.skip')}
                </button>
              </div>

              <AnimatePresence mode="wait">
                <motion.div
                  key={stepIndex}
                  initial={{ opacity: 0, x: 8 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -8 }}
                  transition={{ duration: 0.15 }}
                >
                  <h3 className="text-base font-semibold text-foreground mb-1.5">
                    {t(currentStep.titleKey)}
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed mb-5">
                    {t(currentStep.descriptionKey)}
                  </p>
                </motion.div>
              </AnimatePresence>

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
