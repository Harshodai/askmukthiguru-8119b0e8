import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Play, Pause, RotateCcw } from 'lucide-react';
import { 
  startMeditationSession, 
  completeMeditationSession,
  MeditationSession 
} from '@/lib/meditationStorage';

interface SereneMindModalProps {
  isOpen: boolean;
  onClose: () => void;
}

type BreathPhase = 'idle' | 'inhale' | 'hold' | 'exhale' | 'complete';

const INHALE_DURATION = 4;
const HOLD_DURATION = 2;
const EXHALE_DURATION = 6;
const MIN_DURATION = 180; // 3 minutes in seconds

export const SereneMindModal = ({ isOpen, onClose }: SereneMindModalProps) => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [phase, setPhase] = useState<BreathPhase>('idle');
  const [cycleCount, setCycleCount] = useState(0);
  const [countdown, setCountdown] = useState(0);
  const [totalTime, setTotalTime] = useState(MIN_DURATION);
  const sessionRef = useRef<MeditationSession | null>(null);

  const resetMeditation = useCallback(() => {
    setIsPlaying(false);
    setPhase('idle');
    setCycleCount(0);
    setCountdown(0);
    setTotalTime(MIN_DURATION);
    sessionRef.current = null;
  }, []);

  // Start tracking when meditation begins
  const handleStart = useCallback(() => {
    if (!sessionRef.current) {
      sessionRef.current = startMeditationSession();
    }
    setIsPlaying(true);
  }, []);

  // Complete session tracking
  const handleComplete = useCallback(() => {
    if (sessionRef.current) {
      const duration = MIN_DURATION - totalTime;
      completeMeditationSession(sessionRef.current.id, duration, cycleCount);
    }
    setPhase('complete');
  }, [totalTime, cycleCount]);

  // Handle meditation phases
  useEffect(() => {
    if (!isPlaying || phase === 'complete') return;

    if (phase === 'idle') {
      setPhase('inhale');
      setCountdown(INHALE_DURATION);
      return;
    }

    if (countdown > 0) {
      const timer = setTimeout(() => {
        setCountdown((prev) => prev - 1);
        setTotalTime((prev) => Math.max(0, prev - 1));
      }, 1000);
      return () => clearTimeout(timer);
    }

    // Transition to next phase
    if (phase === 'inhale') {
      setPhase('hold');
      setCountdown(HOLD_DURATION);
    } else if (phase === 'hold') {
      setPhase('exhale');
      setCountdown(EXHALE_DURATION);
    } else if (phase === 'exhale') {
      const newCycleCount = cycleCount + 1;
      setCycleCount(newCycleCount);

      if (totalTime <= 0) {
        handleComplete();
      } else {
        setPhase('inhale');
        setCountdown(INHALE_DURATION);
      }
    }
  }, [isPlaying, phase, countdown, cycleCount, totalTime, handleComplete]);

  // Reset when modal closes
  useEffect(() => {
    if (!isOpen) {
      // Save partial session if exists
      if (sessionRef.current && phase !== 'idle' && phase !== 'complete') {
        const duration = MIN_DURATION - totalTime;
        completeMeditationSession(sessionRef.current.id, duration, cycleCount);
      }
      resetMeditation();
    }
  }, [isOpen, resetMeditation, phase, totalTime, cycleCount]);

  const getPhaseInstruction = () => {
    switch (phase) {
      case 'idle':
        return 'Press play to begin';
      case 'inhale':
        return 'Breathe in slowly...';
      case 'hold':
        return 'Hold gently...';
      case 'exhale':
        return 'Release slowly...';
      case 'complete':
        return 'You are now in a beautiful state';
      default:
        return '';
    }
  };

  const getFlameScale = () => {
    switch (phase) {
      case 'inhale':
        return 1.3;
      case 'hold':
        return 1.3;
      case 'exhale':
        return 1;
      default:
        return 1;
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center"
        >
          {/* Backdrop - Warm light overlay */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-background/95 backdrop-blur-xl"
            onClick={onClose}
          />

          {/* Content */}
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className="relative z-10 w-full max-w-lg mx-4"
          >
            <div className="glass-card p-8 text-center shadow-xl">
              {/* Close Button */}
              <button
                onClick={onClose}
                className="absolute top-4 right-4 p-2 rounded-full hover:bg-muted transition-colors"
              >
                <X className="w-5 h-5 text-muted-foreground" />
              </button>

              {/* Title */}
              <h2 className="text-2xl font-bold text-gradient-gold mb-2">Serene Mind</h2>
              <p className="text-muted-foreground text-sm mb-8">
                Focus on the flame at your eyebrow center
              </p>

              {/* Flame Visualization */}
              <div className="relative w-48 h-48 mx-auto mb-8">
                {/* Outer glow rings */}
                <motion.div
                  animate={{
                    scale: phase === 'inhale' ? [1, 1.1] : phase === 'exhale' ? [1.1, 1] : 1,
                    opacity: isPlaying ? [0.2, 0.4] : 0.2,
                  }}
                  transition={{ duration: phase === 'inhale' ? INHALE_DURATION : EXHALE_DURATION }}
                  className="absolute inset-0 rounded-full border-2 border-ojas/40"
                />
                <motion.div
                  animate={{
                    scale: phase === 'inhale' ? [1, 1.15] : phase === 'exhale' ? [1.15, 1] : 1,
                    opacity: isPlaying ? [0.3, 0.5] : 0.3,
                  }}
                  transition={{ duration: phase === 'inhale' ? INHALE_DURATION : EXHALE_DURATION, delay: 0.1 }}
                  className="absolute inset-4 rounded-full border-2 border-ojas/50"
                />

                {/* Central Flame */}
                <div className="absolute inset-0 flex items-center justify-center">
                  <motion.div
                    animate={{
                      scale: getFlameScale(),
                      rotate: isPlaying ? [-1, 1, -0.5, 0.5, -1] : 0,
                    }}
                    transition={{
                      scale: {
                        duration: phase === 'inhale' ? INHALE_DURATION : phase === 'exhale' ? EXHALE_DURATION : 0.5,
                        ease: 'easeInOut',
                      },
                      rotate: {
                        duration: 2,
                        repeat: Infinity,
                      },
                    }}
                    className="relative"
                  >
                    <div className="w-12 h-20 relative">
                      {/* Flame glow */}
                      <motion.div
                        animate={{ opacity: isPlaying ? [0.5, 0.8, 0.5] : 0.5 }}
                        transition={{ duration: 2, repeat: Infinity }}
                        className="absolute inset-0 blur-xl bg-ojas/60 rounded-full"
                      />
                      {/* Flame shape */}
                      <svg viewBox="0 0 48 80" className="w-full h-full relative">
                        <defs>
                          <linearGradient id="flameGradientModal" x1="0%" y1="100%" x2="0%" y2="0%">
                            <stop offset="0%" stopColor="hsl(30, 100%, 50%)" />
                            <stop offset="50%" stopColor="hsl(43, 96%, 56%)" />
                            <stop offset="100%" stopColor="hsl(45, 100%, 85%)" />
                          </linearGradient>
                        </defs>
                        <path
                          d="M24 0 C24 0, 48 32, 48 52 C48 68, 38 80, 24 80 C10 80, 0 68, 0 52 C0 32, 24 0, 24 0Z"
                          fill="url(#flameGradientModal)"
                        />
                        <path
                          d="M24 25 C24 25, 36 45, 36 55 C36 65, 32 72, 24 72 C16 72, 12 65, 12 55 C12 45, 24 25, 24 25Z"
                          fill="hsl(45, 100%, 95%)"
                          opacity="0.9"
                        />
                      </svg>
                    </div>
                  </motion.div>
                </div>
              </div>

              {/* Countdown & Instruction */}
              <div className="mb-8">
                <AnimatePresence mode="wait">
                  {isPlaying && phase !== 'idle' && phase !== 'complete' && (
                    <motion.div
                      key={countdown}
                      initial={{ opacity: 0, scale: 1.2 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.8 }}
                      className="text-5xl font-bold text-ojas mb-2"
                    >
                      {countdown}
                    </motion.div>
                  )}
                </AnimatePresence>
                <motion.p 
                  className="text-lg text-foreground font-medium"
                  animate={{ opacity: [0.7, 1, 0.7] }}
                  transition={{ duration: 2, repeat: Infinity }}
                >
                  {getPhaseInstruction()}
                </motion.p>
                {isPlaying && phase !== 'complete' && (
                  <p className="text-sm text-muted-foreground mt-2">
                    Remaining: {formatTime(totalTime)} • Cycles: {cycleCount}
                  </p>
                )}
              </div>

              {/* Controls */}
              <div className="flex justify-center gap-4">
                {phase === 'complete' ? (
                  <motion.button
                    onClick={onClose}
                    className="px-6 py-3 bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-medium rounded-full transition-all duration-300 shadow-md"
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                  >
                    Return to Chat
                  </motion.button>
                ) : (
                  <>
                    <motion.button
                      onClick={() => isPlaying ? setIsPlaying(false) : handleStart()}
                      className="p-4 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground transition-all duration-300 shadow-md"
                      whileHover={{ scale: 1.1 }}
                      whileTap={{ scale: 0.9 }}
                    >
                      {isPlaying ? <Pause className="w-6 h-6" /> : <Play className="w-6 h-6" />}
                    </motion.button>
                    {(isPlaying || phase !== 'idle') && (
                      <motion.button
                        onClick={resetMeditation}
                        className="p-4 rounded-full bg-muted hover:bg-muted/80 transition-all duration-300"
                        initial={{ opacity: 0, scale: 0 }}
                        animate={{ opacity: 1, scale: 1 }}
                        whileHover={{ scale: 1.1 }}
                        whileTap={{ scale: 0.9 }}
                      >
                        <RotateCcw className="w-6 h-6 text-muted-foreground" />
                      </motion.button>
                    )}
                  </>
                )}
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
