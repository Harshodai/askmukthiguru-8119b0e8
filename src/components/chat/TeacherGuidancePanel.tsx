import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AnimatePresence, motion } from 'framer-motion';
import { ChevronDown, Info } from 'lucide-react';

export const PRIORITY_CHAT_LANGUAGES = [
  { code: 'en', label: 'English', native: 'English' },
  { code: 'hinglish', label: 'Hinglish', native: 'Hinglish' },
  { code: 'hi', label: 'Hindi', native: 'हिन्दी' },
  { code: 'te', label: 'Telugu', native: 'తెలుగు' },
  { code: 'ta', label: 'Tamil', native: 'தமிழ்' },
  { code: 'kn', label: 'Kannada', native: 'ಕನ್ನಡ' },
] as const;

interface TeacherGuidancePanelProps {
  assistantName?: string;
}

/**
 * A quiet single-line attribution with an optional disclosure.
 *
 * The full boundary statement (attributed guidance, not impersonation, not a
 * substitute for care) still has to be reachable, but it no longer dominates
 * the first screen — it lives one tap away behind the disclosure.
 */
export function TeacherGuidancePanel({ assistantName }: TeacherGuidancePanelProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  return (
    <section aria-labelledby="guidance-context-title" className="mx-auto w-full max-w-md text-center">
      <p
        id="guidance-context-title"
        className="text-[12.5px] leading-relaxed text-muted-foreground/70"
      >
        {t(
          'chat.guidance.attribution',
          'Inspired by the teachings of Sri Preethaji & Sri Krishnaji',
        )}
      </p>

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="mt-1.5 inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] text-muted-foreground/60 transition-colors hover:text-ojas focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ojas/50"
      >
        <Info className="h-3 w-3" aria-hidden="true" />
        <span>{t('chat.guidance.howThisWorks', 'How this guidance works')}</span>
        <ChevronDown
          className={`h-3 w-3 transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
        />
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
            className="overflow-hidden"
          >
            <div className="mt-2 space-y-2 rounded-2xl border border-hairline bg-card/50 px-4 py-3 text-left backdrop-blur-sm">
              <p className="text-[11.5px] leading-relaxed text-muted-foreground">
                {assistantName
                  ? t('chat.guidance.pathPrefix', {
                      defaultValue: '{{name}} is your selected guidance path. ',
                      name: assistantName,
                    })
                  : ''}
                {t(
                  'chat.guidance.body',
                  'Ask in the language that feels natural. Responses are attributed guidance, not an impersonation or a replacement for professional support.',
                )}
              </p>
              <p className="text-[11px] leading-relaxed text-muted-foreground/80">
                {t(
                  'chat.guidance.safety',
                  'For immediate danger or severe distress, please seek local emergency or professional support.',
                )}
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
