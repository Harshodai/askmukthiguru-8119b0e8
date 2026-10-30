import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { MoodCheckIn } from './MoodCheckIn';
import { practices } from '@/lib/practicesContent';
import { completeStep, getJourney, skipJourney, type JourneyState } from '@/lib/dailyJourney';

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
    return () => {
      window.removeEventListener('askmukthiguru:meditation_completed', onPractice);
      window.removeEventListener('askmukthiguru:mood_checkin', onCheckIn);
    };
  }, []);

  const pendingPractice =
    journey && !journey.skipped && !journey.done.practice && journey.practiceSlug
      ? practices.find((p) => p.slug === journey.practiceSlug)
      : undefined;

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
      {!showBanner && !showModal && pendingPractice && (
        <div className="relative z-10 mx-auto max-w-3xl mt-2 mb-1 px-3" data-testid="journey-resume">
          <div className="rounded-full border border-ojas/30 bg-card shadow-sm px-4 py-2 flex items-center justify-between gap-3">
            <p className="text-xs sm:text-sm text-foreground flex-1">
              {t('mood.resumePractice', 'Continue today: {{title}}', { title: pendingPractice.title })}
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => navigate(`/practices/${pendingPractice.slug}`)}
                className="px-3 py-1 rounded-full bg-ojas text-primary-foreground text-xs font-semibold hover:bg-ojas-light transition-colors"
              >
                {t('mood.startPractice')}
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
