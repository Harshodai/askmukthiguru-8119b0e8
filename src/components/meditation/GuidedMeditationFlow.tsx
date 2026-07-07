import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X, Play, Pause, SkipForward, RotateCcw, ChevronLeft,
  HandHeart, Leaf, Feather, Lightbulb, Droplet, Zap, Sparkles,
} from 'lucide-react';
import { GUIDED_STEPS, TOTAL_DURATION_SECONDS, type MeditationStep } from './meditationSteps';
import { MeditationProgressIndicator } from './MeditationProgressIndicator';
import {
  generateSessionId,
  completeMeditationSession,
} from '@/lib/meditationStorage';

interface GuidedMeditationFlowProps {
  isOpen: boolean;
  onClose: () => void;
  /** Teachings-infused custom steps (alternative to GUIDED_STEPS fallback) */
  customSteps?: MeditationStep[];
  /** Source teaching citation shown when customSteps are active */
  sourceTeaching?: string;
  onComplete?: () => void;
}

type BreathPhase = 'inhale' | 'hold' | 'exhale';

// Persistence key — survives reload / accidental close.
const RESUME_KEY = 'serene_mind_resume_v1';
const RESUME_TTL_MS = 24 * 60 * 60 * 1000; // 24 h

interface ResumePayload {
  sessionId: string;
  stepIndex: number;
  elapsed: number;
  savedAt: number;
}

const readResume = (): ResumePayload | null => {
  try {
    const raw = localStorage.getItem(RESUME_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ResumePayload;
    if (!parsed || Date.now() - parsed.savedAt > RESUME_TTL_MS) {
      localStorage.removeItem(RESUME_KEY);
      return null;
    }
    if (parsed.stepIndex >= GUIDED_STEPS.length) return null;
    return parsed;
  } catch {
    return null;
  }
};

const writeResume = (p: ResumePayload) => {
  try { localStorage.setItem(RESUME_KEY, JSON.stringify(p)); } catch { /* noop */ }
};

const clearResume = () => {
  try { localStorage.removeItem(RESUME_KEY); } catch { /* noop */ }
};

export const GuidedMeditationFlow = ({ isOpen, onClose, customSteps, sourceTeaching, onComplete }: GuidedMeditationFlowProps) => {
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [breathPhase, setBreathPhase] = useState<BreathPhase>('inhale');
  const [breathTimer, setBreathTimer] = useState(0);
  // Reflection state
  const [reflectionStep, setReflectionStep] = useState<0 | 1 | 2 | 3>(0);
  const [selectedMood, setSelectedMood] = useState<string>('');
  const [journalText, setJournalText] = useState('');
  const [gratitudeText, setGratitudeText] = useState('');
  // Resume + close-confirm UX
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);
  const [resumeOffer, setResumeOffer] = useState<ResumePayload | null>(null);
  const sessionIdRef = useRef(generateSessionId());
  const startTimeRef = useRef<number>(0);

  // ponytail: prefer customSteps when provided, GUIDED_STEPS as fallback
  const steps = customSteps ?? GUIDED_STEPS;

  const step = steps[currentStepIndex];
  const isComplete = currentStepIndex >= steps.length;
  const stepProgress = step ? Math.min(elapsed / step.durationSeconds, 1) : 1;

  // On open: detect unfinished prior session and offer resume.
  useEffect(() => {
    if (!isOpen) return;
    const prior = readResume();
    if (prior) {
      setResumeOffer(prior);
      // Defer reset until the user chooses Resume or Start fresh.
      return;
    }
    // Fresh start
    setCurrentStepIndex(0);
    setElapsed(0);
    setIsPlaying(false);
    setBreathPhase('inhale');
    setBreathTimer(0);
    setReflectionStep(0);
    setSelectedMood('');
    setJournalText('');
    setGratitudeText('');
    sessionIdRef.current = generateSessionId();
    startTimeRef.current = Date.now();
  }, [isOpen]);

  // Persist progress every tick while running so an unexpected close is recoverable.
  useEffect(() => {
    if (!isOpen || isComplete || resumeOffer) return;
    writeResume({
      sessionId: sessionIdRef.current,
      stepIndex: currentStepIndex,
      elapsed,
      savedAt: Date.now(),
    });
  }, [isOpen, isComplete, resumeOffer, currentStepIndex, elapsed]);

  const acceptResume = () => {
    if (!resumeOffer) return;
    sessionIdRef.current = resumeOffer.sessionId;
    startTimeRef.current = Date.now() - resumeOffer.elapsed * 1000;
    setCurrentStepIndex(resumeOffer.stepIndex);
    setElapsed(resumeOffer.elapsed);
    setReflectionStep(0);
    setSelectedMood('');
    setJournalText('');
    setGratitudeText('');
    setIsPlaying(true);
    setResumeOffer(null);
  };

  const discardResume = () => {
    clearResume();
    setCurrentStepIndex(0);
    setElapsed(0);
    setIsPlaying(false);
    setBreathPhase('inhale');
    setBreathTimer(0);
    setReflectionStep(0);
    setSelectedMood('');
    setJournalText('');
    setGratitudeText('');
    sessionIdRef.current = generateSessionId();
    startTimeRef.current = Date.now();
    setResumeOffer(null);
  };

  // Main timer
  useEffect(() => {
    if (!isPlaying || isComplete) return;
    const id = setInterval(() => {
      setElapsed((prev) => {
        const next = prev + 1;
        if (next >= step.durationSeconds) {
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
          setBreathPhase(bp.hold > 0 ? 'hold' : 'exhale');
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

  // Save session on completion. Keep startTimeRef intact so the reflection
  // step can compute the final duration accurately when the user submits.
  const savedOnCompleteRef = useRef(false);
  useEffect(() => {
    if (isComplete && startTimeRef.current > 0 && !savedOnCompleteRef.current) {
      savedOnCompleteRef.current = true;
      const durationSec = Math.round((Date.now() - startTimeRef.current) / 1000);
      completeMeditationSession(sessionIdRef.current, durationSec, 0);
      clearResume();
      onComplete?.();
    }
    if (!isComplete) savedOnCompleteRef.current = false;
  }, [isComplete, onComplete]);

  const requestClose = useCallback(() => {
    // If the user has not started yet, or has finished, close immediately.
    if (!isPlaying && elapsed === 0 && currentStepIndex === 0) {
      onClose();
      return;
    }
    if (isComplete) {
      onClose();
      return;
    }
    // Otherwise ask before abandoning practice.
    setIsPlaying(false);
    setShowCloseConfirm(true);
  }, [isPlaying, elapsed, currentStepIndex, isComplete, onClose]);

  const confirmPauseAndExit = useCallback(() => {
    // Progress is already persisted to localStorage every tick — keep it
    // so the user can resume next time they open the modal.
    writeResume({
      sessionId: sessionIdRef.current,
      stepIndex: currentStepIndex,
      elapsed,
      savedAt: Date.now(),
    });
    setShowCloseConfirm(false);
    onClose();
  }, [currentStepIndex, elapsed, onClose]);

  const confirmEndAndExit = useCallback(() => {
    // User chose to abandon — save partial session for stats, then clear resume.
    if (startTimeRef.current > 0) {
      const durationSec = Math.round((Date.now() - startTimeRef.current) / 1000);
      if (durationSec > 10) {
        completeMeditationSession(sessionIdRef.current, durationSec, 0);
      }
    }
    clearResume();
    setShowCloseConfirm(false);
    onClose();
  }, [onClose]);

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
          onClick={requestClose}
          className="absolute top-4 right-4 p-2 rounded-full hover:bg-muted transition-colors z-10"
        >
          <X className="w-5 h-5 text-muted-foreground" />
        </button>

        {/* Back Button for post-practice reflection steps */}
        {isComplete && reflectionStep > 0 && reflectionStep < 3 && (
          <button
            onClick={() => setReflectionStep(prev => (prev - 1) as 0 | 1 | 2 | 3)}
            className="absolute top-4 left-4 p-2 rounded-full hover:bg-muted transition-colors z-10"
            aria-label="Back"
          >
            <ChevronLeft className="w-5 h-5 text-muted-foreground" />
          </button>
        )}

        {isComplete ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="w-full max-w-sm mx-auto space-y-5 px-6"
          >
            {reflectionStep === 0 && (
              <>
                <div className="text-center space-y-2">
                  <div className="w-16 h-16 mx-auto rounded-full bg-ojas/15 flex items-center justify-center">
                    <HandHeart className="w-7 h-7 text-ojas" />
                  </div>
                  <h2 className="text-xl font-semibold text-foreground">Namaste</h2>
                  <p className="text-sm text-muted-foreground">How do you feel right now?</p>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { Icon: Leaf, label: 'Peaceful' },
                    { Icon: HandHeart, label: 'Grateful' },
                    { Icon: Feather, label: 'Lighter' },
                    { Icon: Lightbulb, label: 'Reflective' },
                    { Icon: Droplet, label: 'Emotional' },
                    { Icon: Zap, label: 'Energised' },
                  ].map(({ Icon, label }) => (
                    <button
                      key={label}
                      onClick={() => setSelectedMood(label)}
                      className={`flex flex-col items-center gap-1 py-3 rounded-xl border text-xs font-medium transition-all ${
                        selectedMood === label
                          ? 'border-ojas bg-ojas/10 text-ojas'
                          : 'border-border/40 bg-card/60 text-muted-foreground hover:border-ojas/30'
                      }`}
                    >
                      <Icon className="w-5 h-5" />
                      {label}
                    </button>
                  ))}
                </div>
                <button
                  onClick={() => setReflectionStep(1)}
                  disabled={!selectedMood}
                  className="w-full py-2.5 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-medium disabled:opacity-40 transition-opacity"
                >
                  Continue
                </button>
                <button onClick={requestClose} className="w-full py-2 text-xs text-muted-foreground hover:text-foreground transition-colors">
                  Skip to chat
                </button>
              </>
            )}

            {reflectionStep === 1 && (
              <>
                <div className="text-center space-y-1">
                  <h2 className="text-lg font-semibold text-foreground">Capture this moment</h2>
                  <p className="text-sm text-muted-foreground">What insight arose during your meditation?</p>
                </div>
                <textarea
                  value={journalText}
                  onChange={e => setJournalText(e.target.value)}
                  placeholder="What do you notice in this moment… thoughts, sensations, feelings…"
                  rows={4}
                  className="w-full p-3 rounded-xl bg-muted/50 border border-border/40 text-sm text-foreground placeholder:text-muted-foreground/60 resize-none outline-none focus:border-ojas/40"
                />
                <button
                  onClick={() => setReflectionStep(2)}
                  className="w-full py-2.5 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-medium"
                >
                  {journalText.trim() ? 'Continue' : 'Skip'}
                </button>
              </>
            )}

            {reflectionStep === 2 && (
              <>
                <div className="text-center space-y-1">
                  <h2 className="text-lg font-semibold text-foreground">One thing of gratitude</h2>
                  <p className="text-sm text-muted-foreground">Name something you are grateful for right now.</p>
                </div>
                <textarea
                  value={gratitudeText}
                  onChange={e => setGratitudeText(e.target.value)}
                  placeholder="I am grateful for…"
                  rows={3}
                  className="w-full p-3 rounded-xl bg-muted/50 border border-border/40 text-sm text-foreground placeholder:text-muted-foreground/60 resize-none outline-none focus:border-ojas/40"
                />
                <button
                  onClick={async () => {
                    // Save reflection extras to existing session.
                    // Guard against a zeroed startTimeRef (defensive).
                    const durationSec = startTimeRef.current > 0
                      ? Math.round((Date.now() - startTimeRef.current) / 1000)
                      : 0;
                    await completeMeditationSession(sessionIdRef.current, durationSec, 0, {
                      mood: selectedMood,
                      reflection: journalText.trim() || undefined,
                      gratitude: gratitudeText.trim() || undefined,
                    });
                    setReflectionStep(3);
                  }}
                  className="w-full py-2.5 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-medium"
                >
                  {gratitudeText.trim() ? 'Complete' : 'Skip'}
                </button>
              </>
            )}

            {reflectionStep === 3 && (
              <div className="text-center space-y-4">
                <div className="w-16 h-16 mx-auto rounded-full bg-green-500/10 flex items-center justify-center">
                  <Sparkles className="w-7 h-7 text-green-500" />
                </div>
                <h2 className="text-xl font-semibold text-foreground">Beautiful</h2>
                <p className="text-sm text-muted-foreground">
                  You have completed your practice. Carry this {selectedMood.toLowerCase()} state into your day.
                </p>
                <button
                  onClick={requestClose}
                  className="px-6 py-2.5 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-medium"
                >
                  Return to Chat
                </button>
              </div>
            )}
          </motion.div>
        ) : (
          <div className="flex flex-col items-center gap-8 px-6 max-w-md w-full">
            {/* Progress indicator */}
            <MeditationProgressIndicator
              currentStep={currentStepIndex}
              totalSteps={steps.length}
              stepProgress={stepProgress}
            />

            {/* Source teaching attribution — only when custom */}
            {sourceTeaching && (
              <p className="text-xs text-muted-foreground/70 italic">
                Infused from {sourceTeaching}
              </p>
            )}

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

        {/* Resume offer — shown when a prior, unfinished session exists. */}
        {resumeOffer && !isComplete && (
          <div className="absolute inset-0 z-20 bg-background/95 backdrop-blur-sm flex items-center justify-center px-6">
            <motion.div
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              className="w-full max-w-sm rounded-2xl border border-ojas/30 bg-card/90 p-6 text-center space-y-4 shadow-xl"
              role="dialog"
              aria-label="Resume your practice"
            >
              <div className="w-12 h-12 mx-auto rounded-full bg-ojas/15 flex items-center justify-center">
                <RotateCcw className="w-5 h-5 text-ojas" />
              </div>
              <div className="space-y-1">
                <h3 className="text-lg font-semibold text-foreground">Resume your practice?</h3>
                <p className="text-sm text-muted-foreground">
                  You paused at <span className="text-foreground/90 font-medium">{steps[resumeOffer.stepIndex]?.title ?? 'an earlier step'}</span>.
                  Continue right where you left off.
                </p>
              </div>
              <div className="flex flex-col sm:flex-row gap-2">
                <button
                  type="button"
                  onClick={discardResume}
                  className="flex-1 py-2.5 rounded-full border border-border text-sm font-medium text-muted-foreground hover:bg-muted transition-colors"
                >
                  Start fresh
                </button>
                <button
                  type="button"
                  onClick={acceptResume}
                  className="flex-1 py-2.5 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground text-sm font-semibold"
                >
                  Resume
                </button>
              </div>
            </motion.div>
          </div>
        )}

        {/* Close-confirm — gentle pause prompt instead of silent exit. */}
        {showCloseConfirm && (
          <div className="absolute inset-0 z-30 bg-background/95 backdrop-blur-sm flex items-center justify-center px-6">
            <motion.div
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              className="w-full max-w-sm rounded-2xl border border-ojas/30 bg-card/95 p-6 text-center space-y-4 shadow-xl"
              role="alertdialog"
              aria-label="Pause this practice?"
            >
              <h3 className="text-lg font-semibold text-foreground">Pause this practice?</h3>
              <p className="text-sm text-muted-foreground">
                You can continue right where you left off the next time you open Serene Mind.
              </p>
              <div className="flex flex-col gap-2">
                <button
                  type="button"
                  onClick={() => { setShowCloseConfirm(false); setIsPlaying(true); }}
                  className="w-full py-2.5 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground text-sm font-semibold"
                >
                  Keep going
                </button>
                <button
                  type="button"
                  onClick={confirmPauseAndExit}
                  className="w-full py-2.5 rounded-full border border-border text-sm font-medium text-foreground/85 hover:bg-muted transition-colors"
                >
                  Pause &amp; close
                </button>
                <button
                  type="button"
                  onClick={confirmEndAndExit}
                  className="w-full py-2 text-xs text-muted-foreground/80 hover:text-destructive transition-colors"
                >
                  End practice
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </motion.div>
    </AnimatePresence>
  );
};

