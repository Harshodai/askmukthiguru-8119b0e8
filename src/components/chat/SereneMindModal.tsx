import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Play, Pause, RotateCcw, Wind, Headphones, Youtube, ExternalLink } from 'lucide-react';
import { CircularProgressbar, buildStyles } from 'react-circular-progressbar';
import 'react-circular-progressbar/dist/styles.css';
import { BREATH_TECHNIQUES, DEFAULT_TECHNIQUE, BreathTechnique } from '@/components/meditation/breathTechniques';
import { useBreathTeaching } from '@/hooks/useBreathTeaching';
import {
  startMeditationSession,
  completeMeditationSession,
  MeditationSession,
} from '@/lib/meditationStorage';

export type SereneMindTab = 'breathing' | 'audio' | 'video';

interface SereneMindModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialTab?: SereneMindTab;
  onComplete?: () => void;
  isGated?: boolean; // When true: user cannot close until session completes
}

type BreathPhase = 'idle' | 'inhale' | 'hold1' | 'exhale' | 'hold2' | 'complete';

// Sri Preethaji's Serene Mind guidance video
const SERENE_MIND_VIDEO_ID = 'igSp4H0OWLE';
const SERENE_MIND_YOUTUBE_URL = `https://youtu.be/${SERENE_MIND_VIDEO_ID}`;

export const SereneMindModal = ({ isOpen, onClose, initialTab = 'breathing', onComplete, isGated = false }: SereneMindModalProps) => {
  const [activeTab, setActiveTab] = useState<SereneMindTab>(initialTab);
  const [selectedTechnique, setSelectedTechnique] = useState<BreathTechnique>(DEFAULT_TECHNIQUE);
  const [isPlaying, setIsPlaying] = useState(false);
  const [phase, setPhase] = useState<BreathPhase>('idle');
  const [cycleCount, setCycleCount] = useState(0);
  const [countdown, setCountdown] = useState(0);
  const [totalTime, setTotalTime] = useState(DEFAULT_TECHNIQUE.sessionSeconds);
  const sessionRef = useRef<MeditationSession | null>(null);

  // Dynamic teaching fetch from RAG backend
  const { teaching, loading: teachingLoading } = useBreathTeaching(selectedTechnique.id);

  // Sync tab when opened with a fresh initialTab
  useEffect(() => {
    if (isOpen) {
      setActiveTab(initialTab);
      // Reset timer to selected technique duration
      setTotalTime(selectedTechnique.sessionSeconds);
    }
  }, [isOpen, initialTab, selectedTechnique]);

  const resetMeditation = useCallback(() => {
    setIsPlaying(false);
    setPhase('idle');
    setCycleCount(0);
    setCountdown(0);
    setTotalTime(selectedTechnique.sessionSeconds);
    sessionRef.current = null;
  }, [selectedTechnique]);

  const handleStart = useCallback(() => {
    if (!sessionRef.current) {
      sessionRef.current = startMeditationSession();
    }
    setIsPlaying(true);
  }, []);

  const handleComplete = useCallback(() => {
    if (sessionRef.current) {
      const duration = selectedTechnique.sessionSeconds - totalTime;
      completeMeditationSession(sessionRef.current.id, duration, cycleCount);
    }
    setPhase('complete');
    onComplete?.();
  }, [totalTime, cycleCount, onComplete, selectedTechnique]);

  const handleTechniqueChange = (tech: BreathTechnique) => {
    setSelectedTechnique(tech);
    setIsPlaying(false);
    setPhase('idle');
    setCycleCount(0);
    setCountdown(0);
    setTotalTime(tech.sessionSeconds);
    sessionRef.current = null;
  };

  // Breathing phase loop — only runs when breathing tab is active
  useEffect(() => {
    if (activeTab !== 'breathing') return;
    if (!isPlaying || phase === 'complete') return;

    if (phase === 'idle') {
      setPhase('inhale');
      setCountdown(selectedTechnique.inhale);
      return;
    }

    if (totalTime <= 0) {
      handleComplete();
      return;
    }

    if (countdown > 0) {
      const timer = setTimeout(() => {
        setCountdown((prev) => prev - 1);
        setTotalTime((prev) => Math.max(0, prev - 1));
      }, 1000);
      return () => clearTimeout(timer);
    }

    // Phase transitions when countdown hits 0
    if (phase === 'inhale') {
      if (selectedTechnique.hold1 > 0) {
        setPhase('hold1');
        setCountdown(selectedTechnique.hold1);
      } else {
        setPhase('exhale');
        setCountdown(selectedTechnique.exhale);
      }
    } else if (phase === 'hold1') {
      setPhase('exhale');
      setCountdown(selectedTechnique.exhale);
    } else if (phase === 'exhale') {
      if (selectedTechnique.hold2 > 0) {
        setPhase('hold2');
        setCountdown(selectedTechnique.hold2);
      } else {
        setCycleCount((c) => c + 1);
        setPhase('inhale');
        setCountdown(selectedTechnique.inhale);
      }
    } else if (phase === 'hold2') {
      setCycleCount((c) => c + 1);
      setPhase('inhale');
      setCountdown(selectedTechnique.inhale);
    }
  }, [activeTab, isPlaying, phase, countdown, cycleCount, totalTime, selectedTechnique, handleComplete]);

  // Reset when modal closes — save partial breathing session if any
  useEffect(() => {
    if (!isOpen) {
      if (sessionRef.current && phase !== 'idle' && phase !== 'complete') {
        const duration = selectedTechnique.sessionSeconds - totalTime;
        completeMeditationSession(sessionRef.current.id, duration, cycleCount);
      }
      resetMeditation();
    }
  }, [isOpen, resetMeditation, phase, totalTime, cycleCount, selectedTechnique]);

  // Pause breathing if user switches away from breathing tab
  useEffect(() => {
    if (activeTab !== 'breathing' && isPlaying) {
      setIsPlaying(false);
    }
  }, [activeTab, isPlaying]);

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

  const getPhaseInstruction = () => {
    if (selectedTechnique.id === 'serene_mind') {
      switch (phase) {
        case 'idle':
          return 'Sit still with spine erect, close your eyes';
        case 'inhale':
          return 'Breathe in slowly, filling your abdomen';
        case 'hold1':
          return 'Observe the emotion arising within you';
        case 'exhale':
          return 'Exhale slowly, releasing all tension';
        case 'hold2':
          return 'Hold empty...';
        case 'complete':
          return 'Visualize the flame moving to the center of your brain. Smile & open eyes.';
        default:
          return '';
      }
    }
    switch (phase) {
      case 'idle':
        return 'Press play to begin';
      case 'inhale':
        return 'Breathe in slowly...';
      case 'hold1':
        return 'Hold gently...';
      case 'exhale':
        return 'Release slowly...';
      case 'hold2':
        return 'Hold empty...';
      case 'complete':
        return 'You are now in a beautiful state';
      default:
        return '';
    }
  };

  const getFlameScale = () => {
    switch (phase) {
      case 'inhale':
      case 'hold1':
        return 1.3;
      default:
        return 1;
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const getPhaseDuration = (p: BreathPhase, t: BreathTechnique): number => {
    switch (p) {
      case 'inhale': return t.inhale;
      case 'hold1': return t.hold1;
      case 'exhale': return t.exhale;
      case 'hold2': return t.hold2;
      default: return 1;
    }
  };

  const progressPercentage = (() => {
    if (phase === 'idle' || phase === 'complete') return 0;
    const dur = getPhaseDuration(phase, selectedTechnique);
    if (dur <= 0) return 0;
    return ((dur - countdown) / dur) * 100;
  })();

  const tabs: { id: SereneMindTab; label: string; icon: typeof Wind }[] = [
    { id: 'breathing', label: 'Breathe', icon: Wind },
    { id: 'audio', label: 'Audio', icon: Headphones },
    { id: 'video', label: 'Video', icon: Youtube },
  ];

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center"
          role="dialog"
          aria-modal="true"
          aria-label="Serene Mind meditation"
        >
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-background/95 backdrop-blur-xl"
            onClick={isGated ? undefined : onClose}
          />

          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 15 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 15 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className="relative z-10 w-full max-w-lg mx-4"
          >
            <div className="glass-card rounded-3xl bg-card/85 backdrop-blur-xl border border-border/40 shadow-2xl p-6 sm:p-8 text-center max-h-[90vh] overflow-y-auto scrollbar-spiritual">
              {/* Close Button — hidden when gated (must complete session to dismiss) */}
              {!isGated && (
                <button
                  onClick={onClose}
                  className="absolute top-4 right-4 p-2 rounded-full hover:bg-muted transition-colors"
                  aria-label="Close"
                >
                  <X className="w-5 h-5 text-muted-foreground" />
                </button>
              )}

              {/* Title */}
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ojas/85 mb-1.5">
                Serene Mind
              </p>
              <h2 className="text-xl font-medium text-foreground/90 mb-1">Guided Practice</h2>
              <p className="text-muted-foreground/80 text-xs mb-5">
                Inspired by Sri Preethaji & Sri Krishnaji
              </p>

              {/* Tab strip */}
              <div
                role="tablist"
                aria-label="Meditation mode"
                className="inline-flex p-1 rounded-full bg-muted/65 border border-border/30 mb-6"
              >
                {tabs.map((t) => {
                  const Icon = t.icon;
                  const active = activeTab === t.id;
                  return (
                    <button
                      key={t.id}
                      role="tab"
                      aria-selected={active}
                      onClick={() => setActiveTab(t.id)}
                      className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-xs font-medium transition-all ${
                        active
                          ? 'bg-card text-ojas shadow-sm'
                          : 'text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      <Icon className="w-3.5 h-3.5" />
                      <span>{t.label}</span>
                    </button>
                  );
                })}
              </div>

              {/* Tab content */}
              {activeTab === 'breathing' && (
                <BreathingTab
                  phase={phase}
                  isPlaying={isPlaying}
                  countdown={countdown}
                  totalTime={totalTime}
                  cycleCount={cycleCount}
                  formatTime={formatTime}
                  getFlameScale={getFlameScale}
                  getPhaseInstruction={getPhaseInstruction}
                  handleStart={handleStart}
                  setIsPlaying={setIsPlaying}
                  resetMeditation={resetMeditation}
                  onClose={onClose}
                  selectedTechnique={selectedTechnique}
                  onTechniqueChange={handleTechniqueChange}
                  progressPercentage={progressPercentage}
                  teaching={teaching ?? undefined}
                  teachingLoading={teachingLoading}
                />
              )}

              {activeTab === 'audio' && (
                <MediaTab mode="audio" videoId={SERENE_MIND_VIDEO_ID} url={SERENE_MIND_YOUTUBE_URL} isGated={isGated} onComplete={handleComplete} />
              )}

              {activeTab === 'video' && (
                <MediaTab mode="video" videoId={SERENE_MIND_VIDEO_ID} url={SERENE_MIND_YOUTUBE_URL} isGated={isGated} onComplete={handleComplete} />
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

interface BreathingTabProps {
  phase: BreathPhase;
  isPlaying: boolean;
  countdown: number;
  totalTime: number;
  cycleCount: number;
  formatTime: (s: number) => string;
  getFlameScale: () => number;
  getPhaseInstruction: () => string;
  handleStart: () => void;
  setIsPlaying: (v: boolean) => void;
  resetMeditation: () => void;
  onClose: () => void;
  selectedTechnique: BreathTechnique;
  onTechniqueChange: (tech: BreathTechnique) => void;
  progressPercentage: number;
  teaching?: string;
  teachingLoading?: boolean;
}

const BreathingTab = ({
  phase,
  isPlaying,
  countdown,
  totalTime,
  cycleCount,
  formatTime,
  getFlameScale,
  getPhaseInstruction,
  handleStart,
  setIsPlaying,
  resetMeditation,
  onClose,
  selectedTechnique,
  onTechniqueChange,
  progressPercentage,
  teaching,
  teachingLoading,
}: BreathingTabProps) => {
  const activeInhale = selectedTechnique.inhale;
  const activeExhale = selectedTechnique.exhale;

  return (
    <div role="tabpanel">
      {/* Technique Selector */}
      <div className="mb-6">
        <label className="block text-[10px] font-semibold text-muted-foreground/80 uppercase tracking-wider mb-2">
          Select Technique
        </label>
        <div className="flex flex-wrap justify-center gap-2">
          {BREATH_TECHNIQUES.map((tech) => {
            const active = selectedTechnique.id === tech.id;
            return (
              <button
                key={tech.id}
                onClick={() => onTechniqueChange(tech)}
                disabled={isPlaying}
                className={`px-3 py-1.5 rounded-xl text-xs font-medium border transition-all duration-300 ${
                  active
                    ? 'border-ojas bg-ojas/10 text-ojas shadow-sm'
                    : 'border-border/40 hover:border-border text-muted-foreground hover:text-foreground'
                } disabled:opacity-40 disabled:cursor-not-allowed`}
              >
                {tech.name} <span className="text-[10px] opacity-70">({tech.description})</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Visual Breathing Ring with Flame inside */}
      <div className="relative w-44 h-44 sm:w-48 sm:h-48 mx-auto mb-6">
        <div className="absolute inset-0">
          <CircularProgressbar
            value={progressPercentage}
            styles={buildStyles({
              pathColor: 'hsl(var(--ojas-gold, 43 96% 56%))',
              trailColor: 'rgba(255, 255, 255, 0.05)',
              strokeLinecap: 'round',
              pathTransition: isPlaying && countdown > 0 ? 'stroke-dashoffset 1s linear' : 'none',
            })}
          />
        </div>

        {/* Outer pulse circles */}
        <motion.div
          animate={{
            scale: phase === 'inhale' ? [1, 1.1] : phase === 'exhale' ? [1.1, 1] : 1,
            opacity: isPlaying ? [0.2, 0.4] : 0.2,
          }}
          transition={{ duration: phase === 'inhale' ? activeInhale : activeExhale }}
          className="absolute inset-4 rounded-full border-2 border-ojas/40"
        />
        <motion.div
          animate={{
            scale: phase === 'inhale' ? [1, 1.15] : phase === 'exhale' ? [1.15, 1] : 1,
            opacity: isPlaying ? [0.3, 0.5] : 0.3,
          }}
          transition={{ duration: phase === 'inhale' ? activeInhale : activeExhale, delay: 0.1 }}
          className="absolute inset-8 rounded-full border-2 border-ojas/50"
        />

        <div className="absolute inset-0 flex items-center justify-center">
          <motion.div
            animate={{
              scale: getFlameScale(),
              rotate: isPlaying ? [-1, 1, -0.5, 0.5, -1] : 0,
            }}
            transition={{
              scale: {
                duration: phase === 'inhale' ? activeInhale : phase === 'exhale' ? activeExhale : 0.5,
                ease: 'easeInOut',
              },
              rotate: { duration: 2, repeat: Infinity },
            }}
            className="relative"
          >
            <div className="w-12 h-20 relative">
              <motion.div
                animate={{ opacity: isPlaying ? [0.5, 0.8, 0.5] : 0.5 }}
                transition={{ duration: 2, repeat: Infinity }}
                className="absolute inset-0 blur-xl bg-ojas/60 rounded-full"
              />
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
      <div className="mb-6">
        <AnimatePresence mode="wait">
          {isPlaying && phase !== 'idle' && phase !== 'complete' && (
            <motion.div
              key={countdown}
              initial={{ opacity: 0, scale: 1.2 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.8 }}
              className="text-4xl font-bold text-ojas mb-2"
            >
              {countdown}
            </motion.div>
          )}
        </AnimatePresence>
        <motion.p
          className="text-base text-foreground font-medium"
          animate={{ opacity: [0.7, 1, 0.7] }}
          transition={{ duration: 2, repeat: Infinity }}
        >
          {getPhaseInstruction()}
        </motion.p>
        {isPlaying && phase !== 'complete' && (
          <p className="text-xs text-muted-foreground mt-2">
            Remaining: {formatTime(totalTime)} • Cycles: {cycleCount}
          </p>
        )}
      </div>

      {/* Controls */}
      <div className="flex justify-center gap-4">
        {phase === 'complete' ? (
          <motion.button
            onClick={onClose}
            className="px-6 py-2.5 bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-medium rounded-full transition-all duration-300 shadow-md"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            Return
          </motion.button>
        ) : (
          <>
            <motion.button
              onClick={() => (isPlaying ? setIsPlaying(false) : handleStart())}
              className="p-3.5 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground transition-all duration-300 shadow-md"
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
              aria-label={isPlaying ? 'Pause breathing' : 'Start breathing'}
            >
              {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5" />}
            </motion.button>
            {(isPlaying || phase !== 'idle') && (
              <motion.button
                onClick={resetMeditation}
                className="p-3.5 rounded-full bg-muted hover:bg-muted/80 transition-all duration-300"
                initial={{ opacity: 0, scale: 0 }}
                animate={{ opacity: 1, scale: 1 }}
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
                aria-label="Reset"
              >
                <RotateCcw className="w-5 h-5 text-muted-foreground" />
              </motion.button>
            )}
          </>
        )}
      </div>

      {/* Dynamic RAG Teaching Quote */}
      {teachingLoading ? (
        <div className="mt-8 p-4 rounded-2xl bg-card border border-border/40 text-center text-xs text-muted-foreground">
          <span className="inline-block animate-pulse">Retrieving authentic Ekam teaching...</span>
        </div>
      ) : (
        teaching && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-8 p-4 rounded-2xl bg-card border border-border/40 text-left relative overflow-hidden shadow-sm animate-fade-in"
          >
            <div className="absolute top-0 left-0 w-1 h-full bg-gradient-to-b from-ojas to-ojas-gold" />
            <p className="text-xs font-semibold text-ojas uppercase tracking-wider mb-1 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-ojas animate-pulse" />
              Sri Preethaji & Sri Krishnaji Teaching
            </p>
            <p className="text-xs text-muted-foreground italic leading-relaxed">
              "{teaching}"
            </p>
          </motion.div>
        )
      )}
      {/* Serene Mind Practice Guide */}
      {selectedTechnique.id === 'serene_mind' && (
        <div className="mt-6 p-4 rounded-2xl bg-card border border-border/40 text-left">
          <p className="text-xs font-semibold text-ojas uppercase tracking-wider mb-3">
            Serene Mind Practice Guide (5 Steps)
          </p>
          <div className="space-y-3 text-xs text-muted-foreground">
            <div className={`flex gap-2.5 items-start p-2 rounded-xl transition-all duration-300 ${phase === 'idle' ? 'bg-ojas/5 border border-ojas/20' : 'border border-transparent'}`}>
              <div className="w-5 h-5 rounded-full bg-ojas/10 text-ojas flex items-center justify-center font-bold text-[10px] shrink-0">1</div>
              <div>
                <p className={`font-semibold ${phase === 'idle' ? 'text-ojas text-gradient-gold font-bold' : 'text-foreground'}`}>Posture &amp; Preparation</p>
                <p className="text-[11px] leading-relaxed">Sit erect with spine straight, close your eyes, and prepare to turn your attention inward.</p>
              </div>
            </div>
            <div className={`flex gap-2.5 items-start p-2 rounded-xl transition-all duration-300 ${phase === 'inhale' ? 'bg-ojas/5 border border-ojas/20' : 'border border-transparent'}`}>
              <div className="w-5 h-5 rounded-full bg-ojas/10 text-ojas flex items-center justify-center font-bold text-[10px] shrink-0">2</div>
              <div>
                <p className={`font-semibold ${phase === 'inhale' ? 'text-ojas text-gradient-gold font-bold' : 'text-foreground'}`}>Conscious Breathing (4-2-6)</p>
                <p className="text-[11px] leading-relaxed">Inhale slowly for 4s, hold briefly for 2s, then exhale slowly for 6s. The long exhale activates calm.</p>
              </div>
            </div>
            <div className={`flex gap-2.5 items-start p-2 rounded-xl transition-all duration-300 ${phase === 'hold1' ? 'bg-ojas/5 border border-ojas/20' : 'border border-transparent'}`}>
              <div className="w-5 h-5 rounded-full bg-ojas/10 text-ojas flex items-center justify-center font-bold text-[10px] shrink-0">3</div>
              <div>
                <p className={`font-semibold ${phase === 'hold1' ? 'text-ojas text-gradient-gold font-bold' : 'text-foreground'}`}>Self-Observation (Emotion)</p>
                <p className="text-[11px] leading-relaxed">During the hold, identify the exact emotion present in you (irritation, fear, peace) without trying to change it.</p>
              </div>
            </div>
            <div className={`flex gap-2.5 items-start p-2 rounded-xl transition-all duration-300 ${phase === 'exhale' ? 'bg-ojas/5 border border-ojas/20' : 'border border-transparent'}`}>
              <div className="w-5 h-5 rounded-full bg-ojas/10 text-ojas flex items-center justify-center font-bold text-[10px] shrink-0">4</div>
              <div>
                <p className={`font-semibold ${phase === 'exhale' ? 'text-ojas text-gradient-gold font-bold' : 'text-foreground'}`}>Observe Thought Direction</p>
                <p className="text-[11px] leading-relaxed">Observe where your thoughts are wandering—to past memories, future projections, or staying present.</p>
              </div>
            </div>
            <div className={`flex gap-2.5 items-start p-2 rounded-xl transition-all duration-300 ${phase === 'complete' ? 'bg-ojas/5 border border-ojas/20' : 'border border-transparent'}`}>
              <div className="w-5 h-5 rounded-full bg-ojas/10 text-ojas flex items-center justify-center font-bold text-[10px] shrink-0">5</div>
              <div>
                <p className={`font-semibold ${phase === 'complete' ? 'text-ojas text-gradient-gold font-bold' : 'text-foreground'}`}>Flame in the Brain</p>
                <p className="text-[11px] leading-relaxed">Bring focus to your eyebrow center, visualize a tiny flame moving into the center of your brain. Smile and open eyes.</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

interface MediaTabProps {
  mode: 'audio' | 'video';
  videoId: string;
  url: string;
  isGated?: boolean;
  onComplete?: () => void;
}

const MediaTab = ({ mode, videoId, url, isGated, onComplete }: MediaTabProps) => {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const totalDuration = 180; // 3 minutes

  // Append origin for secure local iframe embeds and prevent Error 153
  const embedUrl = `https://www.youtube-nocookie.com/embed/${videoId}?enablejsapi=1&modestbranding=1&rel=0&controls=${mode === 'video' ? 1 : 0}&origin=${encodeURIComponent(window.location.origin)}`;

  const sendPlayerCommand = (func: string, args: (string | number | boolean)[] = []) => {
    if (iframeRef.current && iframeRef.current.contentWindow) {
      iframeRef.current.contentWindow.postMessage(
        JSON.stringify({ event: 'command', func, args }),
        '*'
      );
    }
  };

  const handlePlayPause = () => {
    if (isPlaying) {
      sendPlayerCommand('pauseVideo');
      setIsPlaying(false);
    } else {
      sendPlayerCommand('playVideo');
      setIsPlaying(true);
    }
  };

  const handleSeek = (seconds: number) => {
    setCurrentTime(seconds);
    sendPlayerCommand('seekTo', [seconds, true]);
  };

  const handleReset = () => {
    setIsPlaying(false);
    setCurrentTime(0);
    sendPlayerCommand('pauseVideo');
    sendPlayerCommand('seekTo', [0, true]);
  };

  // Simulating time tracking for custom seekbar
  useEffect(() => {
    let interval: NodeJS.Timeout | null = null;
    if (isPlaying) {
      interval = setInterval(() => {
        setCurrentTime((prev) => {
          if (prev >= totalDuration) {
            setIsPlaying(false);
            if (interval) clearInterval(interval);
            onComplete?.();
            return totalDuration;
          }
          return prev + 1;
        });
      }, 1000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isPlaying, onComplete]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      sendPlayerCommand('pauseVideo');
    };
  }, []);

  const formatMMSS = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const steps = [
    { title: 'Posture & Breathing', start: 0, end: 30, desc: 'Sit erect, close eyes. Slow deep breaths with a long exhale.' },
    { title: 'Observe Emotion', start: 30, end: 60, desc: 'Feel your inner emotional state without trying to change it.' },
    { title: 'Observe Thoughts', start: 60, end: 90, desc: 'Notice where your thoughts wander—past, future, or present.' },
    { title: 'Focus on the Flame', start: 90, end: 150, desc: 'Visualize a flame moving from eyebrow center to center of brain.' },
    { title: 'Hold & Smile', start: 150, end: 180, desc: 'Hold attention on the flame, gently smile and open eyes.' },
  ];

  const activeStepIndex = steps.findIndex(
    (s) => currentTime >= s.start && currentTime < s.end
  );

  return (
    <div role="tabpanel" className="space-y-6">
      {mode === 'video' ? (
        <div className="space-y-4">
          <div className="relative w-full aspect-video rounded-2xl overflow-hidden bg-black border border-border shadow-md">
            <iframe
              ref={iframeRef}
              src={embedUrl}
              title="Serene Mind guided video"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
              referrerPolicy="strict-origin-when-cross-origin"
              className="absolute inset-0 w-full h-full"
            />
          </div>
          <div className="p-4 rounded-2xl bg-card border border-border/40 text-left">
            <p className="text-xs font-semibold text-ojas uppercase tracking-wider mb-3">
              Practice Progression
            </p>
            <div className="space-y-2.5 text-xs text-muted-foreground">
              {steps.map((s, idx) => (
                <div key={idx} className="flex gap-2.5 items-start">
                  <div className="w-5 h-5 rounded-full bg-ojas/10 text-ojas flex items-center justify-center font-bold text-[10px] shrink-0">
                    {idx + 1}
                  </div>
                  <div>
                    <p className="font-semibold text-foreground">{s.title}</p>
                    <p className="text-[11px] leading-relaxed">{s.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Custom Premium Audio Player UI */}
          <div className="glass-card rounded-2xl p-6 border border-border/40 relative overflow-hidden flex flex-col items-center">
            {/* Hidden Iframe to play YouTube Audio */}
            <iframe
              ref={iframeRef}
              src={embedUrl}
              title="Serene Mind audio player helper"
              allow="autoplay; encrypted-media"
              referrerPolicy="strict-origin-when-cross-origin"
              className="absolute opacity-0 w-1 h-1 pointer-events-none"
            />

            {/* Pulsing Mandala/Flame Graphic */}
            <div className="relative w-32 h-32 flex items-center justify-center mb-4">
              <motion.div
                animate={isPlaying ? {
                  scale: [1, 1.08, 1],
                  rotate: 360,
                } : {}}
                transition={{
                  scale: { repeat: Infinity, duration: 4, ease: 'easeInOut' },
                  rotate: { repeat: Infinity, duration: 40, ease: 'linear' }
                }}
                className="absolute inset-0 rounded-full border-2 border-dashed border-ojas/30"
              />
              <motion.div
                animate={isPlaying ? {
                  scale: [1, 1.04, 1],
                } : {}}
                transition={{
                  duration: 4,
                  repeat: Infinity,
                  ease: 'easeInOut',
                }}
                className="w-20 h-20 rounded-full bg-gradient-to-tr from-ojas/20 to-ojas-gold/20 p-1 shadow-lg relative flex items-center justify-center"
              >
                <div className="w-full h-full rounded-full bg-card border border-ojas/40 flex items-center justify-center relative overflow-hidden">
                  <div className="absolute inset-0 bg-ojas/5 blur-sm animate-pulse" />
                  <Headphones className="w-7 h-7 text-ojas" />
                </div>
              </motion.div>
            </div>

            {/* Player Info */}
            <div className="text-center mb-4">
              <h3 className="font-bold text-foreground text-sm">Serene Mind Guidance</h3>
              <p className="text-xs text-muted-foreground mt-0.5">Sri Preethaji's Voice</p>
            </div>

            {/* Simulated Seekbar / Progress Track */}
            <div className="w-full space-y-2 mb-4">
              <div className="flex items-center justify-between text-[10px] text-muted-foreground px-1">
                <span>{formatMMSS(currentTime)}</span>
                <span>{formatMMSS(totalDuration)}</span>
              </div>
              <div className="relative w-full group">
                <input
                  type="range"
                  min={0}
                  max={totalDuration}
                  value={currentTime}
                  onChange={(e) => handleSeek(parseInt(e.target.value, 10))}
                  className="w-full accent-ojas bg-muted hover:bg-muted/80 rounded-lg h-1.5 cursor-pointer appearance-none"
                />
              </div>
            </div>

            {/* Media Controls */}
            <div className="flex items-center gap-4">
              <motion.button
                onClick={handleReset}
                className="p-3 rounded-full bg-muted/60 hover:bg-muted transition-all duration-300"
                whileHover={{ scale: 1.08 }}
                whileTap={{ scale: 0.95 }}
                aria-label="Restart audio"
              >
                <RotateCcw className="w-4 h-4 text-muted-foreground" />
              </motion.button>

              <motion.button
                onClick={handlePlayPause}
                className="p-4 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground transition-all duration-300 shadow-md"
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
                aria-label={isPlaying ? 'Pause guidance' : 'Play guidance'}
              >
                {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
              </motion.button>
            </div>
          </div>

          {/* Dynamic Step Highlighting List */}
          <div className="p-4 rounded-2xl bg-card border border-border/40 text-left">
            <p className="text-xs font-semibold text-ojas uppercase tracking-wider mb-3">
              Practice Progression
            </p>
            <div className="space-y-3 text-xs text-muted-foreground">
              {steps.map((s, idx) => {
                const isActive = activeStepIndex === idx;
                return (
                  <div
                    key={idx}
                    className={`flex gap-2.5 items-start p-2 rounded-xl transition-all duration-300 border ${
                      isActive
                        ? 'bg-ojas/5 border-ojas/25 shadow-sm'
                        : 'border-transparent'
                    }`}
                  >
                    <div
                      className={`w-5 h-5 rounded-full flex items-center justify-center font-bold text-[10px] shrink-0 transition-colors ${
                        isActive
                          ? 'bg-ojas text-primary-foreground'
                          : 'bg-ojas/10 text-ojas'
                      }`}
                    >
                      {idx + 1}
                    </div>
                    <div>
                      <p
                        className={`font-semibold transition-colors ${
                          isActive ? 'text-ojas text-gradient-gold font-bold' : 'text-foreground'
                        }`}
                      >
                        {s.title}
                      </p>
                      <p className="text-[11px] leading-relaxed mt-0.5">{s.desc}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {isGated && (
        <button
          onClick={onComplete}
          className="mt-3 w-full py-2.5 px-4 rounded-full bg-ojas/90 hover:bg-ojas text-white text-sm font-semibold transition-all shadow-md"
        >
          ✓ Complete Meditation &amp; Unlock Chat
        </button>
      )}

      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1.5 text-xs text-ojas hover:text-ojas-light transition-colors"
      >
        <ExternalLink className="w-3.5 h-3.5" />
        Open in YouTube
      </a>
    </div>
  );
};
