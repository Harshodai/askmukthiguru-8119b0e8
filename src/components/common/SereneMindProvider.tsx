import { createContext, useCallback, useContext, useMemo, useState, ReactNode } from 'react';
import { SereneMindModal, SereneMindTab } from '@/components/chat/SereneMindModal';

interface SereneMindContextValue {
  isOpen: boolean;
  isGated: boolean;
  open: (initialTab?: SereneMindTab, gated?: boolean) => void;
  close: () => void;
  toggle: () => void;
  onComplete: (() => void) | null;
  setOnComplete: (cb: (() => void) | null) => void;
}

const SereneMindContext = createContext<SereneMindContextValue | null>(null);

export const SereneMindProvider = ({ children }: { children: ReactNode }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [initialTab, setInitialTab] = useState<SereneMindTab>('breathing');
  const [isGated, setIsGated] = useState(false);
  const [onComplete, setOnCompleteState] = useState<(() => void) | null>(null);

  const open = useCallback((tab: SereneMindTab = 'breathing', gated = false) => {
    setInitialTab(tab);
    setIsGated(gated);
    setIsOpen(true);
  }, []);

  const close = useCallback(() => {
    setIsOpen(false);
    setIsGated(false);
  }, []);

  const toggle = useCallback(() => setIsOpen((v) => !v), []);

  const setOnComplete = useCallback((cb: (() => void) | null) => {
    setOnCompleteState(() => cb);
  }, []);

  const handleComplete = useCallback(() => {
    onComplete?.();
  }, [onComplete]);

  const value = useMemo(
    () => ({ isOpen, isGated, open, close, toggle, onComplete, setOnComplete }),
    [isOpen, isGated, open, close, toggle, onComplete, setOnComplete]
  );

  return (
    <SereneMindContext.Provider value={value}>
      {children}
      <SereneMindModal
        isOpen={isOpen}
        onClose={close}
        initialTab={initialTab}
        isGated={isGated}
        onComplete={handleComplete}
      />
    </SereneMindContext.Provider>
  );
};

/**
 * Hook to access SereneMind context.
 * Returns a safe no-op fallback if called outside the provider during
 * HMR or concurrent rendering edge cases, instead of crashing the app.
 */
export const useSereneMind = (): SereneMindContextValue => {
  const ctx = useContext(SereneMindContext);
  if (!ctx) {
    if (import.meta.env.DEV) {
      console.warn('useSereneMind called outside SereneMindProvider — returning no-op fallback');
    }
    return {
      isOpen: false,
      isGated: false,
      open: () => {},
      close: () => {},
      toggle: () => {},
      onComplete: null,
      setOnComplete: () => {},
    };
  }
  return ctx;
};
