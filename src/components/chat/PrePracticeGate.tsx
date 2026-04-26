import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Flame, Sparkles, Heart, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  recordPrePractice,
  derivePrePracticeInsights,
  loadProfile,
  type PrePracticeAnswer,
} from '@/lib/profileStorage';
import { useSereneMind } from '@/components/common/SereneMindProvider';

const SESSION_KEY = 'askmukthiguru_pre_practice_asked';

interface PrePracticeGateProps {
  children: React.ReactNode;
}

interface OptionSpec {
  id: PrePracticeAnswer;
  label: string;
  helper: string;
  Icon: typeof Flame;
}

const OPTIONS: OptionSpec[] = [
  {
    id: 'soul_sync',
    label: 'Soul Sync',
    helper: 'I synced inward before opening this',
    Icon: Sparkles,
  },
  {
    id: 'serene_mind',
    label: 'Serene Mind',
    helper: 'I just finished the breath practice',
    Icon: Flame,
  },
  {
    id: 'both',
    label: 'Both',
    helper: 'I did Soul Sync and Serene Mind',
    Icon: Heart,
  },
  {
    id: 'none',
    label: 'Not yet',
    helper: 'Coming straight in — guide me as I am',
    Icon: ArrowRight,
  },
];

/**
 * One-time-per-session gate that asks the seeker whether they prepared
 * with Soul Sync or Serene Mind before entering the chat. The answer is
 * persisted on the local profile and feeds derived insights elsewhere.
 */
export const PrePracticeGate = ({ children }: PrePracticeGateProps) => {
  const [asked, setAsked] = useState<boolean>(() => {
    if (typeof window === 'undefined') return true;
    return sessionStorage.getItem(SESSION_KEY) === '1';
  });
  const { open: openSereneMind } = useSereneMind();

  // Pre-warm profile (migrate any older shape) so first answer writes cleanly.
  useEffect(() => {
    if (!asked) loadProfile();
  }, [asked]);

  const handleAnswer = (answer: PrePracticeAnswer) => {
    recordPrePractice(answer);
    sessionStorage.setItem(SESSION_KEY, '1');
    setAsked(true);
    if (answer === 'none') {
      // Gentle invitation rather than a force — open Serene Mind as a soft nudge.
      // The chat still loads beneath; user can dismiss the modal.
      setTimeout(() => openSereneMind('breath'), 250);
    }
  };

  const handleSkip = () => {
    sessionStorage.setItem(SESSION_KEY, '1');
    setAsked(true);
  };

  if (asked) return <>{children}</>;

  const insights = derivePrePracticeInsights(loadProfile().prePracticeLog);

  return (
    <>
      {children}
      <AnimatePresence>
        <motion.div
          key="pre-practice-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center bg-background/70 backdrop-blur-sm p-3 sm:p-6"
          role="dialog"
          aria-modal="true"
          aria-labelledby="pre-practice-title"
        >
          <motion.div
            initial={{ y: 24, opacity: 0, scale: 0.98 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 24, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 220, damping: 24 }}
            className="glass-card w-full max-w-md rounded-3xl p-5 sm:p-7 border border-ojas/20 shadow-2xl"
          >
            <div className="flex items-center gap-2 mb-2">
              <div className="w-9 h-9 rounded-full bg-ojas/15 border border-ojas/30 flex items-center justify-center">
                <Flame className="w-4 h-4 text-ojas" />
              </div>
              <span className="text-xs uppercase tracking-wider text-muted-foreground">
                Before we begin
              </span>
            </div>

            <h2
              id="pre-practice-title"
              className="text-xl sm:text-2xl font-display text-foreground leading-snug"
            >
              Did you do Soul Sync or Serene Mind today?
            </h2>
            <p className="text-sm text-muted-foreground mt-2">
              {insights.encouragement}
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-5">
              {OPTIONS.map(({ id, label, helper, Icon }) => (
                <button
                  key={id}
                  onClick={() => handleAnswer(id)}
                  className="group text-left rounded-2xl border border-border/60 hover:border-ojas/50 hover:bg-ojas/5 transition-colors p-3 focus:outline-none focus:ring-2 focus:ring-ojas/40"
                >
                  <div className="flex items-center gap-2">
                    <Icon className="w-4 h-4 text-ojas group-hover:scale-110 transition-transform" />
                    <span className="font-medium text-foreground">{label}</span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">{helper}</p>
                </button>
              ))}
            </div>

            <div className="flex items-center justify-between mt-5">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleSkip}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                Skip for now
              </Button>
              <span className="text-[11px] text-muted-foreground">
                Saved privately on this device
              </span>
            </div>
          </motion.div>
        </motion.div>
      </AnimatePresence>
    </>
  );
};
