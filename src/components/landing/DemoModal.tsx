import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Compass,
  HeartPulse,
  MessageCircle,
  Sparkles,
  X,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog';

const TOUR_KEY = 'askmukthiguru_landing_tour_v2';

export type TourOutcome = 'dismissed' | 'skipped' | 'completed';

export const getTourOutcome = (): TourOutcome | null => {
  try {
    const value = localStorage.getItem(TOUR_KEY);
    return value === 'dismissed' || value === 'skipped' || value === 'completed' ? value : null;
  } catch {
    return null;
  }
};

export const hasSeenTour = () => getTourOutcome() !== null;

export const recordTourOutcome = (outcome: TourOutcome) => {
  try {
    localStorage.setItem(TOUR_KEY, outcome);
  } catch {
    // Storage can be unavailable in private browsing. Keep onboarding usable.
  }
};

interface DemoModalProps {
  isOpen: boolean;
  onComplete: () => void;
  onDismiss: () => void;
}

const STEPS = [
  {
    eyebrow: 'Conversation',
    title: 'Talk through what is on your mind',
    description: 'Ask a question in your own words. AskMukthiGuru offers reflective guidance rooted in the teachings; it does not replace professional care.',
    icon: MessageCircle,
    action: 'Talk now',
    to: '/chat?source=landing-tour&path=talk-now',
  },
  {
    eyebrow: 'Calm',
    title: 'Take a short pause when you need one',
    description: 'Serene Mind is a guided, three-minute breathing practice for settling into your next conversation, meeting, or rest.',
    icon: HeartPulse,
    action: 'Start 3-minute calm',
    to: '/practices/serene-mind?source=landing-tour&path=three-minute-calm',
  },
  {
    eyebrow: 'Practice',
    title: 'Return to a wisdom practice over time',
    description: 'Explore practices at your pace. Choose one that fits today, then come back whenever you want a steadier rhythm.',
    icon: Compass,
    action: 'Explore wisdom practices',
    to: '/practices?source=landing-tour&path=wisdom-practice',
  },
] as const;

export const DemoModal = ({ isOpen, onComplete, onDismiss }: DemoModalProps) => {
  const { t } = useTranslation();
  const [stepIndex, setStepIndex] = useState(0);
  const completionRef = useRef(false);
  const step = STEPS[stepIndex];
  const StepIcon = step.icon;
  const isLastStep = stepIndex === STEPS.length - 1;

  useEffect(() => {
    if (isOpen) {
      setStepIndex(0);
      completionRef.current = false;
    }
  }, [isOpen]);

  const dismiss = () => {
    if (!completionRef.current) onDismiss();
  };

  const complete = () => {
    completionRef.current = true;
    onComplete();
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && dismiss()}>
      <DialogContent
        hideClose
        className="w-[calc(100%-2rem)] max-w-xl max-h-[calc(100dvh-2rem)] overflow-y-auto rounded-2xl border-ojas/30 bg-background p-4 shadow-2xl sm:p-6"
      >
        <div className="flex items-start justify-between gap-3 pr-1">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-ojas">
              Welcome tour · {stepIndex + 1} of {STEPS.length}
            </p>
            <DialogTitle className="mt-2 text-2xl leading-tight sm:text-3xl">
              {step.title}
            </DialogTitle>
          </div>
          <button
            type="button"
            onClick={dismiss}
            aria-label="Close tour"
            className="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-full border border-border bg-muted/50 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        <DialogDescription className="mt-3 max-w-2xl text-base leading-relaxed text-muted-foreground">
          {step.description}
        </DialogDescription>

        <div className="mt-6 rounded-xl border border-ojas/20 bg-ojas/5 p-4 sm:p-5">
          <div className="flex items-center gap-3 text-foreground">
            <span className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-ojas/15 text-ojas">
              <StepIcon className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <p className="font-semibold">{step.eyebrow}</p>
              <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                Pick this path now or finish the tour first. Your choice stays available from navigation later.
              </p>
            </div>
          </div>
          <Link
            to={step.to}
            onClick={complete}
            className="mt-5 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-lg bg-ojas px-4 py-2.5 font-semibold text-primary-foreground transition-colors hover:bg-ojas-light focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 sm:w-auto"
          >
            {step.action}
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </div>

        <div className="mt-6" aria-label={`Tour progress: step ${stepIndex + 1} of ${STEPS.length}`}>
          <div className="flex gap-2" aria-hidden="true">
            {STEPS.map((item, index) => (
              <span
                key={item.eyebrow}
                className={`h-1.5 flex-1 rounded-full ${index <= stepIndex ? 'bg-ojas' : 'bg-muted'}`}
              />
            ))}
          </div>
          <span className="sr-only">Step {stepIndex + 1} of {STEPS.length}</span>
        </div>

        <div className="mt-5 flex flex-col-reverse gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
          <button
            type="button"
            onClick={dismiss}
            className="min-h-11 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            Skip tour
          </button>
          <div className="grid grid-cols-2 gap-2 sm:flex">
            <button
              type="button"
              onClick={() => setStepIndex((index) => Math.max(0, index - 1))}
              disabled={stepIndex === 0}
              aria-label="Back to previous tour step"
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-border px-3 py-2 text-sm font-medium transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-45"
            >
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
              Back
            </button>
            {isLastStep ? (
              <button
                type="button"
                onClick={complete}
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-ojas px-3 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-ojas-light focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <Check className="h-4 w-4" aria-hidden="true" />
                Finish tour
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setStepIndex((index) => Math.min(STEPS.length - 1, index + 1))}
                aria-label="Next tour step"
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-ojas px-3 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-ojas-light focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                Next
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

interface WelcomePromptProps {
  isVisible: boolean;
  onStartTour: () => void;
  onDismiss: () => void;
}

export const WelcomePrompt = ({ isVisible, onStartTour, onDismiss }: WelcomePromptProps) => {
  if (!isVisible) return null;

  return (
    <aside
      aria-label="Welcome to AskMukthiGuru"
      className="fixed inset-x-4 bottom-4 z-40 mx-auto max-w-md rounded-2xl border border-ojas/25 bg-background/95 p-4 shadow-xl backdrop-blur md:inset-x-auto md:right-4 md:mx-0"
    >
      <div className="flex gap-3">
        <Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-ojas" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-foreground">New here?</p>
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
            See three honest ways to begin: a conversation, a short calm, or a wisdom practice.
          </p>
          <button
            type="button"
            onClick={onStartTour}
            className="mt-3 inline-flex min-h-11 items-center gap-2 rounded-lg bg-ojas px-3 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-ojas-light focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            Take a three-step tour
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss welcome prompt"
          className="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          <X className="h-5 w-5" aria-hidden="true" />
        </button>
      </div>
    </aside>
  );
};
