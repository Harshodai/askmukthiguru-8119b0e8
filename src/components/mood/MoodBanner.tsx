import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
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

export const MoodBanner = () => {
  const { t } = useTranslation();
  const [showBanner, setShowBanner] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const navigate = useNavigate();
  const [journey, setJourney] = useState<JourneyState | null>(() => getJourney());

  useEffect(() => {
    const snooze = parseInt(localStorage.getItem(SNOOZE_KEY) ?? '0', 10) || 0;
    const lastMood = parseInt(localStorage.getItem('askmukthiguru_last_mood_checkin') ?? '0', 10) || 0;
    const now = Date.now();
    if (now - snooze > SNOOZE_MS && now - lastMood > RECENT_MS) {
      setShowBanner(true);
    }
  }, []);

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
        <div className="relative z-10 mx-auto max-w-3xl mt-2 mb-1 px-3" data-testid="journey-resume">
          <div className="rounded-full border border-ojas/30 bg-card shadow-sm px-4 py-2 flex items-center justify-between gap-3">
            <p className="text-xs sm:text-sm text-foreground flex-1">{resume.label}</p>
            <div className="flex items-center gap-2">
              <button
                onClick={resume.go}
                data-testid="journey-resume-cta"
                className="px-3 py-1 rounded-full bg-ojas text-primary-foreground text-xs font-semibold hover:bg-ojas-light transition-colors"
              >
                {resume.cta}
              </button>
              <button
                onClick={() => { skipJourney(); setJourney(getJourney()); }}
                className="px-3 py-1 rounded-full text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                {t('mood.skipJourney', 'Skip for today')}
              </button>
            </div>
          </div>
        </div>
      )}
      {showBanner && (
      <div className="relative z-10 mx-auto max-w-3xl mt-2 mb-1 px-3">
        <div className="rounded-full border border-ojas/30 bg-card shadow-sm px-4 py-2 flex items-center justify-between gap-3">
          <p className="text-xs sm:text-sm text-foreground flex-1">{t('mood.bannerTitle')}</p>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCheckIn}
              className="px-3 py-1 rounded-full bg-ojas text-primary-foreground text-xs font-semibold hover:bg-ojas-light transition-colors"
            >
              {t('mood.bannerCta')}
            </button>
            <button
              onClick={handleSnooze}
              className="px-3 py-1 rounded-full text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              {t('mood.bannerSnooze')}
            </button>
          </div>
        </div>
      </div>
      )}
      <MoodCheckIn isOpen={showModal} onClose={() => setShowModal(false)} />
    </>
  );
};
