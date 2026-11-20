import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Sun, Compass, X } from 'lucide-react';
import { MoodCheckIn } from './MoodCheckIn';
import { practices } from '@/lib/practicesContent';
import {
  JOURNEY_EVENT,
  completeStep,
  getJourney,
  nextPendingStep,
  skipJourney,
  type JourneyState,
} from '@/lib/dailyJourney';

const SNOOZE_KEY = 'askmukthiguru_mood_snooze';
const SNOOZE_MS = 24 * 60 * 60 * 1000;
const RECENT_MS = 24 * 60 * 60 * 1000;

export interface MoodBannerProps {
  isLandingMode?: boolean;
}

export const MoodBanner = ({ isLandingMode = true }: MoodBannerProps) => {
  const { t } = useTranslation();
  const [showBanner, setShowBanner] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const navigate = useNavigate();
  const [journey, setJourney] = useState<JourneyState | null>(() => getJourney());

  useEffect(() => {
    const today = new Date().toISOString().slice(0, 10);
    const checkedInToday = localStorage.getItem(`askmukthiguru_daily_arrival_${today}`);
    const snooze = parseInt(localStorage.getItem(SNOOZE_KEY) ?? '0', 10) || 0;
    const lastMood = parseInt(localStorage.getItem('askmukthiguru_last_mood_checkin') ?? '0', 10) || 0;
    const now = Date.now();
    if (!checkedInToday && now - snooze > SNOOZE_MS && now - lastMood > RECENT_MS) {
      setShowBanner(true);
    }
  }, []);

  const handleModalClose = () => {
    const today = new Date().toISOString().slice(0, 10);
    try {
      localStorage.setItem(`askmukthiguru_daily_arrival_${today}`, 'true');
    } catch { /* storage quota */ }
    setShowModal(false);
  };

  // A completed practice (the check-in no longer fires this event) finishes that step.
  useEffect(() => {
    const onPractice = () => setJourney(completeStep('practice'));
    const onCheckIn = () => setJourney(getJourney());
    window.addEventListener('askmukthiguru:meditation_completed', onPractice);
    window.addEventListener('askmukthiguru:mood_checkin', onCheckIn);
    window.addEventListener(JOURNEY_EVENT, onCheckIn);
    return () => {
      window.removeEventListener(JOURNEY_EVENT, onCheckIn);
      window.removeEventListener('askmukthiguru:meditation_completed', onPractice);
      window.removeEventListener('askmukthiguru:mood_checkin', onCheckIn);
    };
  }, []);

  // In active chat mode, never display check-in or journey banners so conversation remains serene
  if (!isLandingMode) {
    return null;
  }

  const pendingStep = nextPendingStep(journey);
  const pendingPractice =
    pendingStep === 'practice' ? practices.find((p) => p.slug === journey?.practiceSlug) : undefined;

  // Each pending step names its own action. Nothing here marks a step done; the
  // step's own action (playing a clip, finishing a practice, saving a note) does.
  const resume = (() => {
    if (!journey || !pendingStep) return null;
    if (pendingStep === 'teaching') {
      const ask = t('mood.teachingAsk', 'I am feeling {{mood}} today. Which teaching can help me?', {
        mood: t(`mood.${journey.mood}`, journey.mood).toLowerCase(),
      });
      return {
        label: t('mood.resumeTeaching', "Continue today: hear one teaching"),
        cta: t('mood.openTeaching', 'Ask for a teaching'),
        go: () => navigate(`/chat?q=${encodeURIComponent(ask)}`),
      };
    }
    if (pendingStep === 'practice' && pendingPractice) {
      return {
        label: t('mood.resumePractice', 'Continue today: {{title}}', { title: pendingPractice.title }),
        cta: t('mood.startPractice'),
        go: () => navigate(`/practices/${pendingPractice.slug}`),
      };
    }
    if (pendingStep === 'reflection') {
      return {
        label: t('mood.resumeReflection', 'Continue today: write a short reflection'),
        cta: t('mood.openReflection', 'Write a note'),
        go: () => navigate('/profile?tab=memory'),
      };
    }
    return null;
  })();

  const handleSnooze = () => {
    localStorage.setItem(SNOOZE_KEY, String(Date.now()));
    setShowBanner(false);
  };

  const handleCheckIn = () => {
    setShowBanner(false);
    setShowModal(true);
  };

  return (
    <>
      {!showBanner && !showModal && resume && (
        <aside
          data-testid="journey-resume"
          role="region"
          aria-label={t('mood.dailyJourney', 'Daily Journey')}
          className="w-full border-b border-ojas/20 bg-gradient-to-r from-ojas/10 via-background/90 to-ojas/5 px-3 py-2 sm:px-6 transition-all"
        >
          <div className="max-w-3xl mx-auto flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5 min-w-0 flex-1">
              <div className="w-6 h-6 rounded-lg bg-ojas/15 border border-ojas/30 flex items-center justify-center shrink-0">
                <Compass className="w-3.5 h-3.5 text-ojas" aria-hidden="true" />
              </div>
              <p className="text-xs sm:text-sm font-medium leading-tight text-foreground/90 sm:truncate">{resume.label}</p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={resume.go}
                data-testid="journey-resume-cta"
                className="h-11 sm:h-8 px-4 rounded-lg bg-ojas text-primary-foreground text-xs font-semibold hover:bg-ojas-dark shadow-xs transition-colors"
              >
                {resume.cta}
              </button>
              <button
                type="button"
                onClick={() => { skipJourney(); setJourney(getJourney()); }}
                className="h-11 sm:h-8 px-3 rounded-lg text-xs text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors"
              >
                {t('mood.skipJourney', 'Skip for today')}
              </button>
            </div>
          </div>
        </aside>
      )}

      {showBanner && (
        <aside
          role="region"
          aria-label={t('mood.bannerTitle', 'How are you arriving today?')}
          className="w-full border-b border-ojas/20 bg-gradient-to-r from-ojas/10 via-background/90 to-ojas/5 px-3 py-2 sm:px-6 transition-all"
        >
          <div className="max-w-3xl mx-auto flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5 min-w-0 flex-1">
              <div className="w-6 h-6 rounded-lg bg-ojas/15 border border-ojas/30 flex items-center justify-center shrink-0">
                <Sun className="w-3.5 h-3.5 text-ojas" aria-hidden="true" />
              </div>
              <p className="text-xs sm:text-sm font-medium text-foreground/90 truncate">
                {t('mood.bannerTitle', 'How are you arriving today?')}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={handleCheckIn}
                className="h-11 sm:h-8 px-4 rounded-lg bg-ojas text-primary-foreground text-xs font-semibold hover:bg-ojas-dark shadow-xs transition-colors"
              >
                {t('mood.bannerCta', 'Check in')}
              </button>
              <button
                type="button"
                onClick={handleSnooze}
                aria-label={t('mood.bannerSnooze', 'Not now')}
                title={t('mood.bannerSnooze', 'Not now')}
                className="inline-flex h-11 w-11 sm:h-8 sm:w-8 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground hover:bg-foreground/[0.07] transition-colors"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          </div>
        </aside>
      )}
      <MoodCheckIn isOpen={showModal} onClose={handleModalClose} />
    </>
  );
};
