import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles, X, ChevronDown, ChevronUp, ShieldCheck, Brain } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { memoryApi, MemoryApiError } from '@/lib/memoryApi';
import { useToast } from '@/hooks/use-toast';

export const MEMORY_BANNER_DISMISSED_KEY = 'askmukthiguru_memory_banner_dismissed';

interface MemoryConsentBannerProps {
  hasConsent: boolean | null;
  onConsentChange: (granted: boolean) => void;
  isIncognito?: boolean;
  isAuthenticated: boolean;
}

export const MemoryConsentBanner: React.FC<MemoryConsentBannerProps> = ({
  hasConsent,
  onConsentChange,
  isIncognito = false,
  isAuthenticated,
}) => {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [dismissed, setDismissed] = useState<boolean>(true);
  const [expanded, setExpanded] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);

  useEffect(() => {
    // Check if dismissed previously
    if (!isAuthenticated || isIncognito || hasConsent === true) {
      setDismissed(true);
      return;
    }
    const isDismissed = localStorage.getItem(MEMORY_BANNER_DISMISSED_KEY) === '1';
    setDismissed(isDismissed);
  }, [hasConsent, isAuthenticated, isIncognito]);

  if (!isAuthenticated || isIncognito || hasConsent === true || dismissed) {
    return null;
  }

  const handleEnable = async () => {
    setSubmitting(true);
    try {
      await memoryApi.recordConsent(true);
      localStorage.removeItem(MEMORY_BANNER_DISMISSED_KEY);
      toast({
        title: t('chat.memoryBanner.toastEnabledTitle', 'Personal Memory Enabled'),
        description: t(
          'chat.memoryBanner.toastEnabledDesc',
          'Mukthi Guru will now remember key reflections to tailor future guidance.'
        ),
      });
      onConsentChange(true);
    } catch (err) {
      const msg = err instanceof MemoryApiError ? err.message : 'Could not enable personal memory. Please try again.';
      toast({
        title: t('memory.couldNotSave', 'Could not save setting'),
        description: msg,
        variant: 'destructive',
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleDismiss = () => {
    localStorage.setItem(MEMORY_BANNER_DISMISSED_KEY, '1');
    setDismissed(true);
  };

  return (
    <div
      role="region"
      aria-label={t('chat.memoryBanner.title', 'Personalized Spiritual Memory')}
      className="mx-3 sm:mx-6 lg:mx-8 mb-3 p-4 rounded-2xl border border-ojas/25 bg-gradient-to-r from-ojas/10 via-ojas/5 to-background backdrop-blur-sm shadow-sm relative transition-all"
      data-testid="memory-consent-banner"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 p-2 rounded-xl bg-ojas/15 text-ojas flex-shrink-0">
            <Sparkles className="w-4 h-4" />
          </div>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5 font-serif">
                {t('chat.memoryBanner.title', 'Personalized Spiritual Memory')}
              </h3>
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-ojas/10 text-ojas">
                <ShieldCheck className="w-3 h-3" /> Private
              </span>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed max-w-2xl">
              {t(
                'chat.memoryBanner.description',
                'Allow Mukthi Guru to remember your key reflections and spiritual practices across conversations to deepen your guidance. Your data is private, encrypted, and never used to train public AI models.'
              )}
            </p>

            {expanded && (
              <div className="mt-2.5 pt-2.5 border-t border-border/40 text-xs text-muted-foreground space-y-1.5 animate-in fade-in duration-200">
                <p>
                  {t(
                    'chat.memoryBanner.learnMoreDetails',
                    'When enabled, meaningful reflections from your conversations are securely connected to the teachings in your private Wisdom Map. You can pause or erase your memory anytime.'
                  )}
                </p>
                <div className="flex items-center gap-3 pt-1 text-[11px] text-foreground/80 font-medium">
                  <span className="flex items-center gap-1">
                    <Brain className="w-3 h-3 text-ojas" /> Personal Wisdom Map
                  </span>
                  <span>•</span>
                  <span>Full control anytime</span>
                  <span>•</span>
                  <span>One-click permanent erase</span>
                </div>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-2.5 pt-2">
              <Button
                size="sm"
                onClick={handleEnable}
                disabled={submitting}
                className="bg-ojas hover:bg-ojas-light text-white text-xs h-8 px-3.5 rounded-lg shadow-sm font-medium"
                data-testid="enable-memory-button"
              >
                {submitting ? 'Enabling…' : t('chat.memoryBanner.enable', 'Enable Personal Memory')}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={handleDismiss}
                className="text-xs text-muted-foreground hover:text-foreground h-8 px-2.5"
                data-testid="dismiss-memory-banner-button"
              >
                {t('chat.memoryBanner.notNow', 'Not Now')}
              </Button>
              <button
                type="button"
                onClick={() => setExpanded(!expanded)}
                className="text-[11px] text-muted-foreground hover:text-ojas flex items-center gap-0.5 ml-1 transition-colors"
                aria-expanded={expanded}
              >
                {t('chat.memoryBanner.learnMore', 'Learn more')}
                {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              </button>
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={handleDismiss}
          className="text-muted-foreground hover:text-foreground p-1 rounded-lg hover:bg-muted/60 transition-colors"
          aria-label={t('common.close', 'Close')}
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};
