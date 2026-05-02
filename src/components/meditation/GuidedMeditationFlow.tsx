import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Play, Pause, SkipForward } from 'lucide-react';
import { GUIDED_STEPS, TOTAL_DURATION_SECONDS } from './meditationSteps';
import { MeditationProgressIndicator } from './MeditationProgressIndicator';
import {
  generateSessionId,
  completeMeditationSession,
} from '@/lib/meditationStorage';

interface GuidedMeditationFlowProps {
  isOpen: boolean;
  onClose: () => void;
}

type BreathPhase = 'inhale' | 'hold' | 'exhale';

export const GuidedMeditationFlow = ({ isOpen, onClose }: GuidedMeditationFlowProps) => {
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [breathPhase, setBreathPhase] = useState<BreathPhase>('inhale');
  const [breathTimer, setBreathTimer] = useState(0);
  const sessionIdRef = useRef(generateSessionId());
  const startTimeRef = useRef<number>(0);

  const step = GUIDED_STEPS[currentStepIndex];
  const isComplete = currentStepIndex >= GUIDED_STEPS.length;
  const stepProgress = step ? Math.min(elapsed / step.durationSeconds, 1) : 1;

  // Reset on open
  useEffect(() => {
    if (isOpen) {
      setCurrentStepIndex(0);
      setElapsed(0);
      setIsPlaying(false);
      setBreathPhase('inhale');
      setBreathTimer(0);
      sessionIdRef.current = generateSessionId();
      startTimeRef.current = Date.now();
    }
  }, [isOpen]);

  // Main timer
  useEffect(() => {
    if (!isPlaying || isComplete) return;
    const id = setInterval(() => {
      setElapsed((prev) => {
        const next = prev + 1;
        if (next >= step.durationSeconds) {
          // Advance step
          setCurrentStepIndex((si) => si + 1);
          return 0;
        }
        return next;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [isPlaying, isComplete, step]);

  // Breathing cycle within breathing step
  useEffect(() => {
    if (!isPlaying || !step?.breathPattern) return;
    const bp = step.breathPattern;
    const id = setInterval(() => {
      setBreathTimer((prev) => {
        const next = prev + 1;
        if (breathPhase === 'inhale' && next >= bp.inhale) {
          setBreathPhase('hold');
          return 0;
        }
        if (breathPhase === 'hold' && next >= bp.hold) {
          setBreathPhase('exhale');
          return 0;
        }
        if (breathPhase === 'exhale' && next >= bp.exhale) {
          setBreathPhase('inhale');
          return 0;
        }
        return next;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [isPlaying, step, breathPhase]);

  // Save session on completion
  useEffect(() => {
    if (isComplete && startTimeRef.current > 0) {
      const durationSec = Math.round((Date.now() - startTimeRef.current) / 1000);
      completeMeditationSession(sessionIdRef.current, durationSec, 0);
      startTimeRef.current = 0;
    }
  }, [isComplete]);

  const handleClose = useCallback(() => {
    if (isPlaying && !isComplete) {
      // Save partial session
      const durationSec = Math.round((Date.now() - startTimeRef.current) / 1000);
      if (durationSec > 10) {
        completeMeditationSession(sessionIdRef.current, durationSec, 0);
      }
    }
    onClose();
  }, [isPlaying, isComplete, onClose]);

  const skipStep = useCallback(() => {
    setCurrentStepIndex((prev) => prev + 1);
    setElapsed(0);
    setBreathPhase('inhale');
    setBreathTimer(0);
  }, []);

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 bg-background flex flex-col items-center justify-center"
      >
        {/* Close */}
        <button
          onClick={handleClose}
          className="absolute top-4 right-4 p-2 rounded-full hover:bg-muted transition-colors z-10"
        >
          <X className="w-5 h-5 text-muted-foreground" />
        </button>

        {isComplete ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="text-center space-y-6 px-6"
          >
            <div className="w-20 h-20 mx-auto rounded-full bg-ojas/15 flex items-center justify-center">
              <span className="text-3xl">🙏</span>
            </div>
            <h2 className="text-2xl font-semibold text-foreground">Namaste</h2>
            <p className="text-muted-foreground max-w-sm">
              Your meditation is complete. Carry this peace with you throughout your day.
            </p>
            <button
              onClick={handleClose}
              className="px-6 py-2.5 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-medium"
            >
              Return to Chat
            </button>
          </motion.div>
        ) : (
          <div className="flex flex-col items-center gap-8 px-6 max-w-md w-full">
            {/* Progress indicator */}
            <MeditationProgressIndicator
              currentStep={currentStepIndex}
              totalSteps={GUIDED_STEPS.length}
              stepProgress={stepProgress}
            />

            {/* Step content */}
            <AnimatePresence mode="wait">
              <motion.div
                key={step.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className="text-center space-y-3"
              >
                <h3 className="text-sm font-medium uppercase tracking-wider text-ojas">
                  {step.title}
                </h3>
                <p className="text-lg text-foreground leading-relaxed">
                  {step.instruction}
                </p>
              </motion.div>
            </AnimatePresence>

            {/* Breathing visualization */}
            {step.breathPattern && isPlaying && (
              <motion.div className="flex flex-col items-center gap-2">
                <motion.div
                  animate={{
                    scale: breathPhase === 'inhale' ? 1.4 : breathPhase === 'hold' ? 1.4 : 1,
                    opacity: breathPhase === 'hold' ? 0.7 : 1,
                  }}
                  transition={{ duration: breathPhase === 'inhale' ? step.breathPattern.inhale : step.breathPattern.exhale, ease: 'easeInOut' }}
                  className="w-16 h-16 rounded-full bg-gradient-to-br from-ojas/30 to-ojas-light/30 border border-ojas/40"
                />
                <p className="text-sm text-muted-foreground capitalize">{breathPhase}</p>
              </motion.div>
            )}

            {/* Timer */}
            <p className="text-sm text-muted-foreground tabular-nums">
              {Math.max(0, step.durationSeconds - elapsed)}s remaining
            </p>

            {/* Controls */}
            <div className="flex items-center gap-4">
              <button
                onClick={() => setIsPlaying(!isPlaying)}
                className="w-14 h-14 rounded-full bg-gradient-to-br from-ojas to-ojas-light text-primary-foreground flex items-center justify-center shadow-lg"
              >
                {isPlaying ? <Pause className="w-6 h-6" /> : <Play className="w-6 h-6 ml-0.5" />}
              </button>
              <button
                onClick={skipStep}
                className="p-3 rounded-full border border-border hover:border-ojas/40 transition-colors"
                title="Skip step"
              >
                <SkipForward className="w-4 h-4 text-muted-foreground" />
              </button>
            </div>
          </div>
        )}
      </motion.div>
    </AnimatePresence>
  );
};
