import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Play, Pause, RotateCcw, Wind, Headphones, Youtube, ExternalLink } from 'lucide-react';
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
}

type BreathPhase = 'idle' | 'inhale' | 'hold' | 'exhale' | 'complete';

const INHALE_DURATION = 4;
const HOLD_DURATION = 2;
const EXHALE_DURATION = 6;
const MIN_DURATION = 180; // 3 minutes in seconds

// Sri Preethaji's Serene Mind guidance video
const SERENE_MIND_VIDEO_ID = 'igSp4H0OWLE';
const SERENE_MIND_YOUTUBE_URL = `https://youtu.be/${SERENE_MIND_VIDEO_ID}`;

export const SereneMindModal = ({ isOpen, onClose, initialTab = 'breathing' }: SereneMindModalProps) => {
  const [activeTab, setActiveTab] = useState<SereneMindTab>(initialTab);
  const [isPlaying, setIsPlaying] = useState(false);
  const [phase, setPhase] = useState<BreathPhase>('idle');
  const [cycleCount, setCycleCount] = useState(0);
  const [countdown, setCountdown] = useState(0);
  const [totalTime, setTotalTime] = useState(MIN_DURATION);
  const sessionRef = useRef<MeditationSession | null>(null);

  // Sync tab when opened with a fresh initialTab
  useEffect(() => {
    if (isOpen) setActiveTab(initialTab);
  }, [isOpen, initialTab]);

  const resetMeditation = useCallback(() => {
    setIsPlaying(false);
    setPhase('idle');
    setCycleCount(0);
    setCountdown(0);
    setTotalTime(MIN_DURATION);
    sessionRef.current = null;
  }, []);

  const handleStart = useCallback(() => {
    if (!sessionRef.current) {
      sessionRef.current = startMeditationSession();
    }
    setIsPlaying(true);
  }, []);

  const handleComplete = useCallback(() => {
    if (sessionRef.current) {
      const duration = MIN_DURATION - totalTime;
      completeMeditationSession(sessionRef.current.id, duration, cycleCount);
    }
    setPhase('complete');
  }, [totalTime, cycleCount]);

  // Breathing phase loop — only runs when breathing tab is active
  useEffect(() => {
    if (activeTab !== 'breathing') return;
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
  }, [activeTab, isPlaying, phase, countdown, cycleCount, totalTime, handleComplete]);

  // Reset when modal closes — save partial breathing session if any
  useEffect(() => {
    if (!isOpen) {
      if (sessionRef.current && phase !== 'idle' && phase !== 'complete') {
        const duration = MIN_DURATION - totalTime;
        completeMeditationSession(sessionRef.current.id, duration, cycleCount);
      }
      resetMeditation();
    }
  }, [isOpen, resetMeditation, phase, totalTime, cycleCount]);

  // Pause breathing if user switches away from breathing tab
  useEffect(() => {
    if (activeTab !== 'breathing' && isPlaying) {
      setIsPlaying(false);
    }
  }, [activeTab, isPlaying]);

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
      case 'hold':
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
            onClick={onClose}
          />

          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className="relative z-10 w-full max-w-lg mx-4"
          >
            <div className="glass-card p-6 sm:p-8 text-center shadow-xl">
              {/* Close Button */}
              <button
                onClick={onClose}
                className="absolute top-4 right-4 p-2 rounded-full hover:bg-muted transition-colors"
                aria-label="Close"
              >
                <X className="w-5 h-5 text-muted-foreground" />
              </button>

              {/* Title */}
              <h2 className="text-2xl font-bold text-gradient-gold mb-1">Serene Mind</h2>
              <p className="text-muted-foreground text-sm mb-5">
                A guided meditation by Sri Preethaji
              </p>

              {/* Tab strip */}
              <div
                role="tablist"
                aria-label="Meditation mode"
                className="inline-flex p-1 rounded-full bg-muted/50 border border-border mb-6"
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
                      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
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
                />
              )}

              {activeTab === 'audio' && (
                <MediaTab mode="audio" videoId={SERENE_MIND_VIDEO_ID} url={SERENE_MIND_YOUTUBE_URL} />
              )}

              {activeTab === 'video' && (
                <MediaTab mode="video" videoId={SERENE_MIND_VIDEO_ID} url={SERENE_MIND_YOUTUBE_URL} />
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
}: BreathingTabProps) => (
  <div role="tabpanel">
    {/* Flame Visualization */}
    <div className="relative w-44 h-44 sm:w-48 sm:h-48 mx-auto mb-6">
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
          Return
        </motion.button>
      ) : (
        <>
          <motion.button
            onClick={() => (isPlaying ? setIsPlaying(false) : handleStart())}
            className="p-4 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground transition-all duration-300 shadow-md"
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            aria-label={isPlaying ? 'Pause breathing' : 'Start breathing'}
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
              aria-label="Reset"
            >
              <RotateCcw className="w-6 h-6 text-muted-foreground" />
            </motion.button>
          )}
        </>
      )}
    </div>
  </div>
);

interface MediaTabProps {
  mode: 'audio' | 'video';
  videoId: string;
  url: string;
}

const MediaTab = ({ mode, videoId, url }: MediaTabProps) => {
  const embedUrl = `https://www.youtube-nocookie.com/embed/${videoId}?modestbranding=1&rel=0`;

  return (
    <div role="tabpanel" className="space-y-4">
      {mode === 'video' ? (
        <div className="relative w-full aspect-video rounded-2xl overflow-hidden bg-black border border-border shadow-md">
          <iframe
            src={embedUrl}
            title="Serene Mind guided meditation"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
            className="absolute inset-0 w-full h-full"
          />
        </div>
      ) : (
        <div className="rounded-2xl overflow-hidden bg-card border border-border shadow-sm p-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-full bg-ojas/15 flex items-center justify-center">
              <Headphones className="w-5 h-5 text-ojas" />
            </div>
            <div className="text-left flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground truncate">
                Sri Preethaji's voice
              </p>
              <p className="text-xs text-muted-foreground">Listen with eyes closed</p>
            </div>
          </div>
          {/* Slim 16:9 iframe — YouTube does not allow audio-only embeds; we shrink the visual */}
          <div className="relative w-full aspect-video rounded-xl overflow-hidden bg-black">
            <iframe
              src={embedUrl}
              title="Serene Mind audio guidance"
              allow="autoplay; encrypted-media; picture-in-picture"
              className="absolute inset-0 w-full h-full"
            />
          </div>
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        Tap play to begin. Audio and video sessions are not counted in your stats —
        only timed breathing logs a session.
      </p>

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
