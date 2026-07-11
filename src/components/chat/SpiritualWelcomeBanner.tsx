import { useTranslation } from 'react-i18next';
import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, X } from 'lucide-react';
import {
  getDailySpiritualLine,
  isWelcomeDismissed,
  dismissWelcome,
} from '@/lib/welcomeState';

interface SpiritualWelcomeBannerProps {
  onDismiss?: () => void;
}

export function SpiritualWelcomeBanner({ onDismiss }: SpiritualWelcomeBannerProps) {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);
  const [line, setLine] = useState('');

  useEffect(() => {
    if (!isWelcomeDismissed()) {
      setLine(getDailySpiritualLine());
      setVisible(true);
    }
  }, []);

  const handleDismiss = () => {
    setVisible(false);
    dismissWelcome();
    onDismiss?.();
  };

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: -12, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -12, scale: 0.96 }}
          transition={{ type: 'spring', stiffness: 200, damping: 20 }}
          className="relative group rounded-2xl border border-ojas/20 bg-gradient-to-br from-ojas/[0.06] via-ojas/[0.03] to-transparent backdrop-blur-sm px-5 py-4"
        >
          <button
            type="button"
            onClick={handleDismiss}
            className="absolute top-2 right-2 p-1 rounded-full opacity-0 group-hover:opacity-100 hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-all"
            aria-label={t('common.dismiss')}
          >
            <X className="w-3.5 h-3.5" />
          </button>
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-full bg-ojas/10 flex items-center justify-center flex-shrink-0 mt-0.5">
              <Sparkles className="w-4 h-4 text-ojas" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-ojas/80 mb-1">
                {t('chat.todaysLine')}
              </p>
              <p className="text-[15px] font-serif italic leading-relaxed text-foreground/85">
                &ldquo;{line}&rdquo;
              </p>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

