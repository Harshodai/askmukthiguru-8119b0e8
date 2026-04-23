import { createContext, useCallback, useContext, useMemo, useState, ReactNode } from 'react';
import { SereneMindModal, SereneMindTab } from '@/components/chat/SereneMindModal';

interface SereneMindContextValue {
  isOpen: boolean;
  open: (initialTab?: SereneMindTab) => void;
  close: () => void;
  toggle: () => void;
}

const SereneMindContext = createContext<SereneMindContextValue | null>(null);

export const SereneMindProvider = ({ children }: { children: ReactNode }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [initialTab, setInitialTab] = useState<SereneMindTab>('breathing');

  const open = useCallback((tab: SereneMindTab = 'breathing') => {
    setInitialTab(tab);
    setIsOpen(true);
  }, []);

  const close = useCallback(() => setIsOpen(false), []);
  const toggle = useCallback(() => setIsOpen((v) => !v), []);

  const value = useMemo(() => ({ isOpen, open, close, toggle }), [isOpen, open, close, toggle]);

  return (
    <SereneMindContext.Provider value={value}>
      {children}
      <SereneMindModal isOpen={isOpen} onClose={close} initialTab={initialTab} />
    </SereneMindContext.Provider>
  );
};

export const useSereneMind = (): SereneMindContextValue => {
  const ctx = useContext(SereneMindContext);
  if (!ctx) {
    throw new Error('useSereneMind must be used within a SereneMindProvider');
  }
  return ctx;
};
