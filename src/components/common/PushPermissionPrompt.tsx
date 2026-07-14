import { useTranslation } from 'react-i18next';
import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Bell, X } from 'lucide-react';
import { Capacitor } from '@capacitor/core';
import { useWebPush } from '@/hooks/useWebPush';
import { Button } from '@/components/ui/button';

const DISMISS_KEY = 'askmukthiguru_push_prompt_dismissed_at';
const COOLDOWN_MS = 7 * 24 * 60 * 60 * 1000;

export const PushPermissionPrompt = () => {
  const { t } = useTranslation();
  const { supported, permission, subscribed, subscribe, loading } = useWebPush();
  const [open, setOpen] = useState(false);
  const isNative = Capacitor.isNativePlatform();

  useEffect(() => {
    if (isNative) return;
    if (!supported || subscribed || permission === 'denied' || permission === 'unsupported') return;
    const last = Number(localStorage.getItem(DISMISS_KEY) || '0');
    if (Date.now() - last < COOLDOWN_MS) return;
    const timer = setTimeout(() => setOpen(true), 4000);
    return () => clearTimeout(timer);
  }, [supported, subscribed, permission, isNative]);

  if (isNative) return null;

  const dismiss = () => {
    localStorage.setItem(DISMISS_KEY, String(Date.now()));
    setOpen(false);
  };

  const enable = async () => {
    const ok = await subscribe();
    if (ok) setOpen(false);
    else dismiss();
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 20 }}
          className="fixed bottom-4 right-4 z-50 max-w-sm rounded-2xl border border-ojas/30 bg-card/95 backdrop-blur-md shadow-xl p-4"
          role="dialog"
          aria-label={t('common.pushPromptAria')}
        >
          <button
            type="button"
            onClick={dismiss}
            className="absolute top-2 right-2 text-muted-foreground hover:text-foreground"
            aria-label={t('common.dismiss')}
          >
            <X className="w-4 h-4" />
          </button>
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-full bg-ojas/15 flex items-center justify-center flex-shrink-0">
              <Bell className="w-5 h-5 text-ojas" />
            </div>
            <div className="flex-1">
              <p className="font-serif text-sm font-medium text-foreground">
                {t('common.pushPromptTitle')}
              </p>
              <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                {t('common.pushPromptDesc')}
              </p>
              <div className="flex gap-2 mt-3">
                <Button size="sm" variant="ghost" onClick={dismiss} className="text-xs">
                  {t('common.notNow')}
                </Button>
                <Button size="sm" onClick={enable} disabled={loading} className="bg-ojas hover:bg-ojas-light text-xs">
                  {loading ? t('common.enabling') : t('common.enable')}
                </Button>
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
