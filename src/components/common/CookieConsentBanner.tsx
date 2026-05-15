import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Cookie, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

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
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (getConsent() === null) {
      const t = setTimeout(() => setVisible(true), 800);
      return () => clearTimeout(t);
    }
  }, []);

  const decide = (choice: Consent) => {
    try {
      localStorage.setItem(STORAGE_KEY, choice);
    } catch { /* quota — non-fatal */ }
    setVisible(false);
  };

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ y: 100, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 100, opacity: 0 }}
          transition={{ duration: 0.25 }}
          role="dialog"
          aria-label="Cookie consent"
          className="fixed bottom-4 left-4 right-4 sm:left-auto sm:right-4 sm:max-w-md z-[60] rounded-2xl border border-border/60 bg-card/95 backdrop-blur-md shadow-2xl p-4"
        >
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-full bg-ojas/12 border border-ojas/25 flex items-center justify-center flex-shrink-0">
              <Cookie className="w-4 h-4 text-ojas" />
            </div>
            <div className="flex-1 space-y-2">
              <p className="text-sm font-medium text-foreground">We respect your privacy</p>
              <p className="text-xs text-muted-foreground leading-relaxed">
                We use essential storage to keep you signed in and remember your preferences (no
                third-party trackers). See our{' '}
                <Link to="/privacy" className="text-ojas hover:underline">Privacy Policy</Link>.
              </p>
              <div className="flex gap-2 pt-1">
                <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => decide('rejected')}>
                  Reject non-essential
                </Button>
                <Button size="sm" className="h-8 text-xs bg-ojas hover:bg-ojas-light text-primary-foreground" onClick={() => decide('accepted')}>
                  Accept all
                </Button>
              </div>
            </div>
            <button
              onClick={() => decide('rejected')}
              className="p-1 rounded hover:bg-muted text-muted-foreground"
              aria-label="Dismiss"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
