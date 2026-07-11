import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { Sparkles } from 'lucide-react';
import { LANGUAGES, LANGUAGE_FLAGS } from '@/components/chat/LanguageSelector';
import i18n from '@/i18n';

interface LanguageOnboardingStepProps {
  onComplete: (languageCode: string) => void;
}

export const LanguageOnboardingStep = ({ onComplete }: LanguageOnboardingStepProps) => {
  const { t } = useTranslation();
  const [selected, setSelected] = useState('en');

  const handleContinue = () => {
    onComplete(selected);
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="min-h-dvh flex flex-col bg-background"
    >
      <div className="flex-1 flex flex-col items-center justify-center px-4 py-12 max-w-lg mx-auto w-full">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1, duration: 0.4 }}
          className="text-center space-y-3 mb-8"
        >
          <div className="w-14 h-14 rounded-full bg-ojas/15 border border-ojas/25 flex items-center justify-center mx-auto">
            <Sparkles className="w-7 h-7 text-ojas" />
          </div>
          <h1 className="text-2xl font-semibold text-foreground">
            {t('onboarding.language.title')}
          </h1>
          <p className="text-sm text-muted-foreground max-w-sm mx-auto">
            {t('onboarding.language.subtitle')}
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.4 }}
          className="w-full space-y-1.5 mb-8"
        >
          {LANGUAGES.map((lang, index) => {
            const isSelected = selected === lang.code;
            const flag = LANGUAGE_FLAGS[lang.code] ?? '🌐';
            return (
              <motion.button
                key={lang.code}
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.05 * index + 0.25, duration: 0.25 }}
                onClick={() => setSelected(lang.code)}
                className={`w-full flex items-center gap-3 px-4 py-3.5 rounded-xl text-left transition-all border ${
                  isSelected
                    ? 'bg-ojas/10 border-ojas/40 shadow-sm'
                    : 'bg-card border-border hover:border-ojas/20 hover:bg-muted/50'
                }`}
              >
                <span className="text-xl leading-none flex-shrink-0">{flag}</span>
                <div className="flex-1 min-w-0">
                  <span
                    className={`block font-medium truncate ${
                      isSelected ? 'text-ojas' : 'text-foreground'
                    }`}
                  >
                    {lang.native}
                  </span>
                  <span className="block text-xs text-muted-foreground truncate">
                    {lang.name}
                  </span>
                </div>
                {isSelected && (
                  <span className="w-2.5 h-2.5 rounded-full bg-ojas flex-shrink-0" />
                )}
              </motion.button>
            );
          })}
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5, duration: 0.3 }}
          className="w-full"
        >
          <button
            onClick={handleContinue}
            className="w-full h-12 rounded-xl bg-ojas hover:bg-ojas-light text-primary-foreground font-medium transition-colors text-sm"
          >
            {t('onboarding.language.continue')}
          </button>
        </motion.div>
      </div>
    </motion.div>
  );
};
