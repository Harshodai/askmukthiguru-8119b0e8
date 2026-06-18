import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Play, Pause, RotateCcw, ExternalLink } from 'lucide-react';
import {
  startMeditationSession,
  completeMeditationSession,
  MeditationSession,
} from '@/lib/meditationStorage';

// Kept exported for backwards compatibility with SereneMindProvider.
export type SereneMindTab = 'breathing' | 'audio' | 'video';

interface SereneMindModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialTab?: SereneMindTab;
  onComplete?: () => void;
  isGated?: boolean;
}

type BreathPhase = 'idle' | 'inhale' | 'hold' | 'exhale' | 'complete';

// Sri Preethaji's Serene Mind teaching — 4·2·6 conscious breathing
const INHALE = 4;
const HOLD = 2;
const EXHALE = 6;
const CYCLE = INHALE + HOLD + EXHALE; // 12s
const TARGET_CYCLES = 15; // ~3 minutes
const SESSION_SECONDS = CYCLE * TARGET_CYCLES;

const SERENE_MIND_YOUTUBE_URL = 'https://youtu.be/igSp4H0OWLE';

const PHASE_TEXT: Record<BreathPhase, string> = {
  idle: 'Sit erect. Close your eyes. When ready, begin.',
  inhale: 'Breathe in',
  hold: 'Observe the emotion within',
  exhale: 'Breathe out, release',
  complete: 'Carry this beautiful state with you 🙏',
};

export const SereneMindModal = ({
  isOpen,
  onClose,
  onComplete,
  isGated = false,
}: SereneMindModalProps) => {
  const [phase, setPhase] = useState<BreathPhase>('idle');
  const [countdown, setCountdown] = useState(0);
  const [cycles, setCycles] = useState(0);
  const [remaining, setRemaining] = useState(SESSION_SECONDS);
  const [isPlaying, setIsPlaying] = useState(false);
  const sessionRef = useRef<MeditationSession | null>(null);

  const reset = useCallback(() => {
    setIsPlaying(false);
    setPhase('idle');
    setCountdown(0);
    setCycles(0);
    setRemaining(SESSION_SECONDS);
    sessionRef.current = null;
  }, []);

  const finish = useCallback(() => {
    if (sessionRef.current) {
      completeMeditationSession(
        sessionRef.current.id,
        SESSION_SECONDS - remaining,
        cycles
      );
      sessionRef.current = null;
    }
    setIsPlaying(false);
    setPhase('complete');
    onComplete?.();
  }, [cycles, remaining, onComplete]);

  const start = useCallback(() => {
    if (!sessionRef.current) sessionRef.current = startMeditationSession();
    setIsPlaying(true);
    if (phase === 'idle') {
      setPhase('inhale');
      setCountdown(INHALE);
    }
  }, [phase]);

  // tick
  useEffect(() => {
    if (!isOpen || !isPlaying || phase === 'complete' || phase === 'idle') return;
    if (remaining <= 0) {
      finish();
      return;
    }
    const t = setTimeout(() => {
      setCountdown((c) => c - 1);
      setRemaining((r) => Math.max(0, r - 1));
    }, 1000);
    return () => clearTimeout(t);
  }, [isOpen, isPlaying, phase, countdown, remaining, finish]);

  // phase transitions
  useEffect(() => {
    if (!isPlaying || phase === 'idle' || phase === 'complete') return;
    if (countdown > 0) return;
    if (phase === 'inhale') {
      setPhase('hold');
      setCountdown(HOLD);
    } else if (phase === 'hold') {
      setPhase('exhale');
      setCountdown(EXHALE);
    } else if (phase === 'exhale') {
      setCycles((c) => c + 1);
      setPhase('inhale');
      setCountdown(INHALE);
    }
  }, [countdown, phase, isPlaying]);

  // save partial on close
  useEffect(() => {
    if (!isOpen) {
      if (sessionRef.current && phase !== 'idle' && phase !== 'complete') {
        completeMeditationSession(
          sessionRef.current.id,
          SESSION_SECONDS - remaining,
          cycles
        );
      }
      reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  // Prevent tab closure / reload & Escape key closure when Serene Mind is gated and active
  useEffect(() => {
    if (isOpen && isGated && phase !== 'complete') {
      const handleBeforeUnload = (e: BeforeUnloadEvent) => {
        e.preventDefault();
        e.returnValue = 'You are in a Serene Mind meditation. Please pause and complete this practice before leaving.';
        return e.returnValue;
      };
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
          e.preventDefault();
          e.stopPropagation();
        }
      };
      window.addEventListener('beforeunload', handleBeforeUnload);
      window.addEventListener('keydown', handleKeyDown, true);
      return () => {
        window.removeEventListener('beforeunload', handleBeforeUnload);
        window.removeEventListener('keydown', handleKeyDown, true);
      };
    }
  }, [isOpen, isGated, phase]);

  const mmss = (s: number) =>
    `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;

  const phaseScale =
    phase === 'inhale' ? 1.25 : phase === 'hold' ? 1.25 : phase === 'exhale' ? 0.85 : 1;
  const phaseDuration =
    phase === 'inhale' ? INHALE : phase === 'exhale' ? EXHALE : phase === 'hold' ? HOLD : 1;

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center px-4"
          role="dialog"
          aria-modal="true"
          aria-label="Serene Mind meditation"
        >
          <div
            className="absolute inset-0 bg-background/95 backdrop-blur-xl"
            onClick={isGated ? undefined : onClose}
          />

          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96 }}
            transition={{ type: 'spring', damping: 26, stiffness: 280 }}
            className="relative z-10 w-full max-w-sm"
          >
            <div className="relative rounded-3xl bg-card/80 backdrop-blur-xl border border-border/40 shadow-2xl px-6 py-8 text-center">
              {(!isGated || phase === 'complete') && (
                <button
                  onClick={onClose}
                  className="absolute top-3 right-3 p-1.5 rounded-full hover:bg-muted transition-colors"
                  aria-label="Close"
                >
                  <X className="w-4 h-4 text-muted-foreground" />
                </button>
              )}

              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ojas/80 mb-1">
                Serene Mind
              </p>
              <h2 className="text-base font-medium text-foreground/90 mb-8">
                Breathe 4 · Hold 2 · Release 6
              </h2>

              {/* Flame visualization */}
              <div className="relative w-44 h-44 mx-auto mb-7 flex items-center justify-center">
                <motion.div
                  animate={{
                    scale: isPlaying ? phaseScale : 1,
                    opacity: isPlaying ? 0.5 : 0.3,
                  }}
                  transition={{ duration: phaseDuration, ease: 'easeInOut' }}
                  className="absolute inset-0 rounded-full bg-ojas/15 blur-xl"
                />
                <motion.div
                  animate={{ scale: isPlaying ? phaseScale : 1 }}
                  transition={{ duration: phaseDuration, ease: 'easeInOut' }}
                  className="absolute inset-6 rounded-full border border-ojas/30"
                />
                <motion.div
                  animate={{ scale: isPlaying ? phaseScale * 0.95 : 1 }}
                  transition={{ duration: phaseDuration, ease: 'easeInOut' }}
                  className="relative w-14 h-20"
                >
                  <div className="absolute inset-0 blur-xl bg-ojas/60 rounded-full" />
                  <svg viewBox="0 0 48 80" className="w-full h-full relative">
                    <defs>
                      <linearGradient id="serenFlame" x1="0%" y1="100%" x2="0%" y2="0%">
                        <stop offset="0%" stopColor="hsl(30, 100%, 50%)" />
                        <stop offset="50%" stopColor="hsl(43, 96%, 56%)" />
                        <stop offset="100%" stopColor="hsl(45, 100%, 85%)" />
                      </linearGradient>
                    </defs>
                    <path
                      d="M24 0 C24 0, 48 32, 48 52 C48 68, 38 80, 24 80 C10 80, 0 68, 0 52 C0 32, 24 0, 24 0Z"
                      fill="url(#serenFlame)"
                    />
                  </svg>
                </motion.div>

                {isPlaying && phase !== 'complete' && (
                  <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 text-3xl font-light text-ojas tabular-nums">
                    {countdown}
                  </div>
                )}
              </div>

              {/* Instruction */}
              <AnimatePresence mode="wait">
                <motion.p
                  key={phase}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  className="text-base text-foreground font-light min-h-[1.5rem] mb-2"
                >
                  {PHASE_TEXT[phase]}
                </motion.p>
              </AnimatePresence>

              {phase !== 'complete' && (
                <p className="text-xs text-muted-foreground mb-6 tabular-nums">
                  {mmss(remaining)} remaining · {cycles} cycles
                </p>
              )}
              {phase === 'complete' && (
                <p className="text-xs text-muted-foreground mb-6">
                  {cycles} cycles · {mmss(SESSION_SECONDS - remaining)}
                </p>
              )}

              {/* Controls */}
              <div className="flex justify-center items-center gap-3 mb-5">
                {phase === 'complete' ? (
                  <button
                    onClick={onClose}
                    className="px-6 py-2.5 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground text-sm font-medium shadow-md"
                  >
                    Return to chat
                  </button>
                ) : (
                  <>
                    <button
                      onClick={() => (isPlaying ? setIsPlaying(false) : start())}
                      className="p-3.5 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground shadow-md hover:opacity-95 transition"
                      aria-label={isPlaying ? 'Pause' : 'Start'}
                    >
                      {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5" />}
                    </button>
                    {phase !== 'idle' && (
                      <button
                        onClick={reset}
                        className="p-3 rounded-full bg-muted hover:bg-muted/70 transition"
                        aria-label="Reset"
                      >
                        <RotateCcw className="w-4 h-4 text-muted-foreground" />
                      </button>
                    )}
                    {isPlaying && (
                      <button
                        onClick={finish}
                        className="text-xs text-muted-foreground hover:text-foreground px-2 py-1 transition"
                      >
                        End
                      </button>
                    )}
                  </>
                )}
              </div>

              {/* Subtle audio/video link */}
              <a
                href={SERENE_MIND_YOUTUBE_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-[11px] text-muted-foreground/70 hover:text-ojas transition-colors"
              >
                Guided by Sri Preethaji <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
