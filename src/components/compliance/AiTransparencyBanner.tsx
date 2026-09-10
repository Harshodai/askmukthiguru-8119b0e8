import React, { useState, useEffect } from 'react';
import { Info, X } from 'lucide-react';
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
          'w-full border-b border-hairline bg-card/70 px-3 py-1.5 sm:px-5 transition-colors',
          className
        )}
      >
        <div className="max-w-3xl mx-auto flex items-center justify-between gap-2 text-[11px]">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <Info className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
            <p className="truncate text-muted-foreground sm:whitespace-normal">
              <span>AskMukthiGuru is an AI companion grounded in spiritual teachings.</span>
              {' '}
              <button
                type="button"
                onClick={() => setIsDrawerOpen(true)}
                className="text-foreground hover:underline font-medium inline-flex items-center gap-0.5 ml-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ojas rounded"
              >
                Article 50 Notice
              </button>
            </p>
          </div>

          <button
            type="button"
            onClick={handleDismiss}
            aria-label="Dismiss AI transparency notice"
            className="flex min-h-[36px] min-w-[36px] items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ojas/50"
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
