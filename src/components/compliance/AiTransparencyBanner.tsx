import React, { useState, useEffect } from 'react';
import { Sparkles, X, ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ProvenanceDrawer } from './ProvenanceDrawer';

export interface AiTransparencyBannerProps {
  className?: string;
  persistent?: boolean;
  onDismiss?: () => void;
}

const STORAGE_KEY = 'askmukthiguru_ai_transparency_dismissed';

export const AiTransparencyBanner: React.FC<AiTransparencyBannerProps> = ({
  className,
  persistent = false,
  onDismiss,
}) => {
  const [isDismissed, setIsDismissed] = useState<boolean>(true);
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(false);

  useEffect(() => {
    if (persistent) {
      setIsDismissed(false);
      return;
    }
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      setIsDismissed(stored === 'true');
    } catch {
      setIsDismissed(false);
    }
  }, [persistent]);

  const handleDismiss = () => {
    setIsDismissed(true);
    if (!persistent) {
      try {
        localStorage.setItem(STORAGE_KEY, 'true');
      } catch {
        // Ignore storage errors in private browsing/incognito
      }
    }
    onDismiss?.();
  };

  if (isDismissed) {
    return null;
  }

  return (
    <>
      <aside
        data-testid="ai-transparency-banner"
        role="region"
        aria-label="AI Transparency Notice"
        className={cn(
          'w-full bg-gradient-to-r from-ojas/15 via-card to-ojas/10 border-b border-ojas/20 px-3.5 py-2.5 sm:px-6 shadow-sm transition-all duration-300',
          className
        )}
      >
        <div className="max-w-4xl mx-auto flex items-center justify-between gap-3 text-xs sm:text-[13px]">
          <div className="flex items-center gap-2.5 min-w-0 flex-1">
            <div className="p-1 rounded-md bg-ojas/20 text-ojas shrink-0" aria-hidden="true">
              <Sparkles className="w-3.5 h-3.5" />
            </div>
            <p className="text-foreground/90 font-medium leading-tight sm:leading-normal truncate sm:whitespace-normal">
              <span>You are conversing with AskMukthiGuru AI, an artificial intelligence assistant grounded in authentic spiritual teachings.</span>
              {' '}
              <button
                type="button"
                onClick={() => setIsDrawerOpen(true)}
                className="text-ojas hover:underline font-semibold inline-flex items-center gap-0.5 ml-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ojas rounded"
              >
                Article 50 Notice
              </button>
            </p>
          </div>

          <button
            type="button"
            onClick={handleDismiss}
            aria-label="Dismiss AI transparency notice"
            className="p-1 rounded-md hover:bg-ojas/15 text-muted-foreground hover:text-foreground transition-colors shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ojas/50"
            title="Dismiss notice"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>
      </aside>

      <ProvenanceDrawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
      />
    </>
  );
};
