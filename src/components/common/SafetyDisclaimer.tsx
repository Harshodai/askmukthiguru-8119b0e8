import { useTranslation } from 'react-i18next';
import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Heart, AlertCircle, X } from 'lucide-react';

const DISCLAIMER_KEY = 'askmukthiguru_disclaimer_accepted';

export const SafetyDisclaimer = () => {
  const { t } = useTranslation();
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const accepted = localStorage.getItem(DISCLAIMER_KEY);
    if (!accepted) {
      setIsVisible(true);
    }
  }, []);

  const handleAccept = () => {
    localStorage.setItem(DISCLAIMER_KEY, 'true');
    setIsVisible(false);
  };

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
            className="relative z-10 w-full max-w-md"
          >
            <div className="glass-card p-6 md:p-8 shadow-xl">
              <button
                onClick={handleAccept}
                className="absolute top-4 right-4 p-2 rounded-full hover:bg-muted transition-colors opacity-50 hover:opacity-100"
              >
                <X className="w-4 h-4 text-muted-foreground" />
              </button>

              <div className="flex justify-center mb-6">
                <div className="w-16 h-16 rounded-full bg-ojas/20 border border-ojas/30 flex items-center justify-center shadow-md">
                  <Heart className="w-8 h-8 text-ojas" />
                </div>
              </div>

              <h2 className="text-2xl font-bold text-center text-foreground mb-4">
                {t('common.welcomeSeeker')}
              </h2>

              <p className="text-muted-foreground text-center leading-relaxed mb-6">
                {t('common.disclaimerDesc')}
              </p>

              <div className="bg-destructive/10 border border-destructive/20 rounded-xl p-4 mb-6">
                <div className="flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0 mt-0.5" />
                  <div className="text-sm">
                    <p className="font-medium text-destructive mb-1">{t('common.importantNotice')}</p>
                    <p className="text-muted-foreground">
                      {t('common.disclaimerWarning')}
                    </p>
                  </div>
                </div>
              </div>

              <div className="text-xs text-muted-foreground text-center mb-6 bg-muted/30 rounded-lg p-3">
                <p className="font-medium mb-1">{t('common.crisisSupport')}</p>
                <p>{t('common.crisisNumbers')}</p>
              </div>

              <button
                onClick={handleAccept}
                className="w-full py-3 bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-medium rounded-full transition-all duration-300 hover:scale-[1.02] shadow-md"
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
