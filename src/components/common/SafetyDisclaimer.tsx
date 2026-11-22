import { useTranslation } from 'react-i18next';
import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Heart, AlertCircle, X } from 'lucide-react';
import { CrisisLines } from '@/components/common/CrisisLines';
import { INDIA_CRISIS_LINES } from '@/lib/crisisHelplines';
import { useDialogFocus } from '@/hooks/useDialogFocus';
import { focusWhenFree } from '@/lib/focusWhenFree';

const DISCLAIMER_KEY = 'askmukthiguru_disclaimer_accepted';
/** Fired once the seeker accepts, so later first-run prompts can follow it
 *  instead of stacking on top of it (faculty review P2, first-run prompts). */
export const DISCLAIMER_ACCEPTED_EVENT = 'askmukthiguru:disclaimer-accepted';

export const isDisclaimerAccepted = (): boolean => {
  try {
    return Boolean(localStorage.getItem(DISCLAIMER_KEY));
  } catch {
    return true;
  }
};

export const SafetyDisclaimer = () => {
  const { t } = useTranslation();
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    if (!isDisclaimerAccepted()) {
      setIsVisible(true);
    }
  }, []);

  const handleAccept = () => {
    try {
      localStorage.setItem(DISCLAIMER_KEY, 'true');
    } catch { /* private mode — still let them in */ }
    setIsVisible(false);
    window.dispatchEvent(new Event(DISCLAIMER_ACCEPTED_EVENT));
    // The focused button unmounts with the notice; without this focus falls to
    // <body> (A11Y-08). Prefer the chat composer, else the main landmark.
    focusWhenFree(() => {
      const composer = document.querySelector<HTMLElement>('textarea[name="message"]');
      if (composer) return composer;
      const main = document.querySelector<HTMLElement>('main');
      if (main && !main.hasAttribute('tabindex')) main.setAttribute('tabindex', '-1');
      return main;
    }, { waitForFree: true }); // the notice animates out; focus is free once it is gone
  };

  // Keyboard and screen-reader users land on the notice's action, Tab stays
  // inside the notice, and Escape closes it like any other dialog.
  const acceptRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useDialogFocus<HTMLDivElement>(isVisible, {
    initialFocus: acceptRef,
    onEscape: handleAccept,
  });

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[100] flex items-center justify-center p-4"
        >
          <div className="absolute inset-0 bg-background/95 backdrop-blur-xl" />

          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            ref={dialogRef}
            className="relative z-10 w-full max-w-md"
            role="dialog"
            aria-modal="true"
            aria-labelledby="safety-disclaimer-title"
            aria-describedby="safety-disclaimer-description"
          >
            <div className="glass-card p-6 md:p-8 shadow-xl">
              <button
                type="button"
                onClick={handleAccept}
                aria-label={t('common.close')}
                title={t('common.close')}
                className="absolute top-4 right-4 p-2 rounded-full hover:bg-muted transition-colors opacity-50 hover:opacity-100"
              >
                <X className="w-4 h-4 text-muted-foreground" />
              </button>

              <div className="flex justify-center mb-6">
                <div className="w-16 h-16 rounded-full bg-ojas/20 border border-ojas/30 flex items-center justify-center shadow-md">
                  <Heart className="w-8 h-8 text-ojas" />
                </div>
              </div>

              <h2 id="safety-disclaimer-title" className="text-2xl font-bold text-center text-foreground mb-4">
                {t('common.welcomeSeeker')}
              </h2>

              <p id="safety-disclaimer-description" className="text-muted-foreground text-center leading-relaxed mb-6">
                {t('common.disclaimerDesc')}
              </p>

              <div className="bg-muted/40 border border-border/60 rounded-xl p-4 mb-5 text-left">
                <div className="flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-ojas flex-shrink-0 mt-0.5" />
                  <div className="text-xs sm:text-sm">
                    <p className="font-semibold text-foreground mb-1">{t('common.importantNotice')}</p>
                    <p className="text-muted-foreground leading-relaxed">
                      {t('common.disclaimerWarning')}
                    </p>
                  </div>
                </div>
              </div>

              <div className="text-xs text-muted-foreground text-center mb-6 bg-muted/20 border border-border/40 rounded-lg p-3">
                <p className="font-medium mb-1.5 text-foreground/80">{t('common.crisisSupport')}</p>
                <CrisisLines lines={INDIA_CRISIS_LINES} />
              </div>

              <button
                ref={acceptRef}
                type="button"
                onClick={handleAccept}
                className="w-full py-3 bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-semibold rounded-full transition-all duration-300 hover:scale-[1.01] shadow-md min-h-[48px]"
              >
                {t('common.beginJourney')}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
