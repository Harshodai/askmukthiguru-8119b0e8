import { useTranslation } from 'react-i18next';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Cookie, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Capacitor } from '@capacitor/core';
import { DISCLAIMER_ACCEPTED_EVENT, isDisclaimerAccepted } from './SafetyDisclaimer';

const STORAGE_KEY = 'askmukthiguru_consent_v1';

type Consent = 'accepted' | 'rejected';

export const getConsent = (): Consent | null => {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === 'accepted' || v === 'rejected' ? v : null;
  } catch {
    return null;
  }
};

/**
 * DPDP (India) + GDPR friendly consent banner. Persists choice in localStorage.
 * Only shows essential-cookies notice — we don't run third-party trackers.
 */
export const CookieConsentBanner = () => {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);
  const bannerRef = useRef<HTMLDivElement | null>(null);

  // The banner is fixed to the bottom edge, so on a phone it sits on top of
  // whatever the page puts there (e.g. the "Forgot your password?" link on
  // /auth) and a seeker cannot scroll that control clear of it. While it is
  // showing, reserve its height as bottom padding on <body> so the page can
  // always scroll past it.
  useEffect(() => {
    if (!visible) return;
    const el = bannerRef.current;
    if (!el) return;
    const root = document.documentElement;
    const sync = () => root.style.setProperty('--cookie-banner-h', `${el.offsetHeight + 24}px`);
    sync();
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(sync) : null;
    observer?.observe(el);
    return () => {
      observer?.disconnect();
      root.style.removeProperty('--cookie-banner-h');
    };
  }, [visible]);

  // Wait for the safety notice. Showing both at once stacked three first-run
  // prompts on a new seeker (faculty review P2).
  useEffect(() => {
    if (getConsent() !== null) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const show = () => {
      timer = setTimeout(() => setVisible(true), 800);
    };
    if (isDisclaimerAccepted()) {
      show();
      return () => clearTimeout(timer);
    }
    window.addEventListener(DISCLAIMER_ACCEPTED_EVENT, show, { once: true });
    return () => {
      window.removeEventListener(DISCLAIMER_ACCEPTED_EVENT, show);
      clearTimeout(timer);
    };
  }, []);

  const decide = (choice: Consent) => {
    try {
      localStorage.setItem(STORAGE_KEY, choice);
    } catch { /* quota — non-fatal */ }
    setVisible(false);
  };

  if (Capacitor.isNativePlatform()) return null;

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          ref={bannerRef}
          initial={{ y: 100, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 100, opacity: 0 }}
          transition={{ duration: 0.25 }}
          role="dialog"
          aria-label={t('common.cookiesConsent')}
          className={`fixed bottom-[calc(0.75rem+env(safe-area-inset-bottom))] sm:bottom-[calc(1rem+env(safe-area-inset-bottom))] left-3 right-3 sm:left-auto sm:right-4 sm:max-w-sm md:max-w-md z-[60] rounded-xl border border-border/60 bg-card/95 backdrop-blur-md shadow-lg p-3 sm:p-4`}
        >
          <div className="flex items-start gap-2.5">
            <div className="hidden sm:flex w-9 h-9 rounded-full bg-ojas/12 border border-ojas/25 items-center justify-center flex-shrink-0">
              <Cookie className="w-4 h-4 text-ojas" />
            </div>
            <div className="flex-1 space-y-1.5">
              <p className="text-sm font-medium text-foreground">
                {t('common.essentialCookies')}
              </p>
              <p className="text-sm text-muted-foreground leading-snug">
                {t('common.noThirdParty')}{' '}
                <Link to="/privacy" className="text-primary-foreground font-semibold underline underline-offset-2">{t('common.privacy')}</Link>.
              </p>
              <div className="flex gap-2 pt-0.5">
                <Button size="sm" variant="outline" className="min-h-[44px] text-sm px-4" onClick={() => decide('rejected')}>
                  {t('common.reject') === 'common.reject' ? 'Reject' : t('common.reject')}
                </Button>
                <Button size="sm" className="min-h-[44px] text-sm px-4 bg-ojas hover:bg-ojas-dark !text-primary-foreground" onClick={() => decide('accepted')}>
                  {t('common.accept') === 'common.accept' ? 'Accept' : t('common.accept')}
                </Button>
              </div>
            </div>
            <button
              onClick={() => decide('rejected')}
              className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg hover:bg-muted text-muted-foreground"
              aria-label={t('common.dismiss') === 'common.dismiss' ? 'Dismiss' : t('common.dismiss')}
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>

        </motion.div>
      )}
    </AnimatePresence>
  );
};
