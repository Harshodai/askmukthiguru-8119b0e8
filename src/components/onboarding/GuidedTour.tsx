import { useTranslation } from 'react-i18next';
import { useState, useEffect, useLayoutEffect, useCallback, useRef, useMemo } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { X, ChevronRight, ChevronLeft, Sparkles, MapPin } from 'lucide-react';

interface Step {
  target: string;
  /** Mobile fallback target — used when `target` anchor is not visible (e.g. desktop sidebar is hidden on mobile). */
  mobileFallback?: string;
  titleKey: string;
  descriptionKey: string;
  emoji?: string;
}

// Desktop anchors that only exist inside `hidden sm:flex` sidebar map to
// mobile-visible alternatives that live in the MobileConversationSheet's
// Explore tab (data-tour on each card there).
const STEPS: Step[] = [
  {
    target: 'chat-input',
    titleKey: 'onboarding.tour.step1.title',
    descriptionKey: 'onboarding.tour.step1.description',
    emoji: '✨',
  },
  {
    target: 'language-selector',
    titleKey: 'onboarding.tour.step2.title',
    descriptionKey: 'onboarding.tour.step2.description',
    emoji: '🌐',
  },
  {
    target: 'meditation',
    mobileFallback: 'mobile-menu',
    titleKey: 'onboarding.tour.step3.title',
    descriptionKey: 'onboarding.tour.step3.description',
    emoji: '🧘',
  },
  {
    target: 'notebook',
    mobileFallback: 'mobile-menu',
    titleKey: 'onboarding.tour.step4.title',
    descriptionKey: 'onboarding.tour.step4.description',
    emoji: '📖',
  },
  {
    target: 'knowledge-graph',
    mobileFallback: 'mobile-menu',
    titleKey: 'onboarding.tour.step5.title',
    descriptionKey: 'onboarding.tour.step5.description',
    emoji: '🧠',
  },
  {
    target: 'profile',
    titleKey: 'onboarding.tour.step6.title',
    descriptionKey: 'onboarding.tour.step6.description',
    emoji: '🙏',
  },
];

interface GuidedTourProps {
  isOpen: boolean;
  /** Fired only when the user finishes the tour ("Got it") — marks it confirmed. */
  onComplete: () => void;
  /** Fired when the user dismisses without finishing (skip / Escape). Must NOT mark
   *  the tour confirmed, so it can re-show on later visits. Falls back to onComplete. */
  onDismiss?: () => void;
}

const SPOTLIGHT_PAD = 10;

/** Clamp a number between min and max */
const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v));

/** A target only counts as visible if it's mounted, laid out, AND not
 *  aria-hidden (prevents matching sidebar elements hidden via ARIA). */
const isAnchorVisible = (target: string) => {
  const el = document.querySelector<HTMLElement>(`[data-tour="${target}"]`);
  if (!el) return false;
  // Skip elements inside an aria-hidden ancestor
  if (el.closest('[aria-hidden="true"]')) return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};

/** Resolve a step's effective target — prefer primary, fall back to mobile alias. */
const resolveTarget = (step: Step): string | null => {
  if (isAnchorVisible(step.target)) return step.target;
  if (step.mobileFallback && isAnchorVisible(step.mobileFallback)) return step.mobileFallback;
  return null;
};

export const GuidedTour = ({ isOpen, onComplete, onDismiss }: GuidedTourProps) => {
  const dismiss = onDismiss ?? onComplete;
  const { t } = useTranslation();
  const reduceMotion = useReducedMotion();
  const [steps, setSteps] = useState<(Step & { resolvedTarget: string })[]>([]);
  const [stepIndex, setStepIndex] = useState(0);
  const [tooltipStyle, setTooltipStyle] = useState<React.CSSProperties>({});
  const [spotlight, setSpotlight] = useState<{
    top: number;
    left: number;
    width: number;
    height: number;
    radius: number;
  } | null>(null);
  const [arrow, setArrow] = useState<{ side: 'top' | 'bottom'; left: number } | null>(null);
  const [ready, setReady] = useState(false);
  const [showConfetti, setShowConfetti] = useState(false);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const lastSignature = useRef('');
  /** Real measured card height — the flip decision used to run off a hardcoded
   *  200px guess, which mis-flipped tall cards in long translations. */
  const cardHeight = useRef(200);
  const restoreFocus = useRef<HTMLElement | null>(null);
  // Stable ref for stepIndex to avoid stale closures in keyboard handler
  const stepIndexRef = useRef(stepIndex);
  stepIndexRef.current = stepIndex;

  /** Resolve walkable steps against the DOM we actually have. Steps whose
   *  primary AND mobile-fallback anchors are both invisible are skipped, so a
   *  phone (no desktop sidebar) never walks into a dead spotlight. */
  const resolveSteps = useCallback((preserveIndex = false) => {
    const resolved = STEPS.reduce<(Step & { resolvedTarget: string })[]>((acc, s) => {
      const target = resolveTarget(s);
      if (target) acc.push({ ...s, resolvedTarget: target });
      return acc;
    }, []);
    const next = resolved.length
      ? resolved
      : STEPS.slice(0, 1).map((s) => ({ ...s, resolvedTarget: s.target }));
    setSteps(next);
    setStepIndex((i) => (preserveIndex ? clamp(i, 0, next.length - 1) : 0));
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    const id = setTimeout(() => resolveSteps(false), 80);
    return () => clearTimeout(id);
  }, [isOpen, resolveSteps]);

  // Rotating a phone or resizing a window changes which anchors exist — re-resolve
  // instead of leaving the tour pointing at an element that just disappeared.
  useEffect(() => {
    if (!isOpen) return;
    let id: number | undefined;
    const onViewportChange = () => {
      window.clearTimeout(id);
      id = window.setTimeout(() => resolveSteps(true), 150);
    };
    window.addEventListener('resize', onViewportChange);
    window.addEventListener('orientationchange', onViewportChange);
    return () => {
      window.clearTimeout(id);
      window.removeEventListener('resize', onViewportChange);
      window.removeEventListener('orientationchange', onViewportChange);
    };
  }, [isOpen, resolveSteps]);

  const currentStep = steps[Math.min(stepIndex, steps.length - 1)];
  const isLastStep = stepIndex >= steps.length - 1;
  const progress = steps.length > 0 ? (stepIndex + 1) / steps.length : 0;

  const positionTooltip = useCallback(() => {
    if (!currentStep) return;
    const el = document.querySelector<HTMLElement>(`[data-tour="${currentStep.resolvedTarget}"]`);
    if (!el) return;

    const rect = el.getBoundingClientRect();
    // Anchor got unmounted or collapsed mid-tour (sheet closed, sidebar toggled) —
    // recompute the walk rather than freezing on a stale spotlight.
    if (rect.width === 0 && rect.height === 0) {
      resolveSteps(true);
      return;
    }
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const gap = 14;
    const tooltipWidth = clamp(vw - gap * 2, 280, 340);
    const measured = tooltipRef.current?.offsetHeight;
    if (measured && measured > 40) cardHeight.current = measured;
    const tooltipHeight = cardHeight.current;

    // Determine border radius from computed style
    let radius = 12;
    try {
      const cs = window.getComputedStyle(el);
      const r = parseInt(cs.borderRadius) || 12;
      radius = r;
    } catch {/* ignore */}

    // Decide tooltip side
    let top: number;
    let side: 'top' | 'bottom';
    const spaceBelow = vh - rect.bottom;
    const spaceAbove = rect.top;

    if (spaceBelow >= tooltipHeight + gap) {
      top = rect.bottom + gap;
      side = 'bottom';
    } else if (spaceAbove >= tooltipHeight + gap) {
      top = rect.top - tooltipHeight - gap;
      side = 'top';
    } else {
      top = clamp(gap, gap, Math.max(gap, vh - tooltipHeight - gap));
      side = 'bottom';
    }

    let left = rect.left + rect.width / 2 - tooltipWidth / 2;
    left = clamp(left, gap, Math.max(gap, vw - tooltipWidth - gap));

    const signature = [top, left, tooltipWidth, side, rect.top, rect.left, rect.width, rect.height]
      .map((n) => (typeof n === 'number' ? Math.round(n) : n))
      .join('|');
    if (lastSignature.current === signature) return;
    lastSignature.current = signature;

    setTooltipStyle({ position: 'fixed', top, left, width: tooltipWidth });

    // Arrow points FROM the tooltip TOWARD the target.
    // side='bottom' → tooltip is below target → arrow on top of tooltip points UP at target.
    // side='top'    → tooltip is above target → arrow on bottom of tooltip points DOWN at target.
    const arrowLeft = clamp(rect.left + rect.width / 2 - left, 20, tooltipWidth - 20);
    setArrow({ side, left: arrowLeft });

    setSpotlight({
      top: rect.top - SPOTLIGHT_PAD,
      left: rect.left - SPOTLIGHT_PAD,
      width: rect.width + SPOTLIGHT_PAD * 2,
      height: rect.height + SPOTLIGHT_PAD * 2,
      radius: radius + 4,
    });
  }, [currentStep, resolveSteps]);

  // Scroll target into view and position before paint
  useLayoutEffect(() => {
    if (!isOpen || !currentStep) return;
    const el = document.querySelector<HTMLElement>(`[data-tour="${currentStep.resolvedTarget}"]`);
    el?.scrollIntoView({ block: 'center', behavior: reduceMotion ? 'auto' : 'smooth' });
    const id = setTimeout(() => {
      positionTooltip();
      setReady(true);
    }, reduceMotion ? 0 : 120);
    return () => clearTimeout(id);
  }, [isOpen, positionTooltip, stepIndex, currentStep, reduceMotion]);

  // Event-driven tracking + a short rAF burst after each step change.
  // A permanent rAF loop (the old approach) pinned a core and drained battery
  // on mobile for the entire duration of the tour.
  useEffect(() => {
    if (!isOpen || !currentStep) return;
    let raf = 0;
    const settleUntil = performance.now() + 900;
    const tick = () => {
      positionTooltip();
      if (performance.now() < settleUntil) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    const onChange = () => positionTooltip();
    window.addEventListener('scroll', onChange, true);
    window.addEventListener('resize', onChange);

    const el = document.querySelector<HTMLElement>(`[data-tour="${currentStep.resolvedTarget}"]`);
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(onChange) : null;
    if (el && ro) ro.observe(el);
    if (ro) ro.observe(document.documentElement);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('scroll', onChange, true);
      window.removeEventListener('resize', onChange);
      ro?.disconnect();
    };
  }, [isOpen, positionTooltip, currentStep, stepIndex]);

  // Keyboard: navigation, escape, and a focus trap inside the card
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        dismiss();
        return;
      }
      if (e.key === 'ArrowRight' && stepIndexRef.current < steps.length - 1) {
        setStepIndex(i => i + 1);
        return;
      }
      if (e.key === 'ArrowLeft' && stepIndexRef.current > 0) {
        setStepIndex(i => i - 1);
        return;
      }
      if (e.key === 'Tab') {
        const card = tooltipRef.current;
        if (!card) return;
        const focusables = card.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input, [tabindex]:not([tabindex="-1"])',
        );
        if (!focusables.length) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement as HTMLElement | null;
        if (e.shiftKey && (active === first || !card.contains(active))) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isOpen, dismiss, steps.length]);

  // Focus the card when it appears; restore the trigger's focus on close.
  useEffect(() => {
    if (isOpen) {
      restoreFocus.current = document.activeElement as HTMLElement | null;
      return;
    }
    restoreFocus.current?.focus?.();
    restoreFocus.current = null;
  }, [isOpen]);

  useEffect(() => {
    if (isOpen && ready) tooltipRef.current?.focus?.();
  }, [isOpen, ready]);

  // Reset state when tour closes
  useEffect(() => {
    if (!isOpen) {
      setReady(false);
      setStepIndex(0);
      setShowConfetti(false);
      lastSignature.current = '';
    }
  }, [isOpen]);

  const handleNext = () => {
    if (stepIndex < steps.length - 1) {
      setStepIndex(i => i + 1);
    }
  };

  const handleComplete = () => {
    if (reduceMotion) {
      onComplete();
      return;
    }
    setShowConfetti(true);
    setTimeout(() => {
      onComplete();
    }, 600);
  };


  // Stable confetti particles — memoised so they don't regenerate every render
  const confettiParticles = useMemo(
    () =>
      Array.from({ length: 20 }, (_, i) => ({
        id: i,
        x: (i * 5.3) % 100, // deterministic spread
        delay: (i * 0.017) % 0.3,
        color: ['#d4af37', '#f59e0b', '#fbbf24', '#fef08a', '#a7f3d0'][i % 5],
      })),
    [],
  );

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
          className="fixed inset-0 z-[9998] pointer-events-none"
        >
          {/* Backdrop click target — tapping the dimmed area exits */}
          <div
            className="absolute inset-0 pointer-events-auto"
            onClick={dismiss}
            aria-hidden
          />

          {/* Spotlight */}
          {spotlight && (
            <>
              <motion.div
                key={`spotlight-${stepIndex}`}
                layout
                transition={{
                  layout: { type: 'spring', stiffness: 340, damping: 30 },
                }}
                className="absolute pointer-events-none"
                style={{
                  top: spotlight.top,
                  left: spotlight.left,
                  width: spotlight.width,
                  height: spotlight.height,
                  borderRadius: spotlight.radius,
                  boxShadow: '0 0 0 9999px rgba(0,0,0,0.65)',
                  border: '2px solid rgba(212, 175, 55, 0.65)',
                }}
              />

              {/* Pulse ring — skipped entirely under prefers-reduced-motion */}
              {!reduceMotion && (
                <motion.div
                  key={`pulse-${stepIndex}`}
                  className="absolute pointer-events-none"
                  style={{
                    top: spotlight.top - 4,
                    left: spotlight.left - 4,
                    width: spotlight.width + 8,
                    height: spotlight.height + 8,
                    borderRadius: spotlight.radius + 4,
                    border: '2px solid rgba(212, 175, 55, 0.4)',
                  }}
                  animate={{
                    scale: [1, 1.06, 1],
                    opacity: [0.7, 0.2, 0.7],
                  }}
                  transition={{
                    duration: 2,
                    repeat: Infinity,
                    ease: 'easeInOut',
                  }}
                />
              )}
            </>
          )}

          {/* Tour card */}
          {ready && tooltipStyle.left !== undefined && (
            <motion.div
              ref={tooltipRef}
              key={`card-${stepIndex}`}
              layout
              initial={{ opacity: 0, y: 12, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.97 }}
              transition={{
                layout: { type: 'spring', stiffness: 340, damping: 30 },
                opacity: { duration: 0.2 },
                y: { type: 'spring', stiffness: 400, damping: 28 },
                scale: { duration: 0.18 },
              }}
              style={tooltipStyle}
              className="pointer-events-auto"
            >
              {/* Outer shell */}
              <div
                style={{
                  background: 'rgba(24, 18, 15, 0.95)',
                  backdropFilter: 'blur(24px)',
                  WebkitBackdropFilter: 'blur(24px)',
                  border: '1px solid rgba(212, 175, 55, 0.3)',
                  borderRadius: 20,
                  boxShadow: [
                    '0 0 0 1px rgba(212, 175, 55, 0.15) inset',
                    '0 24px 48px rgba(0, 0, 0, 0.65)',
                    '0 0 60px rgba(212, 175, 55, 0.08)',
                  ].join(', '),
                  padding: '1px',
                }}
              >
                {/* Inner core */}
                <div
                  style={{
                    borderRadius: 19,
                    background: 'linear-gradient(135deg, rgba(32, 25, 20, 0.97) 0%, rgba(20, 16, 13, 0.99) 100%)',
                    boxShadow: 'inset 0 1px 1px rgba(255,255,255,0.06)',
                    padding: '18px 20px 20px',
                    position: 'relative',
                  }}
                >
                  {/* Arrow pointer
                      side='bottom' → tooltip is BELOW the target → arrow on TOP edge
                      side='top'    → tooltip is ABOVE the target → arrow on BOTTOM edge */}
                  {arrow && (
                    <div
                      style={{
                        position: 'absolute',
                        left: arrow.left - 7,
                        ...(arrow.side === 'bottom'
                          ? { top: -7 }
                          : { bottom: -7 }),
                        width: 14,
                        height: 14,
                        background: 'rgba(20, 16, 13, 0.99)',
                        transform: 'rotate(45deg)',
                        // When arrow is on TOP of tooltip (pointing up at target below):
                        //   hide the bottom-right corner of the diamond → show top-left
                        // When arrow is on BOTTOM of tooltip (pointing down at target above):
                        //   hide the top-left corner of the diamond → show bottom-right
                        borderTop: arrow.side === 'bottom'
                          ? '1px solid rgba(212, 175, 55, 0.3)'
                          : 'none',
                        borderLeft: arrow.side === 'bottom'
                          ? '1px solid rgba(212, 175, 55, 0.3)'
                          : 'none',
                        borderBottom: arrow.side === 'top'
                          ? '1px solid rgba(212, 175, 55, 0.3)'
                          : 'none',
                        borderRight: arrow.side === 'top'
                          ? '1px solid rgba(212, 175, 55, 0.3)'
                          : 'none',
                      }}
                    />
                  )}

                  {/* Header: step indicator + close */}
                  <div className="flex items-center gap-2 mb-3">
                    <span
                      style={{
                        background: 'rgba(212, 175, 55, 0.12)',
                        border: '1px solid rgba(212, 175, 55, 0.25)',
                        borderRadius: 100,
                        padding: '2px 8px',
                        fontSize: 10,
                        fontWeight: 600,
                        letterSpacing: '0.12em',
                        textTransform: 'uppercase',
                        color: 'rgba(212, 175, 55, 0.95)',
                      }}
                    >
                      <MapPin className="w-2.5 h-2.5 inline mr-1 -mt-0.5" />
                      {t('onboarding.tour.stepIndicator', {
                        current: stepIndex + 1,
                        total: steps.length,
                      })}
                    </span>

                    <div className="flex-1" />

                    <button
                      onClick={dismiss}
                      style={{
                        width: 26,
                        height: 26,
                        borderRadius: '50%',
                        background: 'rgba(255,255,255,0.05)',
                        border: '1px solid rgba(255,255,255,0.08)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: 'rgba(255,255,255,0.4)',
                        transition: 'all 0.15s',
                        cursor: 'pointer',
                      }}
                      onMouseEnter={e => {
                        (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.1)';
                        (e.currentTarget as HTMLButtonElement).style.color = 'rgba(255,255,255,0.8)';
                      }}
                      onMouseLeave={e => {
                        (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.05)';
                        (e.currentTarget as HTMLButtonElement).style.color = 'rgba(255,255,255,0.4)';
                      }}
                      aria-label="Close tour"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>

                  {/* Step content crossfade */}
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={stepIndex}
                      initial={{ opacity: 0, x: 10 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -10 }}
                      transition={{ duration: 0.18, ease: [0.32, 0.72, 0, 1] }}
                    >
                      <div className="flex items-start gap-3 mb-4">
                        <span
                          style={{
                            fontSize: 28,
                            lineHeight: 1,
                            flexShrink: 0,
                            filter: 'drop-shadow(0 2px 8px rgba(212,175,55,0.3))',
                          }}
                        >
                          {currentStep?.emoji}
                        </span>
                        <div>
                          <h3
                            style={{
                              fontSize: 15,
                              fontWeight: 700,
                              color: '#fff',
                              marginBottom: 4,
                              lineHeight: 1.3,
                              letterSpacing: '-0.01em',
                            }}
                          >
                            {currentStep && t(currentStep.titleKey)}
                          </h3>
                          <p
                            style={{
                              fontSize: 13,
                              color: 'rgba(255,255,255,0.55)',
                              lineHeight: 1.6,
                            }}
                          >
                            {currentStep && t(currentStep.descriptionKey)}
                          </p>
                        </div>
                      </div>
                    </motion.div>
                  </AnimatePresence>

                  {/* Progress bar */}
                  <div
                    style={{
                      height: 2,
                      background: 'rgba(255,255,255,0.08)',
                      borderRadius: 100,
                      marginBottom: 16,
                      overflow: 'hidden',
                    }}
                  >
                    <motion.div
                      animate={{ width: `${progress * 100}%` }}
                      transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                      style={{
                        height: '100%',
                        background: 'linear-gradient(90deg, #d4af37, #f59e0b)',
                        borderRadius: 100,
                      }}
                    />
                  </div>

                  {/* Footer: dots + navigation */}
                  <div className="flex items-center gap-3">
                    {/* Step dots */}
                    <div className="flex gap-1.5">
                      {steps.map((_, i) => (
                        <button
                          key={i}
                          onClick={() => setStepIndex(i)}
                          style={{
                            width: i === stepIndex ? 16 : 6,
                            height: 6,
                            borderRadius: 100,
                            background:
                              i === stepIndex
                                ? '#d4af37'
                                : i < stepIndex
                                ? 'rgba(212,175,55,0.4)'
                                : 'rgba(255,255,255,0.12)',
                            transition: 'all 0.25s cubic-bezier(0.32,0.72,0,1)',
                            border: 'none',
                            padding: 0,
                            cursor: 'pointer',
                          }}
                          aria-label={`Step ${i + 1}`}
                        />
                      ))}
                    </div>

                    <div style={{ flex: 1 }} />

                    {/* Back */}
                    {stepIndex > 0 && (
                      <button
                        onClick={() => setStepIndex(i => Math.max(0, i - 1))}
                        aria-label="Back to previous tour step"
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 2,
                          fontSize: 12,
                          color: 'rgba(255,255,255,0.5)',
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          padding: '4px 6px',
                          borderRadius: 8,
                        }}
                      >
                        <ChevronLeft className="w-3.5 h-3.5" />
                        {t('onboarding.tour.back', 'Back')}
                      </button>
                    )}

                    {/* Skip (only on non-last steps) */}
                    {!isLastStep && (
                      <button
                        onClick={dismiss}
                        style={{
                          fontSize: 12,
                          color: 'rgba(255,255,255,0.3)',
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          padding: '4px 8px',
                          borderRadius: 8,
                          transition: 'color 0.15s',
                        }}
                        onMouseEnter={e =>
                          ((e.currentTarget as HTMLButtonElement).style.color = 'rgba(255,255,255,0.6)')
                        }
                        onMouseLeave={e =>
                          ((e.currentTarget as HTMLButtonElement).style.color = 'rgba(255,255,255,0.3)')
                        }
                      >
                        {t('onboarding.tour.skip')}
                      </button>
                    )}

                    {/* Next / Got it button */}
                    {isLastStep ? (
                      <motion.button
                        onClick={handleComplete}
                        whileHover={{ scale: 1.04 }}
                        whileTap={{ scale: 0.97 }}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 6,
                          padding: '8px 16px',
                          borderRadius: 100,
                          background: 'linear-gradient(135deg, #d4af37 0%, #f59e0b 100%)',
                          border: 'none',
                          color: '#fff',
                          fontSize: 13,
                          fontWeight: 700,
                          cursor: 'pointer',
                          boxShadow: '0 4px 16px rgba(212,175,55,0.35)',
                          letterSpacing: '-0.01em',
                          transition: 'box-shadow 0.2s',
                        }}
                      >
                        <Sparkles className="w-3.5 h-3.5" />
                        {t('onboarding.tour.gotIt')}
                      </motion.button>
                    ) : (
                      <motion.button
                        onClick={handleNext}
                        whileHover={{ scale: 1.04 }}
                        whileTap={{ scale: 0.97 }}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 4,
                          padding: '8px 14px',
                          borderRadius: 100,
                          background: 'rgba(212,175,55,0.15)',
                          border: '1px solid rgba(212,175,55,0.3)',
                          color: 'rgba(212,175,55,0.95)',
                          fontSize: 13,
                          fontWeight: 600,
                          cursor: 'pointer',
                          transition: 'all 0.15s',
                        }}
                        onMouseEnter={e => {
                          (e.currentTarget as HTMLButtonElement).style.background = 'rgba(212,175,55,0.22)';
                        }}
                        onMouseLeave={e => {
                          (e.currentTarget as HTMLButtonElement).style.background = 'rgba(212,175,55,0.15)';
                        }}
                      >
                        {t('onboarding.tour.next')}
                        <ChevronRight className="w-3.5 h-3.5" />
                      </motion.button>
                    )}
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* Completion confetti burst */}
          <AnimatePresence>
            {showConfetti && (
              <div
                className="fixed inset-0 pointer-events-none"
                style={{ zIndex: 9999 }}
              >
                {confettiParticles.map(p => (
                  <motion.div
                    key={p.id}
                    initial={{ opacity: 1, y: 0, x: `${p.x}vw`, scale: 1 }}
                    animate={{
                      opacity: 0,
                      y: -120,
                      rotate: p.id * 18,
                      scale: 0,
                    }}
                    transition={{
                      duration: 0.7,
                      delay: p.delay,
                      ease: [0.22, 1, 0.36, 1],
                    }}
                    style={{
                      position: 'absolute',
                      top: '50%',
                      width: 8,
                      height: 8,
                      borderRadius: 2,
                      background: p.color,
                    }}
                  />
                ))}
              </div>
            )}
          </AnimatePresence>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
