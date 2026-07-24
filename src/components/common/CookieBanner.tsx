import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Cookie } from 'lucide-react';
import { Button } from '@/components/ui/button';

const COOKIE_CONSENT_KEY = 'askmukthiguru_cookie_consent';
const COOKIE_CONSENT_VERSION = '2026-07-24';

interface CookieConsent {
  accepted: boolean;
  version: string;
  timestamp: number;
}

export function CookieBanner() {
  const { t } = useTranslation();
  const [show, setShow] = useState(false);

  useEffect(() => {
    const consent = getConsent();
    if (!consent || consent.version !== COOKIE_CONSENT_VERSION) {
      setShow(true);
    }
  }, []);

  const getConsent = (): CookieConsent | null => {
    try {
      const stored = localStorage.getItem(COOKIE_CONSENT_KEY);
      if (stored) {
        return JSON.parse(stored);
      }
    } catch {
      // Ignore parse errors
    }
    return null;
  };

  const handleAccept = (accepted: boolean) => {
    const consent: CookieConsent = {
      accepted,
      version: COOKIE_CONSENT_VERSION,
      timestamp: Date.now(),
    };
    localStorage.setItem(COOKIE_CONSENT_KEY, JSON.stringify(consent));
    setShow(false);
    
    // If accepted, initialize analytics
    if (accepted) {
      initializeAnalytics();
    }
  };

  if (!show) return null;

  return (
    <div
      className="fixed bottom-4 left-4 right-4 sm:bottom-6 sm:left-6 sm:right-6 z-50 max-w-md mx-auto animate-slide-up"
      role="dialog"
      aria-label="Cookie consent"
    >
      <div className="bg-card border border-border/60 rounded-2xl shadow-2xl p-4 sm:p-6 backdrop-blur-xl">
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 w-10 h-10 rounded-xl bg-ojas/10 flex items-center justify-center text-ojas">
            <Cookie className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-foreground">
              {t('cookieBanner.description', 'We use cookies to improve your experience and analyze site traffic. By clicking "Accept", you consent to our use of cookies.')}
            </p>
          </div>
          <button
            onClick={() => handleAccept(false)}
            className="flex-shrink-0 p-1 text-muted-foreground/60 hover:text-foreground transition-colors"
            aria-label="Dismiss"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex flex-col sm:flex-row gap-3 mt-4 pt-4 border-t border-border/50">
          <Button
            variant="outline"
            className="flex-1"
            onClick={() => handleAccept(false)}
          >
            {t('cookieBanner.decline', 'Decline')}
          </Button>
          <Button
            className="flex-1 bg-ojas hover:bg-ojas-light"
            onClick={() => handleAccept(true)}
          >
            {t('cookieBanner.accept', 'Accept')}
          </Button>
        </div>
      </div>
    </div>
  );
}

function initializeAnalytics() {
  // Initialize Google Analytics / Plausible / other analytics
  // This is a placeholder - actual implementation would load the analytics script
  if (typeof window !== 'undefined') {
    // Example for Google Analytics (gtag)
    // window.dataLayer = window.dataLayer || [];
    // function gtag(){window.dataLayer.push(arguments);}
    // gtag('js', new Date());
    // gtag('config', 'GA_MEASUREMENT_ID');
    
    // Example for Plausible
    // const script = document.createElement('script');
    // script.defer = true;
    // script.dataset.domain = 'askmukthiguru.com';
    // script.src = 'https://plausible.io/js/script.js';
    // document.head.appendChild(script);
  }
}