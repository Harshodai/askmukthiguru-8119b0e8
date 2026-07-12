import { useTranslation } from 'react-i18next';
import { useState, useEffect, useLayoutEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ChevronRight, Sparkles, MapPin } from 'lucide-react';

interface Step {
  target: string;
  titleKey: string;
  descriptionKey: string;
  emoji?: string;
}

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
    titleKey: 'onboarding.tour.step3.title',
    descriptionKey: 'onboarding.tour.step3.description',
    emoji: '🧘',
  },
  {
    target: 'notebook',
    titleKey: 'onboarding.tour.step4.title',
    descriptionKey: 'onboarding.tour.step4.description',
    emoji: '📖',
  },
  {
    target: 'knowledge-graph',
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

export const GuidedTour = ({ isOpen, onComplete, onDismiss }: GuidedTourProps) => {
  const dismiss = onDismiss ?? onComplete;
  const { t } = useTranslation();
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

  const currentStep = STEPS[stepIndex];
  const isLastStep = stepIndex === STEPS.length - 1;
  const progress = (stepIndex + 1) / STEPS.length;

  // Re-reads the target's *current* rect every call — safe to call from a resize
  // handler, a ResizeObserver, or after a step change.
  const positionTooltip = useCallback(() => {
    const el = document.querySelector<HTMLElement>(`[data-tour="${currentStep.target}"]`);
    if (!el) return;

    const rect = el.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const gap = 14;
    const tooltipWidth = clamp(340, 280, vw - gap * 2);
    // Use a stable estimated height to prevent feedback loop during layout animations
    const tooltipHeight = 200;

    // Determine radius of the element (approximated from computed style)
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
      top = clamp(gap, gap, vh - tooltipHeight - gap);
      side = 'bottom';
    }

    let left = rect.left + rect.width / 2 - tooltipWidth / 2;
    left = clamp(left, gap, vw - tooltipWidth - gap);

    setTooltipStyle({ position: 'fixed', top, left, width: tooltipWidth });
    setArrow({
      side,
      left: clamp(rect.left + rect.width / 2 - left, 20, tooltipWidth - 20),
    });
    setSpotlight({
      top: rect.top - SPOTLIGHT_PAD,
      left: rect.left - SPOTLIGHT_PAD,
      width: rect.width + SPOTLIGHT_PAD * 2,
      height: rect.height + SPOTLIGHT_PAD * 2,
      radius: radius + 4,
    });
  }, [currentStep.target]);

  // Target changed: scroll it into view and position synchronously before paint.
  useLayoutEffect(() => {
    if (!isOpen) return;
    const el = document.querySelector<HTMLElement>(`[data-tour="${currentStep.target}"]`);
    el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    // Give scroll a moment, then position
    const t = setTimeout(() => {
      positionTooltip();
      setReady(true);
    }, 120);
    return () => clearTimeout(t);
  }, [isOpen, positionTooltip, stepIndex]);

  // Continuous rAF tracking — same technique as Shepherd.js / driver.js.
  // Can't miss a layout shift because it never assumes one won't happen.
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

  // Keyboard handling
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') dismiss();
      if (e.key === 'ArrowRight' && stepIndex < STEPS.length - 1) setStepIndex(i => i + 1);
      if (e.key === 'ArrowLeft' && stepIndex > 0) setStepIndex(i => i - 1);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isOpen, dismiss, stepIndex]);

  // Reset state when tour closes
  useEffect(() => {
    if (!isOpen) {
      setReady(false);
      setStepIndex(0);
      setShowConfetti(false);
    }
  }, [isOpen]);

  const handleNext = () => {
    if (stepIndex < STEPS.length - 1) {
      setStepIndex(i => i + 1);
    }
  };

  const handleComplete = () => {
    setShowConfetti(true);
    setTimeout(() => {
      onComplete();
    }, 600);
  };

  // Confetti particles
  const confettiParticles = Array.from({ length: 20 }, (_, i) => ({
    id: i,
    x: Math.random() * 100,
    delay: Math.random() * 0.3,
    color: ['#d4af37', '#f59e0b', '#fbbf24', '#fef08a', '#a7f3d0'][Math.floor(Math.random() * 5)],
  }));

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
          {/* Dark overlay using clip-path trick for the spotlight cutout.
              We use box-shadow on the spotlight element — the standard driver.js
              technique, immune to ancestor stacking context bugs. */}
          {spotlight && (
            <>
              {/* Spotlight cutout */}
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
                  // Single large box-shadow = the dark overlay with a "hole" at this element
                  boxShadow: '0 0 0 9999px rgba(0,0,0,0.65)',
                  // Accent border around the target - Gold
                  border: '2px solid rgba(212, 175, 55, 0.65)',
                }}
              />

              {/* Animated pulse ring — the "this is where to look" signal */}
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
              {/* Outer shell — double-bezel technique */}
              <div
                style={{
                  background: 'rgba(10, 10, 14, 0.94)',
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
                    background: 'linear-gradient(135deg, rgba(18,18,24,0.95) 0%, rgba(12,12,18,0.98) 100%)',
                    boxShadow: 'inset 0 1px 1px rgba(255,255,255,0.06)',
                    padding: '18px 20px 20px',
                  }}
                >
                  {/* Arrow pointer */}
                  {arrow && (
                    <div
                      style={{
                        position: 'absolute',
                        left: arrow.left - 7,
                        [arrow.side === 'bottom' ? 'top' : 'bottom']: -7,
                        width: 14,
                        height: 14,
                        background: 'rgba(12,12,18,0.98)',
                        border: `1px solid rgba(212, 175, 55, 0.3)`,
                        transform: 'rotate(45deg)',
                        borderRight: arrow.side === 'bottom' ? 'none' : '1px solid rgba(212, 175, 55, 0.3)',
                        borderBottom: arrow.side === 'bottom' ? 'none' : '1px solid rgba(212, 175, 55, 0.3)',
                        borderTop: arrow.side === 'top' ? 'none' : '1px solid rgba(212, 175, 55, 0.3)',
                        borderLeft: arrow.side === 'top' ? 'none' : '1px solid rgba(212, 175, 55, 0.3)',
                      }}
                    />
                  )}

                  {/* Header: step indicator + emoji + close */}
                  <div className="flex items-center gap-2 mb-3">
                    {/* Eyebrow pill */}
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
                        total: STEPS.length,
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
                          {currentStep.emoji}
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
                            {t(currentStep.titleKey)}
                          </h3>
                          <p
                            style={{
                              fontSize: 13,
                              color: 'rgba(255,255,255,0.55)',
                              lineHeight: 1.6,
                            }}
                          >
                            {t(currentStep.descriptionKey)}
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
                      {STEPS.map((_, i) => (
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
                      rotate: Math.random() * 360,
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
