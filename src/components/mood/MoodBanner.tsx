import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MoodCheckIn } from './MoodCheckIn';

const SNOOZE_KEY = 'askmukthiguru_mood_snooze';
const SNOOZE_MS = 24 * 60 * 60 * 1000;
const RECENT_MS = 24 * 60 * 60 * 1000;

export const MoodBanner = () => {
  const { t } = useTranslation();
  const [showBanner, setShowBanner] = useState(false);
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    const snooze = parseInt(localStorage.getItem(SNOOZE_KEY) ?? '0', 10) || 0;
    const lastMood = parseInt(localStorage.getItem('askmukthiguru_last_mood_checkin') ?? '0', 10) || 0;
    const now = Date.now();
    if (now - snooze > SNOOZE_MS && now - lastMood > RECENT_MS) {
      setShowBanner(true);
    }
  }, []);

  const handleSnooze = () => {
    localStorage.setItem(SNOOZE_KEY, String(Date.now()));
    setShowBanner(false);
  };

  const handleCheckIn = () => {
    setShowBanner(false);
    setShowModal(true);
  };

  if (!showBanner) return null;

  return (
    <>
      <div className="mx-auto max-w-3xl mt-2 mb-1 px-3">
        <div className="glass-card rounded-full border border-ojas/25 bg-ojas/5 px-4 py-2 flex items-center justify-between gap-3">
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
      <MoodCheckIn isOpen={showModal} onClose={() => setShowModal(false)} />
    </>
  );
};
