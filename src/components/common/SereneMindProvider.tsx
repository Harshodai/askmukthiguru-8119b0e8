import { createContext, useCallback, useContext, useMemo, useState, ReactNode } from 'react';
import { SereneMindModal, SereneMindTab } from '@/components/chat/SereneMindModal';
import { GuidedMeditationFlow } from '@/components/meditation/GuidedMeditationFlow';
import type { MeditationStep } from '@/components/meditation/meditationSteps';

interface SereneMindContextValue {
  isOpen: boolean;
  isGated: boolean;
  open: (initialTab?: SereneMindTab, gated?: boolean, customSteps?: MeditationStep[], sourceTeaching?: string) => void;
  close: () => void;
  toggle: () => void;
  onComplete: (() => void) | null;
  setOnComplete: (cb: (() => void) | null) => void;
}

const SereneMindContext = createContext<SereneMindContextValue | null>(null);

export const SereneMindProvider = ({ children }: { children: ReactNode }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [initialTab, setInitialTab] = useState<SereneMindTab>('audio');
  const [isGated, setIsGated] = useState(false);
  const [onComplete, setOnCompleteState] = useState<(() => void) | null>(null);
  const [customSteps, setCustomSteps] = useState<MeditationStep[] | undefined>();
  const [sourceTeaching, setSourceTeaching] = useState<string | undefined>();

  const open = useCallback(
    (tab: SereneMindTab = 'audio', gated = false, steps?: MeditationStep[], teaching?: string) => {
      setInitialTab(tab);
      setIsGated(gated);
      setCustomSteps(steps);
      setSourceTeaching(teaching);
      setIsOpen(true);
    },
    [],
  );

  const close = useCallback(() => {
    setIsOpen(false);
    setIsGated(false);
    setCustomSteps(undefined);
    setSourceTeaching(undefined);
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
    [isOpen, isGated, open, close, toggle, onComplete, setOnComplete],
  );

  // Merged player: 'audio' → GuidedMeditationFlow (unified audio + step + breath ring).
  // 'video' → SereneMindModal (retains the YouTube-embed experience).
  // Custom teaching-driven steps always route to GuidedMeditationFlow.
  const useGuided = (customSteps && customSteps.length > 0) || initialTab === 'audio';

  return (
    <SereneMindContext.Provider value={value}>
      {children}
      {useGuided ? (
        <GuidedMeditationFlow
          isOpen={isOpen}
          onClose={close}
          customSteps={customSteps}
          sourceTeaching={sourceTeaching}
          onComplete={handleComplete}
        />
      ) : (
        <SereneMindModal
          isOpen={isOpen}
          onClose={close}
          initialTab={initialTab}
          isGated={isGated}
          onComplete={handleComplete}
        />
      )}
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
    } as SereneMindContextValue;
  }
  return ctx;
};
