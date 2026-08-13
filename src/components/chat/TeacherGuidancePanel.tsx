import { BookOpen, Languages, ShieldCheck } from 'lucide-react';

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
  language: string;
  onLanguageChange: (language: string) => void;
}

/**
 * Sets clear expectations before a seeker begins: this is attributed guidance,
 * not a claim to be either teacher or a substitute for professional care.
 */
export function TeacherGuidancePanel({
  assistantName,
  language,
  onLanguageChange,
}: TeacherGuidancePanelProps) {
  return (
    <section
      aria-labelledby="guidance-context-title"
      className="w-full max-w-2xl rounded-2xl border border-ojas/20 bg-card/80 px-4 py-3 shadow-[0_12px_40px_-28px_hsl(var(--ojas))] backdrop-blur-sm sm:px-5"
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-ojas/12 text-ojas">
          <BookOpen className="h-4 w-4" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-ojas">
            Teaching-grounded guidance
          </p>
          <h3 id="guidance-context-title" className="mt-0.5 font-serif text-base text-foreground">
            Inspired by the teachings of Sri Preethaji &amp; Sri Krishnaji
          </h3>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            {assistantName ? `${assistantName} is your selected guidance path. ` : ''}
            Ask in the language that feels natural. Responses are attributed guidance,
            not an impersonation or a replacement for professional support.
          </p>
        </div>
      </div>

      <div className="mt-3 border-t border-border/60 pt-3">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <Languages className="h-3.5 w-3.5 text-ojas" aria-hidden="true" />
          <span>Your language</span>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Priority response languages">
          {PRIORITY_CHAT_LANGUAGES.map((option) => {
            const active = language === option.code;
            return (
              <button
                key={option.code}
                type="button"
                onClick={() => onLanguageChange(option.code)}
                aria-pressed={active}
                className={`rounded-full border px-2.5 py-1 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ojas/60 ${
                  active
                    ? 'border-ojas bg-ojas text-ojas-foreground'
                    : 'border-border bg-background/70 text-foreground hover:border-ojas/40 hover:bg-ojas/5'
                }`}
              >
                <span lang={option.code === 'hinglish' ? 'en-IN' : undefined}>
                  {option.native}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <p className="mt-3 flex items-start gap-1.5 text-[11px] leading-relaxed text-muted-foreground">
        <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ojas" aria-hidden="true" />
        <span>For immediate danger or severe distress, please seek local emergency or professional support.</span>
      </p>
    </section>
  );
}
